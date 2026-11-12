"""Encryption of what Compass stores and has to read back, like the Microsoft sign-ins.

Fernet (AES-128-CBC with HMAC-SHA256) with a key derived from COMPASS_SECRET_KEY, so any long
random string works as the setting. Losing or changing the setting makes what was stored
unreadable: the affected sign-ins have to be done again, nothing else breaks.
"""

import base64
import hashlib
import json

from cryptography.fernet import Fernet, InvalidToken

from app.config import get_settings


class SecretKeyError(RuntimeError):
    """No key, or a stored value that this key cannot read."""


def _fernet() -> Fernet:
    key = get_settings().compass_secret_key.strip()
    if len(key) < 16:
        raise SecretKeyError("COMPASS_SECRET_KEY is not set (openssl rand -hex 32)")
    digest = hashlib.sha256(b"compass-secrets:" + key.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt(value: dict) -> str:
    return _fernet().encrypt(json.dumps(value).encode()).decode()


def decrypt(token: str) -> dict:
    try:
        return json.loads(_fernet().decrypt(token.encode()))
    except InvalidToken as exc:
        raise SecretKeyError(
            "stored sign-in cannot be read with this COMPASS_SECRET_KEY; sign in again"
        ) from exc
