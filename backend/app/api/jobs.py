from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_

from backend.app.api.deps import get_current_user, get_db
from backend.app.core.exceptions import AppError
from backend.app.models import Company, Job
from backend.app.schemas.job import JobOut, JobPage

jobs_router = APIRouter(prefix="/api/jobs", tags=["jobs"])


def _with_company(jobs: list[Job], db) -> list[JobOut]:
    """为职位附加公司名称与活跃度（来自 companies 表）。"""
    ids = {j.company_id for j in jobs if j.company_id}
    comp_map = {
        c.company_id: c
        for c in db.query(Company).filter(Company.company_id.in_(ids)).all()
    }
    out = []
    for j in jobs:
        item = JobOut.model_validate(j)
        c = comp_map.get(j.company_id)
        if c:
            item.company_name = c.name
            item.company_activity = c.activity
            item.company_activity_score = c.activity_score
        out.append(item)
    return out


@jobs_router.get("", response_model=JobPage)
def list_jobs(
    city: str | None = None,
    company_id: str | None = None,
    keyword: str | None = None,
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
    if keyword:
        q = q.filter(or_(Job.title.contains(keyword), Job.area.contains(keyword)))
    if salary_min is not None:
        q = q.filter(Job.salary_min >= salary_min)
    if salary_max is not None:
        q = q.filter(Job.salary_max <= salary_max)
    if tag:
        # tags 为 JSON 数组（SQLite 存储为转义文本，LIKE 不可靠），用相关 EXISTS + json_each 精确匹配
        tags_tv = func.json_each(Job.tags).table_valued("value")
        q = q.filter(db.query(tags_tv.c.value).filter(tags_tv.c.value == tag).exists())
    total = q.count()
    start = (page - 1) * page_size
    items = (
        q.order_by(Job.updated_at.desc())
        .offset(start)
        .limit(page_size)
        .all()
    )
    return JobPage(total=total, items=_with_company(items, db))


@jobs_router.get("/{job_key}", response_model=JobOut)
def get_job(job_key: str, db=Depends(get_db), user=Depends(get_current_user)):
    job = db.query(Job).filter(Job.job_id == job_key).first()
    if job is None:
        raise AppError("职位不存在", 404)
    return _with_company([job], db)[0]
