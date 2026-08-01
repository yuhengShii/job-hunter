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


class PlaywrightScraper(Scraper):
    def __init__(self, headful: bool = False):
        self._headful = headful
        self._playwright = None
        self._browser = None

    async def _ensure_browser(self):
        if self._browser:
            return
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(headless=not self._headful)

    async def _new_page(self):
        ua = random.choice(
            [
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
            ]
        )
        page = await self._browser.new_page(user_agent=ua, viewport={"width": 1600, "height": 1000})
        return page

    async def search(self, keyword: str, pages: int) -> AsyncGenerator[PageResult, None]:
        await self._ensure_browser()
        for n in range(1, pages + 1):
            result = await self._fetch_page(keyword, n)
            if result.failed:
                logger.warning("第 %s 页抓取失败（已重试）: keyword=%s", n, keyword)
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
        if self._browser:
            await self._browser.close()
            self._browser = None
        if self._playwright:
            await self._playwright.stop()
            self._playwright = None
