"""Sign-in with Microsoft for IMAP (Microsoft 365 and Outlook.com), as an OAuth public client.

The device authorization grant needs no redirect URL, which suits a server that is often only
reachable in a VPN: Compass shows a code, the user enters it at microsoft.com/devicelogin and signs
in there. The tokens never pass through the browser.

Only the HTTP calls live here; app.services.mail_auth stores the tokens. Nothing in this module
logs or returns a token in an error message.
"""

import base64
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass

from app.config import get_settings

LOGIN = "https://login.microsoftonline.com"
DEVICE_GRANT = "urn:ietf:params:oauth:grant-type:device_code"
# IMAP for the signed-in user, a refresh token, and the user's address for the app to show.
SCOPE = "https://outlook.office.com/IMAP.AccessAsUser.All offline_access openid profile"
TIMEOUT = 30

# AADSTS codes in error_description, and what the user can do about them.
_ADMIN = "an administrator of your organisation has to approve the app first (admin consent)"
_HINTS = {
    "AADSTS65001": _ADMIN,
    "AADSTS90094": _ADMIN,
    "AADSTS90095": _ADMIN,
    "AADSTS53003": "blocked by a conditional access policy of your organisation",
    "AADSTS7000218": (
        'the app registration has to allow public client flows ("Allow public client flows" '
        "under Authentication)"
    ),
    "AADSTS700016": (
        "MICROSOFT_CLIENT_ID is not an app in this tenant (check it and MICROSOFT_TENANT)"
    ),
    "AADSTS50020": "the app registration does not accept this kind of account",
    "AADSTS9002331": "the app registration does not accept personal Microsoft accounts",
    "AADSTS50194": "the app registration is single tenant: set MICROSOFT_TENANT to its tenant id",
}


class SignInError(RuntimeError):
    """A sign-in or token refresh that did not work. `again` means the user has to sign in again
    (expired, revoked, password changed); otherwise it may be temporary (network, Microsoft)."""

    def __init__(self, message: str, again: bool):
        super().__init__(message)
        self.again = again


@dataclass
class DeviceCode:
    device_code: str
    user_code: str
    verification_uri: str
    expires_at: float
    interval: int


@dataclass
class Tokens:
    access_token: str
    refresh_token: str
    expires_at: float
    signed_in_as: str | None


def _config() -> tuple[str, str]:
    s = get_settings()
    if not s.microsoft_client_id.strip():
        raise SignInError("MICROSOFT_CLIENT_ID is not set (see docs/deploy.md)", again=False)
    return s.microsoft_client_id.strip(), (s.microsoft_tenant.strip() or "common")


def describe(error: str, description: str) -> str:
    """A readable reason from Microsoft's error answer, with a hint where one helps."""
    first = (description or error).splitlines()[0].strip()
    for code, hint in _HINTS.items():
        if code in (description or ""):
            return f"Microsoft: {hint} ({code})"
    return f"Microsoft: {first[:300]}"


def _post(path: str, fields: dict) -> dict:
    """POST a form to the tenant's endpoint; Microsoft answers errors with 400 and a JSON body."""
    _, tenant = _config()
    url = f"{LOGIN}/{urllib.parse.quote(tenant)}/oauth2/v2.0/{path}"
    request = urllib.request.Request(
        url,
        data=urllib.parse.urlencode(fields).encode(),
        headers={"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            return json.loads(response.read())
    except urllib.error.HTTPError as exc:
        try:
            body = json.loads(exc.read())
        except (ValueError, OSError):
            raise SignInError(f"Microsoft: HTTP {exc.code}", again=False) from None
        return {"error": body.get("error", f"http_{exc.code}"), **body}
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        reason = getattr(exc, "reason", exc)
        raise SignInError(f"Microsoft not reachable: {reason}", again=False) from None


def _signed_in_as(id_token: str | None) -> str | None:
    """The address from the ID token. Only shown in the app, so the signature is not checked;
    the token comes straight from Microsoft over TLS."""
    if not id_token:
        return None
    try:
        payload = id_token.split(".")[1]
        claims = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
    except (IndexError, ValueError):
        return None
    name = claims.get("preferred_username") or claims.get("email")
    return str(name)[:320] if name else None


def _tokens(body: dict, previous_refresh: str | None = None) -> Tokens:
    refresh = body.get("refresh_token") or previous_refresh
    if not body.get("access_token") or not refresh:
        raise SignInError("Microsoft sent no usable token (offline_access missing?)", again=True)
    return Tokens(
        access_token=body["access_token"],
        refresh_token=refresh,
        expires_at=time.time() + int(body.get("expires_in", 3600)),
        signed_in_as=_signed_in_as(body.get("id_token")),
    )


def start() -> DeviceCode:
    client_id, _ = _config()
    body = _post("devicecode", {"client_id": client_id, "scope": SCOPE})
    if "error" in body:
        raise SignInError(describe(body["error"], body.get("error_description", "")), again=True)
    return DeviceCode(
        device_code=body["device_code"],
        user_code=body["user_code"],
        verification_uri=body.get("verification_uri", "https://microsoft.com/devicelogin"),
        expires_at=time.time() + int(body.get("expires_in", 900)),
        interval=int(body.get("interval", 5)),
    )


@dataclass
class Poll:
    """One look at a device sign-in: done (tokens), still waiting, or "slow_down"."""

    tokens: Tokens | None = None
    slow_down: bool = False


def poll(device_code: str) -> Poll:
    client_id, _ = _config()
    body = _post(
        "token", {"grant_type": DEVICE_GRANT, "client_id": client_id, "device_code": device_code}
    )
    error = body.get("error")
    if error is None:
        return Poll(tokens=_tokens(body))
    if error == "authorization_pending":
        return Poll()
    if error == "slow_down":
        return Poll(slow_down=True)
    if error == "authorization_declined":
        raise SignInError("sign-in cancelled at Microsoft", again=True)
    if error in ("expired_token", "bad_verification_code", "code_expired"):
        raise SignInError("the code expired, start the sign-in again", again=True)
    raise SignInError(describe(error, body.get("error_description", "")), again=True)


def refresh(refresh_token: str) -> Tokens:
    client_id, _ = _config()
    body = _post(
        "token",
        {
            "grant_type": "refresh_token",
            "client_id": client_id,
            "refresh_token": refresh_token,
            "scope": SCOPE,
        },
    )
    error = body.get("error")
    if error is None:
        return _tokens(body, refresh_token)
    message = describe(error, body.get("error_description", ""))
    # invalid_grant: expired, revoked, password changed or new MFA rule. Others (temporarily
    # unavailable, server errors) can work again on the next run.
    again = error in ("invalid_grant", "interaction_required", "invalid_client")
    raise SignInError(message, again=again)
