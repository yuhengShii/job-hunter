from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.core.database import Base

# 51job 城市编码（000000 = 全国）。完整编码表见 docs/PRD.md。
DEFAULT_CITY = "000000"


class Keyword(Base):
    __tablename__ = "keywords"
    __table_args__ = (UniqueConstraint("keyword", "city", name="uq_keywords_keyword_city"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    keyword: Mapped[str] = mapped_column(String(128), nullable=False)
    city: Mapped[str] = mapped_column(String(64), default=DEFAULT_CITY, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    scrape_mode: Mapped[str] = mapped_column(String(32), default="playwright")
    last_scraped_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
