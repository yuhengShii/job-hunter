from datetime import datetime

import pytest
from sqlalchemy import create_engine, text
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


def test_activity_score_migration_backfills(config):
    engine = create_engine(f"sqlite:///{config.db_path}")
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE companies (
                    id INTEGER NOT NULL PRIMARY KEY,
                    company_id VARCHAR(64) NOT NULL,
                    name VARCHAR(255),
                    type VARCHAR(32),
                    industry VARCHAR(128),
                    size VARCHAR(64),
                    activity VARCHAR(64),
                    website VARCHAR(255),
                    created_at DATETIME,
                    updated_at DATETIME
                )
                """
            )
        )
        conn.execute(
            text(
                "INSERT INTO companies (company_id, name, activity) VALUES "
                "('c1', 'A公司', '今日回复10+次'),"
                "('c2', 'B公司', '未知标签'),"
                "('c3', 'C公司', NULL)"
            )
        )
    init_db(config)
    with SessionLocal() as s:
        c1 = s.query(Company).filter_by(company_id="c1").one()
        c2 = s.query(Company).filter_by(company_id="c2").one()
        c3 = s.query(Company).filter_by(company_id="c3").one()
        assert c1.activity_score == 10
        assert c2.activity_score == -1
        assert c3.activity_score == -1
