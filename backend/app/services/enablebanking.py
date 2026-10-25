"""Client for the Enable Banking API (PSD2 account information), https://enablebanking.com/docs.

Every request carries a JWT signed (RS256) with the private key of the application registered at
Enable Banking; the application id is the key id. ENABLEBANKING_PRIVATE_KEY holds the PEM file,
either as is (newlines written as \\n) or base64 encoded on one line.
"""

import base64
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

from app.config import get_settings

API = "https://api.enablebanking.com"
TOKEN_TTL = 3600


class BankingError(RuntimeError):
    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status


def configured() -> bool:
    s = get_settings()
    return bool(s.enablebanking_app_id.strip() and s.enablebanking_private_key.strip())


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _private_key() -> rsa.RSAPrivateKey:
    raw = get_settings().enablebanking_private_key.strip().replace("\\n", "\n")
    try:
        if not raw.startswith("-----"):
            raw = base64.b64decode(raw).decode()
        key = serialization.load_pem_private_key(raw.encode(), password=None)
    except ValueError as exc:
        raise BankingError("ENABLEBANKING_PRIVATE_KEY is not a readable PEM key") from exc
    if not isinstance(key, rsa.RSAPrivateKey):
        raise BankingError("ENABLEBANKING_PRIVATE_KEY is not an RSA key")
    return key


def token(now: float | None = None) -> str:
    now = int(now or time.time())
    header = {"typ": "JWT", "alg": "RS256", "kid": get_settings().enablebanking_app_id.strip()}
    claims = {
        "iss": "enablebanking.com",
        "aud": "api.enablebanking.com",
        "iat": now,
        "exp": now + TOKEN_TTL,
    }
    signing_input = f"{_b64(json.dumps(header).encode())}.{_b64(json.dumps(claims).encode())}"
    signature = _private_key().sign(signing_input.encode(), padding.PKCS1v15(), hashes.SHA256())
    return f"{signing_input}.{_b64(signature)}"


def request(method: str, path: str, body: dict | None = None, query: dict | None = None) -> Any:
    """One API call; raises BankingError with the API's message. Replaced in tests."""
    url = API + path
    if query:
        url += "?" + urllib.parse.urlencode({k: v for k, v in query.items() if v is not None})
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode() if body is not None else None,
        method=method,
        headers={"Authorization": f"Bearer {token()}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as response:
            data = response.read()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")[:500]
        try:
            parsed = json.loads(detail)
            detail = parsed.get("message") or parsed.get("error") or detail
        except ValueError:
            pass
        raise BankingError(f"Enable Banking {exc.code}: {detail}", exc.code) from exc
    except urllib.error.URLError as exc:
        raise BankingError(f"Enable Banking not reachable: {exc.reason}") from exc
    return json.loads(data) if data else None


def aspsps(country: str) -> list[dict]:
    return request("GET", "/aspsps", query={"country": country, "psu_type": "personal"})["aspsps"]


def start_auth(name: str, country: str, valid_until: str, state: str, redirect_url: str) -> str:
    """The bank's login URL for the user."""
    data = request(
        "POST",
        "/auth",
        {
            "access": {"valid_until": valid_until},
            "aspsp": {"name": name, "country": country},
            "state": state,
            "redirect_url": redirect_url,
            "psu_type": "personal",
        },
    )
    return data["url"]


def create_session(code: str) -> dict:
    return request("POST", "/sessions", {"code": code})


def balances(uid: str) -> list[dict]:
    return request("GET", f"/accounts/{uid}/balances")["balances"]


def transactions(uid: str, date_from: str) -> list[dict]:
    """All booked transactions since date_from, every page."""
    out: list[dict] = []
    key = None
    seen = set()
    while True:
        data = request(
            "GET",
            f"/accounts/{uid}/transactions",
            query={"date_from": date_from, "transaction_status": "BOOK", "continuation_key": key},
        )
        out.extend(data.get("transactions") or [])
        key = data.get("continuation_key")
        # Some banks hand out the same key again (seen with Trade Republic): stop there.
        if not key or key in seen:
            return out
        seen.add(key)
