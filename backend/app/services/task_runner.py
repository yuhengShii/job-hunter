import asyncio
import logging
import random
import threading
import time
from datetime import datetime

from sqlalchemy.orm import Session

from backend.app.core.config import REPO_ROOT, Config
from backend.app.core.database import SessionLocal
from backend.app.models import Company, Keyword, ScrapeTask, TaskStatus
from backend.app.scrapers.playwright import PlaywrightScraper
from backend.app.services.storage import upsert_companies, upsert_jobs

logger = logging.getLogger("job_hunter")

_POLL_SECONDS = 5


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


async def _fetch_missing_company_details(scraper, company_urls: dict[str, str]) -> None:
    """公司详情页补抓：仅补 website 为空（卡片不提供、从未抓成）的公司，PRD §6。"""
    if not company_urls:
        return
    with SessionLocal() as db:
        missing = {
            cid: url
            for cid, url in company_urls.items()
            if db.query(Company)
            .filter(Company.company_id == cid, Company.website.is_(None))
            .first()
        }
    for cid, url in missing.items():
        try:
            draft = await scraper.fetch_company(cid, url)
            if draft:
                with SessionLocal() as db:
                    upsert_companies(db, [draft])
                    logger.info("公司详情已入库 company_id=%s", cid)
        except Exception:
            logger.exception("公司详情补抓异常 company_id=%s", cid)
        await asyncio.sleep(random.uniform(3.0, 8.0))


async def execute_task(task_id: int) -> None:
    with SessionLocal() as db:
        task = db.get(ScrapeTask, task_id)
        keyword = db.get(Keyword, task.keyword_id)
        kw_text = keyword.keyword if keyword else ""
        kw_area = keyword.city if keyword else "000000"
        task_max_pages = task.max_pages
    cfg = Config(repo_root=REPO_ROOT)
    # per-task max_pages 优先（创建时已校验 ≤ 全局上限），默认取全局上限
    max_pages = min(task_max_pages, cfg.max_pages) if task_max_pages else cfg.max_pages
    scraper = PlaywrightScraper(headful=cfg.headful)
    company_urls: dict[str, str] = {}
    try:
        first_page = True
        async for result in scraper.search(kw_text, max_pages, area=kw_area):
            with SessionLocal() as db:
                task = db.get(ScrapeTask, task_id)
                if result.failed:
                    task.failed_count += 1
                else:
                    task.success_count += 1
                    upsert_jobs(db, result.jobs)
                    upsert_companies(db, result.companies)
                    task.total_found += len(result.jobs)
                    for c in result.companies:
                        if c.company_url:
                            company_urls.setdefault(c.company_id, c.company_url)
                task.last_page = result.page_num
                if first_page and result.total_pages:
                    task.total_pages = result.total_pages
                    first_page = False
                db.commit()
        await _fetch_missing_company_details(scraper, company_urls)
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
