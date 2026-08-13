import asyncio

from backend.app.core.config import REPO_ROOT
from backend.app.core.database import SessionLocal, init_db
from backend.app.core.site_security import encrypt_password
from backend.app.models import ApplyTask, SiteCredential, TaskStatus
from backend.app.scrapers.applier import ApplyResult
from backend.app.services import apply_runner


class FakeScraper:
    def __init__(self, headful=False, login_credential=None):
        self.headful = headful
        self.login_credential_arg = login_credential
        self.results = []
        self.raise_on_apply = None

    async def apply_to_jobs(self, targets):
        if self.raise_on_apply:
            raise self.raise_on_apply
        for r in self.results:
            yield r

    async def close(self):
        pass


def _patch(monkeypatch, fake, config):
    def _factory(headful=False, login_credential=None, use_system_chrome=False):
        fake.login_credential_arg = login_credential
        return fake

    monkeypatch.setattr(apply_runner, "PlaywrightScraper", _factory)
    monkeypatch.setattr(apply_runner, "Config", lambda repo_root=REPO_ROOT: config)


def _seed_credential(config) -> int:
    with SessionLocal() as s:
        c = SiteCredential(
            site="51job",
            username="13800000000",
            password_enc=encrypt_password("pw123", config.site_secret_key),
        )
        s.add(c)
        s.commit()
        return c.id


def _snapshot(*job_ids):
    return [
        {
            "job_id": j,
            "title": j,
            "job_url": f"https://jobs.51job.com/all/{j}.html",
            "status": "pending",
            "message": "",
        }
        for j in job_ids
    ]


def _seed_apply_task(credential_id, results) -> int:
    with SessionLocal() as s:
        t = ApplyTask(
            credential_id=credential_id,
            credential_username="13800000000",
            status=TaskStatus.QUEUED.value,
            results=results,
            total_count=len(results),
        )
        s.add(t)
        s.commit()
        return t.id


def test_recover_interrupted_apply_tasks(config):
    init_db(config)
    with SessionLocal() as s:
        s.add_all([
            ApplyTask(credential_username="u", status=TaskStatus.QUEUED.value),
            ApplyTask(credential_username="u", status=TaskStatus.IN_PROGRESS.value),
            ApplyTask(credential_username="u", status=TaskStatus.SUCCESS.value),
        ])
        s.commit()
    apply_runner.recover_interrupted_apply_tasks()
    with SessionLocal() as s:
        statuses = {t.status for t in s.query(ApplyTask).all()}
        assert "queued" in statuses
        assert "in_progress" not in statuses
        failed = s.query(ApplyTask).filter_by(status=TaskStatus.FAILED.value).all()
        assert len(failed) == 1
        assert failed[0].error_message == "进程重启中断"


def test_execute_apply_task_success(config, monkeypatch):
    init_db(config)
    fake = FakeScraper()
    fake.results = [
        ApplyResult("j1", "success", "投递成功"),
        ApplyResult("j2", "skipped", "已投递"),
    ]
    _patch(monkeypatch, fake, config)
    cid = _seed_credential(config)
    task_id = _seed_apply_task(cid, _snapshot("j1", "j2"))
    asyncio.run(apply_runner.execute_apply_task(task_id))
    with SessionLocal() as s:
        t = s.get(ApplyTask, task_id)
        assert t.status == TaskStatus.SUCCESS.value
        assert t.success_count == 1
        assert t.skipped_count == 1
        assert t.failed_count == 0
        assert t.end_time is not None
        assert {r["job_id"]: r["status"] for r in t.results} == {"j1": "success", "j2": "skipped"}
    assert fake.login_credential_arg.username == "13800000000"


def test_execute_apply_task_partial_success(config, monkeypatch):
    init_db(config)
    fake = FakeScraper()
    fake.results = [
        ApplyResult("j1", "success", "投递成功"),
        ApplyResult("j2", "failed", "未找到投递入口"),
    ]
    _patch(monkeypatch, fake, config)
    cid = _seed_credential(config)
    task_id = _seed_apply_task(cid, _snapshot("j1", "j2"))
    asyncio.run(apply_runner.execute_apply_task(task_id))
    with SessionLocal() as s:
        t = s.get(ApplyTask, task_id)
        assert t.status == TaskStatus.PARTIAL_SUCCESS.value
        assert t.success_count == 1
        assert t.failed_count == 1


def test_execute_apply_task_login_failure(config, monkeypatch):
    init_db(config)
    fake = FakeScraper()
    fake.raise_on_apply = RuntimeError("登录失败，无法投递")
    _patch(monkeypatch, fake, config)
    cid = _seed_credential(config)
    task_id = _seed_apply_task(cid, _snapshot("j1"))
    asyncio.run(apply_runner.execute_apply_task(task_id))
    with SessionLocal() as s:
        t = s.get(ApplyTask, task_id)
        assert t.status == TaskStatus.FAILED.value
        assert "登录失败" in (t.error_message or "")
        assert t.end_time is not None


def test_execute_apply_task_credential_missing(config, monkeypatch):
    init_db(config)
    task_id = _seed_apply_task(None, _snapshot("j1"))
    asyncio.run(apply_runner.execute_apply_task(task_id))
    with SessionLocal() as s:
        t = s.get(ApplyTask, task_id)
        assert t.status == TaskStatus.FAILED.value
        assert "凭据" in (t.error_message or "")
