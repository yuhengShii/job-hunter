from datetime import datetime

import pytest
from sqlalchemy.exc import IntegrityError

from backend.app.core.database import SessionLocal, init_db
from backend.app.models import Company, Job, Keyword, Setting, User


def test_tables_created_and_unique_keys(config):
    init_db(config)
    with SessionLocal() as s:
        s.add_all([
            Keyword(keyword="python"),
            User(username="u1", password_hash="h"),
            Company(company_id="c1", name="A公司"),
            Setting(key="schedule", value={"enabled": False}),
        ])
        s.commit()
        assert s.query(Keyword).count() == 1
        with pytest.raises(IntegrityError):
            s.add(Keyword(keyword="python"))
            s.commit()
        s.rollback()
        assert s.query(Job).count() == 0


def test_job_upsert_by_unique_job_id(config):
    init_db(config)
    with SessionLocal() as s:
        now = datetime.now()
        s.add(Job(job_id="171875192", title="旧", salary_raw="1-2万", tags=[], created_at=now, updated_at=now))
        s.commit()
    with SessionLocal() as s:
        job = s.query(Job).filter_by(job_id="171875192").one()
        assert job.title == "旧"
