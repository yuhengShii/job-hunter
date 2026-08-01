from pydantic import BaseModel


class ScheduleIn(BaseModel):
    enabled: bool
    interval_minutes: int
    keyword_ids: list[int] = []


class ScheduleOut(ScheduleIn):
    pass
