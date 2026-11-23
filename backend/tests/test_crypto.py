import pytest

from app import cli, crypto
from app.config import get_settings
from app.models.credentials import Credential


def test_encrypt_decrypt_and_key_rotation(monkeypatch, session):
    settings = get_settings()
    old_key = "old-secret-key-0123456789abcdef"
    new_key = "new-secret-key-fedcba9876543210"

    monkeypatch.setattr(settings, "compass_secret_key", old_key)
    monkeypatch.setattr(settings, "compass_previous_secret_key", "")
    token = crypto.encrypt({"refresh_token": "r1"})
    assert crypto.decrypt(token) == {"refresh_token": "r1"}

    # Switching to the new key without keeping the old key fails cleanly.
    monkeypatch.setattr(settings, "compass_secret_key", new_key)
    with pytest.raises(crypto.SecretKeyError):
        crypto.decrypt(token)

    # With COMPASS_PREVIOUS_SECRET_KEY set, the old token is readable and can be rotated.
    monkeypatch.setattr(settings, "compass_previous_secret_key", old_key)
    assert crypto.decrypt(token) == {"refresh_token": "r1"}

    session.add(Credential(name="mail:outlook", kind="microsoft", secret=token))
    session.flush()
    assert cli.rotate_secrets(session) == {"rotated": 1}

    # After dropping the old key, the rotated credential still decrypts with the new key alone.
    monkeypatch.setattr(settings, "compass_previous_secret_key", "")
    cred = session.get(Credential, "mail:outlook")
    assert crypto.decrypt(cred.secret) == {"refresh_token": "r1"}


def test_short_secret_key_is_rejected(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "compass_secret_key", "too-short")
    monkeypatch.setattr(settings, "compass_previous_secret_key", "")
    with pytest.raises(crypto.SecretKeyError):
        crypto.encrypt({"a": 1})
