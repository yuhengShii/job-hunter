from datetime import datetime

from pydantic import BaseModel


class JobOut(BaseModel):
    id: int
    job_id: str
    title: str
    salary_raw: str | None
    salary_min: int | None
    salary_max: int | None
    city: str | None
    district: str | None
    area: str | None
    degree: str | None
    year: str | None
    tags: list[str]
    publish_time: datetime | None
    source: str
    company_id: str | None
    company_name: str | None = None
    company_activity: str | None = None
    company_activity_score: int = -1
    is_favorite: bool = False
    applied: bool = False
    job_url: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class JobPage(BaseModel):
    total: int
    items: list[JobOut]


class JobFilterOptions(BaseModel):
    cities: list[str]
    districts: list[str]


class FavoriteBatchIn(BaseModel):
    job_ids: list[str]


class FavoriteAddOut(BaseModel):
    added: int = 0
    skipped: int = 0


class FavoriteRemoveOut(BaseModel):
    removed: int = 0
    skipped: int = 0
