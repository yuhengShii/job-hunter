import asyncio

from backend.app.core.config import REPO_ROOT
from backend.app.core.database import SessionLocal, init_db
from backend.app.models import Company, Job, Keyword, ScrapeTask, Setting, SiteCredential, TaskStatus
from backend.app.scrapers.base import CompanyDraft, JobDraft, PageResult
from backend.app.services import task_runner


class FakeScraper:
    def __init__(self, headful: bool = False, login_credential=None):
        self.headful = headful
        self.login_credential_arg = login_credential
        self.pages_arg: int | None = None
        self.area_arg: str | None = None
        self.keyword_arg: str | None = None
        self.industry_arg: str | None = None
        self.search_results: list[PageResult] = []
        self.raise_on_search: Exception | None = None

    async def search(self, keyword, pages, area="000000", industry=None):
        self.keyword_arg = keyword
        self.pages_arg = pages
        self.area_arg = area
        self.industry_arg = industry
        if self.raise_on_search:
            raise self.raise_on_search
        for r in self.search_results:
            yield r

    async def close(self):
        pass


def _seed_task(db_path, max_pages: int | None = None) -> tuple[int, int]:
    with SessionLocal() as s:
        kw = Keyword(keyword="python")
        s.add(kw)
        s.commit()
        task = ScrapeTask(keyword_id=kw.id, status=TaskStatus.QUEUED.value, max_pages=max_pages)
        s.add(task)
        s.commit()
        return task.id, kw.id


def _patch(monkeypatch, fake: FakeScraper, config):
    def _factory(headful=False, login_credential=None, use_system_chrome=False):
        fake.login_credential_arg = login_credential
        return fake

    monkeypatch.setattr(task_runner, "PlaywrightScraper", _factory)
    monkeypatch.setattr(task_runner, "Config", lambda repo_root=REPO_ROOT: config)


def test_execute_task_success(config, monkeypatch):
    init_db(config)
    fake = FakeScraper()
    fake.search_results = [
        PageResult(
            page_num=1,
            jobs=[JobDraft(job_id="j1", title="t1", company_id="c1", salary_min=1000, salary_max=2000)],
            companies=[CompanyDraft(company_id="c1", name="A公司")],
            total_pages=2,
        ),
        PageResult(page_num=2, jobs=[JobDraft(job_id="j2", title="t2", company_id="c1")]),
    ]
    _patch(monkeypatch, fake, config)
    task_id, kw_id = _seed_task(config.db_path, max_pages=2)
    asyncio.run(task_runner.execute_task(task_id))
    with SessionLocal() as s:
        t = s.get(ScrapeTask, task_id)
        assert t.status == TaskStatus.SUCCESS.value
        assert t.success_count == 2
        assert t.failed_count == 0
        assert t.total_pages == 2
        assert t.last_page == 2
        assert t.total_found == 2
        assert t.end_time is not None
        assert s.query(Job).count() == 2
        comp = s.query(Company).filter_by(company_id="c1").one()
        assert comp.name == "A公司"
        assert s.get(Keyword, kw_id).last_scraped_at is not None
    assert fake.pages_arg == 2
    assert fake.area_arg == "000000"
    assert fake.keyword_arg == "python"


def test_execute_task_default_max_pages(config, monkeypatch):
    init_db(config)
    fake = FakeScraper()
    fake.search_results = [PageResult(page_num=1, jobs=[JobDraft(job_id="j1", title="t1")])]
    _patch(monkeypatch, fake, config)
    task_id, _ = _seed_task(config.db_path, max_pages=None)
    asyncio.run(task_runner.execute_task(task_id))
    assert fake.pages_arg == config.max_pages


def test_execute_task_partial_success(config, monkeypatch):
    init_db(config)
    fake = FakeScraper()
    fake.search_results = [
        PageResult(page_num=1, jobs=[JobDraft(job_id="j1", title="t1")], total_pages=2),
        PageResult(page_num=2, jobs=[], failed=True),
    ]
    _patch(monkeypatch, fake, config)
    task_id, _ = _seed_task(config.db_path)
    asyncio.run(task_runner.execute_task(task_id))
    with SessionLocal() as s:
        t = s.get(ScrapeTask, task_id)
        assert t.status == TaskStatus.PARTIAL_SUCCESS.value
        assert t.success_count == 1
        assert t.failed_count == 1
        assert s.query(Job).count() == 1


def test_execute_task_exception_marks_failed(config, monkeypatch):
    init_db(config)
    fake = FakeScraper()
    fake.raise_on_search = RuntimeError("boom")
    _patch(monkeypatch, fake, config)
    task_id, _ = _seed_task(config.db_path)
    asyncio.run(task_runner.execute_task(task_id))
    with SessionLocal() as s:
        t = s.get(ScrapeTask, task_id)
        assert t.status == TaskStatus.FAILED.value
        assert "boom" in (t.error_message or "")
        assert t.end_time is not None


def test_execute_task_passes_industry(config, monkeypatch):
    init_db(config)
    fake = FakeScraper()
    fake.search_results = [PageResult(page_num=1, jobs=[JobDraft(job_id="j1", title="t1")])]
    _patch(monkeypatch, fake, config)
    with SessionLocal() as s:
        kw = Keyword(keyword="医疗采购", industry="47")
        s.add(kw)
        s.commit()
        kw_id = kw.id
        task = ScrapeTask(keyword_id=kw_id, status=TaskStatus.QUEUED.value)
        s.add(task)
        s.commit()
        task_id = task.id
    asyncio.run(task_runner.execute_task(task_id))
    assert fake.industry_arg == "47"


def test_execute_task_industry_none_when_unset(config, monkeypatch):
    init_db(config)
    fake = FakeScraper()
    fake.search_results = [PageResult(page_num=1, jobs=[JobDraft(job_id="j1", title="t1")])]
    _patch(monkeypatch, fake, config)
    task_id, _ = _seed_task(config.db_path)
    asyncio.run(task_runner.execute_task(task_id))
    assert fake.industry_arg is None


def _seed_credential(config, username="13800000000") -> int:
    from backend.app.core.site_security import encrypt_password

    with SessionLocal() as s:
        c = SiteCredential(
            site="51job",
            username=username,
            password_enc=encrypt_password("pw123", config.site_secret_key),
        )
        s.add(c)
        s.commit()
        return c.id


def _seed_setting_scraper_login(credential_id: int) -> None:
    with SessionLocal() as s:
        s.add(Setting(key="scraper_login", value={"enabled": True, "credential_id": credential_id}))
        s.commit()


def test_execute_task_uses_task_login_credential(config, monkeypatch):
    init_db(config)
    fake = FakeScraper()
    fake.search_results = [PageResult(page_num=1, jobs=[JobDraft(job_id="j1", title="t1")])]
    _patch(monkeypatch, fake, config)
    cid = _seed_credential(config)
    with SessionLocal() as s:
        kw = Keyword(keyword="python")
        s.add(kw)
        s.commit()
        task = ScrapeTask(keyword_id=kw.id, status=TaskStatus.QUEUED.value, login_credential_id=cid)
        s.add(task)
        s.commit()
        task_id = task.id
    asyncio.run(task_runner.execute_task(task_id))
    assert fake.login_credential_arg is not None
    assert fake.login_credential_arg.username == "13800000000"
    assert fake.login_credential_arg.password == "pw123"


def test_execute_task_uses_global_default_when_task_unset(config, monkeypatch):
    init_db(config)
    fake = FakeScraper()
    fake.search_results = [PageResult(page_num=1, jobs=[JobDraft(job_id="j1", title="t1")])]
    _patch(monkeypatch, fake, config)
    cid = _seed_credential(config)
    _seed_setting_scraper_login(cid)
    task_id, _ = _seed_task(config.db_path)
    asyncio.run(task_runner.execute_task(task_id))
    assert fake.login_credential_arg is not None
    assert fake.login_credential_arg.username == "13800000000"


def test_execute_task_no_login_by_default(config, monkeypatch):
    init_db(config)
    fake = FakeScraper()
    fake.search_results = [PageResult(page_num=1, jobs=[JobDraft(job_id="j1", title="t1")])]
    _patch(monkeypatch, fake, config)
    task_id, _ = _seed_task(config.db_path)
    asyncio.run(task_runner.execute_task(task_id))
    assert fake.login_credential_arg is None
