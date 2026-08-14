import asyncio
import inspect
from collections.abc import AsyncGenerator
from types import SimpleNamespace

from backend.app.scrapers import playwright as playwright_mod
from backend.app.scrapers.base import PageResult, Scraper
from backend.app.scrapers.playwright import PlaywrightScraper


def test_playwright_scraper_implements_interface():
    assert issubclass(PlaywrightScraper, Scraper)
    sig = inspect.signature(PlaywrightScraper.search)
    assert sig.return_annotation == AsyncGenerator[PageResult, None]
    assert "industry" in sig.parameters


def test_build_search_url_with_industry():
    from backend.app.scrapers.playwright import build_search_url

    url = build_search_url("医疗采购", 2, "020000", "08,46,47")
    assert "keyword=%E5%8C%BB%E7%96%97%E9%87%87%E8%B4%AD" in url
    assert "searchType=2" in url and "pageNum=2" in url and "jobArea=020000" in url
    assert "industry=08%2C46%2C47" in url


def test_build_search_url_without_industry():
    from backend.app.scrapers.playwright import build_search_url

    url = build_search_url("python", 1, "000000", None)
    assert "industry" not in url


def test_scraper_is_async_generator():
    s = PlaywrightScraper(headful=False)
    assert inspect.isasyncgenfunction(s.search)
    assert inspect.iscoroutinefunction(s.close)


class _FakePage:
    def is_closed(self):
        return False

    async def close(self):
        pass


class _FakeContext:
    def __init__(self):
        self.init_scripts = []
        self.storage_state_path = None

    async def add_init_script(self, script):
        pass

    async def new_page(self):
        return _FakePage()

    async def close(self):
        pass

    async def storage_state(self, path=None):
        if path:
            self.storage_state_path = path
        return {}


class _FakeBrowser:
    async def close(self):
        pass

    async def new_context(self, **kwargs):
        return _FakeContext()


class _FakeChromium:
    def __init__(self, launches):
        self._launches = launches

    async def launch(self, **kwargs):
        self._launches.append(kwargs)
        return _FakeBrowser()


class _FakePWStarted:
    def __init__(self, launches):
        self.chromium = _FakeChromium(launches)

    async def stop(self):
        pass


class _FakePW:
    def __init__(self, launches):
        self._launches = launches

    async def start(self):
        return _FakePWStarted(self._launches)


def _seq_fetch(seq):
    async def fetch(page, keyword, n, area="000000", industry=None):
        return next(seq), page

    return fetch


async def _noop_sleep(delay):
    pass


async def _noop_async():
    pass


def _setup(monkeypatch, launches):
    monkeypatch.setattr(playwright_mod, "async_playwright", lambda: _FakePW(launches))
    monkeypatch.setattr(asyncio, "sleep", _noop_sleep)


def test_consecutive_failures_degrade_to_headful(monkeypatch):
    launches = []
    _setup(monkeypatch, launches)
    s = PlaywrightScraper(headful=False)
    monkeypatch.setattr(
        s,
        "_fetch_page",
        _seq_fetch(
            iter(
                [
                    PageResult(page_num=1, jobs=[], failed=True),
                    PageResult(page_num=2, jobs=[], failed=True),
                    PageResult(page_num=2, jobs=[]),   # 有头重试成功
                    PageResult(page_num=3, jobs=[]),
                ]
            )
        ),
    )

    async def run():
        return [r async for r in s.search("python", 3)]

    out = asyncio.run(run())
    assert len(launches) == 2
    assert launches[0]["headless"] is True
    assert launches[1]["headless"] is False
    for launch in launches:
        assert launch["args"] == ["--disable-blink-features=AutomationControlled"]
    assert not out[2].failed


def test_success_resets_failure_counter(monkeypatch):
    launches = []
    _setup(monkeypatch, launches)
    s = PlaywrightScraper(headful=False)
    monkeypatch.setattr(
        s,
        "_fetch_page",
        _seq_fetch(
            iter(
                [
                    PageResult(page_num=1, jobs=[], failed=True),
                    PageResult(page_num=2, jobs=[]),           # 成功，计数清零
                    PageResult(page_num=3, jobs=[], failed=True),
                    PageResult(page_num=4, jobs=[], failed=True),
                    PageResult(page_num=4, jobs=[]),           # 有头重试成功
                ]
            )
        ),
    )

    async def run():
        return [r async for r in s.search("python", 4)]

    out = asyncio.run(run())
    assert len(launches) == 2
    assert launches[0]["headless"] is True
    assert launches[1]["headless"] is False
    assert not out[-1].failed


def test_blocked_page_triggers_immediate_degrade(monkeypatch):
    launches = []
    _setup(monkeypatch, launches)
    s = PlaywrightScraper(headful=False)
    monkeypatch.setattr(
        s,
        "_fetch_page",
        _seq_fetch(
            iter(
                [
                    PageResult(page_num=1, jobs=[], failed=True, blocked=True),
                    PageResult(page_num=1, jobs=[]),   # 有头重试成功
                    PageResult(page_num=2, jobs=[]),
                ]
            )
        ),
    )

    async def run():
        return [r async for r in s.search("python", 2)]

    out = asyncio.run(run())
    assert len(launches) == 2
    assert launches[1]["headless"] is False
    assert not out[0].failed


def test_fetch_page_returns_early_on_blocked(monkeypatch):
    from playwright.async_api import TimeoutError as PWTimeoutError

    pages_created = []

    class _FakePage:
        def is_closed(self):
            return False

        async def goto(self, *a, **k):
            pass

        async def wait_for_selector(self, *a, **k):
            raise PWTimeoutError("timeout")

        async def content(self):
            return "<html><body>安全验证</body></html>"

        async def close(self):
            pass

    class _FakeContext:
        def __init__(self, browser):
            self.browser = browser

        async def add_init_script(self, script):
            self.browser.init_scripts.append(script)

        async def new_page(self):
            pages_created.append(1)
            return _FakePage()

        async def close(self):
            pass

    class _FakeBrowser2:
        def __init__(self):
            self.init_scripts = []

        async def close(self):
            pass

        async def new_context(self, **kwargs):
            self.context_kwargs = kwargs
            return _FakeContext(self)

    class _FakeChromium2:
        async def launch(self, **kwargs):
            return _FakeBrowser2()

    class _FakePW2:
        async def start(self):
            return SimpleNamespace(chromium=_FakeChromium2())

        async def stop(self):
            pass

    monkeypatch.setattr(playwright_mod, "async_playwright", lambda: _FakePW2())
    s = PlaywrightScraper(headful=False)

    async def run():
        await s._ensure_browser()
        page = await s._new_page()
        return await s._fetch_page(page, "python", 1)

    result, page = asyncio.run(run())
    assert result.failed
    assert result.blocked
    assert len(pages_created) == 1   # blocked 页只尝试一次，不做无头重试
    assert s._browser.context_kwargs["locale"] == "zh-CN"
    assert s._browser.context_kwargs["timezone_id"] == "Asia/Shanghai"
    assert "accept_language" not in s._browser.context_kwargs
    assert len(s._browser.init_scripts) == 1
    assert "webdriver" in s._browser.init_scripts[0]


def test_fetch_page_solves_captcha_then_returns_list(monkeypatch):
    from playwright.async_api import TimeoutError as PWTimeoutError

    class _StatePage:
        def __init__(self):
            self.times = 0

        def is_closed(self):
            return False

        async def goto(self, *a, **k):
            pass

        async def wait_for_selector(self, *a, **k):
            self.times += 1
            if self.times == 1:
                raise PWTimeoutError("timeout")
            return True

        async def content(self):
            if self.times == 1:
                return '<html><body><div id="aliyunCaptcha-window-embed" class="aliyunCaptcha-show">请按住滑块</div></body></html>'
            return (
                "<html><body><div class='joblist-item'>"
                "<div class='joblist-item-job' "
                'sensorsdata=\'{"jobId":"123","jobTitle":"测试","jobSalary":"8千-1.2万","jobArea":"上海","companyId":"456"}\'>'
                "</div></div></body></html>"
            )

        async def close(self):
            pass

    pages = []

    class _Ctx:
        def __init__(self, browser):
            self.browser = browser

        async def add_init_script(self, script):
            pass

        async def new_page(self):
            p = _StatePage()
            pages.append(p)
            return p

        async def close(self):
            pass

    class _Br:
        async def close(self):
            pass

        async def new_context(self, **kwargs):
            return _Ctx(self)

    class _Ch:
        async def launch(self, **kwargs):
            return _Br()

    class _Pw:
        async def start(self):
            return SimpleNamespace(chromium=_Ch())

        async def stop(self):
            pass

    solved = []

    async def _fake_solve(page):
        solved.append(page)
        return True

    monkeypatch.setattr(playwright_mod, "async_playwright", lambda: _Pw())
    monkeypatch.setattr(playwright_mod, "solve_aliyun_captcha", _fake_solve)
    s = PlaywrightScraper(headful=False)

    async def run():
        await s._ensure_browser()
        page = await s._new_page()
        return await s._fetch_page(page, "python", 1)

    result, page = asyncio.run(run())
    assert not result.failed
    assert len(result.jobs) == 1
    assert len(solved) == 1


def test_search_captcha_page_cooldowns_then_retries(monkeypatch):
    sleeps = []

    async def _recording_sleep(delay):
        sleeps.append(delay)

    launches = []
    _setup(monkeypatch, launches)
    monkeypatch.setattr(asyncio, "sleep", _recording_sleep)
    s = PlaywrightScraper(headful=False)
    monkeypatch.setattr(
        s,
        "_fetch_page",
        _seq_fetch(
            iter(
                [
                    PageResult(page_num=1, jobs=[], failed=True, captcha=True),
                    PageResult(page_num=1, jobs=[], failed=True, captcha=True),  # 冷却后重试仍验证码
                    PageResult(page_num=2, jobs=[]),
                ]
            )
        ),
    )

    async def run():
        return [r async for r in s.search("python", 2)]

    out = asyncio.run(run())
    assert sleeps[0] == 90                       # 冷却 90s 先于一切
    assert all(3.0 <= s <= 8.0 for s in sleeps[1:])  # 页间延时 3-8s
    assert out[0].failed and not out[1].failed
    assert len(launches) == 1  # 未触发 headful 降级


def test_search_captcha_solved_after_cooldown_continues(monkeypatch):
    sleeps = []

    async def _recording_sleep(delay):
        sleeps.append(delay)

    launches = []
    _setup(monkeypatch, launches)
    monkeypatch.setattr(asyncio, "sleep", _recording_sleep)
    s = PlaywrightScraper(headful=False)
    monkeypatch.setattr(
        s,
        "_fetch_page",
        _seq_fetch(
            iter(
                [
                    PageResult(page_num=1, jobs=[], failed=True, captcha=True),
                    PageResult(page_num=1, jobs=[]),   # 冷却后重试成功
                    PageResult(page_num=2, jobs=[]),
                ]
            )
        ),
    )

    async def run():
        return [r async for r in s.search("python", 2)]

    out = asyncio.run(run())
    assert sleeps[0] == 90
    assert not out[0].failed and not out[1].failed
    assert len(launches) == 1


def test_search_aborts_after_three_consecutive_captcha_pages(monkeypatch):
    sleeps = []

    async def _recording_sleep(delay):
        sleeps.append(delay)

    launches = []
    _setup(monkeypatch, launches)
    monkeypatch.setattr(asyncio, "sleep", _recording_sleep)
    s = PlaywrightScraper(headful=False)
    fetched = []

    def _counting_fetch(seq):
        async def fetch(page, keyword, n, area="000000", industry=None):
            fetched.append(n)
            return next(seq), page

        return fetch

    monkeypatch.setattr(
        s,
        "_fetch_page",
        _counting_fetch(
            iter(
                [
                    PageResult(page_num=1, jobs=[], failed=True, captcha=True),
                    PageResult(page_num=1, jobs=[], failed=True, captcha=True),
                    PageResult(page_num=2, jobs=[], failed=True, captcha=True),
                    PageResult(page_num=2, jobs=[], failed=True, captcha=True),
                    PageResult(page_num=3, jobs=[], failed=True, captcha=True),
                    PageResult(page_num=3, jobs=[], failed=True, captcha=True),
                ]
            )
        ),
    )

    async def run():
        return [r async for r in s.search("python", 5)]

    out = asyncio.run(run())
    assert sleeps[0] == sleeps[2] == sleeps[4] == 90   # 每页冷却 90s，连续 3 页
    assert len(sleeps) == 5                            # 第 3 页冷却后直接放弃，无页间延时
    assert [r.page_num for r in out] == [1, 2]         # 第 3 页结果不产出，任务提前结束
    assert len(fetched) == 6                           # 无第 4 页抓取（seq 恰好耗尽）
    assert len(launches) == 1                          # 未触发 headful 降级


def test_search_calls_login_before_fetch(monkeypatch):
    from backend.app.scrapers.base import LoginCredential

    launches = []
    _setup(monkeypatch, launches)
    login_calls = []

    async def _fake_login(page, site, username, password):
        login_calls.append((site, username, password))
        return True

    monkeypatch.setattr(playwright_mod, "login", _fake_login)
    monkeypatch.setattr(playwright_mod, "storage_state_valid", lambda p: False)
    s = PlaywrightScraper(headful=False, login_credential=LoginCredential("51job", "13800000000", "pw123"))
    monkeypatch.setattr(
        s,
        "_fetch_page",
        _seq_fetch(iter([PageResult(page_num=1, jobs=[]), PageResult(page_num=2, jobs=[])])),
    )

    async def run():
        return [r async for r in s.search("python", 2)]

    out = asyncio.run(run())
    assert login_calls == [("51job", "13800000000", "pw123")]
    assert len(out) == 2


def test_search_login_failure_falls_back_anonymous(monkeypatch):
    from backend.app.scrapers.base import LoginCredential

    launches = []
    _setup(monkeypatch, launches)

    async def _fake_login(page, site, username, password):
        return False

    monkeypatch.setattr(playwright_mod, "login", _fake_login)
    monkeypatch.setattr(playwright_mod, "storage_state_valid", lambda p: False)
    s = PlaywrightScraper(headful=False, login_credential=LoginCredential("51job", "u", "w"))
    monkeypatch.setattr(
        s,
        "_fetch_page",
        _seq_fetch(iter([PageResult(page_num=1, jobs=[]), PageResult(page_num=2, jobs=[])])),
    )

    async def run():
        return [r async for r in s.search("python", 2)]

    out = asyncio.run(run())
    assert len(out) == 2  # 登录失败不中断抓取
    assert not out[0].failed


def test_search_reuses_saved_login_state(monkeypatch):
    """登录状态文件有效时跳过登录，直接复用已加载的会话。"""
    from backend.app.scrapers.base import LoginCredential

    launches = []
    _setup(monkeypatch, launches)
    login_calls = []

    async def _fake_login(page, site, username, password):
        login_calls.append((site, username, password))
        return True

    monkeypatch.setattr(playwright_mod, "login", _fake_login)
    monkeypatch.setattr(playwright_mod, "storage_state_valid", lambda p: True)
    s = PlaywrightScraper(headful=False, login_credential=LoginCredential("51job", "13800000000", "pw123"))
    monkeypatch.setattr(
        s,
        "_fetch_page",
        _seq_fetch(iter([PageResult(page_num=1, jobs=[]), PageResult(page_num=2, jobs=[])])),
    )

    async def run():
        return [r async for r in s.search("python", 2)]

    out = asyncio.run(run())
    assert login_calls == []  # 未走登录流程
    assert len(out) == 2


class _ApplyFakePage:
    def is_closed(self):
        return False

    async def close(self):
        pass


def _setup_apply_scraper(monkeypatch, s, group_seq, degrade_result=False):
    async def _ensure_browser():
        pass

    async def _new_page():
        return _ApplyFakePage()

    async def _ensure_logged_in(page):
        return page, True

    async def _degrade():
        if degrade_result:
            s._headful = True
        return degrade_result

    async def _fake_apply_group(page, group, area="000000", industry=None, manual_wait=0.0):
        return next(group_seq)

    monkeypatch.setattr(s, "_ensure_browser", _ensure_browser)
    monkeypatch.setattr(s, "_new_page", _new_page)
    monkeypatch.setattr(s, "_ensure_logged_in", _ensure_logged_in)
    monkeypatch.setattr(s, "_degrade_to_headful", _degrade)
    monkeypatch.setattr(playwright_mod, "apply_job_group", _fake_apply_group)


def test_apply_to_jobs_captcha_cooldown_then_retry(monkeypatch):
    from backend.app.scrapers.applier import ApplyResult, ApplyTarget

    sleeps = []

    async def _recording_sleep(delay):
        sleeps.append(delay)

    monkeypatch.setattr(asyncio, "sleep", _recording_sleep)
    s = PlaywrightScraper(headful=False)
    _setup_apply_scraper(
        monkeypatch,
        s,
        iter([
            {"j1": ApplyResult("j1", "captcha", "验证码未通过")},
            {"j1": ApplyResult("j1", "success", "投递成功")},
        ]),
    )

    async def run():
        return [r async for r in s.apply_to_jobs([ApplyTarget("j1", "t")])]

    out = asyncio.run(run())
    assert [r.status for r in out] == ["success"]
    assert sleeps == [90]  # 冷却 90s 先于一切，单组无组间延时


def test_apply_to_jobs_captcha_degrades_headful(monkeypatch):
    from backend.app.scrapers.applier import ApplyResult, ApplyTarget

    monkeypatch.setattr(asyncio, "sleep", _noop_sleep)
    s = PlaywrightScraper(headful=False)
    _setup_apply_scraper(
        monkeypatch,
        s,
        iter([
            {"j1": ApplyResult("j1", "captcha", "验证码未通过")},
            {"j1": ApplyResult("j1", "captcha", "验证码未通过")},
            {"j1": ApplyResult("j1", "success", "投递成功")},
        ]),
        degrade_result=True,
    )

    async def run():
        return [r async for r in s.apply_to_jobs([ApplyTarget("j1", "t")])]

    out = asyncio.run(run())
    assert [r.status for r in out] == ["success"]
    assert s._headful is True  # 已降级有头


def test_apply_to_jobs_captcha_gives_up(monkeypatch):
    from backend.app.scrapers.applier import ApplyResult, ApplyTarget

    monkeypatch.setattr(asyncio, "sleep", _noop_sleep)
    s = PlaywrightScraper(headful=False)
    _setup_apply_scraper(
        monkeypatch,
        s,
        iter([
            {"j1": ApplyResult("j1", "captcha", "验证码未通过")},
            {"j1": ApplyResult("j1", "captcha", "验证码未通过")},
        ]),
        degrade_result=False,  # 已是 headless 且降级失败
    )

    async def run():
        return [r async for r in s.apply_to_jobs([ApplyTarget("j1", "t")])]

    out = asyncio.run(run())
    assert out[0].status == "failed"
    assert "验证码" in out[0].message


def test_expand_and_group_search_units():
    from backend.app.scrapers.applier import ApplyTarget

    targets = [
        ApplyTarget("j1", "采购专员", city="上海", sources=[("020000", "08,46,47"), ("000000", None)]),
        ApplyTarget("j2", "采购专员", city="上海", sources=[("020000", "08,46,47")]),
        ApplyTarget("j3", "办公室行政专员", city="上海", sources=[]),  # 无源 → 城市兜底
    ]
    units = playwright_mod._expand_search_units(targets)
    assert len(units) == 4  # j1 两条件 → 2 单元，j2 1 单元，j3 兜底 1 单元
    groups = playwright_mod._group_search_units(units)
    keys = sorted((g[0]["title"], g[0]["city"], g[0]["industry"]) for g in groups)
    assert keys == [
        ("办公室行政专员", "020000", None),
        ("采购专员", "000000", None),
        ("采购专员", "020000", "08,46,47"),
    ]
    # 同组内：j1/j2 同标题同条件归一组
    group_020000 = [g for g in groups if g[0]["city"] == "020000" and g[0]["industry"] == "08,46,47"][0]
    assert {u["target"].job_id for u in group_020000} == {"j1", "j2"}


def test_apply_to_jobs_tries_next_source_after_failed(monkeypatch):
    """同一职位两组源条件：第一组未找到(failed)，第二组投成(success) → 最终 success 且只投一次。"""
    from backend.app.scrapers.applier import ApplyResult, ApplyTarget

    monkeypatch.setattr(asyncio, "sleep", _noop_sleep)
    s = PlaywrightScraper(headful=False)

    async def _fake_apply_group(page, group, area="000000", industry=None, manual_wait=0.0):
        if industry == "08,46,47":
            return {"j1": ApplyResult("j1", "failed", "未找到该职位")}
        return {"j1": ApplyResult("j1", "success", "投递成功")}

    monkeypatch.setattr(playwright_mod, "apply_job_group", _fake_apply_group)
    monkeypatch.setattr(s, "_ensure_browser", _noop_async)

    async def _new_page():
        return _ApplyFakePage()

    monkeypatch.setattr(s, "_new_page", _new_page)

    async def _ensure_logged_in(page):
        return page, True

    monkeypatch.setattr(s, "_ensure_logged_in", _ensure_logged_in)
    monkeypatch.setattr(s, "_degrade_to_headful", lambda: False)

    async def run():
        return [r async for r in s.apply_to_jobs(
            [ApplyTarget("j1", "采购专员", city="上海", sources=[("020000", "08,46,47"), ("020000", None)])]
        )]

    out = asyncio.run(run())
    assert [r.status for r in out] == ["success"]  # 第二组条件投成，覆盖第一组 failed


def test_ensure_browser_uses_system_chrome(monkeypatch):
    launches = []
    monkeypatch.setattr(playwright_mod, "async_playwright", lambda: _FakePW(launches))
    s = PlaywrightScraper(headful=False, use_system_chrome=True)
    asyncio.run(s._ensure_browser())
    assert launches[0]["channel"] == "chrome"
    assert launches[0]["headless"] is True


def test_ensure_browser_falls_back_when_chrome_missing(monkeypatch):
    launches = []

    class _Chromium:
        async def launch(self, **kwargs):
            launches.append(kwargs)
            if kwargs.get("channel") == "chrome":
                raise RuntimeError("Executable doesn't exist")
            return _FakeBrowser()

    class _PW:
        async def start(self):
            return SimpleNamespace(chromium=_Chromium())

        async def stop(self):
            pass

    monkeypatch.setattr(playwright_mod, "async_playwright", lambda: _PW())
    s = PlaywrightScraper(headful=False, use_system_chrome=True)
    asyncio.run(s._ensure_browser())
    assert launches[0]["channel"] == "chrome"
    assert "channel" not in launches[1]  # 回退内置 Chromium
    assert s._browser is not None

