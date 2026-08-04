from datetime import datetime

from sqlalchemy import JSON, DateTime, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.core.database import Base


class Job(Base):
    __tablename__ = "jobs"
    __table_args__ = (Index("ix_jobs_created_at", "created_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    title: Mapped[str] = mapped_column(String(255))
    salary_raw: Mapped[str | None] = mapped_column(String(64))
    salary_min: Mapped[int | None] = mapped_column()
    salary_max: Mapped[int | None] = mapped_column()
    city: Mapped[str | None] = mapped_column(String(64))
    district: Mapped[str | None] = mapped_column(String(64))
    area: Mapped[str | None] = mapped_column(String(128))
    degree: Mapped[str | None] = mapped_column(String(32))
    year: Mapped[str | None] = mapped_column(String(32))
    tags: Mapped[list] = mapped_column(JSON, default=list)
    publish_time: Mapped[datetime | None] = mapped_column(DateTime)
    source: Mapped[str] = mapped_column(String(32), default="51job")
    company_id: Mapped[str | None] = mapped_column(String(64))
    job_url: Mapped[str | None] = mapped_column(String(512))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)
