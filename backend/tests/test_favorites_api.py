from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from backend.app.core import database
from backend.app.core.database import SessionLocal, init_db
from backend.app.main import create_app
from backend.app.models import Company, Job


def test_favorites_table_created(config):
    init_db(config)
    from sqlalchemy import inspect

    tables = inspect(database.engine).get_table_names()
    assert "favorites" in tables


def _seed(config):
    with SessionLocal() as s:
        s.add_all([
            Company(company_id="c1", name="A公司", type="民营", industry="软件", size="100-499人", activity="今日回复8次", activity_score=8),
            Job(job_id="j1", title="Python工程师", salary_min=10000, salary_max=20000, city="上海", degree="本科", tags=["急招"], company_id="c1", publish_time=datetime(2024, 3, 1)),
            Job(job_id="j2", title="Java工程师", salary_min=15000, salary_max=25000, city="北京", tags=["高薪"], company_id="c1", publish_time=datetime(2024, 2, 1)),
            Job(job_id="j3", title="前端工程师", salary_min=None, salary_max=None, city="上海", tags=[], publish_time=datetime(2024, 1, 15)),
            Job(job_id="j4", title="测试工程师", city="上海", publish_time=datetime(2024, 1, 1)),
        ])
        s.commit()


@pytest.fixture()
def client(config):
    init_db(config)
    _seed(config)
    app = create_app(config)
    with TestClient(app) as c:
        token = c.post("/api/auth/login", json={"username": config.auth_username, "password": config.auth_password}).json()["access_token"]
        c.headers.update({"Authorization": f"Bearer {token}"})
        yield c