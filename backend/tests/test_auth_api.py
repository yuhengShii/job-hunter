from fastapi.testclient import TestClient

from backend.app.api.deps import ensure_admin
from backend.app.core.database import SessionLocal, init_db
from backend.app.main import create_app


def _client(config):
    init_db(config)
    with SessionLocal() as s:
        ensure_admin(s, config)
    app = create_app(config)
    return TestClient(app)


def test_login_success(config):
    client = _client(config)
    resp = client.post("/api/auth/login", json={"username": config.auth_username, "password": config.auth_password})
    assert resp.status_code == 200
    assert resp.json()["token_type"] == "bearer"
    assert resp.json()["access_token"]


def test_login_wrong_password(config):
    client = _client(config)
    resp = client.post("/api/auth/login", json={"username": config.auth_username, "password": "wrong"})
    assert resp.status_code == 401


def test_me_with_token(config):
    client = _client(config)
    token = client.post("/api/auth/login", json={"username": config.auth_username, "password": config.auth_password}).json()["access_token"]
    resp = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert resp.json()["username"] == config.auth_username


def test_me_without_token(config):
    client = _client(config)
    resp = client.get("/api/auth/me")
    assert resp.status_code == 401
