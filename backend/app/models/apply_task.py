from datetime import datetime

from sqlalchemy import JSON, DateTime, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.core.database import Base
from backend.app.models.scrape_task import TaskStatus


class ApplyTask(Base):
    __tablename__ = "apply_tasks"
    __table_args__ = (
        Index("ix_apply_tasks_created_at", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    # 凭据删除时置 NULL（保留 credential_username 快照用于展示）
    credential_id: Mapped[int | None] = mapped_column(Integer)
    credential_username: Mapped[str] = mapped_column(String(128), default="")
    status: Mapped[str] = mapped_column(String(32), default=TaskStatus.QUEUED.value)
    total_count: Mapped[int] = mapped_column(Integer, default=0)
    success_count: Mapped[int] = mapped_column(Integer, default=0)
    failed_count: Mapped[int] = mapped_column(Integer, default=0)
    skipped_count: Mapped[int] = mapped_column(Integer, default=0)
    # [{job_id, title, status: pending/success/failed/skipped, message}]
    results: Mapped[list] = mapped_column(JSON, default=list)
    start_time: Mapped[datetime | None] = mapped_column(DateTime)
    end_time: Mapped[datetime | None] = mapped_column(DateTime)
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
