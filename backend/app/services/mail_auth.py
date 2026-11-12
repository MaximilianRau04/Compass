"""Microsoft sign-ins of mail accounts: start and finish a device sign-in, keep the tokens.

Tokens are stored encrypted (app.crypto) in `credentials`, one row per account ("mail:<name>").
The access token is reused until shortly before it expires, then renewed with the refresh token;
Microsoft hands out a new refresh token each time, which replaces the old one.
"""

import time
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app import crypto
from app.config import MailAccount
from app.mail import microsoft
from app.mail.microsoft import SignInError
from app.models.credentials import Credential

# Renew the access token when less than this is left, so it cannot expire during a sync.
EARLY_SECONDS = 300


def credential_name(account: str) -> str:
    return f"mail:{account}"


def _check(account: MailAccount) -> None:
    if account.auth != "microsoft":
        raise SignInError(f"{account.name} signs in with a password", again=False)


@dataclass
class PendingSignIn:
    user_code: str
    verification_uri: str
    expires_at: datetime
    interval: int


@dataclass
class SignInState:
    signed_in: bool
    signed_in_as: str | None
    error: str | None


def state(session: Session, account: str) -> SignInState:
    cred = session.get(Credential, credential_name(account))
    if cred is None:
        return SignInState(False, None, None)
    return SignInState(cred.secret is not None, cred.signed_in_as, cred.error)


def start(session: Session, account: MailAccount) -> PendingSignIn:
    """Ask Microsoft for a code. A sign-in started before is replaced; tokens of an earlier
    sign-in keep working until the new one is done."""
    _check(account)
    code = microsoft.start()
    cred = session.get(Credential, credential_name(account.name))
    if cred is None:
        cred = Credential(name=credential_name(account.name), kind="microsoft")
        session.add(cred)
    cred.pending = crypto.encrypt(
        {
            "device_code": code.device_code,
            "user_code": code.user_code,
            "verification_uri": code.verification_uri,
            "expires_at": code.expires_at,
            "interval": code.interval,
            "next_poll": time.time() + code.interval,
        }
    )
    session.flush()
    return PendingSignIn(
        code.user_code,
        code.verification_uri,
        datetime.fromtimestamp(code.expires_at, UTC),
        code.interval,
    )


@dataclass
class PollResult:
    status: str  # pending | done | failed
    message: str | None = None
    signed_in_as: str | None = None


def poll(session: Session, account: MailAccount) -> PollResult:
    """Look once whether the user finished the sign-in. Asking more often than Microsoft allows
    answers "pending" without a request."""
    _check(account)
    cred = session.get(Credential, credential_name(account.name), with_for_update=True)
    if cred is None or cred.pending is None:
        return PollResult("failed", "no sign-in started")
    try:
        pending = crypto.decrypt(cred.pending)
    except crypto.SecretKeyError as exc:
        cred.pending = None
        return PollResult("failed", str(exc))
    now = time.time()
    if now >= pending["expires_at"]:
        cred.pending = None
        return PollResult("failed", "the code expired, start the sign-in again")
    if now < pending["next_poll"]:
        return PollResult("pending")
    try:
        result = microsoft.poll(pending["device_code"])
    except SignInError as exc:
        cred.pending = None
        return PollResult("failed", str(exc))
    if result.tokens is None:
        if result.slow_down:
            pending["interval"] += 5
        pending["next_poll"] = now + pending["interval"]
        cred.pending = crypto.encrypt(pending)
        return PollResult("pending")
    _store(cred, result.tokens)
    cred.pending = None
    session.flush()
    return PollResult("done", signed_in_as=cred.signed_in_as)


def _store(cred: Credential, tokens: microsoft.Tokens) -> None:
    cred.secret = crypto.encrypt(
        {
            "access_token": tokens.access_token,
            "refresh_token": tokens.refresh_token,
            "expires_at": tokens.expires_at,
        }
    )
    cred.signed_in_as = tokens.signed_in_as or cred.signed_in_as
    cred.error = None


def access_token(session: Session, account: MailAccount) -> str:
    """A valid access token for IMAP, renewed if needed. The row stays locked until the caller
    commits, so the worker and a sync started in the app do not both spend the refresh token.

    Raises SignInError; with `again` the stored sign-in is dropped and the app asks for a new one.
    """
    _check(account)
    cred = session.get(Credential, credential_name(account.name), with_for_update=True)
    if cred is None or cred.secret is None:
        if cred is not None and cred.error:
            raise SignInError(f"sign in again: {cred.error}"[:500], again=True)
        raise SignInError("not signed in: sign in with Microsoft in the Mail tab", again=True)
    try:
        tokens = crypto.decrypt(cred.secret)
    except crypto.SecretKeyError as exc:
        cred.secret, cred.error = None, str(exc)
        raise SignInError(str(exc), again=True) from None
    if tokens["expires_at"] - EARLY_SECONDS > time.time():
        return tokens["access_token"]
    try:
        renewed = microsoft.refresh(tokens["refresh_token"])
    except SignInError as exc:
        if exc.again:
            cred.secret, cred.error = None, str(exc)[:500]
        raise SignInError(
            f"sign in again: {exc}"[:500] if exc.again else str(exc), exc.again
        ) from None
    _store(cred, renewed)
    session.flush()
    return renewed.access_token


def sign_out(session: Session, account: str) -> None:
    """Forget the tokens. Access can also be removed at Microsoft (account.microsoft.com)."""
    cred = session.get(Credential, credential_name(account))
    if cred is not None:
        session.delete(cred)
        session.flush()
