from fastapi import APIRouter, Depends, Query

from backend.app.api.deps import get_current_user, get_db
from backend.app.core.exceptions import AppError
from backend.app.models import Job
from backend.app.schemas.job import JobOut, JobPage

jobs_router = APIRouter(prefix="/api/jobs", tags=["jobs"])


@jobs_router.get("", response_model=JobPage)
def list_jobs(
    city: str | None = None,
    company_id: str | None = None,
    tag: str | None = None,
    salary_min: int | None = None,
    salary_max: int | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db=Depends(get_db),
    user=Depends(get_current_user),
):
    q = db.query(Job)
    if city:
        q = q.filter(Job.city == city)
    if company_id:
        q = q.filter(Job.company_id == company_id)
    if salary_min is not None:
        q = q.filter(Job.salary_min >= salary_min)
    if salary_max is not None:
        q = q.filter(Job.salary_max <= salary_max)
    items = q.order_by(Job.updated_at.desc()).all()
    if tag:
        items = [j for j in items if tag in (j.tags or [])]
    total = len(items)
    start = (page - 1) * page_size
    return JobPage(total=total, items=items[start : start + page_size])


@jobs_router.get("/{job_key}", response_model=JobOut)
def get_job(job_key: str, db=Depends(get_db), user=Depends(get_current_user)):
    job = db.query(Job).filter(Job.job_id == job_key).first()
    if job is None:
        raise AppError("职位不存在", 404)
    return job
