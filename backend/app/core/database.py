from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from backend.app.core.config import Config

engine: object = None
SessionLocal: sessionmaker = sessionmaker(autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def init_db(config: Config) -> None:
    global engine
    engine = create_engine(config.database_url, connect_args={"check_same_thread": False})
    SessionLocal.configure(bind=engine)
    import backend.app.models  # noqa: F401 确保模型注册

    Base.metadata.create_all(engine)
