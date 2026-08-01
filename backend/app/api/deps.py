from collections.abc import Generator

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from backend.app.core.config import Config
from backend.app.core.database import SessionLocal
from backend.app.core.exceptions import AppError
from backend.app.core.security import decode_access_token, hash_password, verify_password
from backend.app.models import User

_bearer = HTTPBearer(auto_error=False)
_current_config: Config | None = None


def set_current_config(config: Config) -> None:
    global _current_config
    _current_config = config


def get_db() -> Generator:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def ensure_admin(db, config: Config) -> None:
    if db.query(User).count() == 0:
        db.add(User(username=config.auth_username, password_hash=hash_password(config.auth_password)))
        db.commit()


def authenticate(db, username: str, password: str) -> User:
    user = db.query(User).filter_by(username=username).first()
    if not user or not verify_password(password, user.password_hash):
        raise AppError("用户名或密码错误", 401)
    return user


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db=Depends(get_db),
) -> User:
    if credentials is None or _current_config is None:
        raise AppError("未认证", 401)
    username = decode_access_token(credentials.credentials, _current_config.jwt_secret)
    user = db.query(User).filter_by(username=username).first()
    if user is None:
        raise AppError("用户不存在", 401)
    return user
