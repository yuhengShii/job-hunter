import pytest
from fastapi.testclient import TestClient

from backend.app.api.deps import ensure_admin
from backend.app.core.database import SessionLocal, init_db
from backend.app.main import create_app
from backend.app.models import Company, Job


@pytest.fixture()
def client(config):
    init_db(config)
    with SessionLocal() as s:
        ensure_admin(s, config)
        s.add_all([
            Company(company_id="c1", name="A公司", type="民营", industry="软件", size="100-499人", activity="今日回复8次", activity_score=8),
            Job(job_id="j1", title="Python工程师", salary_min=10000, salary_max=20000, city="上海", district="长宁区", area="长宁区", tags=["急招"], company_id="c1"),
            Job(job_id="j2", title="Java工程师", salary_min=15000, salary_max=25000, city="北京", tags=["高薪"], company_id="c1"),
            Job(job_id="j3", title="前端工程师", salary_min=None, salary_max=None, city="上海", tags=[], company_id="c1"),
        ])
        s.commit()
    app = create_app(config)
    with TestClient(app) as c:
        token = c.post("/api/auth/login", json={"username": config.auth_username, "password": config.auth_password}).json()["access_token"]
        c.headers.update({"Authorization": f"Bearer {token}"})
        yield c


def test_list_jobs(client):
    resp = client.get("/api/jobs")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 3
    assert len(data["items"]) == 3


def test_filter_jobs(client):
    resp = client.get("/api/jobs", params={"city": "上海"})
    assert resp.json()["total"] == 2
    resp = client.get("/api/jobs", params={"tag": "急招"})
    assert resp.json()["total"] == 1
    resp = client.get("/api/jobs", params={"salary_min": 12000})
    assert resp.json()["total"] == 1
    resp = client.get("/api/jobs", params={"company_id": "c1"})
    assert resp.json()["total"] == 3
    resp = client.get("/api/jobs", params={"keyword": "工程师"})
    assert resp.json()["total"] == 3
    resp = client.get("/api/jobs", params={"keyword": "Python"})
    assert resp.json()["total"] == 1
    resp = client.get("/api/jobs", params={"keyword": "长宁"})
    assert resp.json()["total"] == 1


def test_get_job_detail(client):
    resp = client.get("/api/jobs/j1")
    assert resp.status_code == 200
    assert resp.json()["title"] == "Python工程师"


def test_job_company_fields(client):
    resp = client.get("/api/jobs/j1")
    data = resp.json()
    assert data["company_id"] == "c1"
    assert data["company_name"] == "A公司"
    assert data["company_activity"] == "今日回复8次"
    assert data["company_activity_score"] == 8
    resp2 = client.get("/api/jobs")
    first = resp2.json()["items"][0]
    assert first["company_name"] == "A公司"
    assert first["company_activity"] == "今日回复8次"
    assert first["company_activity_score"] == 8


def test_companies_filter(client):
    resp = client.get("/api/companies", params={"type": "民营"})
    assert resp.status_code == 200
    assert resp.json()["total"] == 1
