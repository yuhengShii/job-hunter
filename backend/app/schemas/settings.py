from pydantic import BaseModel


class ScheduleIn(BaseModel):
    enabled: bool
    interval_minutes: int
    keyword_ids: list[int] = []


class ScheduleOut(ScheduleIn):
    pass


class ScraperLoginIn(BaseModel):
    enabled: bool
    credential_id: int | None = None


class ScraperLoginOut(ScraperLoginIn):
    pass
