import os
from contextlib import asynccontextmanager

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
from backend.app.services.scheduler import SchedulerService, set_active_scheduler
from backend.app.services.task_runner import TaskRunner, recover_interrupted_tasks

_config: Config | None = None
_runner: TaskRunner | None = None
_scheduler: SchedulerService | None = None


def create_app(config: Config | None = None) -> FastAPI:
    global _config, _runner, _scheduler
    cfg = config or Config(repo_root=REPO_ROOT)
    _config = cfg
    set_current_config(cfg)
    setup_logging(cfg.log_dir)
    init_db(cfg)
    recover_interrupted_tasks()
    with SessionLocal() as db:
        ensure_admin(db, cfg)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        global _runner, _scheduler
        # 测试通过 conftest 设置 JOB_HUNTER_TESTING=1，不启动 worker/scheduler 线程
        if not os.environ.get("JOB_HUNTER_TESTING"):
            _runner = TaskRunner()
            _runner.start()
            _scheduler = SchedulerService()
            set_active_scheduler(_scheduler)
            _scheduler.start()
        yield
        set_active_scheduler(None)
        if _runner:
            _runner.stop()
        if _scheduler:
            _scheduler.stop()

    app = FastAPI(title="job-hunter", lifespan=lifespan)
    app.add_exception_handler(AppError, app_error_handler)
    for router in (auth_router, keywords_router, tasks_router, jobs_router, companies_router, stats_router, settings_router):
        app.include_router(router)
    return app


# 测试通过 conftest 设置 JOB_HUNTER_TESTING=1，避免污染真实 data/
if not os.environ.get("JOB_HUNTER_TESTING"):
    app = create_app()
