# 抓取器反爬降级 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 降低 51job 无头抓取被反爬拦截概率；拦截时自动降级有头模式重试当前页。

**Architecture:** 两个独立任务：(1) 解析层 `PageResult.blocked` 拦截标记（WAF 标记 → `failed=True, blocked=True`）；(2) 抓取层反指纹（launch args + 上下文指纹 + init script）+ 自动降级（WAF 标记立即触发、连续 2 页失败触发、已是有头则 no-op、降级后重试当前页一次）。任务层（task_runner）零改动。

**Tech Stack:** Python 3.14、Playwright async API、pytest（无 pytest-asyncio，异步测试用 `asyncio.run` 包同步测试函数）。

**Spec:** `docs/superpowers/specs/2026-08-02-scraper-antibot-degrade-design.md`

## Global Constraints

- 测试禁止访问真实 51job；scraper 测试 mock `async_playwright`，不启动真实浏览器。
- 降级语义：`_degrade_to_headful()` 在已是 headful 时返回 False（no-op），否则 close 重启浏览器为有头并返回 True；本次任务后续页面保持有头。
- 触发规则（已确认）：(a) `blocked=True` 页面 → 立即降级（跳过无头重试等待）；(b) 无标记连续 2 页失败 → 降级；(c) 成功页重置连续失败计数。
- `search()`/`fetch_company`/`close` 签名不变；`PageResult` 新增字段必须带默认值（dataclass 字段顺序：`blocked` 加在最后）。
- 现有 46 个测试必须保持全绿；提交信息遵循仓库风格。
- 工作分支：`feat/antibot-degrade`（自 main 创建），完成后走 PR。
- 测试命令：`uv run pytest backend/tests/test_parser.py -v` / `uv run pytest backend/tests/test_playwright_scraper.py -v`，全套 `uv run pytest backend/tests -q`。

---

### Task 1: 拦截检测（PageResult.blocked）

**Files:**
- Modify: `backend/app/scrapers/base.py:34-40`
- Modify: `backend/app/scrapers/parser.py:86-88`
- Modify: `backend/tests/test_parser.py:48-52`

**Interfaces:**
- Consumes: 现有 `PageResult(page_num, jobs, companies, total_pages, failed)` dataclass
- Produces: `PageResult.blocked: bool = False`（命中 WAF 标记时 `failed=True, blocked=True`）——Task 2 的 `search()`/`_fetch_page()` 依据此字段降级

> 注：spec 原拟新增 fixture 文件 `51job_waf.html`，计划改为扩展现有 `test_waf_page_marks_failed`（test_parser.py:48-52 已是内联 HTML 的同类测试，遵循既有模式，避免冗余文件）。

- [ ] **Step 1: 写失败测试**

修改 `backend/tests/test_parser.py`：将现有 `test_waf_page_marks_failed` 改名并加 `blocked` 断言，新增正常页断言：

```python
def test_waf_page_marks_blocked():
    html = '<html><body>安全验证页面</body></html>'
    result = parse_search_page(html, page_num=1)
    assert result.failed
    assert result.blocked is True
    assert result.jobs == []


def test_normal_page_not_blocked():
    result = parse_search_page(SEARCH_HTML, page_num=1)
    assert not result.failed
    assert result.blocked is False
```

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run pytest backend/tests/test_parser.py -v`
Expected: FAIL（`PageResult` 无 `blocked` 属性 → AttributeError / dataclass 未知字段 TypeError）

- [ ] **Step 3: 实现**

`backend/app/scrapers/base.py` 的 `PageResult` 末尾加字段：

```python
@dataclass
class PageResult:
    page_num: int
    jobs: list[JobDraft]
    companies: list[CompanyDraft] = field(default_factory=list)
    total_pages: int | None = None
    failed: bool = False
    blocked: bool = False
```

`backend/app/scrapers/parser.py` 的 `parse_search_page` 首个分支：

```python
def parse_search_page(html: str, page_num: int) -> PageResult:
    if _is_verification(html):
        return PageResult(page_num=page_num, jobs=[], failed=True, blocked=True)
```

- [ ] **Step 4: 运行测试确认通过**

Run: `uv run pytest backend/tests/test_parser.py -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add backend/app/scrapers/base.py backend/app/scrapers/parser.py backend/tests/test_parser.py
git commit -m "feat: mark blocked pages with PageResult.blocked flag"
```

---

### Task 2: 反指纹与自动降级（PlaywrightScraper）

**Files:**
- Modify: `backend/app/scrapers/playwright.py`（全部按 Step 3 代码改写）
- Modify: `backend/tests/test_playwright_scraper.py`（追加 Step 1 的测试）

**Interfaces:**
- Consumes: `PageResult.blocked`（Task 1）；`async_playwright`、`parse_search_page`
- Produces: `PlaywrightScraper.search()`（降级重试语义）、`_degrade_to_headful() -> bool`、反指纹浏览器上下文；公开接口签名不变

**行为契约（评审以此为准）：**
- 启动：`chromium.launch(headless=not self._headful, args=["--disable-blink-features=AutomationControlled"])`
- 上下文：`locale="zh-CN"`、`timezone_id="Asia/Shanghai"`、`accept_language="zh-CN,zh;q=0.9"` + `add_init_script(_FINGERPRINT_SCRIPT)`；UA 从每页轮换改为每浏览器一次（一个真实用户一个 UA，更拟真）
- `_fetch_page`：命中 blocked → 直接返回（不再无头重试 3 次，交 search 层降级）
- `search()`：连续失败计数；blocked 页立即降级；无标记连续 2 页失败降级；降级后立即重试当前页一次；成功重置计数
- `_degrade_to_headful()`：headful 已开 → False；否则 `close()` → `_headful=True` → `_ensure_browser()` → True

- [ ] **Step 1: 写失败测试**

`backend/tests/test_playwright_scraper.py` 追加（文件头新增 import，测试均同步包在 `asyncio.run` 里，不引入 pytest-asyncio）：

```python
import asyncio
from types import SimpleNamespace

from backend.app.scrapers import playwright as playwright_mod
from backend.app.scrapers.base import PageResult
from backend.app.scrapers.playwright import PlaywrightScraper


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
            pass

        async def new_page(self):
            pages_created.append(1)
            return _FakePage()

        async def close(self):
            pass

    class _FakeBrowser2:
        async def close(self):
            pass

        async def new_context(self, **kwargs):
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
```

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run pytest backend/tests/test_playwright_scraper.py -v`
Expected: FAIL（`_degrade_to_headful` 不存在 / 行为不符：连续失败未触发 headless=False 的第二次 launch）

- [ ] **Step 3: 实现**

`backend/app/scrapers/playwright.py` 全文改写为：

```python
import asyncio
import logging
import random
from collections.abc import AsyncGenerator
from urllib.parse import quote

from playwright.async_api import TimeoutError as PWTimeoutError
from playwright.async_api import async_playwright

from backend.app.scrapers.base import CompanyDraft, PageResult, Scraper
from backend.app.scrapers.parser import parse_company_page, parse_search_page

logger = logging.getLogger("job_hunter")

_SEARCH_URL = "https://we.51job.com/pc/search?keyword={kw}&searchType=2&sortType=0&pageNum={n}"
_JOB_CARD_SELECTOR = ".joblist-item"
_MAX_RETRIES = 3
_LAUNCH_ARGS = ["--disable-blink-features=AutomationControlled"]
_FINGERPRINT_SCRIPT = """
Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
Object.defineProperty(navigator, 'languages', {get: () => ['zh-CN', 'zh']});
Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});
window.chrome = window.chrome || {runtime: {}};
"""


class PlaywrightScraper(Scraper):
    def __init__(self, headful: bool = False):
        self._headful = headful
        self._playwright = None
        self._browser = None
        self._context = None

    async def _ensure_browser(self):
        if self._browser:
            return
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(
            headless=not self._headful, args=_LAUNCH_ARGS
        )

    async def _new_page(self):
        if self._context is None:
            ua = random.choice(
                [
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
                ]
            )
            self._context = await self._browser.new_context(
                user_agent=ua,
                viewport={"width": 1600, "height": 1000},
                locale="zh-CN",
                timezone_id="Asia/Shanghai",
                accept_language="zh-CN,zh;q=0.9",
            )
            await self._context.add_init_script(_FINGERPRINT_SCRIPT)
        page = await self._context.new_page()
        return page

    async def _degrade_to_headful(self) -> bool:
        if self._headful:
            return False
        logger.warning("检测到反爬拦截，降级为有头模式")
        await self.close()
        self._headful = True
        await self._ensure_browser()
        return True

    async def search(self, keyword: str, pages: int) -> AsyncGenerator[PageResult, None]:
        await self._ensure_browser()
        consecutive_failures = 0
        for n in range(1, pages + 1):
            result = await self._fetch_page(keyword, n)
            if result.failed:
                if result.blocked:
                    consecutive_failures = 0
                    degraded = await self._degrade_to_headful()
                else:
                    consecutive_failures += 1
                    degraded = consecutive_failures >= 2 and await self._degrade_to_headful()
                if degraded:
                    result = await self._fetch_page(keyword, n)
                if result.failed:
                    logger.warning("第 %s 页抓取失败（已重试）: keyword=%s", n, keyword)
                else:
                    consecutive_failures = 0
            else:
                consecutive_failures = 0
            yield result
            await asyncio.sleep(random.uniform(2.0, 5.0))

    async def _fetch_page(self, keyword: str, page_num: int) -> PageResult:
        last_result: PageResult | None = None
        for attempt in range(1, _MAX_RETRIES + 1):
            page = await self._new_page()
            try:
                url = _SEARCH_URL.format(kw=quote(keyword), n=page_num)
                await page.goto(url, wait_until="domcontentloaded", timeout=60000)
                try:
                    await page.wait_for_selector(_JOB_CARD_SELECTOR, timeout=30000)
                except PWTimeoutError:
                    html = await page.content()
                    last_result = parse_search_page(html, page_num)
                    if last_result.failed:
                        if last_result.blocked:
                            # 命中 WAF 标记：不做无头重试，交 search 层立即降级
                            return last_result
                        raise
                if page_num == 1:
                    for _ in range(3):
                        await page.mouse.wheel(0, 1200)
                        await page.wait_for_timeout(random.randint(400, 900))
                    await page.wait_for_timeout(1500)
                html = await page.content()
                last_result = parse_search_page(html, page_num)
                return last_result
            except Exception as exc:
                logger.warning("第 %s 页第 %s 次尝试失败: %s", page_num, attempt, exc)
                await asyncio.sleep(attempt * 2.0)
            finally:
                await page.close()
        if last_result is None:
            return PageResult(page_num=page_num, jobs=[], failed=True)
        return last_result

    async def fetch_company(self, company_id: str, company_url: str) -> CompanyDraft | None:
        if not company_url:
            return None
        await self._ensure_browser()
        page = await self._new_page()
        try:
            await page.goto(company_url, wait_until="domcontentloaded", timeout=60000)
            await page.wait_for_timeout(5000)
            html = await page.content()
            draft = parse_company_page(html)
            if draft:
                draft.company_id = company_id
            return draft
        except Exception as exc:
            logger.warning("公司详情抓取失败 company_id=%s: %s", company_id, exc)
            return None
        finally:
            await page.close()

    async def close(self) -> None:
        if self._context:
            await self._context.close()
            self._context = None
        if self._browser:
            await self._browser.close()
            self._browser = None
        if self._playwright:
            await self._playwright.stop()
            self._playwright = None
```

- [ ] **Step 4: 运行测试确认通过 + 全套回归**

Run: `uv run pytest backend/tests/test_playwright_scraper.py -v` — Expected: PASS（4 个新测试 + 2 个既有接口测试）
Run: `uv run pytest backend/tests -q` — Expected: 52 passed（46 既有 + Task 1 新增 2 + Task 2 新增 4），全部通过；site-packages starlette 弃用警告已知，忽略

- [ ] **Step 5: 提交**

```bash
git add backend/app/scrapers/playwright.py backend/tests/test_playwright_scraper.py
git commit -m "feat: add anti-fingerprint and auto headful degrade to scraper"
```

---
