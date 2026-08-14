import asyncio
import json
import logging
import random
import time
from collections.abc import AsyncGenerator
from pathlib import Path
from urllib.parse import quote

from playwright.async_api import TimeoutError as PWTimeoutError
from playwright.async_api import async_playwright

from backend.app.scrapers.applier import (
    ApplyResult,
    ApplyTarget,
    _CITY_CODE,
    apply_job_group,
)
from backend.app.scrapers.auth import MANUAL_CAPTCHA_TIMEOUT, login
from backend.app.scrapers.base import LoginCredential, PageResult, Scraper
from backend.app.scrapers.captcha import solve_aliyun_captcha
from backend.app.scrapers.parser import parse_search_page

logger = logging.getLogger("job_hunter")

_SEARCH_URL = (
    "https://we.51job.com/pc/search?keyword={kw}&searchType=2&sortType=0&pageNum={n}&jobArea={area}"
)

# 登录状态持久化文件（cookie/localStorage）。登录成功后保存，后续任务/test-login 自动复用，
# 会话过期或失效时才需要重新人工验证。位于 data/（已 gitignore，不入库）。
_STORAGE_STATE_PATH = Path(__file__).resolve().parents[3] / "data" / "51job_storage.json"


def build_search_url(
    keyword: str, page_num: int, area: str, industry: str | None = None
) -> str:
    url = _SEARCH_URL.format(kw=quote(keyword), n=page_num, area=area)
    if industry:
        url += f"&industry={quote(industry)}"
    return url
_JOB_CARD_SELECTOR = ".joblist-item"
_MAX_RETRIES = 3
_CAPTCHA_COOLDOWN = 90


def _expand_search_units(targets: list[ApplyTarget]) -> list[dict]:
    """每个职位按源条件展开为搜索单元（同职位多条件 → 多单元，带行业筛选的在前）。

    无源条件的职位用「职位城市名→编码 + 无行业」兜底。
    """
    units = []
    for t in targets:
        sources = t.sources or [(_CITY_CODE.get(t.city or "", "000000"), None)]
        for city, industry in sources:
            units.append({"title": t.title, "city": city, "industry": industry, "target": t})
    return units


def _group_search_units(units: list[dict]) -> list[list[dict]]:
    """按（标题, 城市, 行业）分组，保持首次出现顺序（源条件已按精准度排序）。"""
    groups: dict[tuple[str, str, str | None], list[dict]] = {}
    for u in units:
        key = (u["title"], u["city"], u["industry"])
        groups.setdefault(key, []).append(u)
    return list(groups.values())
_LAUNCH_ARGS = ["--disable-blink-features=AutomationControlled"]
_FINGERPRINT_SCRIPT = """
Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
Object.defineProperty(navigator, 'languages', {get: () => ['zh-CN', 'zh']});
Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});
window.chrome = window.chrome || {runtime: {}};
"""


async def _probe_logged_in(page) -> bool:
    """探测当前浏览器上下文是否已登录 51job。

    实测（2026-08）：my.51job.com 即使带有效登录 cookie 也会重定向到登录页，
    不可用作探测；we.51job.com 搜索页登录态下顶部显示用户名、
    无「登录/注册」入口，匿名态则相反，以此判断。
    """
    try:
        await page.goto(
            "https://we.51job.com/pc/search?keyword=test&searchType=2&sortType=0&pageNum=1&jobArea=000000",
            wait_until="domcontentloaded",
            timeout=30000,
        )
        await page.wait_for_timeout(2500)
        body = await page.evaluate("document.body ? document.body.innerText : ''")
        return "登录/注册" not in body
    except Exception as exc:
        logger.warning("登录态探测失败，按未登录处理: %s", exc)
        return False


def storage_state_valid(path: str | Path | None) -> bool:
    """登录状态文件存在且至少含一个未过期 cookie 才算有效。"""
    if not path:
        return False
    p = Path(path)
    if not p.exists():
        return False
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return False
    now = time.time()
    for cookie in data.get("cookies", []):
        exp = cookie.get("expires", -1)
        if exp == -1 or exp > now:  # session cookie(-1) 或未过期
            return True
    return False


class PlaywrightScraper(Scraper):
    def __init__(
        self,
        headful: bool = False,
        login_credential: LoginCredential | None = None,
        storage_state_path: str | Path | None = None,
        use_system_chrome: bool = False,
    ):
        self._headful = headful
        self._login_credential = login_credential
        self._storage_state = str(storage_state_path or _STORAGE_STATE_PATH)
        self._use_system_chrome = use_system_chrome
        self._playwright = None
        self._browser = None
        self._context = None

    async def _ensure_browser(self):
        if self._browser:
            return
        self._playwright = await async_playwright().start()
        if self._use_system_chrome:
            try:
                self._browser = await self._playwright.chromium.launch(
                    channel="chrome", headless=not self._headful, args=_LAUNCH_ARGS
                )
                logger.info("已使用系统 Chrome 启动浏览器")
                return
            except Exception as exc:
                logger.warning("系统 Chrome 启动失败，回退内置 Chromium: %s", exc)
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
            ctx_kwargs: dict = {
                "user_agent": ua,
                "viewport": {"width": 1600, "height": 1000},
                "locale": "zh-CN",
                "timezone_id": "Asia/Shanghai",
            }
            if storage_state_valid(self._storage_state):
                ctx_kwargs["storage_state"] = self._storage_state
                logger.info("已加载保存的登录状态: %s", self._storage_state)
            self._context = await self._browser.new_context(**ctx_kwargs)
            await self._context.add_init_script(_FINGERPRINT_SCRIPT)
        page = await self._context.new_page()
        return page

    async def save_storage_state(self) -> None:
        """把当前浏览器会话（cookie/localStorage）导出到文件，供下次复用。"""
        if self._context is None:
            return
        path = Path(self._storage_state)
        path.parent.mkdir(parents=True, exist_ok=True)
        await self._context.storage_state(path=str(path))
        logger.info("已保存登录状态: %s", path)

    async def _degrade_to_headful(self) -> bool:
        if self._headful:
            return False
        logger.warning("检测到反爬拦截，降级为有头模式")
        await self.close()
        self._headful = True
        try:
            await self._ensure_browser()
        except Exception as exc:
            logger.warning("有头模式重启失败: %s", exc)
            return False
        return True

    async def _ensure_logged_in(self, page) -> tuple:
        """按需登录（含 storage_state 复用与极验降级有头重试）。

        返回 (可能重建的 page, 是否已登录)；匿名（无 login_credential）视为已就绪。
        """
        if self._login_credential is None:
            return page, True
        logged_in, reason = False, ""
        if storage_state_valid(self._storage_state):
            # 已保存的登录状态仍有效：直接复用（cookie 已随 context 加载）
            logger.info("复用已保存的登录状态: %s", self._storage_state)
            logged_in = True
        else:
            try:
                logged_in, reason = await login(
                    page,
                    self._login_credential.site,
                    self._login_credential.username,
                    self._login_credential.password,
                )
            except Exception as exc:
                logger.warning("登录异常，降级为匿名抓取: %s", exc)
            if not logged_in and reason == "geetest":
                # 极验风控拒绝：切换有头模式并暂停等待人工完成验证码
                logger.warning(
                    "检测到极验验证码，切换有头模式等待人工验证（最多 %.0f 秒）",
                    MANUAL_CAPTCHA_TIMEOUT,
                )
                if await self._degrade_to_headful():
                    page = await self._new_page()
                    logged_in, reason = await login(
                        page,
                        self._login_credential.site,
                        self._login_credential.username,
                        self._login_credential.password,
                        manual_wait=MANUAL_CAPTCHA_TIMEOUT,
                    )
            if logged_in:
                await self.save_storage_state()
        if not logged_in:
            logger.warning(
                "登录失败，降级为匿名抓取: site=%s username=%s reason=%s",
                self._login_credential.site,
                self._login_credential.username,
                reason,
            )
        return page, logged_in

    async def search(
        self, keyword: str, pages: int, area: str = "000000", industry: str | None = None
    ) -> AsyncGenerator[PageResult, None]:
        await self._ensure_browser()
        page = await self._new_page()
        page, _ = await self._ensure_logged_in(page)
        consecutive_failures = 0
        consecutive_captcha = 0
        last_ids: set[str] | None = None
        try:
            n = 1
            while n <= pages:
                result, page = await self._fetch_page(page, keyword, n, area, industry)
                if not result.failed and result.jobs and last_ids is not None:
                    ids = {j.job_id for j in result.jobs}
                    if ids == last_ids:
                        logger.warning(
                            "第 %s 页与上一页职位完全相同，视为翻页失败: keyword=%s", n, keyword
                        )
                        result = PageResult(page_num=n, jobs=[], failed=True)
                if not result.failed:
                    last_ids = {j.job_id for j in result.jobs}
                    # 首页解析出总页数后截断循环，避免越过真实末页空转
                    if result.total_pages:
                        pages = min(pages, result.total_pages)
                if result.failed:
                    if result.captcha:
                        consecutive_failures = 0
                        logger.warning("滑块验证未通过，冷却 %s 秒后重试: page=%s", _CAPTCHA_COOLDOWN, n)
                        await asyncio.sleep(_CAPTCHA_COOLDOWN)
                        result, page = await self._fetch_page(page, keyword, n, area, industry)
                        if result.failed:
                            consecutive_captcha += 1
                            logger.warning("第 %s 页抓取失败（冷却重试仍失败）: keyword=%s", n, keyword)
                            if consecutive_captcha >= 3:
                                logger.warning("连续 %s 页验证码未通过，放弃剩余页", consecutive_captcha)
                                return
                        else:
                            consecutive_captcha = 0
                    elif result.blocked:
                        consecutive_captcha = 0
                        consecutive_failures = 0
                        degraded = await self._degrade_to_headful()
                        if degraded:
                            result, page = await self._fetch_page(page, keyword, n, area, industry)
                        if result.failed:
                            logger.warning("第 %s 页抓取失败（已重试）: keyword=%s", n, keyword)
                        else:
                            consecutive_failures = 0
                    else:
                        consecutive_captcha = 0
                        consecutive_failures += 1
                        degraded = consecutive_failures >= 2 and await self._degrade_to_headful()
                        if degraded:
                            result, page = await self._fetch_page(page, keyword, n, area, industry)
                        if result.failed:
                            logger.warning("第 %s 页抓取失败（已重试）: keyword=%s", n, keyword)
                            if consecutive_failures >= 3:
                                logger.warning("连续 %s 页抓取失败，放弃剩余页: keyword=%s", consecutive_failures, keyword)
                                break
                        else:
                            consecutive_failures = 0
                else:
                    consecutive_captcha = 0
                    consecutive_failures = 0
                yield result
                await asyncio.sleep(random.uniform(3.0, 8.0))
                n += 1
        finally:
            await page.close()

    async def apply_to_jobs(
        self, targets: list[ApplyTarget]
    ) -> AsyncGenerator[ApplyResult, None]:
        """批量投递：按（真实标题, 源城市, 源行业）展开搜索单元并分组。

        每个职位按其全部源抓取条件展开（带行业筛选的窄搜索在前），各组在同一
        搜索页勾选后「一键投递」（页面代签）；某职位 success/skipped 后从后续
        组剔除（绝不重复投），failed 保留在其它条件的组里继续尝试。

        投递必须登录，登录失败抛 RuntimeError（由上层判任务失败）。
        遇滑块验证码时：冷却 90s 重试一次（风控为滚动窗口，冷却后自动解除），
        仍拦截则降级有头模式供人工拖动兜底，再失败才记为失败。
        """
        await self._ensure_browser()
        page = await self._new_page()
        try:
            page, logged_in = await self._ensure_logged_in(page)
            if not logged_in:
                raise RuntimeError("登录失败，无法投递")
            groups = _group_search_units(_expand_search_units(targets))
            final: dict[str, ApplyResult] = {}
            for i, group in enumerate(groups):
                title = group[0]["title"]
                city = group[0]["city"]
                industry = group[0]["industry"]
                group_targets = [
                    u["target"]
                    for u in group
                    if u["target"].job_id not in final
                    or final[u["target"].job_id].status == "failed"
                ]
                if not group_targets:
                    continue
                try:
                    page, results = await self._apply_group_with_captcha(
                        page, group_targets, city, industry
                    )
                except Exception as exc:
                    logger.warning("投递异常: err=%s", exc)
                    results = {
                        t.job_id: ApplyResult(t.job_id, "failed", f"投递异常：{exc}")
                        for t in group_targets
                    }
                for job_id, r in results.items():
                    final[job_id] = r
                if i < len(groups) - 1:
                    await asyncio.sleep(random.uniform(5.0, 10.0))
            for t in targets:
                if t.job_id not in final:
                    final[t.job_id] = ApplyResult(t.job_id, "failed", "未找到可用的搜索条件")
            for r in final.values():
                yield r
        finally:
            await page.close()

    async def _apply_group_with_captcha(
        self, page, group: list[ApplyTarget], city: str, industry: str | None
    ) -> tuple:
        """对一组同（标题,城市,行业）职位执行批量投递，含滑块冷却重试/有头兜底。

        返回 (可能重建的 page, {job_id: ApplyResult})。
        """
        results = await apply_job_group(page, group, city, industry)
        if any(r.status == "captcha" for r in results.values()):
            logger.warning(
                "投递遇滑块验证，冷却 %s 秒后重试: keyword=%s",
                _CAPTCHA_COOLDOWN,
                group[0].title,
            )
            await asyncio.sleep(_CAPTCHA_COOLDOWN)
            results = await apply_job_group(page, group, city, industry)
            if any(r.status == "captcha" for r in results.values()) and await self._degrade_to_headful():
                logger.warning("滑块仍拦截，切换有头模式等待人工验证: keyword=%s", group[0].title)
                page = await self._new_page()
                results = await apply_job_group(
                    page, group, city, industry, manual_wait=MANUAL_CAPTCHA_TIMEOUT
                )
            for job_id, r in results.items():
                if r.status == "captcha":
                    results[job_id] = ApplyResult(job_id, "failed", "验证码未通过")
        return page, results

    async def _click_next_page(self, page, target_page_num: int) -> None:
        """51job 新版 SPA：URL pageNum 参数不生效（实测各页返回同一批职位），
        必须点击分页器按钮触发前端翻页。"""
        next_btn = page.locator(".el-pagination .btn-next, .el-pager .btn-next").first
        await next_btn.click(timeout=15000)
        await page.wait_for_function(
            f"document.querySelector('.el-pager li.number.active')?.textContent.trim() === '{target_page_num}'",
            timeout=15000,
        )
        await page.wait_for_timeout(800)

    async def _fetch_page(
        self, page, keyword: str, page_num: int, area: str = "000000", industry: str | None = None
    ) -> tuple:
        await self._ensure_browser()
        last_result: PageResult | None = None
        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                if page.is_closed() or page_num == 1:
                    if page.is_closed():
                        page = await self._new_page()
                        logger.warning("第 %s 页浏览器已重建，回退为 URL 加载", page_num)
                    url = build_search_url(keyword, page_num, area, industry)
                    await page.goto(url, wait_until="domcontentloaded", timeout=60000)
                else:
                    await self._click_next_page(page, page_num)
                try:
                    await page.wait_for_selector(_JOB_CARD_SELECTOR, timeout=30000)
                except PWTimeoutError:
                    html = await page.content()
                    last_result = parse_search_page(html, page_num)
                    if last_result.failed:
                        if last_result.captcha:
                            if await solve_aliyun_captcha(page):
                                await page.wait_for_selector(_JOB_CARD_SELECTOR, timeout=30000)
                                html = await page.content()
                                last_result = parse_search_page(html, page_num)
                                return last_result, page
                            return last_result, page
                        if last_result.blocked:
                            return last_result, page
                        raise
                if page_num == 1:
                    for _ in range(3):
                        await page.mouse.wheel(0, 1200)
                        await page.wait_for_timeout(random.randint(400, 900))
                    await page.wait_for_timeout(1500)
                html = await page.content()
                last_result = parse_search_page(html, page_num)
                return last_result, page
            except Exception as exc:
                logger.warning("第 %s 页第 %s 次尝试失败: %s", page_num, attempt, exc)
                await asyncio.sleep(attempt * 2.0)
        if last_result is None:
            return PageResult(page_num=page_num, jobs=[], failed=True), page
        return last_result, page

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


async def run_test_login(
    site: str, username: str, password: str, headful: bool = False, use_system_chrome: bool = False
) -> tuple[bool, str]:
    """独立验证凭据可用性（test-login API 使用）。测试通过 monkeypatch 本模块的 login/PlaywrightScraper 完成。"""
    scraper = PlaywrightScraper(headful=headful, use_system_chrome=use_system_chrome)
    try:
        await scraper._ensure_browser()
        page = await scraper._new_page()
        if storage_state_valid(scraper._storage_state) and await _probe_logged_in(page):
            # 已保存的登录状态仍有效：直接复用，免人工验证
            logger.info(
                "test-login 复用已保存的登录状态: site=%s username=%s", site, username
            )
            return True, "登录成功（复用已保存的登录状态）"
        ok, reason = await login(page, site, username, password)
        if not ok and reason == "geetest":
            # 极验风控拒绝 headless：重启为有头模式并等待人工完成验证码
            logger.warning("test-login 检测到极验验证码，切换有头模式等待人工验证")
            await scraper.close()
            scraper = PlaywrightScraper(headful=True, use_system_chrome=use_system_chrome)
            await scraper._ensure_browser()
            page = await scraper._new_page()
            ok, reason = await login(
                page, site, username, password, manual_wait=MANUAL_CAPTCHA_TIMEOUT
            )
        if ok:
            await scraper.save_storage_state()
        msg = "登录成功" if ok else f"登录失败：{reason}"
        return ok, msg
    except Exception as exc:
        logger.warning("test-login 异常: %s", exc)
        return False, f"登录异常: {exc}"
    finally:
        await scraper.close()
