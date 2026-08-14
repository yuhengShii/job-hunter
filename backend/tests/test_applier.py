import asyncio

from backend.app.scrapers import applier
from backend.app.scrapers.applier import (
    ApplyResult,
    ApplyTarget,
    apply_job_group,
    apply_to_job,
    build_job_url,
)


class _Page:
    def __init__(self, cards_ready=True, first_wait_fails=False, goto_error=None):
        self.cards_ready = cards_ready
        self.first_wait_fails = first_wait_fails
        self.goto_error = goto_error
        self.goto_url = None
        self.wait_calls = 0

    async def goto(self, url, **kw):
        self.goto_url = url
        if self.goto_error:
            raise self.goto_error

    async def wait_for_selector(self, sel, timeout=None):
        self.wait_calls += 1
        if not self.cards_ready or (self.first_wait_fails and self.wait_calls == 1):
            raise TimeoutError("timeout")

    async def wait_for_timeout(self, ms):
        pass

    async def evaluate(self, js, arg=None):
        return None

    def locator(self, sel):
        return self


def _run(coro):
    return asyncio.run(coro)


def _target(job_id="j1", title="采购工程师", city="上海", sources=None):
    return ApplyTarget(job_id=job_id, title=title, city=city, sources=sources or [])


def _patch_helpers(
    monkeypatch,
    *,
    body="",
    select=None,
    batch_apply=True,
    batch_result=None,
    next_page=True,
):
    if select is None:
        select = {"selected": [], "skipped": []}
    if batch_result is None:
        batch_result = ApplyResult("", "success", "投递成功")

    async def _body(page):
        return body

    async def _select(page, job_ids):
        return select

    async def _apply(page):
        return batch_apply

    async def _dialog(page):
        return batch_result

    async def _next(page, target_page):
        return next_page

    async def _visible(page):
        return None

    monkeypatch.setattr(applier, "_body_text", _body)
    monkeypatch.setattr(applier, "_select_cards", _select)
    monkeypatch.setattr(applier, "_click_batch_apply", _apply)
    monkeypatch.setattr(applier, "_batch_dialog", _dialog)
    monkeypatch.setattr(applier, "_click_next_page", _next)
    monkeypatch.setattr(applier, "_visible_dialog", _visible)


def test_batch_success_with_source_conditions(monkeypatch):
    page = _Page()
    _patch_helpers(monkeypatch, select={"selected": ["j1", "j2"], "skipped": []})
    targets = [_target("j1"), _target("j2")]
    results = _run(apply_job_group(page, targets, "020000", "08,46,47"))
    assert {r.status for r in results.values()} == {"success"}
    # 真实岗位标题 + 源城市 + 源行业
    assert "keyword=%E9%87%87%E8%B4%AD%E5%B7%A5%E7%A8%8B%E5%B8%88" in page.goto_url
    assert "jobArea=020000" in page.goto_url
    assert "industry=08%2C46%2C47" in page.goto_url


def test_batch_no_industry_param_when_none(monkeypatch):
    page = _Page()
    _patch_helpers(monkeypatch, select={"selected": ["j1"], "skipped": []})
    _run(apply_job_group(page, [_target()], "020000", None))
    assert "industry" not in page.goto_url


def test_batch_skipped_when_already_applied(monkeypatch):
    page = _Page()
    _patch_helpers(monkeypatch, select={"selected": ["j1"], "skipped": ["j2"]})
    results = _run(apply_job_group(page, [_target("j1"), _target("j2")], "020000", None))
    assert results["j1"].status == "success"
    assert results["j2"].status == "skipped"


def test_batch_not_found_on_all_pages(monkeypatch):
    page = _Page()
    _patch_helpers(monkeypatch, select={"selected": [], "skipped": []})
    results = _run(apply_job_group(page, [_target()], "020000", None))
    assert results["j1"].status == "failed"
    assert "未找到该职位" in results["j1"].message


def test_batch_apply_button_missing(monkeypatch):
    page = _Page()
    _patch_helpers(monkeypatch, select={"selected": ["j1"], "skipped": []}, batch_apply=False)
    results = _run(apply_job_group(page, [_target()], "020000", None))
    assert results["j1"].status == "failed"
    assert "一键投递按钮" in results["j1"].message


def test_batch_dialog_failed_message(monkeypatch):
    page = _Page()
    _patch_helpers(
        monkeypatch,
        select={"selected": ["j1"], "skipped": []},
        batch_result=ApplyResult("", "failed", "弹窗异常：神秘弹窗"),
    )
    results = _run(apply_job_group(page, [_target()], "020000", None))
    assert results["j1"].status == "failed"
    assert "神秘弹窗" in results["j1"].message


def test_batch_dialog_daily_limit(monkeypatch):
    page = _Page()
    _patch_helpers(
        monkeypatch,
        select={"selected": ["j1"], "skipped": []},
        batch_result=ApplyResult("", "failed", "今日投递已达上限（51job 每日限制）"),
    )
    results = _run(apply_job_group(page, [_target()], "020000", None))
    assert results["j1"].status == "failed"
    assert "上限" in results["j1"].message


def test_batch_captcha(monkeypatch):
    async def _fake_solve(page):
        return False

    monkeypatch.setattr(applier, "solve_aliyun_captcha", _fake_solve)
    page = _Page(cards_ready=False)
    _patch_helpers(monkeypatch, body="请按住滑块")
    results = _run(apply_job_group(page, [_target()], "020000", None))
    assert results["j1"].status == "captcha"  # 内部信号，由 apply_to_jobs 兜底


def test_batch_captcha_manual_solve_then_success(monkeypatch):
    async def _fake_wait(page, timeout=120.0):
        return True

    monkeypatch.setattr(applier, "wait_aliyun_manual", _fake_wait)
    page = _Page(first_wait_fails=True)
    _patch_helpers(monkeypatch, body="请按住滑块", select={"selected": ["j1"], "skipped": []})
    results = _run(apply_job_group(page, [_target()], "020000", None, manual_wait=120.0))
    assert results["j1"].status == "success"


def test_apply_to_job_uses_first_source(monkeypatch):
    page = _Page()
    _patch_helpers(monkeypatch, select={"selected": ["j1"], "skipped": []})
    target = _target(sources=[("020000", "08,46,47"), ("000000", None)])
    result = _run(apply_to_job(page, target))
    assert result.status == "success"
    assert "industry=08%2C46%2C47" in page.goto_url  # 用了第一组源条件（带行业）


def test_apply_to_job_fallback_city(monkeypatch):
    page = _Page()
    _patch_helpers(monkeypatch, select={"selected": ["j1"], "skipped": []})
    result = _run(apply_to_job(page, _target(city="上海")))  # 无源条件 → 城市名兜底
    assert result.status == "success"
    assert "jobArea=020000" in page.goto_url
    assert "industry" not in page.goto_url


def test_goto_error_failed():
    page = _Page(goto_error=RuntimeError("network"))
    results = _run(apply_job_group(page, [_target()], "020000", None))
    assert results["j1"].status == "failed"
    assert "页面打开失败" in results["j1"].message


def test_search_not_loaded(monkeypatch):
    page = _Page(cards_ready=False)
    _patch_helpers(monkeypatch, body="")
    results = _run(apply_job_group(page, [_target()], "020000", None))
    assert results["j1"].status == "failed"
    assert "搜索结果未加载" in results["j1"].message


def test_build_job_url_fallback():
    assert build_job_url(ApplyTarget("j9", "t")) == "https://jobs.51job.com/all/j9.html"
    assert build_job_url(ApplyTarget("j9", "t", "https://x/j9.html")) == "https://x/j9.html"


def test_build_search_url_quotes_title_and_industry():
    url = applier.build_search_url("采购 工程师")
    assert "keyword=%E9%87%87%E8%B4%AD" in url
    assert "sortType=0" in url
    assert "jobArea=000000" in url
    assert "industry" not in url
    url2 = applier.build_search_url("采购", 2, "020000", "08,46,47")
    assert "jobArea=020000" in url2
    assert "industry=08%2C46%2C47" in url2


def test_first_source_prefers_source_then_city():
    assert applier._first_source(_target(city="上海")) == ("020000", None)
    assert applier._first_source(_target(city="北京")) == ("010000", None)
    t = _target(city="上海", sources=[("020000", "08,46,47"), ("000000", None)])
    assert applier._first_source(t) == ("020000", "08,46,47")
    t2 = _target(city="上海", sources=[("000000", None)])
    assert applier._first_source(t2) == ("000000", None)
