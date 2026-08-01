from fastapi.routing import _IncludedRouter
from fastapi.testclient import TestClient

from backend.app.core.database import SessionLocal, init_db
from backend.app.main import create_app
from backend.app.models import Keyword, ScrapeTask, TaskStatus


def _route_paths(app):
    paths = set()
    for r in app.routes:
        if isinstance(r, _IncludedRouter):
            paths.update(x.path for x in r.original_router.routes)
        else:
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
        tasks = s.query(ScrapeTask).all()
        assert len(tasks) == 2
        assert all(t.status == TaskStatus.FAILED.value for t in tasks)
        assert all(t.error_message == "进程重启中断" for t in tasks)
