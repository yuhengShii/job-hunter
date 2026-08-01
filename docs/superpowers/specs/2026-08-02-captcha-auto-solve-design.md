# 滑块验证码自动通过设计（2026-08-02）

## 背景与目标

51job 在请求频率累积后弹出**阿里云滑块验证码（aliyunCaptcha）**：页面正常加载（title/HTML 完整）但职位列表不渲染（无 `.joblist-item`），表现为 30s 超时。实测证据（探针脚本，2026-08-02）：

- 无头 + 无反指纹 → 第 1 页即全部验证码（反指纹是决定性因素，已实现于 feat/antibot-degrade）
- 有反指纹 → 前 39 页正常，40+ 页开始验证码（**频率风控**，非页码上限——两次会话触发位置不同：27 页 / 40 页）
- 验证码页特征：`#aliyunCaptcha-window-embed`、`#aliyunCaptcha-sliding-slider`、文案「请按住滑块，拖动到最右边」

目标：检测到滑块验证码后**自动拟人轨迹拖动通过**，通过后继续抓取；拖动失败走冷却重试兜底。与已有反指纹、headful 降级共同构成完整反爬体系。

## 改动范围

`backend/app/scrapers/parser.py`、`backend/app/scrapers/base.py`、`backend/app/scrapers/captcha.py`（新）、`backend/app/scrapers/playwright.py`、`backend/tests/test_parser.py`、`backend/tests/test_captcha.py`（新）、`backend/tests/test_playwright_scraper.py`

## 1. 检测（parser.py + base.py）

- `PageResult` 新增 `captcha: bool = False`（dataclass 末尾）。
- `parse_search_page` 新增判定，**captcha 优先于 WAF blocked**：

```python
_CAPTCHA_MARKERS = ("aliyunCaptcha", "请按住滑块")

def _is_captcha(html: str) -> bool:
    return any(m in html for m in _CAPTCHA_MARKERS)
```

- `_is_captcha(html)` 命中 → `PageResult(failed=True, captcha=True)`（不置 blocked，避免误走 headful 降级——验证码是服务端风控，换浏览器模式无济于事）。

## 2. 自动拖动（新模块 scrapers/captcha.py）

职责单一：给定验证码页的 Page，尝试拖动通过，返回是否成功。

```python
async def solve_aliyun_captcha(page, max_attempts: int = 3) -> bool
```

- **定位**：`#aliyunCaptcha-sliding-slider`；轨道宽度 = `#aliyunCaptcha-sliding-wrapper` 与 slider 的 bounding_box 宽度差（slider 需从最左拖到最右）。
- **拟人轨迹**：`_human_track(distance) -> list[float]` 生成分段位移（步数 40-60）：
  - ease-out 加速-减速曲线（`1-(1-t)^3`）
  - 每步叠加随机抖动 ±2px（累积位置随动，不改变总距离）
  - 随机 1-2 处微停顿（连续 3-5 步同位）
- **执行**：`page.mouse.move(start_x, y)` → `mouse.down()` → 按轨迹 `mouse.move(x, y, steps=1)`（每步间隔 10-25ms）→ `mouse.up()`；总时长 1.2-2.8s。
- **结果判定**：拖动后等待 1-2s，检查滑块容器状态——`#aliyunCaptcha-window-embed` 失去显示态（class 不含 `aliyunCaptcha-show`）视为通过；出现错误提示（`#aliyunCaptcha-sliding-errorCode` 非空）视为失败，间隔 1-2s 重试（最多 `max_attempts` 次）。
- 任一环节异常（元素不存在、定位失败）→ 记日志并返回 False。

## 3. 集成（playwright.py）

- `_fetch_page` 超时路径：解析结果 `captcha=True` → 调 `solve_aliyun_captcha(page)`（滑块就在当前页）：
  - 成功 → 重新 `wait_for_selector(_JOB_CARD_SELECTOR)` 拿列表 → 正常返回
  - 失败 → 返回 `captcha=True` 结果（不做无头 3 次重试）
- `search()` 新增冷却分支：`captcha=True` 的失败页 → `asyncio.sleep(90)`（记日志「滑块验证未通过，冷却 90 秒」）→ 重试该页一次 → 仍失败则跳过（该页计数失败）。
- **降频**：页间随机延时 2.0-5.0s → **3.0-8.0s**（降低触发率）。

## 4. 测试（禁止访问真实 51job）

- `test_parser.py`：
  - 伪造 aliyunCaptcha 页（内联 HTML 含 `aliyunCaptcha-sliding-slider`）→ `failed=True, captcha=True, blocked=False`
  - 现有 51job_search.html → `captcha=False`；WAF 页 → `blocked=True, captcha=False`
- `test_captcha.py`（fake page，不启动浏览器）：
  - 拖动序列：断言 mouse down/move/up 被调用、总位移 = 轨道宽、步数 ≥ 40
  - 失败重试：errorCode 持续出现 → 调用 `max_attempts` 次拖动
  - 成功判定：容器 class 变化 → 返回 True
- `test_playwright_scraper.py`（mock）：
  - `_fetch_page` 遇 captcha → mock solve 成功 → 重新取列表返回正常结果
  - solve 失败 → 返回 captcha=True → `search()` 冷却 sleep(90) 被调用（monkeypatch 记录时长）→ 重试一次 → 仍 captcha 跳过

## 5. 实测验证（真实 51job，探针升级）

升级探针脚本（反指纹上下文 + 自动拖滑块），在风控激活状态下运行：
- 命中验证码页 → 自动拖动 → 观察通过率与恢复抓取
- 记录：拖动尝试次数、成功率、单次耗时；据实测调整轨迹参数（步数/时长/抖动幅度）

## 非目标（YAGNI）

- 不做验证码接口逆向/轨迹参数伪造（不直接调阿里云服务端接口）。
- 不做 IP 代理池；不做验证码打码平台对接。
- 成功判定仅基于页面 DOM 状态，不做图像识别。
