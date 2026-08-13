import asyncio

from backend.app.scrapers import applier
from backend.app.scrapers.applier import ApplyTarget, apply_to_job, build_job_url


class _Loc:
    def __init__(self, fail=False):
        self.first = self
        self.fail = fail

    async def click(self, timeout=None):
        if self.fail:
            raise RuntimeError("no button")


class _Page:
    def __init__(self, cards_ready=True, first_wait_fails=False, goto_error=None, loc_fail=False):
        self.cards_ready = cards_ready
        self.first_wait_fails = first_wait_fails
        self.goto_error = goto_error
        self.loc_fail = loc_fail
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
        return _Loc(fail=self.loc_fail)


def _run(coro):
    return asyncio.run(coro)


def _target():
    return ApplyTarget(job_id="123", title="采购工程师", city="上海")


def _patch_helpers(
    monkeypatch,
    *,
    body="",
    card_index=0,
    card_text="",
    dialogs=None,
    click_btn="立即申请",
    resume=True,
    close=True,
    apply_click=True,
):
    dialog_iter = iter(dialogs) if isinstance(dialogs, list) else None

    async def _body(page):
        return body

    async def _find(page, job_id):
        return card_index

    async def _card_t(page, job_id):
        return card_text

    async def _dialog(page):
        if dialog_iter is None:
            return dialogs
        return next(dialog_iter, None)

    async def _click(page, texts):
        return click_btn

    async def _resume(page):
        return resume

    async def _close_d(page):
        return close

    async def _apply(page, index):
        return apply_click

    monkeypatch.setattr(applier, "_body_text", _body)
    monkeypatch.setattr(applier, "_find_card_index", _find)
    monkeypatch.setattr(applier, "_card_text", _card_t)
    monkeypatch.setattr(applier, "_visible_dialog", _dialog)
    monkeypatch.setattr(applier, "_click_dialog_button", _click)
    monkeypatch.setattr(applier, "_click_resume_item", _resume)
    monkeypatch.setattr(applier, "_close_dialog", _close_d)
    monkeypatch.setattr(applier, "_click_card_apply", _apply)


def test_apply_success(monkeypatch):
    page = _Page()
    _patch_helpers(
        monkeypatch,
        dialogs=[
            {"text": "请选择需要投递的简历 立即申请", "buttons": [{"text": "立即申请"}]},
            {"text": "投递成功", "buttons": []},
        ],
    )
    result = _run(apply_to_job(page, _target()))
    assert result.status == "success"
    assert page.goto_url.startswith("https://we.51job.com/pc/search?keyword=")
    assert "jobArea=020000" in page.goto_url  # 目标城市上海 → 城市编码收窄搜索


def test_paginates_to_find_job(monkeypatch):
    page = _Page()
    state = {"page": 1, "next_calls": 0}
    _patch_helpers(monkeypatch, dialogs=[{"text": "投递成功", "buttons": []}])

    async def _find(page, job_id):
        return 0 if state["page"] >= 2 else -1

    async def _next(page, target_page):
        state["next_calls"] += 1
        state["page"] = target_page
        return True

    monkeypatch.setattr(applier, "_find_card_index", _find)
    monkeypatch.setattr(applier, "_click_next_page", _next)
    result = _run(apply_to_job(page, _target()))
    assert result.status == "success"
    assert state["next_calls"] == 1


def test_not_found_after_all_pages(monkeypatch):
    page = _Page()
    _patch_helpers(monkeypatch, card_text="")

    async def _find(page, job_id):
        return -1

    async def _next(page, target_page):
        return True

    monkeypatch.setattr(applier, "_find_card_index", _find)
    monkeypatch.setattr(applier, "_click_next_page", _next)
    result = _run(apply_to_job(page, _target()))
    assert result.status == "failed"
    assert "未找到该职位" in result.message


def test_search_keyword_strips_suffix():
    assert applier._search_keyword("项目运作实习生 （上海）") == "项目运作实习生"
    assert applier._search_keyword("采购工程师--供应商开发") == "采购工程师"
    assert applier._search_keyword("市场专员") == "市场专员"


def test_apply_skipped_when_already_applied(monkeypatch):
    page = _Page()
    _patch_helpers(monkeypatch, card_text="采购工程师 已投递 3M公司")
    result = _run(apply_to_job(page, _target()))
    assert result.status == "skipped"


def test_card_not_found(monkeypatch):
    page = _Page()
    _patch_helpers(monkeypatch, card_index=-1)
    result = _run(apply_to_job(page, _target()))
    assert result.status == "failed"
    assert "未找到该职位" in result.message


def test_no_apply_button(monkeypatch):
    page = _Page()
    _patch_helpers(monkeypatch, apply_click=False)
    result = _run(apply_to_job(page, _target()))
    assert result.status == "failed"
    assert "投递按钮" in result.message


def test_search_captcha_failed(monkeypatch):
    async def _fake_solve(page):
        return False

    monkeypatch.setattr(applier, "solve_aliyun_captcha", _fake_solve)
    page = _Page(cards_ready=False)
    _patch_helpers(monkeypatch, body="请按住滑块")
    result = _run(apply_to_job(page, _target()))
    assert result.status == "captcha"  # 内部信号，由 apply_to_jobs 兜底


def test_search_captcha_manual_solve_then_success(monkeypatch):
    async def _fake_wait(page, timeout=120.0):
        return True

    monkeypatch.setattr(applier, "wait_aliyun_manual", _fake_wait)
    page = _Page(first_wait_fails=True)
    _patch_helpers(
        monkeypatch,
        body="请按住滑块",
        dialogs=[
            {"text": "请选择需要投递的简历 立即申请", "buttons": [{"text": "立即申请"}]},
            {"text": "投递成功", "buttons": []},
        ],
    )
    result = _run(apply_to_job(page, _target(), manual_wait=120.0))
    assert result.status == "success"


def test_search_not_loaded(monkeypatch):
    page = _Page(cards_ready=False)
    _patch_helpers(monkeypatch, body="")
    result = _run(apply_to_job(page, _target()))
    assert result.status == "failed"
    assert "搜索结果未加载" in result.message


def test_goto_error_failed():
    page = _Page(goto_error=RuntimeError("network"))
    result = _run(apply_to_job(page, _target()))
    assert result.status == "failed"
    assert "页面打开失败" in result.message


def test_hint_dialog_closed_then_success(monkeypatch):
    page = _Page()
    _patch_helpers(
        monkeypatch,
        dialogs=[
            {"text": "该简历的工作经验不完整，建议完善后再投递", "buttons": [{"text": "去完善"}]},
            {"text": "请选择需要投递的简历 立即申请", "buttons": [{"text": "立即申请"}]},
            {"text": "投递成功", "buttons": []},
        ],
    )
    result = _run(apply_to_job(page, _target()))
    assert result.status == "success"


def test_resume_dialog_missing_apply_button(monkeypatch):
    page = _Page()
    _patch_helpers(
        monkeypatch,
        click_btn=None,
        dialogs=[{"text": "请选择需要投递的简历", "buttons": []}],
    )
    result = _run(apply_to_job(page, _target()))
    assert result.status == "failed"
    assert "申请按钮" in result.message


def test_unknown_dialog_reports_text(monkeypatch):
    page = _Page()
    _patch_helpers(monkeypatch, dialogs=[{"text": "神秘弹窗内容", "buttons": []}])
    result = _run(apply_to_job(page, _target()))
    assert result.status == "failed"
    assert "神秘弹窗内容" in result.message


def test_no_dialog_but_card_shows_applied(monkeypatch):
    page = _Page()
    state = {"clicked": False}
    _patch_helpers(monkeypatch, dialogs=None, card_text="")

    async def _apply(page, index):
        state["clicked"] = True
        return True

    async def _card_t(page, job_id):
        # 点击投递前卡片无「已投递」，点击后出现
        return "采购工程师 已投递" if state["clicked"] else ""

    monkeypatch.setattr(applier, "_click_card_apply", _apply)
    monkeypatch.setattr(applier, "_card_text", _card_t)
    result = _run(apply_to_job(page, _target()))
    assert result.status == "success"


def test_build_job_url_fallback():
    assert build_job_url(ApplyTarget("j9", "t")) == "https://jobs.51job.com/all/j9.html"
    assert build_job_url(ApplyTarget("j9", "t", "https://x/j9.html")) == "https://x/j9.html"


def test_build_search_url_quotes_title():
    url = applier.build_search_url("采购 工程师")
    assert "keyword=%E9%87%87%E8%B4%AD" in url
    assert "pageNum=1" in url
    assert "jobArea=000000" in url
    assert "jobArea=020000" in applier.build_search_url("采购", 2, "020000")
