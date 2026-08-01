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
    assert s._browser.context_kwargs["accept_language"] == "zh-CN,zh;q=0.9"
    assert len(s._browser.init_scripts) == 1
    assert "webdriver" in s._browser.init_scripts[0]
