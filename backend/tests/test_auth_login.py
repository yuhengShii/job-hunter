import asyncio

from backend.app.scrapers import auth
from backend.app.scrapers.auth import login


class _FakeLocator:
    def __init__(self, count_result=0):
        self.filled = None
        self.first = self
        self._count = count_result

    async def fill(self, value):
        self.filled = value

    async def click(self, timeout=None):
        pass

    async def count(self):
        return self._count

    async def wait_for(self, state=None, timeout=None):
        pass


class _FakePage:
    def __init__(self, url_after="https://we.51job.com/pc/index", geetest=False, evaluate_result=True):
        self._url = url_after
        self.geetest = geetest
        self.evaluate_result = evaluate_result
        self.locators = {}
        self.loginway_clicked = False
        self.agree_clicked = False

    def locator(self, sel, **kw):
        if sel not in self.locators:
            count = 1 if (self.geetest and sel in (".geetest_panel", ".geetest_holder")) else 0
            loc = _FakeLocator(count_result=count)
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

    async def evaluate(self, js):
        return self.evaluate_result

    def is_closed(self):
        return False

    async def screenshot(self, **kw):
        return None

    @property
    def url(self):
        return self._url


def _run(coro):
    return asyncio.run(coro)


def test_login_success_fills_credentials():
    page = _FakePage(url_after="https://we.51job.com/pc/index")
    assert _run(login(page, "51job", "13800000000", "pw123")) == (True, "")
    assert page.goto_url == "https://login.51job.com/login.php?lang=c"
    assert page.locators["#loginname"].filled == "13800000000"
    assert page.locators["#password"].filled == "pw123"
    assert page.loginway_clicked is True  # 默认短信模式，已点击「密码登录」tab
    assert page.agree_clicked is True  # 已点击协议同意（隐藏 checkbox 的 label）


def test_login_failure_stays_on_login_page():
    page = _FakePage(url_after="https://login.51job.com/login.php")
    ok, reason = _run(login(page, "51job", "u", "w"))
    assert ok is False
    assert reason  # 返回失败原因


def test_login_unsupported_site():
    page = _FakePage()
    ok, reason = _run(login(page, "zhilian", "u", "w"))
    assert ok is False
    assert not hasattr(page, "goto_url")  # 未访问页面


def test_login_exception_returns_false(monkeypatch):
    page = _FakePage()

    async def _boom(*a, **k):
        raise RuntimeError("network")

    monkeypatch.setattr(page, "goto", _boom)
    ok, reason = _run(login(page, "51job", "u", "w"))
    assert ok is False
    assert "登录异常" in reason


def test_login_geetest_manual_wait():
    """manual_wait>0 且极验面板存在时，等待人工验证；URL 仍在登录页则判定失败并返回 geetest 原因。"""
    page = _FakePage(url_after="https://login.51job.com/login.php", geetest=True)
    ok, reason = _run(login(page, "51job", "u", "w", manual_wait=30))
    assert ok is False
    assert reason == "geetest"  # 上层据此切换有头模式


def test_captcha_detect_and_wait_geetest(monkeypatch):
    from backend.app.scrapers import captcha as cap_mod

    class _FakeLocator:
        def __init__(self, n):
            self._n = n

        async def count(self):
            return self._n

    class _FakePage:
        def __init__(self, present, evaluate_result):
            self.present = present
            self.evaluate_result = evaluate_result
            self.eval_count = 0

        def locator(self, sel):
            return _FakeLocator(1 if self.present else 0)

        async def evaluate(self, js):
            self.eval_count += 1
            return self.evaluate_result

        def is_closed(self):
            return False

        async def screenshot(self, **kw):
            return None

    assert _run(cap_mod.detect_geetest(_FakePage(True, True))) is True
    assert _run(cap_mod.detect_geetest(_FakePage(False, True))) is False
    # 人工等待：evaluate 立即返回成功
    assert _run(cap_mod.wait_geetest_manual(_FakePage(True, True), timeout=10)) is True
    # 人工等待：一直未完成 → 超时返回 False
    page = _FakePage(True, False)
    assert _run(cap_mod.wait_geetest_manual(page, timeout=0.1, poll_interval=0.05)) is False
    assert page.eval_count > 1


def test_run_test_login_delegates_to_login(monkeypatch):
    from backend.app.scrapers import playwright as pw_mod

    calls = []

    async def _fake_login(page, site, username, password, manual_wait=0.0):
        calls.append((site, username, password, manual_wait))
        return True, ""

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
    assert calls == [("51job", "13800000000", "pw", 0.0)]
    assert "成功" in msg


def test_run_test_login_failure_message(monkeypatch):
    from backend.app.scrapers import playwright as pw_mod

    async def _fake_login(page, site, username, password, manual_wait=0.0):
        return False, "账号或密码错误"

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


def test_run_test_login_geetest_switches_headful(monkeypatch):
    """极验拦截时 test-login 重启为有头模式并带 manual_wait 重试登录。"""
    from backend.app.scrapers import playwright as pw_mod

    calls = []

    async def _fake_login(page, site, username, password, manual_wait=0.0):
        calls.append((site, username, password, manual_wait))
        if len(calls) == 1:
            return False, "geetest"  # 首次 headless 被极验拦截
        return True, ""

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
    ok, msg = _run(pw_mod.run_test_login("51job", "13800000000", "pw"))
    assert ok is True
    assert "成功" in msg
    assert calls == [("51job", "13800000000", "pw", 0.0), ("51job", "13800000000", "pw", 120.0)]
