from fastapi.testclient import TestClient

from backend.app.core.database import SessionLocal, init_db
from backend.app.main import create_app
from backend.app.models import Keyword, ScrapeTask, TaskStatus


def _route_paths(app):
    paths = set()
    for r in app.routes:
        routes = getattr(r, "original_router", None)
        if routes is not None:
            paths.update(x.path for x in routes.routes)
        elif hasattr(r, "path"):
            paths.add(r.path)
    return paths


def test_app_startup_and_shutdown(config):
    init_db(config)
    app = create_app(config)
    with TestClient(app) as client:
        resp = client.get("/api/auth/me")
        assert resp.status_code == 401
    assert app is not None


def test_full_routes_registered(config):
    init_db(config)
    app = create_app(config)
    paths = _route_paths(app)
    assert "/api/auth/login" in paths
    assert "/api/keywords" in paths
    assert "/api/tasks" in paths
    assert "/api/jobs" in paths
    assert "/api/companies" in paths
    assert "/api/stats/overview" in paths
    assert "/api/settings/schedule" in paths


def test_create_app_recovers_interrupted_tasks(config):
    init_db(config)
    with SessionLocal() as s:
        kw = Keyword(keyword="python")
        s.add(kw)
        s.commit()
        s.add(ScrapeTask(keyword_id=kw.id, status=TaskStatus.QUEUED.value))
        s.add(ScrapeTask(keyword_id=kw.id, status=TaskStatus.IN_PROGRESS.value))
        s.commit()
    create_app(config)
    with SessionLocal() as s:
        tasks = s.query(ScrapeTask).order_by(ScrapeTask.id).all()
        assert len(tasks) == 2
        by_status = {t.status: t for t in tasks}
        assert "queued" in by_status
        failed = by_status[TaskStatus.FAILED.value]
        assert failed.error_message == "进程重启中断"
