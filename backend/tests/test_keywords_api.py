import pytest
from fastapi.testclient import TestClient

from backend.app.api.deps import ensure_admin
from backend.app.core.database import SessionLocal, init_db
from backend.app.main import create_app


@pytest.fixture()
def client(config):
    init_db(config)
    with SessionLocal() as s:
        ensure_admin(s, config)
    app = create_app(config)
    with TestClient(app) as c:
        token = c.post("/api/auth/login", json={"username": config.auth_username, "password": config.auth_password}).json()["access_token"]
        c.headers.update({"Authorization": f"Bearer {token}"})
        yield c


def test_keyword_crud(client):
    resp = client.post("/api/keywords", json={"keyword": "python"})
    assert resp.status_code == 200
    kid = resp.json()["id"]
    assert resp.json()["enabled"] is True
    assert resp.json()["scrape_mode"] == "playwright"
    assert resp.json()["city"] == "000000"

    resp = client.post("/api/keywords", json={"keyword": "python"})
    assert resp.status_code == 409

    resp = client.put(f"/api/keywords/{kid}", json={"scrape_mode": "playwright"})
    assert resp.status_code == 200

    resp = client.post(f"/api/keywords/{kid}/toggle")
    assert resp.status_code == 200
    assert resp.json()["enabled"] is False

    resp = client.get("/api/keywords")
    assert resp.status_code == 200
    assert len(resp.json()) == 1

    resp = client.delete(f"/api/keywords/{kid}")
    assert resp.status_code == 200
    assert client.get("/api/keywords").json() == []


def test_keyword_unique_by_keyword_and_city(client):
    resp = client.post("/api/keywords", json={"keyword": "算法工程师", "city": "020000"})
    assert resp.status_code == 200
    assert resp.json()["city"] == "020000"

    # 同关键字不同城市：允许
    resp = client.post("/api/keywords", json={"keyword": "算法工程师", "city": "010000"})
    assert resp.status_code == 200

    # 同关键字同城市：409
    resp = client.post("/api/keywords", json={"keyword": "算法工程师", "city": "020000"})
    assert resp.status_code == 409

    # 更新撞联合唯一：409
    ids = [k["id"] for k in client.get("/api/keywords").json() if k["city"] == "010000"]
    resp = client.put(f"/api/keywords/{ids[0]}", json={"city": "020000"})
    assert resp.status_code == 409

    # 更新 city 到未占用组合：200
    resp = client.put(f"/api/keywords/{ids[0]}", json={"city": "080200"})
    assert resp.status_code == 200
    assert resp.json()["city"] == "080200"


def test_keyword_delete_blocked_by_running_task(client):
    from backend.app.models import ScrapeTask

    kid = client.post("/api/keywords", json={"keyword": "python"}).json()["id"]
    tid = client.post("/api/tasks", json={"keyword_id": kid}).json()["id"]
    with SessionLocal() as s:
        t = s.get(ScrapeTask, tid)
        t.status = "in_progress"
        s.commit()
    resp = client.delete(f"/api/keywords/{kid}")
    assert resp.status_code == 400
    # 任务结束后可删除
    with SessionLocal() as s:
        t = s.get(ScrapeTask, tid)
        t.status = "success"
        s.commit()
    assert client.delete(f"/api/keywords/{kid}").status_code == 200


def test_keyword_industry_crud(client):
    resp = client.post("/api/keywords", json={"keyword": "医疗采购", "industry": "08,46,47"})
    assert resp.status_code == 200
    assert resp.json()["industry"] == "08,46,47"
    kid = resp.json()["id"]

    # 非法格式：三位编码
    resp = client.post("/api/keywords", json={"keyword": "x", "industry": "080"})
    assert resp.status_code == 422
    # 非法格式：超过 5 个
    resp = client.post("/api/keywords", json={"keyword": "y", "industry": "01,02,03,04,05,06"})
    assert resp.status_code == 422
    # 空字符串归一为 None
    resp = client.post("/api/keywords", json={"keyword": "z", "industry": ""})
    assert resp.json()["industry"] is None

    # 编辑设置
    resp = client.put(f"/api/keywords/{kid}", json={"industry": "47"})
    assert resp.status_code == 200
    assert resp.json()["industry"] == "47"
    # 未传 industry 不清除已有值
    resp = client.put(f"/api/keywords/{kid}", json={"city": "020000"})
    assert resp.json()["industry"] == "47"
    # 显式置 null 清除筛选
    resp = client.put(f"/api/keywords/{kid}", json={"industry": None})
    assert resp.json()["industry"] is None


def test_keyword_requires_auth(config):
    init_db(config)
    with SessionLocal() as s:
        ensure_admin(s, config)
    app = create_app(config)
    with TestClient(app) as c:
        assert c.get("/api/keywords").status_code == 401
