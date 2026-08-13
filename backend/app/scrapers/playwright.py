import asyncio
import logging
import random
from collections.abc import AsyncGenerator
from urllib.parse import quote

from playwright.async_api import TimeoutError as PWTimeoutError
from playwright.async_api import async_playwright

from backend.app.scrapers.auth import login
from backend.app.scrapers.base import LoginCredential, PageResult, Scraper
from backend.app.scrapers.captcha import solve_aliyun_captcha
from backend.app.scrapers.parser import parse_search_page

logger = logging.getLogger("job_hunter")

_SEARCH_URL = (
    "https://we.51job.com/pc/search?keyword={kw}&searchType=2&sortType=0&pageNum={n}&jobArea={area}"
)


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
_LAUNCH_ARGS = ["--disable-blink-features=AutomationControlled"]
_FINGERPRINT_SCRIPT = """
Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
Object.defineProperty(navigator, 'languages', {get: () => ['zh-CN', 'zh']});
Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});
window.chrome = window.chrome || {runtime: {}};
"""


class PlaywrightScraper(Scraper):
    def __init__(self, headful: bool = False, login_credential: LoginCredential | None = None):
        self._headful = headful
        self._login_credential = login_credential
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
        try:
            await self._ensure_browser()
        except Exception as exc:
            logger.warning("有头模式重启失败: %s", exc)
            return False
        return True

    async def search(
        self, keyword: str, pages: int, area: str = "000000", industry: str | None = None
    ) -> AsyncGenerator[PageResult, None]:
        await self._ensure_browser()
        page = await self._new_page()
        if self._login_credential is not None:
            try:
                logged_in = await login(
                    page,
                    self._login_credential.site,
                    self._login_credential.username,
                    self._login_credential.password,
                )
            except Exception as exc:
                logged_in = False
                logger.warning("登录异常，降级为匿名抓取: %s", exc)
            if not logged_in:
                logger.warning(
                    "登录失败，降级为匿名抓取: site=%s username=%s",
                    self._login_credential.site, self._login_credential.username,
                )
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


async def run_test_login(site: str, username: str, password: str, headful: bool = False) -> tuple[bool, str]:
    """独立验证凭据可用性（test-login API 使用）。测试通过 monkeypatch 本模块的 login/PlaywrightScraper 完成。"""
    scraper = PlaywrightScraper(headful=headful)
    try:
        await scraper._ensure_browser()
        page = await scraper._new_page()
        ok = await login(page, site, username, password)
        msg = "登录成功" if ok else "登录失败（账号密码错误、验证码未通过或风控拦截）"
        return ok, msg
    except Exception as exc:
        logger.warning("test-login 异常: %s", exc)
        return False, f"登录异常: {exc}"
    finally:
        await scraper.close()
