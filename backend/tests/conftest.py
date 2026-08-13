import os
import sys
from datetime import datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

# 阻止 main.py 模块级 app=create_app() 在测试 import 时创建真实 data/config.ini
os.environ["JOB_HUNTER_TESTING"] = "1"

from backend.app.api.deps import ensure_admin
from backend.app.core.config import Config  # noqa: E402
from backend.app.core.database import SessionLocal, init_db
from backend.app.main import create_app
from backend.app.models import Company, Job


@pytest.fixture()
def config(tmp_path):
    return Config(
        repo_root=tmp_path,
        config_path=tmp_path / "config.ini",
        db_path=tmp_path / "test.db",
    )


@pytest.fixture()
def client(config):
    init_db(config)
    with SessionLocal() as s:
        ensure_admin(s, config)
        s.add_all([
            Company(company_id="c1", name="A公司", type="民营", industry="软件", size="100-499人", activity="今日回复8次", activity_score=8),
            Company(company_id="c2", name="B公司", type="外企", industry="金融", size="1000人以上", activity="3分钟前回复", activity_score=3),
            Job(job_id="j1", title="Python工程师", salary_min=10000, salary_max=20000, city="上海", district="长宁区", area="长宁区", degree="本科", year="3-4年", tags=["急招"], company_id="c1", publish_time=datetime(2024, 3, 1)),
            Job(job_id="j2", title="Java工程师", salary_min=15000, salary_max=25000, city="北京", district="海淀区", tags=["高薪"], company_id="c1", publish_time=datetime(2024, 2, 1)),
            Job(job_id="j3", title="前端工程师", salary_min=None, salary_max=None, city="上海", tags=[], company_id="c1", publish_time=datetime(2024, 1, 15)),
            Job(job_id="j4", title="测试工程师", company_id="c2", publish_time=datetime(2024, 1, 1)),
            Job(job_id="j5", title="运维工程师", company_id="c2", publish_time=datetime(2024, 6, 1)),
            Job(job_id="j6", title="数据工程师"),
        ])
        s.commit()
    app = create_app(config)
    with TestClient(app) as c:
        token = c.post("/api/auth/login", json={"username": config.auth_username, "password": config.auth_password}).json()["access_token"]
        c.headers.update({"Authorization": f"Bearer {token}"})
        yield c