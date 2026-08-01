import inspect
from collections.abc import AsyncGenerator

from backend.app.scrapers.base import PageResult, Scraper
from backend.app.scrapers.playwright import PlaywrightScraper


def test_playwright_scraper_implements_interface():
    assert issubclass(PlaywrightScraper, Scraper)
    sig = inspect.signature(PlaywrightScraper.search)
    assert sig.return_annotation == AsyncGenerator[PageResult, None]


def test_scraper_is_async_generator():
    s = PlaywrightScraper(headful=False)
    assert inspect.isasyncgenfunction(s.search)
    assert inspect.iscoroutinefunction(s.fetch_company)
    assert inspect.iscoroutinefunction(s.close)
