from datetime import datetime

from sqlalchemy import DateTime, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.core.database import Base


class SiteCredential(Base):
    __tablename__ = "site_credentials"
    __table_args__ = (
        Index("uq_site_credentials_site_username", "site", "username", unique=True),
        Index("ix_site_credentials_site", "site"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    site: Mapped[str] = mapped_column(String(32), nullable=False)
    username: Mapped[str] = mapped_column(String(128), nullable=False)
    password_enc: Mapped[str] = mapped_column(Text, nullable=False)
    remark: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)

    @property
    def has_password(self) -> bool:
        return True
