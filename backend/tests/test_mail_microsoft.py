import base64
import imaplib
import json
import time
from contextlib import nullcontext

import pytest

from app import crypto
from app.config import get_settings
from app.ingestion import mail as mail_sync
from app.mail import imap, microsoft
from app.models.credentials import Credential
from app.models.integrations import IntegrationState
from app.services import mail_auth
from tests.test_mail import mailbox, raw_mail

ACCESS = "eyJ-access-token-that-must-never-leak"
REFRESH = "M.R3-refresh-token-that-must-never-leak"


def id_token(address: str) -> str:
    claims = base64.urlsafe_b64encode(json.dumps({"preferred_username": address}).encode())
    return f"e30.{claims.decode().rstrip('=')}.sig"


@pytest.fixture
def outlook(monkeypatch):
    """A password account (uni) and a Microsoft account (outlook)."""
    s = get_settings()
    monkeypatch.setattr(s, "mail_account_names", "uni outlook")
    monkeypatch.setattr(s, "microsoft_client_id", "00000000-1111-2222-3333-444444444444")
    monkeypatch.setattr(s, "microsoft_tenant", "common")
    monkeypatch.setattr(s, "compass_secret_key", "test-secret-key-0123456789abcdef")
    for name, value in {
        "UNI_IMAP_HOST": "imap.uni.example",
        "UNI_IMAP_USER": "st123",
        "UNI_IMAP_PASSWORD": "secret",
        "OUTLOOK_IMAP_USER": "me@outlook.com",
        "MAIL_AUTH_OUTLOOK": "microsoft",
    }.items():
        monkeypatch.setenv(name, value)
    return s.mail_accounts


class Microsoft:
    """Stands in for login.microsoftonline.com: answers queued per endpoint, calls recorded."""

    def __init__(self):
        self.answers: dict[str, list[dict]] = {"devicecode": [], "token": []}
        self.calls: list[tuple[str, dict]] = []

    def __call__(self, path, fields):
        self.calls.append((path, fields))
        return self.answers[path].pop(0)


@pytest.fixture
def ms(monkeypatch):
    fake = Microsoft()
    monkeypatch.setattr(microsoft, "_post", fake)
    return fake


@pytest.fixture
def clock(monkeypatch):
    now = [1_800_000_000.0]
    monkeypatch.setattr(time, "time", lambda: now[0])
    return now


def tokens(access=ACCESS, refresh=REFRESH, address="me@outlook.com", expires_in=3600):
    return {
        "access_token": access,
        "refresh_token": refresh,
        "expires_in": expires_in,
        "id_token": id_token(address),
    }


def sign_in(session, account, ms, clock):
    ms.answers["devicecode"].append(
        {"device_code": "dev-123", "user_code": "ABCD-EFGH", "expires_in": 900, "interval": 5}
    )
    mail_auth.start(session, account)
    clock[0] += 5
    ms.answers["token"].append(tokens())
    assert mail_auth.poll(session, account).status == "done"


# --- Settings ------------------------------------------------------------------------------------


def test_a_microsoft_account_needs_no_password_or_host(outlook, monkeypatch):
    account = outlook["outlook"]
    assert (account.auth, account.host, account.port, account.password) == (
        "microsoft",
        "outlook.office365.com",
        993,
        "",
    )
    assert outlook["uni"].auth == "password"

    monkeypatch.setenv("MAIL_AUTH_OUTLOOK", "kerberos")
    with pytest.raises(ValueError, match="MAIL_AUTH_OUTLOOK"):
        _ = get_settings().mail_accounts
    # The laptop reads the mail text itself and cannot use the server's sign-in.
    monkeypatch.setenv("MAIL_AUTH_OUTLOOK", "microsoft")
    monkeypatch.setenv("MAIL_TRIAGE_OUTLOOK", "local")
    with pytest.raises(ValueError, match="MAIL_TRIAGE_OUTLOOK=local"):
        _ = get_settings().mail_accounts


def test_secrets_need_the_key_they_were_written_with(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "compass_secret_key", "first-key-0123456789")
    sealed = crypto.encrypt({"refresh_token": REFRESH})
    assert REFRESH not in sealed
    assert crypto.decrypt(sealed) == {"refresh_token": REFRESH}
    monkeypatch.setattr(s, "compass_secret_key", "other-key-0123456789")
    with pytest.raises(crypto.SecretKeyError, match="sign in again"):
        crypto.decrypt(sealed)
    monkeypatch.setattr(s, "compass_secret_key", "")
    with pytest.raises(crypto.SecretKeyError, match="COMPASS_SECRET_KEY"):
        crypto.encrypt({})


# --- IMAP ----------------------------------------------------------------------------------------


def test_xoauth2_login(outlook, monkeypatch):
    login = b"user=me@outlook.com\x01auth=Bearer tok\x01\x01"
    assert imap.xoauth2("me@outlook.com", "tok") == login

    sent = []

    class Conn:
        def __init__(self, host, port, ssl_context, timeout):
            sent.append(("connect", host, port))

        def authenticate(self, mechanism, callback):
            sent.append((mechanism, callback(b"")))

        def login(self, *args):
            raise AssertionError("no password login for a Microsoft account")

        def logout(self):
            pass

    monkeypatch.setattr(imaplib, "IMAP4_SSL", Conn)
    with imap.Mailbox(outlook["outlook"], access_token="tok"):
        pass
    assert sent == [
        ("connect", "outlook.office365.com", 993),
        ("XOAUTH2", login),
    ]

    # The local tools have no token: a clear error before any connection.
    with (
        pytest.raises(imaplib.IMAP4.error, match="only the Compass server"),
        imap.Mailbox(outlook["outlook"]),
    ):
        pass
    assert len(sent) == 2


# --- Sign-in -------------------------------------------------------------------------------------


def test_device_sign_in(session, outlook, ms, clock):
    account = outlook["outlook"]
    ms.answers["devicecode"].append(
        {
            "device_code": "dev-123",
            "user_code": "ABCD-EFGH",
            "verification_uri": "https://microsoft.com/devicelogin",
            "expires_in": 900,
            "interval": 5,
        }
    )
    pending = mail_auth.start(session, account)
    assert (pending.user_code, pending.interval) == ("ABCD-EFGH", 5)
    path, fields = ms.calls[0]
    assert path == "devicecode" and "IMAP.AccessAsUser.All" in fields["scope"]
    assert "offline_access" in fields["scope"]

    # Too early: no request at all.
    assert mail_auth.poll(session, account).status == "pending"
    assert len(ms.calls) == 1

    clock[0] += 5
    ms.answers["token"].append({"error": "authorization_pending"})
    assert mail_auth.poll(session, account).status == "pending"
    clock[0] += 5
    ms.answers["token"].append({"error": "slow_down"})
    assert mail_auth.poll(session, account).status == "pending"
    clock[0] += 5  # the interval is 10 now
    assert mail_auth.poll(session, account).status == "pending"
    assert len(ms.calls) == 3

    clock[0] += 5
    ms.answers["token"].append(tokens())
    done = mail_auth.poll(session, account)
    assert (done.status, done.signed_in_as) == ("done", "me@outlook.com")
    assert ms.calls[-1][1]["device_code"] == "dev-123"

    cred = session.get(Credential, "mail:outlook")
    assert cred.pending is None and cred.error is None
    assert ACCESS not in cred.secret and REFRESH not in cred.secret
    assert mail_auth.state(session, "outlook").signed_in is True


def test_a_declined_or_expired_sign_in_ends(session, outlook, ms, clock):
    account = outlook["outlook"]
    ms.answers["devicecode"].append({"device_code": "d", "user_code": "U", "expires_in": 900})
    mail_auth.start(session, account)
    clock[0] += 5
    ms.answers["token"].append({"error": "authorization_declined"})
    assert mail_auth.poll(session, account).message == "sign-in cancelled at Microsoft"
    assert mail_auth.poll(session, account).message == "no sign-in started"

    ms.answers["devicecode"].append({"device_code": "d", "user_code": "U", "expires_in": 900})
    mail_auth.start(session, account)
    clock[0] += 901
    result = mail_auth.poll(session, account)
    assert result.status == "failed"
    assert result.message == "the code expired, start the sign-in again"


def test_admin_consent_is_named():
    message = microsoft.describe(
        "invalid_grant",
        "AADSTS65001: The user or administrator has not consented to use the application.",
    )
    assert "administrator" in message and "AADSTS65001" in message
    assert microsoft.describe("x", "AADSTS999: Something else.\nTrace ID: 1") == (
        "Microsoft: AADSTS999: Something else."
    )


def test_missing_client_id_is_explained(session, outlook, ms, monkeypatch):
    monkeypatch.setattr(get_settings(), "microsoft_client_id", "")
    with pytest.raises(microsoft.SignInError, match="MICROSOFT_CLIENT_ID"):
        mail_auth.start(session, outlook["outlook"])
    assert ms.calls == []


# --- Tokens --------------------------------------------------------------------------------------


def test_the_access_token_is_reused_then_renewed(session, outlook, ms, clock):
    account = outlook["outlook"]
    sign_in(session, account, ms, clock)
    calls = len(ms.calls)
    assert mail_auth.access_token(session, account) == ACCESS
    assert len(ms.calls) == calls

    clock[0] += 3600 - mail_auth.EARLY_SECONDS
    ms.answers["token"].append(tokens(access="new-access", refresh="new-refresh"))
    assert mail_auth.access_token(session, account) == "new-access"
    path, fields = ms.calls[-1]
    assert (fields["grant_type"], fields["refresh_token"]) == ("refresh_token", REFRESH)
    stored = crypto.decrypt(session.get(Credential, "mail:outlook").secret)
    assert stored["refresh_token"] == "new-refresh"


def test_a_revoked_sign_in_asks_for_a_new_one(session, outlook, ms, clock):
    account = outlook["outlook"]
    sign_in(session, account, ms, clock)
    clock[0] += 4000
    ms.answers["token"].append(
        {"error": "invalid_grant", "error_description": "AADSTS70008: The refresh token expired."}
    )
    with pytest.raises(microsoft.SignInError) as error:
        mail_auth.access_token(session, account)
    assert error.value.again
    state = mail_auth.state(session, "outlook")
    assert state.signed_in is False
    assert state.error.startswith("Microsoft: AADSTS70008")
    assert str(error.value).startswith("sign in again: Microsoft: AADSTS70008")

    # A temporary problem keeps the sign-in.
    sign_in(session, account, ms, clock)
    clock[0] += 4000
    ms.answers["token"].append({"error": "temporarily_unavailable", "error_description": "busy"})
    with pytest.raises(microsoft.SignInError):
        mail_auth.access_token(session, account)
    assert mail_auth.state(session, "outlook").signed_in is True


# --- Sync and API --------------------------------------------------------------------------------


def test_sync_uses_the_token_and_reports_a_missing_sign_in(session, outlook, ms, clock):
    box = mailbox({1: (raw_mail(), False)})
    opened = []

    class Recording(box):
        def __enter__(self):
            opened.append((self.account.name, self.access_token))
            return self

    results = mail_sync.sync_all(lambda: nullcontext(session), Recording)
    # Not signed in yet: the password account still syncs.
    assert results["uni"]["new"] == 1
    assert results["outlook"] == "not signed in: sign in with Microsoft in the Mail tab"
    assert session.get(IntegrationState, "mail:outlook").last_error == results["outlook"]
    assert opened == [("uni", None)]

    sign_in(session, outlook["outlook"], ms, clock)
    results = mail_sync.sync_all(lambda: nullcontext(session), Recording)
    assert results["outlook"]["new"] == 1
    assert opened[-1] == ("outlook", ACCESS)
    assert session.get(IntegrationState, "mail:outlook").last_error is None


def test_api_sign_in_and_overview_never_show_tokens(client, session, outlook, ms, clock):
    overview = client.get("/api/mail/overview").json()
    account = next(a for a in overview["accounts"] if a["account"] == "outlook")
    # Listed before its first sync, so the app can offer the sign-in.
    assert (account["auth"], account["signed_in"]) == ("microsoft", False)
    uni = next(a for a in overview["accounts"] if a["account"] == "uni")
    assert (uni["auth"], uni["signed_in"]) == ("password", None)

    ms.answers["devicecode"].append(
        {"device_code": "dev-secret", "user_code": "ABCD-EFGH", "expires_in": 900, "interval": 5}
    )
    start = client.post("/api/mail/accounts/outlook/signin")
    assert start.status_code == 200
    assert start.json()["user_code"] == "ABCD-EFGH"
    assert "dev-secret" not in start.text

    clock[0] += 5
    ms.answers["token"].append(tokens())
    poll = client.post("/api/mail/accounts/outlook/signin/poll").json()
    assert poll == {"status": "done", "message": None, "signed_in_as": "me@outlook.com"}

    overview = client.get("/api/mail/overview")
    account = next(a for a in overview.json()["accounts"] if a["account"] == "outlook")
    assert (account["signed_in"], account["signed_in_as"]) == (True, "me@outlook.com")
    for secret in (ACCESS, REFRESH, "dev-secret"):
        assert secret not in overview.text and secret not in poll.__repr__()

    assert client.post("/api/mail/accounts/uni/signin").status_code == 400
    assert client.post("/api/mail/accounts/nope/signin").status_code == 404

    assert client.delete("/api/mail/accounts/outlook/signin").status_code == 204
    assert session.get(Credential, "mail:outlook") is None
