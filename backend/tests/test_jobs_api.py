import pytest
from fastapi.testclient import TestClient
from datetime import datetime

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
            Company(company_id="c2", name="B公司", type="外企", industry="金融", size="1000人以上", activity="3分钟前回复", activity_score=3),
            Job(job_id="j1", title="Python工程师", salary_min=10000, salary_max=20000, city="上海", district="长宁区", area="长宁区", degree="本科", year="3-4年", tags=["急招"], company_id="c1", publish_time=datetime(2024, 3, 1)),
            Job(job_id="j2", title="Java工程师", salary_min=15000, salary_max=25000, city="北京", tags=["高薪"], company_id="c1", publish_time=datetime(2024, 2, 1)),
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


def test_list_jobs(client):
    resp = client.get("/api/jobs")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 6
    assert len(data["items"]) == 6


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
    assert resp.json()["total"] == 6
    resp = client.get("/api/jobs", params={"keyword": "Python"})
    assert resp.json()["total"] == 1
    resp = client.get("/api/jobs", params={"keyword": "长宁"})
    assert resp.json()["total"] == 1


def test_sort_by_activity_score(client):
    resp = client.get("/api/jobs", params={"sort": "activity_score:desc"})
    items = resp.json()["items"]
    assert [i["company_activity_score"] for i in items] == [8, 8, 8, 3, 3, -1]
    assert items[-1]["job_id"] == "j6"


def test_sort_by_publish_time(client):
    resp = client.get("/api/jobs", params={"sort": "publish_time:desc"})
    assert [i["job_id"] for i in resp.json()["items"]] == ["j5", "j1", "j2", "j3", "j4", "j6"]
    resp = client.get("/api/jobs", params={"sort": "publish_time:asc"})
    assert [i["job_id"] for i in resp.json()["items"]] == ["j4", "j3", "j2", "j1", "j5", "j6"]


def test_sort_combined(client):
    resp = client.get("/api/jobs", params=[("sort", "activity_score:desc"), ("sort", "publish_time:desc")])
    assert [i["job_id"] for i in resp.json()["items"]] == ["j1", "j2", "j3", "j5", "j4", "j6"]


def test_sort_invalid(client):
    resp = client.get("/api/jobs", params={"sort": "foo:desc"})
    assert resp.status_code == 400
    resp = client.get("/api/jobs", params={"sort": "publish_time"})
    assert resp.status_code == 400
    resp = client.get("/api/jobs", params={"sort": "publish_time:sideways"})
    assert resp.status_code == 400


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
    assert data["degree"] == "本科"
    assert data["year"] == "3-4年"
    resp2 = client.get("/api/jobs", params={"sort": "publish_time:desc"})
    first = resp2.json()["items"][0]
    assert first["company_name"] == "B公司"
    assert first["company_activity"] == "3分钟前回复"
    assert first["company_activity_score"] == 3


def test_companies_filter(client):
    resp = client.get("/api/companies", params={"type": "民营"})
    assert resp.status_code == 200
    assert resp.json()["total"] == 1
