def test_get_default_scraper_login(client):
    resp = client.get("/api/settings/scraper-login")
    assert resp.status_code == 200
    assert resp.json() == {"enabled": False, "credential_id": None}


def test_put_and_get_scraper_login(client):
    cid = client.post("/api/site-credentials", json={
        "site": "51job", "username": "13800000000", "password": "pw123",
    }).json()["id"]
    body = {"enabled": True, "credential_id": cid}
    assert client.put("/api/settings/scraper-login", json=body).status_code == 200
    assert client.get("/api/settings/scraper-login").json() == body


def test_put_invalid_credential_400(client):
    resp = client.put("/api/settings/scraper-login", json={"enabled": True, "credential_id": 999})
    assert resp.status_code == 400


def test_put_disabled_without_credential_ok(client):
    resp = client.put("/api/settings/scraper-login", json={"enabled": False, "credential_id": None})
    assert resp.status_code == 200
