import asyncio
import logging
import random
from collections.abc import AsyncGenerator
from urllib.parse import quote

from playwright.async_api import TimeoutError as PWTimeoutError
from playwright.async_api import async_playwright

from backend.app.scrapers.base import CompanyDraft, PageResult, Scraper
from backend.app.scrapers.captcha import solve_aliyun_captcha
from backend.app.scrapers.parser import parse_company_page, parse_search_page

logger = logging.getLogger("job_hunter")

_SEARCH_URL = "https://we.51job.com/pc/search?keyword={kw}&searchType=2&sortType=0&pageNum={n}"
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

    async def search(self, keyword: str, pages: int) -> AsyncGenerator[PageResult, None]:
        await self._ensure_browser()
        consecutive_failures = 0
        consecutive_captcha = 0
        for n in range(1, pages + 1):
            result = await self._fetch_page(keyword, n)
            if result.failed:
                if result.captcha:
                    consecutive_failures = 0
                    logger.warning("滑块验证未通过，冷却 %s 秒后重试: page=%s", _CAPTCHA_COOLDOWN, n)
                    await asyncio.sleep(_CAPTCHA_COOLDOWN)
                    result = await self._fetch_page(keyword, n)
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
                        result = await self._fetch_page(keyword, n)
                    if result.failed:
                        logger.warning("第 %s 页抓取失败（已重试）: keyword=%s", n, keyword)
                    else:
                        consecutive_failures = 0
                else:
                    consecutive_captcha = 0
                    consecutive_failures += 1
                    degraded = consecutive_failures >= 2 and await self._degrade_to_headful()
                    if degraded:
                        result = await self._fetch_page(keyword, n)
                    if result.failed:
                        logger.warning("第 %s 页抓取失败（已重试）: keyword=%s", n, keyword)
                    else:
                        consecutive_failures = 0
            else:
                consecutive_captcha = 0
                consecutive_failures = 0
            yield result
            await asyncio.sleep(random.uniform(3.0, 8.0))

    async def _fetch_page(self, keyword: str, page_num: int) -> PageResult:
        await self._ensure_browser()
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
