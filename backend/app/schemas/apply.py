from datetime import datetime

from pydantic import BaseModel


class ApplyTaskCreate(BaseModel):
    credential_id: int
    job_ids: list[str] | None = None


class ApplyResultOut(BaseModel):
    job_id: str
    title: str
    status: str
    message: str = ""


class ApplyTaskOut(BaseModel):
    id: int
    credential_id: int | None
    credential_username: str
    status: str
    total_count: int
    success_count: int
    failed_count: int
    skipped_count: int
    results: list[ApplyResultOut]
    start_time: datetime | None
    end_time: datetime | None
    error_message: str | None
    created_at: datetime

    model_config = {"from_attributes": True}
