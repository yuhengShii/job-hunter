from datetime import datetime

from sqlalchemy import DateTime, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.core.database import Base


class JobSource(Base):
    """职位被命中的源抓取条件（一个职位可被多个关键字/筛选条件命中，多行共存）。

    投递时按「真实岗位标题 + 源条件」搜索：带行业筛选的窄搜索优先，其次按
    last_seen_at 新到旧；同一条件再次命中只刷新 last_seen_at。
    """

    __tablename__ = "job_sources"
    __table_args__ = (
        Index(
            "uq_job_sources_job_id_keyword_city_industry",
            "job_id",
            "source_keyword",
            "source_city",
            "source_industry",
            unique=True,
        ),
        Index("ix_job_sources_job_id", "job_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[str] = mapped_column(String(64), nullable=False)
    source_keyword: Mapped[str] = mapped_column(String(128), nullable=False)
    source_city: Mapped[str] = mapped_column(String(64), nullable=False)
    source_industry: Mapped[str | None] = mapped_column(String(128))
    first_seen_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)
