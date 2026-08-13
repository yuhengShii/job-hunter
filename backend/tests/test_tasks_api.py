import pytest
from fastapi.testclient import TestClient

from backend.app.api.deps import ensure_admin
from backend.app.core.database import SessionLocal, init_db
from backend.app.main import create_app
from backend.app.models import ScrapeTask


@pytest.fixture()
def client(config):
    init_db(config)
    with SessionLocal() as s:
        ensure_admin(s, config)
        kw = __import__("backend.app.models", fromlist=["Keyword"]).Keyword(keyword="python")
        s.add(kw)
        s.commit()
    app = create_app(config)
    with TestClient(app) as c:
        token = c.post("/api/auth/login", json={"username": config.auth_username, "password": config.auth_password}).json()["access_token"]
        c.headers.update({"Authorization": f"Bearer {token}"})
        yield c


def test_create_task(client):
    resp = client.post("/api/tasks", json={"keyword_id": 1})
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "queued"
    assert data["mode"] == "playwright"


def test_create_task_conflict_409(client):
    assert client.post("/api/tasks", json={"keyword_id": 1}).status_code == 200
    resp = client.post("/api/tasks", json={"keyword_id": 1})
    assert resp.status_code == 409


def test_create_task_max_pages_cap(client):
    resp = client.post("/api/tasks", json={"keyword_id": 1, "max_pages": 9999})
    assert resp.status_code == 400


def test_create_task_stores_max_pages(client):
    resp = client.post("/api/tasks", json={"keyword_id": 1, "max_pages": 3})
    assert resp.status_code == 200
    assert resp.json()["max_pages"] == 3
    tasks = client.get("/api/tasks").json()
    assert tasks[0]["max_pages"] == 3


def test_list_and_delete_task(client):
    client.post("/api/tasks", json={"keyword_id": 1})
    tasks = client.get("/api/tasks").json()
    assert len(tasks) == 1
    tid = tasks[0]["id"]
    resp = client.delete(f"/api/tasks/{tid}")
    assert resp.status_code == 200
    assert client.get("/api/tasks").json() == []


def test_delete_running_task_400(client):
    tid = client.post("/api/tasks", json={"keyword_id": 1}).json()["id"]
    with SessionLocal() as s:
        t = s.get(ScrapeTask, tid)
        t.status = "in_progress"
        s.commit()
    resp = client.delete(f"/api/tasks/{tid}")
    assert resp.status_code == 400


def test_create_task_with_login_credential(client):
    cid = client.post("/api/site-credentials", json={
        "site": "51job", "username": "13800000000", "password": "pw123",
    }).json()["id"]
    resp = client.post("/api/tasks", json={"keyword_id": 1, "login_credential_id": cid})
    assert resp.status_code == 200
    data = resp.json()
    assert data["login_credential_id"] == cid
    assert data["login_username"] == "13800000000"


def test_create_task_invalid_credential_400(client):
    resp = client.post("/api/tasks", json={"keyword_id": 1, "login_credential_id": 999})
    assert resp.status_code == 400


def test_list_task_has_login_username(client):
    cid = client.post("/api/site-credentials", json={
        "site": "51job", "username": "13800000000", "password": "pw123",
    }).json()["id"]
    client.post("/api/tasks", json={"keyword_id": 1, "login_credential_id": cid})
    task = client.get("/api/tasks").json()[0]
    assert task["login_credential_id"] == cid
    assert task["login_username"] == "13800000000"
