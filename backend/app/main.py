import os

from fastapi import FastAPI

from backend.app.api.auth import auth_router
from backend.app.api.companies import companies_router
from backend.app.api.deps import ensure_admin, set_current_config
from backend.app.api.jobs import jobs_router
from backend.app.api.keywords import keywords_router
from backend.app.api.settings import settings_router
from backend.app.api.stats import stats_router
from backend.app.api.tasks import tasks_router
from backend.app.core.config import REPO_ROOT, Config
from backend.app.core.database import SessionLocal, init_db
from backend.app.core.exceptions import AppError, app_error_handler
from backend.app.core.logging import setup_logging

_config: Config | None = None


def create_app(config: Config | None = None) -> FastAPI:
    global _config
    cfg = config or Config(repo_root=REPO_ROOT)
    _config = cfg
    set_current_config(cfg)
    setup_logging(cfg.log_dir)
    init_db(cfg)
    with SessionLocal() as db:
        ensure_admin(db, cfg)
    app = FastAPI(title="job-hunter")
    app.add_exception_handler(AppError, app_error_handler)
    app.include_router(auth_router)
    app.include_router(keywords_router)
    app.include_router(settings_router)
    app.include_router(tasks_router)
    app.include_router(jobs_router)
    app.include_router(companies_router)
    app.include_router(stats_router)
    return app


# 测试通过 conftest 设置 JOB_HUNTER_TESTING=1，避免污染真实 data/
if not os.environ.get("JOB_HUNTER_TESTING"):
    app = create_app()
