from datetime import datetime

from pydantic import BaseModel


class SiteCredentialCreate(BaseModel):
    site: str
    username: str
    password: str
    remark: str | None = None


class SiteCredentialUpdate(BaseModel):
    remark: str | None = None
    password: str | None = None


class SiteCredentialOut(BaseModel):
    id: int
    site: str
    username: str
    remark: str | None
    has_password: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
