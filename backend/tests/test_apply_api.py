import pytest
from fastapi.testclient import TestClient

from backend.app.core.database import SessionLocal, init_db
from backend.app.core.site_security import encrypt_password
from backend.app.main import create_app
from backend.app.models import ApplyTask, Favorite, Job, SiteCredential, TaskStatus


def _seed_credential(config, site="51job") -> int:
    with SessionLocal() as s:
        cred = SiteCredential(
            site=site,
            username="13800000000",
            password_enc=encrypt_password("pw123", config.site_secret_key),
        )
        s.add(cred)
        s.commit()
        return cred.id


def _seed_jobs():
    with SessionLocal() as s:
        s.add_all([Job(job_id="j1", title="Python工程师"), Job(job_id="j2", title="Java工程师")])
        s.commit()


def _seed_favorites(job_ids):
    with SessionLocal() as s:
        s.add_all([Favorite(job_id=jid) for jid in job_ids])
        s.commit()


@pytest.fixture()
def client(config):
    init_db(config)
    cid = _seed_credential(config)
    _seed_jobs()
    app = create_app(config)
    with TestClient(app) as c:
        token = c.post("/api/auth/login", json={"username": config.auth_username, "password": config.auth_password}).json()["access_token"]
        c.headers.update({"Authorization": f"Bearer {token}"})
        yield c, cid


def test_create_all_favorites(client):
    c, cid = client
    _seed_favorites(["j1", "j2"])
    resp = c.post("/api/apply", json={"credential_id": cid})
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "queued"
    assert data["total_count"] == 2
    assert data["credential_username"] == "13800000000"
    assert [r["status"] for r in data["results"]] == ["pending", "pending"]
    assert {r["job_id"] for r in data["results"]} == {"j1", "j2"}


def test_create_explicit_job_ids(client):
    c, cid = client
    resp = c.post("/api/apply", json={"credential_id": cid, "job_ids": ["j1", "j1", "no_such"]})
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_count"] == 1
    assert data["results"][0]["job_id"] == "j1"


def test_create_snapshot_includes_sources(client):
    """目标快照应包含源抓取条件（job_sources），供投递搜索使用。"""
    from backend.app.core.database import SessionLocal
    from backend.app.models import JobSource

    c, cid = client
    with SessionLocal() as s:
        s.add_all([
            JobSource(job_id="j1", source_keyword="采购", source_city="020000", source_industry="08,46,47"),
            JobSource(job_id="j1", source_keyword="医疗采购", source_city="010000", source_industry=None),
        ])
        s.commit()
    resp = c.post("/api/apply", json={"credential_id": cid, "job_ids": ["j1"]})
    assert resp.status_code == 200
    with SessionLocal() as s:
        from backend.app.models import ApplyTask

        row = s.get(ApplyTask, resp.json()["id"])
        sources = row.results[0]["sources"]
    # 带行业筛选的在前，其次 last_seen 新到旧
    assert sources == [["020000", "08,46,47"], ["010000", None]]


def test_create_no_jobs_400(client):
    c, cid = client
    resp = c.post("/api/apply", json={"credential_id": cid})
    assert resp.status_code == 400


def test_create_unknown_credential_400(client):
    c, _ = client
    assert c.post("/api/apply", json={"credential_id": 999, "job_ids": ["j1"]}).status_code == 400


def test_create_non_51job_credential_400(client, config):
    c, _ = client
    zid = _seed_credential(config, site="zhilian")
    assert c.post("/api/apply", json={"credential_id": zid, "job_ids": ["j1"]}).status_code == 400


def test_create_conflict_409(client):
    c, cid = client
    _seed_favorites(["j1"])
    assert c.post("/api/apply", json={"credential_id": cid}).status_code == 200
    assert c.post("/api/apply", json={"credential_id": cid}).status_code == 409


def test_list_and_get(client):
    c, cid = client
    _seed_favorites(["j1"])
    c.post("/api/apply", json={"credential_id": cid})
    lst = c.get("/api/apply").json()
    assert len(lst) == 1
    tid = lst[0]["id"]
    detail = c.get(f"/api/apply/{tid}").json()
    assert detail["total_count"] == 1
    assert c.get("/api/apply/999").status_code == 404


def test_delete(client):
    c, cid = client
    _seed_favorites(["j1"])
    tid = c.post("/api/apply", json={"credential_id": cid}).json()["id"]
    assert c.delete(f"/api/apply/{tid}").status_code == 200
    assert c.get(f"/api/apply/{tid}").status_code == 404


def test_delete_in_progress_400(client):
    c, cid = client
    _seed_favorites(["j1"])
    tid = c.post("/api/apply", json={"credential_id": cid}).json()["id"]
    with SessionLocal() as s:
        s.get(ApplyTask, tid).status = TaskStatus.IN_PROGRESS.value
        s.commit()
    assert c.delete(f"/api/apply/{tid}").status_code == 400


def test_requires_auth(config):
    init_db(config)
    app = create_app(config)
    with TestClient(app) as c:
        assert c.post("/api/apply", json={"credential_id": 1}).status_code == 401
        assert c.get("/api/apply").status_code == 401
