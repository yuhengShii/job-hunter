import re
from datetime import datetime

from pydantic import BaseModel, field_validator

from backend.app.models.keyword import DEFAULT_CITY

_INDUSTRY_RE = re.compile(r"^\d{2}(,\d{2})*$")
_MAX_INDUSTRIES = 5


def _normalize_industry(v: str | None) -> str | None:
    if v is None or not v.strip():
        return None
    v = v.strip()
    if len(v.split(",")) > _MAX_INDUSTRIES or not _INDUSTRY_RE.match(v):
        raise ValueError(f"industry 需为逗号分隔的行业编码（≤{_MAX_INDUSTRIES} 个），如 '08,46,47'")
    return v


class KeywordCreate(BaseModel):
    keyword: str
    scrape_mode: str = "playwright"
    city: str = DEFAULT_CITY
    industry: str | None = None

    _normalize_industry = field_validator("industry")(_normalize_industry)


class KeywordUpdate(BaseModel):
    keyword: str | None = None
    scrape_mode: str | None = None
    city: str | None = None
    industry: str | None = None

    _normalize_industry = field_validator("industry")(_normalize_industry)


class KeywordOut(BaseModel):
    id: int
    keyword: str
    city: str
    enabled: bool
    scrape_mode: str
    industry: str | None
    last_scraped_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}
