"""Encryption of what Compass stores and has to read back, like the Microsoft sign-ins.

Fernet (AES-128-CBC with HMAC-SHA256) with a key derived from COMPASS_SECRET_KEY, so any long
random string works as the setting. Setting COMPASS_PREVIOUS_SECRET_KEY enables MultiFernet so
values encrypted with the previous key can still be read and rotated to the new key via
`python -m app.cli rotate-secrets`.
"""

import base64
import hashlib
import json

from cryptography.fernet import Fernet, InvalidToken, MultiFernet

from app.config import get_settings


class SecretKeyError(RuntimeError):
    """No key, or a stored value that this key cannot read."""


def _key_to_fernet(raw: str, name: str) -> Fernet:
    key = raw.strip()
    if len(key) < 16:
        raise SecretKeyError(f"{name} must be at least 16 characters (openssl rand -hex 32)")
    digest = hashlib.sha256(b"compass-secrets:" + key.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def _cipher() -> Fernet | MultiFernet:
    settings = get_settings()
    if len(settings.compass_secret_key.strip()) < 16:
        raise SecretKeyError("COMPASS_SECRET_KEY is not set (openssl rand -hex 32)")
    primary = _key_to_fernet(settings.compass_secret_key, "COMPASS_SECRET_KEY")
    previous = settings.compass_previous_secret_key.strip()
    if not previous:
        return primary
    old = [
        _key_to_fernet(part, "COMPASS_PREVIOUS_SECRET_KEY")
        for part in previous.split(",")
        if part.strip()
    ]
    return MultiFernet([primary, *old]) if old else primary


def encrypt(value: dict) -> str:
    return _cipher().encrypt(json.dumps(value).encode()).decode()


def decrypt(token: str) -> dict:
    try:
        return json.loads(_cipher().decrypt(token.encode()))
    except InvalidToken as exc:
        raise SecretKeyError(
            "stored sign-in cannot be read with this COMPASS_SECRET_KEY; sign in again"
        ) from exc


def rotate(token: str) -> str:
    """Re-encrypt a stored token under the current primary COMPASS_SECRET_KEY."""
    cipher = _cipher()
    try:
        if isinstance(cipher, MultiFernet):
            return cipher.rotate(token.encode()).decode()
        # Single key: verify it decrypts and issue a fresh token.
        return cipher.encrypt(cipher.decrypt(token.encode())).decode()
    except InvalidToken as exc:
        raise SecretKeyError("stored sign-in cannot be rotated with the configured keys") from exc
