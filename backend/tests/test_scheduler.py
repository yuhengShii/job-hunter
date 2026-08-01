from fastapi.testclient import TestClient

from backend.app.core.database import SessionLocal, init_db
from backend.app.main import create_app
from backend.app.models import Keyword, ScrapeTask, Setting
from backend.app.services import scheduler as scheduler_mod
from backend.app.services.scheduler import create_scheduled_tasks


def test_create_scheduled_tasks(config):
    init_db(config)
    with SessionLocal() as s:
        k1 = Keyword(keyword="a")
        k2 = Keyword(keyword="b")
        s.add_all([k1, k2])
        s.commit()
        create_scheduled_tasks([k1.id, k2.id])
        assert s.query(ScrapeTask).count() == 2
        create_scheduled_tasks([k1.id, k2.id])
        assert s.query(ScrapeTask).count() == 2
        task = s.query(ScrapeTask).filter_by(keyword_id=k1.id).first()
        task.status = "in_progress"
        s.commit()
        create_scheduled_tasks([k1.id, k2.id])
        assert s.query(ScrapeTask).count() == 2
        k3 = Keyword(keyword="c")
        s.add(k3)
        s.commit()
        create_scheduled_tasks([k3.id])
        assert s.query(ScrapeTask).count() == 3


def test_put_schedule_reapplies_active_scheduler(config):
    from backend.app.api.deps import ensure_admin

    init_db(config)
    with SessionLocal() as s:
        ensure_admin(s, config)
    calls = []

    class FakeScheduler:
        def apply_schedule(self):
            calls.append(1)

    scheduler_mod.set_active_scheduler(FakeScheduler())
    try:
        app = create_app(config)
        with TestClient(app) as c:
            token = c.post(
                "/api/auth/login",
                json={"username": config.auth_username, "password": config.auth_password},
            ).json()["access_token"]
            c.headers.update({"Authorization": f"Bearer {token}"})
            resp = c.put(
                "/api/settings/schedule",
                json={"enabled": True, "interval_minutes": 30, "keyword_ids": [1]},
            )
            assert resp.status_code == 200
            assert calls == [1]
    finally:
        scheduler_mod.set_active_scheduler(None)
