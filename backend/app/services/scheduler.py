import logging

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

from backend.app.core.database import SessionLocal
from backend.app.models import ScrapeTask, Setting, TaskStatus

logger = logging.getLogger("job_hunter")

_SCHEDULE_KEY = "schedule"
_DEFAULT_SCHEDULE = {"enabled": False, "interval_minutes": 60, "keyword_ids": []}


def create_scheduled_tasks(keyword_ids: list[int]) -> int:
    created = 0
    with SessionLocal() as db:
        running = {
            t.keyword_id
            for t in db.query(ScrapeTask).filter(
                ScrapeTask.status.in_([TaskStatus.QUEUED.value, TaskStatus.IN_PROGRESS.value])
            )
        }
        for kid in keyword_ids:
            if kid in running:
                continue
            db.add(ScrapeTask(keyword_id=kid, status=TaskStatus.QUEUED.value))
            created += 1
        db.commit()
    if created:
        logger.info("定时任务入队 %s 个", created)
    return created


def _read_schedule() -> dict:
    with SessionLocal() as db:
        row = db.query(Setting).filter_by(key=_SCHEDULE_KEY).first()
        return row.value if row else _DEFAULT_SCHEDULE


class SchedulerService:
    def __init__(self):
        self._scheduler = BackgroundScheduler(daemon=True)

    def start(self) -> None:
        self.apply_schedule()
        self._scheduler.start()

    def stop(self) -> None:
        self._scheduler.shutdown(wait=False)

    def apply_schedule(self) -> None:
        schedule = _read_schedule()
        job_id = "scheduled_scrape"
        if self._scheduler.get_job(job_id):
            self._scheduler.remove_job(job_id)
        if not schedule.get("enabled"):
            logger.info("定时任务已停用")
            return
        minutes = max(1, int(schedule.get("interval_minutes", 60)))
        keyword_ids = list(schedule.get("keyword_ids", []))
        self._scheduler.add_job(
            create_scheduled_tasks,
            trigger=IntervalTrigger(minutes=minutes),
            args=[keyword_ids],
            id=job_id,
            replace_existing=True,
        )
        logger.info("定时任务已启用 interval=%s 分钟 keywords=%s", minutes, keyword_ids)
