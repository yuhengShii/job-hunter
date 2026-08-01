import pytest

from backend.app.core.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)
from backend.app.core.exceptions import AppError


def test_password_hash_roundtrip():
    h = hash_password("secret123")
    assert h != "secret123"
    assert verify_password("secret123", h)
    assert not verify_password("wrong", h)


def test_token_roundtrip():
    token = create_access_token("admin", "secret-key")
    assert decode_access_token(token, "secret-key") == "admin"


def test_token_bad_signature():
    token = create_access_token("admin", "secret-key")
    with pytest.raises(AppError):
        decode_access_token(token, "other-key")


def test_token_expired():
    token = create_access_token("admin", "secret-key", expires_hours=-1)
    with pytest.raises(AppError):
        decode_access_token(token, "secret-key")
