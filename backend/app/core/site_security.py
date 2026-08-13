import base64
import logging
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from backend.app.core.exceptions import AppError

logger = logging.getLogger("job_hunter")

_NONCE_LEN = 12


def encrypt_password(plain: str, key: bytes) -> str:
    aesgcm = AESGCM(key)
    nonce = os.urandom(_NONCE_LEN)
    ct = aesgcm.encrypt(nonce, plain.encode("utf-8"), None)
    return base64.b64encode(nonce + ct).decode("ascii")


def decrypt_password(enc: str, key: bytes) -> str:
    try:
        raw = base64.b64decode(enc)
        nonce, ct = raw[:_NONCE_LEN], raw[_NONCE_LEN:]
        return AESGCM(key).decrypt(nonce, ct, None).decode("utf-8")
    except Exception as exc:
        logger.error("凭据密码解密失败: %s", exc)
        raise AppError("凭据密码解密失败，凭据可能已损坏", 500) from exc
