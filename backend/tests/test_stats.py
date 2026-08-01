from datetime import datetime, timedelta

from fastapi.testclient import TestClient

from backend.app.api.deps import ensure_admin
from backend.app.core.database import SessionLocal, init_db
from backend.app.main import create_app
from backend.app.models import Company, Job, Keyword, ScrapeTask, TaskStatus
from backend.app.services.stats import get_window_start, overview, tag_stats


def _seed(config):
    init_db(config)
    with SessionLocal() as s:
        ensure_admin(s, config)
        kw = Keyword(keyword="python")
        s.add(kw)
        s.commit()
        base = datetime(2026, 7, 1, 10, 0, 0)
        s.add(ScrapeTask(keyword_id=kw.id, status=TaskStatus.SUCCESS.value, start_time=base, end_time=base + timedelta(minutes=5)))
        old = datetime(2026, 6, 1, 10, 0, 0)
        s.add(ScrapeTask(keyword_id=kw.id, status=TaskStatus.SUCCESS.value, start_time=old, end_time=old + timedelta(minutes=5)))
        s.add_all([
            Company(company_id="c1", name="A", type="民营", industry="软件", size="100人"),
            Company(company_id="c2", name="B", type="国企", industry="金融", size="1000人"),
        ])
        s.add_all([
            Job(job_id="j1", title="t1", salary_min=8000, salary_max=12000, city="上海", tags=["急招"], company_id="c1", updated_at=base + timedelta(hours=1)),
            Job(job_id="j2", title="t2", salary_min=15000, salary_max=25000, city="北京", tags=["高薪"], company_id="c2", updated_at=base + timedelta(hours=2)),
            Job(job_id="j3", title="t3", salary_min=9000, salary_max=15000, city="上海", tags=["急招", "双休"], company_id="c1", updated_at=old + timedelta(hours=1)),
        ])
        s.commit()


def test_window_uses_latest_success_task(config):
    _seed(config)
    with SessionLocal() as s:
        window = get_window_start(s)
        assert window == datetime(2026, 7, 1, 10, 0, 0)
        stats = overview(s, window)
        assert stats["total_jobs"] == 2
        assert stats["total_cities"] == 2
        assert stats["total_companies"] == 2
        assert stats["salary_parsed"] == 2


def test_tag_stats_window(config):
    _seed(config)
    with SessionLocal() as s:
        tags = tag_stats(s, get_window_start(s), top_n=2)
        assert [t["tag"] for t in tags] == ["急招", "高薪"]


def test_stats_api_endpoints(config):
    _seed(config)
    app = create_app(config)
    with TestClient(app) as c:
        token = c.post("/api/auth/login", json={"username": config.auth_username, "password": config.auth_password}).json()["access_token"]
        c.headers.update({"Authorization": f"Bearer {token}"})
        for ep in ["overview", "salary", "company", "trend", "tags"]:
            resp = c.get(f"/api/stats/{ep}")
            assert resp.status_code == 200
