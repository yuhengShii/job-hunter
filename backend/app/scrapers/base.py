from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class JobDraft:
    job_id: str
    title: str
    salary_raw: str | None = None
    salary_min: int | None = None
    salary_max: int | None = None
    city: str | None = None
    district: str | None = None
    area: str | None = None
    tags: list[str] = field(default_factory=list)
    publish_time: datetime | None = None
    company_id: str | None = None
    job_url: str | None = None


@dataclass
class CompanyDraft:
    company_id: str
    name: str | None = None
    type: str | None = None
    industry: str | None = None
    size: str | None = None
    activity: str | None = None
    website: str | None = None


@dataclass
class PageResult:
    page_num: int
    jobs: list[JobDraft]
    companies: list[CompanyDraft] = field(default_factory=list)
    total_pages: int | None = None
    failed: bool = False
    blocked: bool = False
    captcha: bool = False


class Scraper(ABC):
    @abstractmethod
    async def search(
        self, keyword: str, pages: int, area: str = "000000"
    ) -> AsyncGenerator[PageResult, None]:
        """按关键字搜索职位。area 为 51job 城市编码（000000 = 全国）。"""
        ...

    @abstractmethod
    async def fetch_company(self, company_id: str, company_url: str) -> CompanyDraft | None:
        ...

    @abstractmethod
    async def close(self) -> None:
        ...
