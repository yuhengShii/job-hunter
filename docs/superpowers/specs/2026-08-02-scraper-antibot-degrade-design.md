# 抓取器反爬降级设计（2026-08-02）

## 背景与目标

v1 冒烟测试中 51job 对无头浏览器限流/拦截：第 27–30 页 `.joblist-item` 30s 超时（每页重试 3 次仍失败，页面无 WAF 标记文本），第 2–26 页返回相同职位集（分页失效）。目标：

1. 降低无头模式被检测概率（反指纹）。
2. 被拦截时**自动**切换有头模式重试当前页，而非干等 3×30s 超时。
3. 保持 PRD §6 架构（Scraper 接口不变，任务层零改动）。

## 改动范围

`backend/app/scrapers/playwright.py`、`backend/app/scrapers/parser.py`、`backend/app/scrapers/base.py`、`backend/tests/fixtures/51job_waf.html`、`backend/tests/test_parser.py`、`backend/tests/test_playwright_scraper.py`

## 1. 反指纹（playwright.py）

- `chromium.launch` 增加 args：`--disable-blink-features=AutomationControlled`。
- 页面上下文：`locale="zh-CN"`、`timezone_id="Asia/Shanghai"`、`accept_language="zh-CN,zh;q=0.9"`；保留现有 UA 轮换与 viewport。
- 每个浏览器上下文 `add_init_script`：抹掉 `navigator.webdriver`，补充 `navigator.plugins`/`navigator.languages`/`window.chrome` 等真实指纹属性。
- 页面创建从 `browser.new_page()` 改为 `browser.new_context(**args)` + `context.new_page()`（context 随浏览器生命周期，页面仍逐页关闭）。

## 2. 拦截检测（base.py + parser.py）

- `PageResult` 新增字段 `blocked: bool = False`。
- `parse_search_page`：命中 `_VERIFY_MARKERS`（安全验证/验证码/renderData）时返回 `PageResult(..., failed=True, blocked=True)`。
- 新增 fixture `backend/tests/fixtures/51job_waf.html`（几行微型页，含"安全验证"文本）。

## 3. 自动降级（playwright.py）

**触发规则**（已与用户确认，两者都要）：

- **WAF 标记**：`_fetch_page` 内解析出 `blocked=True` → 立即降级（跳过剩余重试等待）。
- **连续失败**：`search()` 维护连续失败计数，连续 2 页失败（无标记，超时/空列表）→ 降级；任何成功页重置计数。

**降级动作** `_degrade_to_headful()`：

- 已是 headful → no-op（返回 False）。
- 否则 `close()` 关浏览器 → `_headful = True` → 重启浏览器 → 返回 True。本次任务后续页面均保持有头模式。

**降级后重试**：降级成功后立即对当前页用有头模式重试一次（仍失败则按原逻辑跳过该页，任务继续）。

**幂等与边界**：降级全任务至多触发一次（已是 headful 后 no-op）；浏览器重启失败由 `_degrade_to_headful` 内部 try/except 兜底（记日志、返回 False，任务继续）。

## 4. 测试（禁止访问真实 51job）

- `test_parser.py`：`51job_waf.html` → `blocked=True, failed=True`；`51job_search.html` → `blocked=False`。
- `test_playwright_scraper.py`（mock `async_playwright`，不启动真实浏览器）：
  - 记录每次 `launch(headless=...)` 调用；
  - 场景 A：前 2 页返回 failed（无标记）→ 断言第 3 页前已以 `headless=False` 重启；
  - 场景 B：首页返回 blocked=True → 断言立即降级重启并重试该页。
- 现有 46 个测试保持全绿。

## 非目标（YAGNI）

- 不做 IP 代理池、验证码识别、firecrawl 切换（v2 预留位不动）。
- 不自动调整抓取频率/页数（配置已有 headful 与 max_pages，由用户按需调）。
- 不新增 Config 开关：降级为 PRD §6 既定行为，始终开启。
