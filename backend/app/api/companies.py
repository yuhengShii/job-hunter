from fastapi import APIRouter, Depends, Query

from backend.app.api.deps import get_current_user, get_db
from backend.app.models import Company
from backend.app.schemas.company import CompanyOut, CompanyPage

companies_router = APIRouter(prefix="/api/companies", tags=["companies"])


@companies_router.get("", response_model=CompanyPage)
def list_companies(
    type: str | None = None,
    industry: str | None = None,
    size: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db=Depends(get_db),
    user=Depends(get_current_user),
):
    q = db.query(Company)
    if type:
        q = q.filter(Company.type == type)
    if industry:
        q = q.filter(Company.industry.contains(industry))
    if size:
        q = q.filter(Company.size == size)
    total = q.count()
    items = q.order_by(Company.updated_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
    return CompanyPage(total=total, items=items)
