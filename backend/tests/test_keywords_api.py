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


def test_keyword_requires_auth(config):
    init_db(config)
    with SessionLocal() as s:
        ensure_admin(s, config)
    app = create_app(config)
    with TestClient(app) as c:
        assert c.get("/api/keywords").status_code == 401
