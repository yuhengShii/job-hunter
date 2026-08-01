from backend.app.core.database import SessionLocal, init_db
from backend.app.models import Keyword, ScrapeTask, TaskStatus
from backend.app.services.task_runner import recover_interrupted_tasks


def test_recover_interrupted_tasks(config):
    init_db(config)
    with SessionLocal() as s:
        kw = Keyword(keyword="python")
        s.add(kw)
        s.commit()
        s.add_all([
            ScrapeTask(keyword_id=kw.id, status=TaskStatus.QUEUED.value),
            ScrapeTask(keyword_id=kw.id, status=TaskStatus.IN_PROGRESS.value),
            ScrapeTask(keyword_id=kw.id, status=TaskStatus.SUCCESS.value),
        ])
        s.commit()
    recover_interrupted_tasks()
    with SessionLocal() as s:
        statuses = {t.status for t in s.query(ScrapeTask).all()}
        assert "queued" not in statuses
        assert "in_progress" not in statuses
        failed = s.query(ScrapeTask).filter_by(status=TaskStatus.FAILED.value).all()
        assert len(failed) == 2
        assert failed[0].error_message == "进程重启中断"
