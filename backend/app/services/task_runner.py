import asyncio
import logging
import threading
import time
from datetime import datetime

from sqlalchemy.orm import Session

from backend.app.core.config import REPO_ROOT, Config
from backend.app.core.database import SessionLocal
from backend.app.core.exceptions import AppError
from backend.app.core.site_security import decrypt_password
from backend.app.models import Keyword, ScrapeTask, Setting, SiteCredential, TaskStatus
from backend.app.scrapers.base import LoginCredential
from backend.app.scrapers.playwright import PlaywrightScraper
from backend.app.services.storage import upsert_companies, upsert_jobs

logger = logging.getLogger("job_hunter")

_POLL_SECONDS = 5
_SCRAPER_LOGIN_KEY = "scraper_login"
_DEFAULT_SCRAPER_LOGIN = {"enabled": False, "credential_id": None}


def recover_interrupted_tasks() -> None:
    """进程重启时仅将 in_progress 任务置为失败（PRD §6 崩溃恢复）；queued 未开始，交给 worker 继续执行。"""
    with SessionLocal() as db:
        tasks = (
            db.query(ScrapeTask)
            .filter(ScrapeTask.status == TaskStatus.IN_PROGRESS.value)
            .all()
        )
        for t in tasks:
            t.status = TaskStatus.FAILED.value
            t.error_message = "进程重启中断"
        if tasks:
            db.commit()
            logger.warning("崩溃恢复：%s 个进行中任务置为失败", len(tasks))


def _claim_next_task(db: Session) -> ScrapeTask | None:
    task = (
        db.query(ScrapeTask)
        .filter_by(status=TaskStatus.QUEUED.value)
        .order_by(ScrapeTask.created_at)
        .first()
    )
    if task is None:
        return None
    task.status = TaskStatus.IN_PROGRESS.value
    task.start_time = datetime.now()
    db.commit()
    db.refresh(task)
    return task


def _resolve_login_credential(db: Session, task: ScrapeTask) -> LoginCredential | None:
    """任务级 login_credential_id 优先，其次全局 scraper_login 默认，均无则匿名。"""
    cred_id = task.login_credential_id
    if cred_id is None:
        row = db.query(Setting).filter_by(key=_SCRAPER_LOGIN_KEY).first()
        value = row.value if row else _DEFAULT_SCRAPER_LOGIN
        if not value.get("enabled") or not value.get("credential_id"):
            return None
        cred_id = value["credential_id"]
    cred = db.get(SiteCredential, cred_id)
    if cred is None:
        logger.warning("任务引用的凭据不存在，降级为匿名抓取: task_id=%s cred_id=%s", task.id, cred_id)
        return None
    cfg = Config(repo_root=REPO_ROOT)
    try:
        password = decrypt_password(cred.password_enc, cfg.site_secret_key)
    except AppError:
        logger.error("任务凭据解密失败，降级为匿名抓取: task_id=%s", task.id)
        return None
    return LoginCredential(site=cred.site, username=cred.username, password=password)


async def execute_task(task_id: int) -> None:
    with SessionLocal() as db:
        task = db.get(ScrapeTask, task_id)
        keyword = db.get(Keyword, task.keyword_id)
        kw_text = keyword.keyword if keyword else ""
        kw_area = keyword.city if keyword else "000000"
        kw_industry = keyword.industry if keyword else None
        task_max_pages = task.max_pages
        login_credential = _resolve_login_credential(db, task)
    cfg = Config(repo_root=REPO_ROOT)
    # per-task max_pages 优先（创建时已校验 ≤ 全局上限），默认取全局上限
    max_pages = min(task_max_pages, cfg.max_pages) if task_max_pages else cfg.max_pages
    scraper = PlaywrightScraper(
        headful=cfg.headful,
        login_credential=login_credential,
        use_system_chrome=cfg.use_system_chrome,
    )
    try:
        first_page = True
        async for result in scraper.search(kw_text, max_pages, area=kw_area, industry=kw_industry):
            with SessionLocal() as db:
                task = db.get(ScrapeTask, task_id)
                if result.failed:
                    task.failed_count += 1
                else:
                    task.success_count += 1
                    upsert_jobs(db, result.jobs)
                    upsert_companies(db, result.companies)
                    task.total_found += len(result.jobs)
                task.last_page = result.page_num
                if first_page and result.total_pages:
                    task.total_pages = result.total_pages
                    first_page = False
                db.commit()
    except Exception as exc:
        logger.exception("任务执行异常 task_id=%s", task_id)
        with SessionLocal() as db:
            task = db.get(ScrapeTask, task_id)
            task.status = TaskStatus.FAILED.value
            task.end_time = datetime.now()
            task.error_message = str(exc)[:1000]
            db.commit()
        await scraper.close()
        return
    with SessionLocal() as db:
        task = db.get(ScrapeTask, task_id)
        keyword = db.get(Keyword, task.keyword_id)
        if keyword:
            keyword.last_scraped_at = datetime.now()
        task.end_time = datetime.now()
        if task.failed_count == 0:
            task.status = TaskStatus.SUCCESS.value
        else:
            task.status = TaskStatus.PARTIAL_SUCCESS.value
        db.commit()
        logger.info(
            "任务完成 task_id=%s keyword=%s status=%s success=%s failed=%s",
            task_id, kw_text, task.status, task.success_count, task.failed_count,
        )
    await scraper.close()


class TaskRunner:
    def __init__(self):
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                task = None
                with SessionLocal() as db:
                    task = _claim_next_task(db)
                if task:
                    logger.info("开始执行任务 task_id=%s", task.id)
                    asyncio.run(execute_task(task.id))
                else:
                    self._stop.wait(_POLL_SECONDS)
            except Exception:
                logger.exception("任务执行循环异常")
                continue
