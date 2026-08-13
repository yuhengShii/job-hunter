from sqlalchemy import create_engine, inspect

from backend.app.core.database import Base
from backend.app.models import ApplyTask


def test_apply_task_table_and_index():
    eng = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(eng)
    cols = {c["name"] for c in inspect(eng).get_columns("apply_tasks")}
    assert {
        "id",
        "credential_id",
        "credential_username",
        "status",
        "total_count",
        "success_count",
        "failed_count",
        "skipped_count",
        "results",
        "start_time",
        "end_time",
        "error_message",
        "created_at",
    } <= cols
    idx = {i["name"] for i in inspect(eng).get_indexes("apply_tasks")}
    assert "ix_apply_tasks_created_at" in idx
