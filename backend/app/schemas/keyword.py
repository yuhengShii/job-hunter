from datetime import datetime

from pydantic import BaseModel


class KeywordCreate(BaseModel):
    keyword: str
    scrape_mode: str = "playwright"


class KeywordUpdate(BaseModel):
    keyword: str | None = None
    scrape_mode: str | None = None


class KeywordOut(BaseModel):
    id: int
    keyword: str
    enabled: bool
    scrape_mode: str
    last_scraped_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}
