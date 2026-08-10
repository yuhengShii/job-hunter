from datetime import datetime

from pydantic import BaseModel


class CompanyOut(BaseModel):
    id: int
    company_id: str
    name: str
    type: str | None
    industry: str | None
    size: str | None
    activity: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class CompanyPage(BaseModel):
    total: int
    items: list[CompanyOut]
