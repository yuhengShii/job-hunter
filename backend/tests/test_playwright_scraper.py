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


def test_scraper_is_async_generator():
    s = PlaywrightScraper(headful=False)
    assert inspect.isasyncgenfunction(s.search)
    assert inspect.iscoroutinefunction(s.fetch_company)
    assert inspect.iscoroutinefunction(s.close)


class _FakeBrowser:
    async def close(self):
        pass


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
    async def fetch(keyword, n):
        return next(seq)

    return fetch


async def _noop_sleep(delay):
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
        return await s._fetch_page("python", 1)

    result = asyncio.run(run())
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
        return await s._fetch_page("python", 1)

    result = asyncio.run(run())
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
        async def fetch(keyword, n):
            fetched.append(n)
            return next(seq)

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
