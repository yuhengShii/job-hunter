import asyncio
import logging
import threading
from datetime import datetime

from sqlalchemy.orm import Session

from backend.app.core.config import REPO_ROOT, Config
from backend.app.core.database import SessionLocal
from backend.app.core.exceptions import AppError
from backend.app.core.site_security import decrypt_password
from backend.app.models import ApplyTask, SiteCredential, TaskStatus
from backend.app.scrapers.applier import ApplyResult, ApplyTarget
from backend.app.scrapers.base import LoginCredential
from backend.app.scrapers.playwright import PlaywrightScraper

logger = logging.getLogger("job_hunter")

_POLL_SECONDS = 5


def recover_interrupted_apply_tasks() -> None:
    """进程重启时仅将 in_progress 的投递任务置为失败；queued 交给 worker 继续执行。"""
    with SessionLocal() as db:
        tasks = (
            db.query(ApplyTask)
            .filter(ApplyTask.status == TaskStatus.IN_PROGRESS.value)
            .all()
        )
        for t in tasks:
            t.status = TaskStatus.FAILED.value
            t.error_message = "进程重启中断"
        if tasks:
            db.commit()
            logger.warning("崩溃恢复：%s 个进行中投递任务置为失败", len(tasks))


def _claim_next_apply_task(db: Session) -> ApplyTask | None:
    task = (
        db.query(ApplyTask)
        .filter_by(status=TaskStatus.QUEUED.value)
        .order_by(ApplyTask.created_at)
        .first()
    )
    if task is None:
        return None
    task.status = TaskStatus.IN_PROGRESS.value
    task.start_time = datetime.now()
    db.commit()
    db.refresh(task)
    return task


def _resolve_apply_credential(db: Session, task: ApplyTask) -> LoginCredential | None:
    if task.credential_id is None:
        return None
    cred = db.get(SiteCredential, task.credential_id)
    if cred is None:
        logger.warning(
            "投递任务引用的凭据不存在: task_id=%s cred_id=%s", task.id, task.credential_id
        )
        return None
    cfg = Config(repo_root=REPO_ROOT)
    try:
        password = decrypt_password(cred.password_enc, cfg.site_secret_key)
    except AppError:
        logger.error("投递任务凭据解密失败: task_id=%s", task.id)
        return None
    return LoginCredential(site=cred.site, username=cred.username, password=password)


def _mark_result(results: list, result: ApplyResult) -> None:
    for r in results:
        if r.get("job_id") == result.job_id:
            r["status"] = result.status
            r["message"] = result.message
            return


def _sync_task_from_results(task: ApplyTask, results: list) -> None:
    task.results = results  # JSON 整列重新赋值，触发 SQLAlchemy 变更检测
    task.total_count = len(results)
    task.success_count = sum(1 for r in results if r.get("status") == "success")
    task.failed_count = sum(1 for r in results if r.get("status") == "failed")
    task.skipped_count = sum(1 for r in results if r.get("status") == "skipped")


def _record_result(task_id: int, results: list, result: ApplyResult) -> None:
    _mark_result(results, result)
    with SessionLocal() as db:
        task = db.get(ApplyTask, task_id)
        _sync_task_from_results(task, results)
        db.commit()


def _fail_task(task_id: int, message: str) -> None:
    with SessionLocal() as db:
        task = db.get(ApplyTask, task_id)
        task.status = TaskStatus.FAILED.value
        task.end_time = datetime.now()
        task.error_message = message
        db.commit()


async def execute_apply_task(task_id: int) -> None:
    with SessionLocal() as db:
        task = db.get(ApplyTask, task_id)
        if task is None:
            return
        results = list(task.results or [])
        credential = _resolve_apply_credential(db, task)
    if credential is None:
        logger.warning("投递任务凭据不可用，判失败: task_id=%s", task_id)
        _fail_task(task_id, "登录凭据不可用或解密失败")
        return

    targets = [
        ApplyTarget(
            job_id=r["job_id"],
            title=r.get("title", ""),
            job_url=r.get("job_url"),
            city=r.get("city"),
            sources=[(s[0], s[1]) for s in (r.get("sources") or [])],
        )
        for r in results
    ]
    cfg = Config(repo_root=REPO_ROOT)
    scraper = PlaywrightScraper(
        headful=cfg.headful,
        login_credential=credential,
        use_system_chrome=cfg.use_system_chrome,
    )
    try:
        async for result in scraper.apply_to_jobs(targets):
            _record_result(task_id, results, result)
    except Exception as exc:
        logger.exception("投递任务执行异常 task_id=%s", task_id)
        with SessionLocal() as db:
            task = db.get(ApplyTask, task_id)
            task.status = TaskStatus.FAILED.value
            task.end_time = datetime.now()
            task.error_message = str(exc)[:1000]
            _sync_task_from_results(task, results)
            db.commit()
        await scraper.close()
        return

    with SessionLocal() as db:
        task = db.get(ApplyTask, task_id)
        task.end_time = datetime.now()
        task.status = (
            TaskStatus.SUCCESS.value
            if task.failed_count == 0
            else TaskStatus.PARTIAL_SUCCESS.value
        )
        _sync_task_from_results(task, results)
        db.commit()
        logger.info(
            "投递任务完成 task_id=%s status=%s success=%s failed=%s skipped=%s",
            task_id,
            task.status,
            task.success_count,
            task.failed_count,
            task.skipped_count,
        )
    await scraper.close()


class ApplyRunner:
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
                    task = _claim_next_apply_task(db)
                if task:
                    logger.info("开始执行投递任务 task_id=%s", task.id)
                    asyncio.run(execute_apply_task(task.id))
                else:
                    self._stop.wait(_POLL_SECONDS)
            except Exception:
                logger.exception("投递任务执行循环异常")
                continue
