from datetime import datetime

from pydantic import BaseModel


class TaskCreate(BaseModel):
    keyword_id: int
    mode: str = "playwright"
    max_pages: int | None = None
    login_credential_id: int | None = None


class TaskOut(BaseModel):
    id: int
    keyword_id: int
    mode: str
    max_pages: int | None
    status: str
    total_pages: int | None
    total_found: int
    success_count: int
    failed_count: int
    last_page: int
    start_time: datetime | None
    end_time: datetime | None
    error_message: str | None
    created_at: datetime
    login_credential_id: int | None
    login_username: str | None = None

    model_config = {"from_attributes": True}
