import asyncio

from backend.app.scrapers import auth
from backend.app.scrapers.auth import login


class _FakeLocator:
    def __init__(self):
        self.filled = None
        self.first = self

    async def fill(self, value):
        self.filled = value

    async def click(self, timeout=None):
        pass

    async def count(self):
        return 0  # 滑块/嵌入容器均不存在 → solve_aliyun_captcha 视为已通过

    async def wait_for(self, state=None, timeout=None):
        pass


class _FakePage:
    def __init__(self, url_after="https://we.51job.com/pc/index"):
        self._url = url_after
        self.locators = {}
        self.loginway_clicked = False
        self.agree_clicked = False

    def locator(self, sel, **kw):
        if sel not in self.locators:
            loc = _FakeLocator()
            if kw.get("has_text") == "密码登录":
                self.loginway_clicked = True
            if kw.get("has_text") == "我已阅读并同意":
                self.agree_clicked = True
            self.locators[sel] = loc
        return self.locators[sel]

    async def goto(self, url, **kw):
        self.goto_url = url

    async def wait_for_timeout(self, ms):
        pass

    @property
    def url(self):
        return self._url


def _run(coro):
    return asyncio.run(coro)


def test_login_success_fills_credentials():
    page = _FakePage(url_after="https://we.51job.com/pc/index")
    assert _run(login(page, "51job", "13800000000", "pw123")) is True
    assert page.goto_url == "https://login.51job.com/login.php?lang=c"
    assert page.locators["#loginname"].filled == "13800000000"
    assert page.locators["#password"].filled == "pw123"
    assert page.loginway_clicked is True  # 默认短信模式，已点击「密码登录」tab
    assert page.agree_clicked is True  # 已点击协议同意（隐藏 checkbox 的 label）


def test_login_failure_stays_on_login_page():
    page = _FakePage(url_after="https://login.51job.com/login.php")
    assert _run(login(page, "51job", "u", "w")) is False


def test_login_unsupported_site():
    page = _FakePage()
    assert _run(login(page, "zhilian", "u", "w")) is False
    assert not hasattr(page, "goto_url")  # 未访问页面


def test_login_exception_returns_false(monkeypatch):
    page = _FakePage()

    async def _boom(*a, **k):
        raise RuntimeError("network")

    monkeypatch.setattr(page, "goto", _boom)
    assert _run(login(page, "51job", "u", "w")) is False


def test_run_test_login_delegates_to_login(monkeypatch):
    from backend.app.scrapers import playwright as pw_mod

    calls = []

    async def _fake_login(page, site, username, password):
        calls.append((site, username, password))
        return True

    class _FakeScraper:
        def __init__(self, headful=False):
            self.headful = headful

        async def _ensure_browser(self):
            pass

        async def _new_page(self):
            return object()

        async def close(self):
            pass

    monkeypatch.setattr(pw_mod, "login", _fake_login)
    monkeypatch.setattr(pw_mod, "PlaywrightScraper", lambda headful=False: _FakeScraper(headful))
    ok, msg = _run(pw_mod.run_test_login("51job", "13800000000", "pw", headful=True))
    assert ok is True
    assert calls == [("51job", "13800000000", "pw")]
    assert "成功" in msg


def test_run_test_login_failure_message(monkeypatch):
    from backend.app.scrapers import playwright as pw_mod

    async def _fake_login(page, site, username, password):
        return False

    class _FakeScraper:
        def __init__(self, headful=False):
            pass

        async def _ensure_browser(self):
            pass

        async def _new_page(self):
            return object()

        async def close(self):
            pass

    monkeypatch.setattr(pw_mod, "login", _fake_login)
    monkeypatch.setattr(pw_mod, "PlaywrightScraper", lambda headful=False: _FakeScraper())
    ok, msg = _run(pw_mod.run_test_login("51job", "u", "w"))
    assert ok is False
    assert "失败" in msg
