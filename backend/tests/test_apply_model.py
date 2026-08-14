import pytest
from sqlalchemy import create_engine, inspect
from sqlalchemy.exc import IntegrityError

from backend.app.core.database import Base
from backend.app.models import ApplyTask, JobSource


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


def test_job_source_table_and_unique_index():
    eng = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(eng)
    idx = {i["name"] for i in inspect(eng).get_indexes("job_sources")}
    assert "uq_job_sources_job_id_keyword_city_industry" in idx
    assert "ix_job_sources_job_id" in idx
    with eng.begin() as conn:
        conn.execute(JobSource.__table__.insert().values(
            job_id="j1", source_keyword="采购", source_city="020000", source_industry="08,46,47",
        ))
        with pytest.raises(IntegrityError):
            conn.execute(JobSource.__table__.insert().values(
                job_id="j1", source_keyword="采购", source_city="020000", source_industry="08,46,47",
            ))
