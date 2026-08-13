import pytest

from backend.app.core.exceptions import AppError
from backend.app.core.site_security import decrypt_password, encrypt_password

KEY = bytes.fromhex("ab" * 32)


def test_encrypt_decrypt_roundtrip():
    enc = encrypt_password("P@ssw0rd!中文", KEY)
    assert enc != "P@ssw0rd!中文"
    assert decrypt_password(enc, KEY) == "P@ssw0rd!中文"


def test_same_password_encrypts_differently():
    assert encrypt_password("pw", KEY) != encrypt_password("pw", KEY)


def test_wrong_key_fails():
    enc = encrypt_password("pw", KEY)
    other = bytes.fromhex("cd" * 32)
    with pytest.raises(Exception):
        decrypt_password(enc, other)


def test_corrupted_data_fails_with_app_error():
    with pytest.raises(AppError):
        decrypt_password("not-base64!!!", KEY)
