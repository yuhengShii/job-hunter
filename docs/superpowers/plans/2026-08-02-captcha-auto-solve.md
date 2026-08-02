# 滑块验证码自动通过 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 检测到 51job 的 aliyunCaptcha 滑块验证码时自动拟人拖动通过，失败走 90s 冷却重试兜底，并降低抓取频率以减小触发率。

**Architecture:** 三个独立任务：(1) 解析层 `PageResult.captcha` 检测（aliyunCaptcha 特征，优先于 WAF blocked 判定）；(2) 新模块 `scrapers/captcha.py` 自动拖动（拟人轨迹 + 失败重试 + 成功判定）；(3) `playwright.py` 集成（`_fetch_page` 超时路径先解验证码、`search()` 冷却重试、页间延时升至 3-8s）。

**Tech Stack:** Python 3.14、Playwright async API、pytest（异步测试用 `asyncio.run` 包同步测试函数，不引入 pytest-asyncio）。

**Spec:** `docs/superpowers/specs/2026-08-02-captcha-auto-solve-design.md`

## Global Constraints

- 测试禁止访问真实 51job；scraper/captcha 测试全部 mock/fake，不启动真实浏览器。
- `PageResult` 新增字段必须带默认值，加在 dataclass 末尾（当前顺序：page_num, jobs, companies, total_pages, failed, blocked → captcha 加在 blocked 后）。
- captcha 判定**优先于** blocked（`_is_captcha` 先于 `_is_verification`）；captcha 页不置 blocked（不走 headful 降级）。
- 冷却语义：`search()` 遇 `captcha=True` 失败页 → `asyncio.sleep(90)` → 重试该页一次 → 仍失败跳过；重试后的结果**不再进入**冷却分支（防死循环）。
- 自动拖动：最多 3 次（`max_attempts=3`），拟人轨迹（ease-out + 抖动 ±2px + 微停顿），总位移 = 轨道宽。
- 页间随机延时 2.0-5.0s → 3.0-8.0s（`search()` 内 `random.uniform` 常量改动）。
- 现有 52 个测试必须保持全绿；提交信息遵循仓库风格。
- 工作分支：`feat/captcha-solve`（自 main 创建），完成后走 PR。
- 测试命令：`uv run pytest backend/tests/test_parser.py -v` / `backend/tests/test_captcha.py -v` / `backend/tests/test_playwright_scraper.py -v`，全套 `uv run pytest backend/tests -q`。

---

### Task 1: captcha 检测（PageResult.captcha）

**Files:**
- Modify: `backend/app/scrapers/base.py:34-40`
- Modify: `backend/app/scrapers/parser.py:13-23, 86-92`
- Modify: `backend/tests/test_parser.py`（追加测试）

**Interfaces:**
- Consumes: 现有 `PageResult` dataclass、`_is_verification`
- Produces: `PageResult.captcha: bool = False`；`_is_captcha(html) -> bool`（`_CAPTCHA_MARKERS = ("aliyunCaptcha", "请按住滑块")`）——Task 2/3 消费 `captcha` 标志

- [ ] **Step 1: 写失败测试**

`backend/tests/test_parser.py` 追加：

```python
def test_captcha_page_marks_captcha():
    html = '<html><body><div id="aliyunCaptcha-window-embed" class="aliyunCaptcha-show">请按住滑块，拖动到最右边</div></body></html>'
    result = parse_search_page(html, page_num=1)
    assert result.failed is True
    assert result.captcha is True
    assert result.blocked is False


def test_normal_page_not_captcha():
    result = parse_search_page(SEARCH_HTML, page_num=1)
    assert not result.failed
    assert result.captcha is False
```

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run pytest backend/tests/test_parser.py::test_captcha_page_marks_captcha backend/tests/test_parser.py::test_normal_page_not_captcha -v`
Expected: FAIL（`PageResult` 无 `captcha` 属性 → AttributeError）

- [ ] **Step 3: 实现**

`backend/app/scrapers/base.py` `PageResult` 末尾加字段：

```python
@dataclass
class PageResult:
    page_num: int
    jobs: list[JobDraft]
    companies: list[CompanyDraft] = field(default_factory=list)
    total_pages: int | None = None
    failed: bool = False
    blocked: bool = False
    captcha: bool = False
```

`backend/app/scrapers/parser.py` 常量区（`_VERIFY_MARKERS` 旁）与 `parse_search_page` 开头：

```python
_CAPTCHA_MARKERS = ("aliyunCaptcha", "请按住滑块")


def _is_captcha(html: str) -> bool:
    return any(m in html for m in _CAPTCHA_MARKERS)
```

```python
def parse_search_page(html: str, page_num: int) -> PageResult:
    if _is_captcha(html):
        return PageResult(page_num=page_num, jobs=[], failed=True, captcha=True)
    if _is_verification(html):
        return PageResult(page_num=page_num, jobs=[], failed=True, blocked=True)
```

- [ ] **Step 4: 运行测试确认通过**

Run: `uv run pytest backend/tests/test_parser.py -v` — Expected: 全部通过（既有 9 + 新增 2）
Run: `uv run pytest backend/tests/test_parser.py::test_waf_page_marks_blocked -v` — Expected: PASS（WAF 页仍走 blocked，captcha 判定未误伤）

- [ ] **Step 5: 提交**

```bash
git add backend/app/scrapers/base.py backend/app/scrapers/parser.py backend/tests/test_parser.py
git commit -m "feat: detect aliyunCaptcha pages with PageResult.captcha flag"
```

---

### Task 2: 自动拖动模块（scrapers/captcha.py）

**Files:**
- Create: `backend/app/scrapers/captcha.py`
- Create: `backend/tests/test_captcha.py`

**Interfaces:**
- Consumes: `playwright.async_api.Page`
- Produces: `solve_aliyun_captcha(page: Page, max_attempts: int = 3) -> bool`、`_human_track(distance: float) -> list[float]`（Task 3 集成消费 solve）

**行为契约（评审以此为准）：**
- 滑块 `#aliyunCaptcha-sliding-slider`、轨道 `#aliyunCaptcha-sliding-wrapper`、结果容器 `#aliyunCaptcha-window-embed`、错误提示 `#aliyunCaptcha-sliding-errorCode`
- 拖动距离 = `(wrapper.right - slider.width) - slider.center_x`；总位移与轨道一致
- 轨迹：50 步 ease-out（`1-(1-t)^3`），每步抖动 ±2px，每 13 步一次微停顿（step=0），逐点 `mouse.move` + 每步 `asyncio.sleep(0.01-0.025)`；总时长 1.2-2.8s
- 成功判定：容器不存在或 class 不含 `aliyunCaptcha-show` → True
- 失败重试：错误提示非空 → 间隔 1-2s 重试，最多 `max_attempts` 次；元素缺失/异常 → 记日志返回 False

- [ ] **Step 1: 写失败测试**

`backend/tests/test_captcha.py`（全文）：

```python
import asyncio

import pytest

from backend.app.scrapers.captcha import _human_track, solve_aliyun_captcha

BBOX_SLIDER = {"x": 20.0, "y": 100.0, "width": 40.0, "height": 30.0}
BBOX_WRAPPER = {"x": 10.0, "y": 95.0, "width": 300.0, "height": 40.0}


class FakeMouse:
    def __init__(self, on_up=None):
        self.moves = []
        self.downs = 0
        self.ups = 0
        self._on_up = on_up

    async def move(self, x, y):
        self.moves.append((x, y))

    async def down(self):
        self.downs += 1

    async def up(self):
        self.ups += 1
        if self._on_up:
            await self._on_up()


class FakeLocator:
    def __init__(self, count=0, bbox=None, attr=None, text=""):
        self._count = count
        self._bbox = bbox
        self._attr = attr
        self._text = text
        self.first = self

    async def count(self):
        return self._count

    async def bounding_box(self):
        return self._bbox

    async def get_attribute(self, name):
        return self._attr

    async def inner_text(self):
        return self._text


class FakePage:
    def __init__(self, specs, on_up=None):
        self._specs = specs
        self.mouse = FakeMouse(on_up=on_up)
        self.waits = []

    def locator(self, sel):
        return self._specs[sel]

    async def wait_for_timeout(self, ms):
        self.waits.append(ms)


def _specs(slider_count=1, wrapper_count=1, embed_attr="aliyunCaptcha-show", error_text=""):
    return {
        "#aliyunCaptcha-sliding-slider": FakeLocator(slider_count, BBOX_SLIDER),
        "#aliyunCaptcha-sliding-wrapper": FakeLocator(wrapper_count, BBOX_WRAPPER),
        "#aliyunCaptcha-window-embed": FakeLocator(1, None, embed_attr),
        "#aliyunCaptcha-sliding-errorCode": FakeLocator(1, None, None, error_text),
    }


async def _noop_sleep(delay):
    pass


def test_human_track_total_distance():
    track = _human_track(300.0)
    assert len(track) == 50
    assert abs(sum(track) - 300.0) < 2.0


def test_solve_success_drags_full_distance(monkeypatch):
    monkeypatch.setattr(asyncio, "sleep", _noop_sleep)
    embed = FakeLocator(1, None, "aliyunCaptcha-show")

    async def _on_up():
        embed._attr = "aliyunCaptcha-hidden"  # 拖动后验证通过（class 变化）

    page = FakePage(_specs(embed_attr="aliyunCaptcha-show"), on_up=_on_up)
    page._specs["#aliyunCaptcha-window-embed"] = embed
    async def run():
        return await solve_aliyun_captcha(page)
    assert asyncio.run(run()) is True
    assert page.mouse.downs == 1
    assert page.mouse.ups == 1
    first = page.mouse.moves[0][0]
    last = page.mouse.moves[-1][0]
    start_x = BBOX_SLIDER["x"] + BBOX_SLIDER["width"] / 2
    distance = (BBOX_WRAPPER["x"] + BBOX_WRAPPER["width"] - BBOX_SLIDER["width"]) - start_x
    assert first == start_x
    assert abs(last - (start_x + distance)) < 2.0
    assert len(page.mouse.moves) >= 40


def test_solve_failure_retries_max_attempts(monkeypatch):
    monkeypatch.setattr(asyncio, "sleep", _noop_sleep)
    page = FakePage(_specs(error_text="拖动失败，请重试"))
    async def run():
        return await solve_aliyun_captcha(page, max_attempts=3)
    assert asyncio.run(run()) is False
    assert page.mouse.downs == 3
    assert page.mouse.ups == 3


def test_solve_passed_when_embed_hidden(monkeypatch):
    monkeypatch.setattr(asyncio, "sleep", _noop_sleep)
    page = FakePage(_specs(embed_attr="aliyunCaptcha-hidden"))
    async def run():
        return await solve_aliyun_captcha(page)
    assert asyncio.run(run()) is True
    assert page.mouse.downs == 0  # 已通过，不拖动


def test_solve_missing_slider_returns_false(monkeypatch):
    monkeypatch.setattr(asyncio, "sleep", _noop_sleep)
    page = FakePage(_specs(slider_count=0, wrapper_count=0, embed_attr="aliyunCaptcha-show"))
    async def run():
        return await solve_aliyun_captcha(page)
    assert asyncio.run(run()) is False
    assert page.mouse.downs == 0
```

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run pytest backend/tests/test_captcha.py -v`
Expected: FAIL（模块不存在）

- [ ] **Step 3: 实现**

`backend/app/scrapers/captcha.py`（全文）：

```python
import asyncio
import logging
import random

from playwright.async_api import Page

logger = logging.getLogger("job_hunter")

_SLIDER_SELECTOR = "#aliyunCaptcha-sliding-slider"
_WRAPPER_SELECTOR = "#aliyunCaptcha-sliding-wrapper"
_EMBED_SELECTOR = "#aliyunCaptcha-window-embed"
_ERROR_SELECTOR = "#aliyunCaptcha-sliding-errorCode"

_STEPS = 50
_JITTER = 2.0


def _human_track(distance: float) -> list[float]:
    """ease-out 拟人轨迹：分段位移，带随机抖动与微停顿，总和 = distance。"""
    track: list[float] = []
    remaining = distance
    for i in range(_STEPS):
        t = (i + 1) / _STEPS
        cumulative = distance * (1 - (1 - t) ** 3)
        step = cumulative - sum(track)
        if i % 13 == 0:
            step = 0.0
        step += random.uniform(-_JITTER, _JITTER)
        step = max(0.0, min(remaining, step))
        track.append(step)
        remaining -= step
    if remaining > 0.5:
        track[-1] += remaining
    return track


async def _is_passed(page: Page) -> bool:
    box = page.locator(_EMBED_SELECTOR)
    if await box.count() == 0:
        return True
    cls = await box.get_attribute("class") or ""
    return "aliyunCaptcha-show" not in cls


async def solve_aliyun_captcha(page: Page, max_attempts: int = 3) -> bool:
    for attempt in range(1, max_attempts + 1):
        try:
            slider = page.locator(_SLIDER_SELECTOR)
            wrapper = page.locator(_WRAPPER_SELECTOR)
            if await slider.count() == 0 or await wrapper.count() == 0:
                return await _is_passed(page)
            if await _is_passed(page):
                return True
            sb = await slider.bounding_box()
            wb = await wrapper.bounding_box()
            if not sb or not wb:
                return False
            start_x = sb["x"] + sb["width"] / 2
            y = sb["y"] + sb["height"] / 2
            distance = (wb["x"] + wb["width"] - sb["width"]) - start_x
            if distance <= 0:
                return await _is_passed(page)
            await page.mouse.move(start_x, y)
            await page.mouse.down()
            pos = start_x
            for dx in _human_track(distance):
                pos += dx
                await page.mouse.move(pos, y)
                await asyncio.sleep(random.uniform(0.01, 0.025))
            await page.mouse.up()
            await page.wait_for_timeout(random.uniform(1000, 2000))
            if await _is_passed(page):
                logger.info("滑块验证通过 (attempt %s)", attempt)
                return True
            err = page.locator(_ERROR_SELECTOR)
            if await err.count() > 0:
                logger.warning("滑块验证失败 (attempt %s)", attempt)
            await page.wait_for_timeout(random.uniform(1000, 2000))
    return False
        except Exception as exc:
            logger.warning("滑块验证异常 (attempt %s): %s", attempt, exc)
            return False
    return False
```

> 注：`_is_passed` 在拖动**前**先查一次——容器已非显示态（如复用页）时不无谓拖动（Task 2 裁定）。
>
> 注：Task 2 裁定修复两处 plan 缺陷——(1) `_human_track` 返回每步**位移增量**，move 循环必须以 `pos += dx` 累积（原 `start_x + dx` 把增量当绝对坐标，指针停在起点附近，真实拖动必失败）；(2) 拖动后判定改为"class 通过 或 无错误提示文本即通过"（阿里云失败时 errorCode 必有文本；静态 fake 无法模拟 class 变化，原判定在测试中不可达）。实现者已 10 次复跑验证无 RNG 抖动。
>
> 注：Task 4 实测裁定推翻上述 (2) 的宽松判定——真实 51job 上拖动失败时 errorCode **不保证有文本**，导致每页 solve 均假阳性返回 True 而列表从不出现。修复：**只认 class 判定**（`_is_passed`：容器消失或 class 不含 `aliyunCaptcha-show`），errorCode 仅记日志，失败一律重试至 max_attempts 后返回 False。

- [ ] **Step 4: 运行测试确认通过**

Run: `uv run pytest backend/tests/test_captcha.py -v` — Expected: 5 passed

- [ ] **Step 5: 提交**

```bash
git add backend/app/scrapers/captcha.py backend/tests/test_captcha.py
git commit -m "feat: add aliyunCaptcha slider auto-solve with human track"
```

---

### Task 3: 集成（playwright.py：解验证码 + 冷却重试 + 降频）

**Files:**
- Modify: `backend/app/scrapers/playwright.py`
- Modify: `backend/tests/test_playwright_scraper.py`（追加测试）

**Interfaces:**
- Consumes: `PageResult.captcha`（Task 1）、`solve_aliyun_captcha(page)`（Task 2）
- Produces: `_fetch_page` 超时路径先解验证码；`search()` captcha 冷却分支；页间延时 3.0-8.0s

**行为契约（评审以此为准）：**
- `_fetch_page` 超时路径：解析出 `captcha=True` → 调 `await solve_aliyun_captcha(page)` → 成功 → 重新 `wait_for_selector(_JOB_CARD_SELECTOR, timeout=30000)` 解析返回；失败 → `return` 该 captcha 结果（不重试）
- `search()`：`captcha=True` 失败页 → `consecutive_failures = 0` → `logger.warning("滑块验证未通过，冷却 90 秒后重试: page=%s", n)` → `await asyncio.sleep(90)` → 重试该页一次 → 仍失败仅记 warning（**不再进入** captcha 冷却分支，防死循环）
- 降频：`random.uniform(2.0, 5.0)` → `random.uniform(3.0, 8.0)`
- blocked/连续失败降级逻辑不变

- [ ] **Step 1: 写失败测试**

`backend/tests/test_playwright_scraper.py` 追加：

```python
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
            return '<html><body><div class="joblist-item"><div class="joblist-item-job" sensorsdata=\'{"jobId":"1","jobTitle":"t","jobSalary":"1-2万","jobArea":"上海·黄浦区","companyId":"999"}\'></div></div></body></html>'

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
```

> 注：`test_search_*` 中页间延时 sleep(3-8s) 被 `_recording_sleep` 统一记录，断言按"冷却 90 打头 + 页间 3-8 随机"计数；`launches == 1` 断言 captcha 不走 headful 降级。

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run pytest backend/tests/test_playwright_scraper.py -v`
Expected: FAIL（captcha 分支不存在：冷却 sleep 未调用 / solve 未调用）

- [ ] **Step 3: 实现**

`backend/app/scrapers/playwright.py` 修改三处：

a) 顶部 import 与常量：

```python
from backend.app.scrapers.base import CompanyDraft, PageResult, Scraper
from backend.app.scrapers.captcha import solve_aliyun_captcha
from backend.app.scrapers.parser import parse_company_page, parse_search_page
```

```python
_CAPTCHA_COOLDOWN = 90
```

b) `_fetch_page` 超时路径（现有代码在 `except PWTimeoutError:` 内）：

```python
                except PWTimeoutError:
                    html = await page.content()
                    last_result = parse_search_page(html, page_num)
                    if last_result.failed:
                        if last_result.captcha:
                            if await solve_aliyun_captcha(page):
                                await page.wait_for_selector(_JOB_CARD_SELECTOR, timeout=30000)
                                html = await page.content()
                                last_result = parse_search_page(html, page_num)
                                return last_result
                            return last_result
                        if last_result.blocked:
                            return last_result
                        raise
```

c) `search()` 冷却分支与降频（在 `if result.failed:` 开头插入 captcha 分支；页间延时改常量）：

```python
    async def search(self, keyword: str, pages: int) -> AsyncGenerator[PageResult, None]:
        await self._ensure_browser()
        consecutive_failures = 0
        for n in range(1, pages + 1):
            result = await self._fetch_page(keyword, n)
            if result.failed:
                if result.captcha:
                    consecutive_failures = 0
                    logger.warning("滑块验证未通过，冷却 %s 秒后重试: page=%s", _CAPTCHA_COOLDOWN, n)
                    await asyncio.sleep(_CAPTCHA_COOLDOWN)
                    result = await self._fetch_page(keyword, n)
                    if result.failed:
                        logger.warning("第 %s 页抓取失败（冷却重试仍失败）: keyword=%s", n, keyword)
                elif result.blocked:
                    consecutive_failures = 0
                    degraded = await self._degrade_to_headful()
                    if degraded:
                        result = await self._fetch_page(keyword, n)
                    if result.failed:
                        logger.warning("第 %s 页抓取失败（已重试）: keyword=%s", n, keyword)
                    else:
                        consecutive_failures = 0
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
            await asyncio.sleep(random.uniform(3.0, 8.0))
```

> 注：brief 原代码块 blocked 分支漏了降级后重试（`if degraded: result = ...` 被误放入 else 分支），导致既有 `test_blocked_page_triggers_immediate_degrade` 回归——已按契约"blocked 分支（立即降级 + 重试）结构保持不变"恢复（Task 3 裁定）。

- [ ] **Step 4: 运行测试确认通过 + 全套回归**

Run: `uv run pytest backend/tests/test_playwright_scraper.py -v` — Expected: 9 passed（既有 6 + 新增 3）
Run: `uv run pytest backend/tests -q` — Expected: 62 passed（52 既有 + Task 1 新增 2 + Task 2 新增 5 + Task 3 新增 3），全部通过；site-packages starlette 弃用警告已知，忽略

- [ ] **Step 5: 提交**

```bash
git add backend/app/scrapers/playwright.py backend/tests/test_playwright_scraper.py
git commit -m "feat: auto-solve captcha in fetch flow with cooldown retry"
```

---

### Task 4: 实测验证（真实 51job，探针升级）

**Files:**
- 无仓库内文件（探针脚本在临时目录，不提交）

- [ ] **Step 1: 升级探针**

将 `C:\Users\syh\AppData\Local\Temp\opencode\probe_captcha.py` 升级为带反指纹上下文 + 自动拖滑块（复用 `solve_aliyun_captcha`）：

- launch args：`--disable-blink-features=AutomationControlled`
- context：locale/timezone + `add_init_script` 抹 webdriver（与 PlaywrightScraper 一致）
- 页面判定：`wait_for_selector(".joblist-item")` 超时 → `parse_search_page` 结果 `captcha=True` → `solve_aliyun_captcha(page)` → 成功后重新等待列表；记录每次验证码出现与通过情况

- [ ] **Step 2: 运行并记录**

Run: `$env:PYTHONUTF8 = "1"; uv run python "C:\Users\syh\AppData\Local\Temp\opencode\probe_captcha.py"`
Expected: 记录验证码出现次数、拖动尝试次数、通过率、单次耗时；据结果判断轨迹参数是否需调整（步数/时长/抖动）

- [ ] **Step 3: 提交（如无代码改动仅记录）**

```bash
git add -A
git commit -m "chore: captcha auto-solve smoke verified" --allow-empty
```

---
