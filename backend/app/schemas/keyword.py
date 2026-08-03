from datetime import datetime

from pydantic import BaseModel

from backend.app.models.keyword import DEFAULT_CITY


class KeywordCreate(BaseModel):
    keyword: str
    scrape_mode: str = "playwright"
    city: str = DEFAULT_CITY


class KeywordUpdate(BaseModel):
    keyword: str | None = None
    scrape_mode: str | None = None
    city: str | None = None


class KeywordOut(BaseModel):
    id: int
    keyword: str
    city: str
    enabled: bool
    scrape_mode: str
    last_scraped_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}
