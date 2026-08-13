from backend.app.core.database import SessionLocal
from backend.app.core.site_security import decrypt_password
from backend.app.models import ApplyTask, ScrapeTask, SiteCredential


def test_crud_flow(client, config):
    # create
    resp = client.post("/api/site-credentials", json={
        "site": "51job", "username": "13800000000", "password": "pw123", "remark": "主账号",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["has_password"] is True
    assert "password" not in data
    assert data["remark"] == "主账号"
    cid = data["id"]
    # list
    lst = client.get("/api/site-credentials").json()
    assert [c["id"] for c in lst] == [cid]
    # site 过滤
    assert client.get("/api/site-credentials", params={"site": "zhilian"}).json() == []
    assert len(client.get("/api/site-credentials", params={"site": "51job"}).json()) == 1
    # update remark
    resp = client.put(f"/api/site-credentials/{cid}", json={"remark": "新备注"})
    assert resp.status_code == 200 and resp.json()["remark"] == "新备注"
    # 密码仍加密存库（校验可解密回明文，且未泄露到响应）
    with SessionLocal() as s:
        row = s.get(SiteCredential, cid)
        assert decrypt_password(row.password_enc, config.site_secret_key) == "pw123"
    # update password 覆盖
    resp = client.put(f"/api/site-credentials/{cid}", json={"password": "newpw"})
    assert resp.status_code == 200
    with SessionLocal() as s:
        row = s.get(SiteCredential, cid)
        assert decrypt_password(row.password_enc, config.site_secret_key) == "newpw"
    # delete
    assert client.delete(f"/api/site-credentials/{cid}").status_code == 200
    assert client.get("/api/site-credentials").json() == []


def test_duplicate_site_username_409(client):
    body = {"site": "51job", "username": "13800000000", "password": "pw123"}
    assert client.post("/api/site-credentials", json=body).status_code == 200
    resp = client.post("/api/site-credentials", json=body)
    assert resp.status_code == 409


def test_duplicate_same_username_different_site_ok(client):
    body = {"site": "51job", "username": "13800000000", "password": "pw123"}
    assert client.post("/api/site-credentials", json=body).status_code == 200
    body["site"] = "zhilian"
    assert client.post("/api/site-credentials", json=body).status_code == 200


def test_update_404(client):
    assert client.put("/api/site-credentials/999", json={"remark": "x"}).status_code == 404
    assert client.delete("/api/site-credentials/999").status_code == 404


def test_requires_auth(client):
    client.headers.clear()
    resp = client.get("/api/site-credentials")
    assert resp.status_code == 401


def test_delete_blocked_by_running_task(client):
    cid = client.post("/api/site-credentials", json={
        "site": "51job", "username": "13800000000", "password": "pw123",
    }).json()["id"]
    with SessionLocal() as s:
        s.add(ScrapeTask(keyword_id=1, status="queued", login_credential_id=cid))
        s.commit()
    resp = client.delete(f"/api/site-credentials/{cid}")
    assert resp.status_code == 409


def test_delete_nullifies_finished_task_reference(client):
    cid = client.post("/api/site-credentials", json={
        "site": "51job", "username": "13800000000", "password": "pw123",
    }).json()["id"]
    with SessionLocal() as s:
        t = ScrapeTask(keyword_id=1, status="success", login_credential_id=cid)
        s.add(t)
        s.commit()
        tid = t.id
    assert client.delete(f"/api/site-credentials/{cid}").status_code == 200
    with SessionLocal() as s:
        assert s.get(ScrapeTask, tid).login_credential_id is None


def test_delete_blocked_by_running_apply_task(client):
    cid = client.post("/api/site-credentials", json={
        "site": "51job", "username": "13800000000", "password": "pw123",
    }).json()["id"]
    with SessionLocal() as s:
        s.add(ApplyTask(credential_id=cid, credential_username="13800000000", status="queued"))
        s.commit()
    resp = client.delete(f"/api/site-credentials/{cid}")
    assert resp.status_code == 409


def test_delete_nullifies_finished_apply_task_reference(client):
    cid = client.post("/api/site-credentials", json={
        "site": "51job", "username": "13800000000", "password": "pw123",
    }).json()["id"]
    with SessionLocal() as s:
        t = ApplyTask(credential_id=cid, credential_username="13800000000", status="success")
        s.add(t)
        s.commit()
        tid = t.id
    assert client.delete(f"/api/site-credentials/{cid}").status_code == 200
    with SessionLocal() as s:
        t = s.get(ApplyTask, tid)
        assert t.credential_id is None
        assert t.credential_username == "13800000000"  # 快照保留


def test_test_login_ok(client, monkeypatch):
    from backend.app.api import site_credentials as sc_mod

    cid = client.post("/api/site-credentials", json={
        "site": "51job", "username": "13800000000", "password": "pw123",
    }).json()["id"]

    async def _fake_run(site, username, password, headful=False):
        assert site == "51job" and username == "13800000000" and password == "pw123"
        return True, "登录成功"

    monkeypatch.setattr(sc_mod, "run_test_login", _fake_run)
    resp = client.post(f"/api/site-credentials/{cid}/test-login")
    assert resp.status_code == 200
    assert resp.json() == {"ok": True, "message": "登录成功"}


def test_test_login_404(client):
    assert client.post("/api/site-credentials/999/test-login").status_code == 404
