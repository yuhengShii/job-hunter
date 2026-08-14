from datetime import date, datetime, time, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_

from backend.app.api.deps import get_current_user, get_db
from backend.app.core.exceptions import AppError
from backend.app.models import ApplyTask, Company, Favorite, Job
from backend.app.schemas.job import FavoriteAddOut, FavoriteBatchIn, FavoriteRemoveOut, JobFilterOptions, JobOut, JobPage

jobs_router = APIRouter(prefix="/api/jobs", tags=["jobs"])

# 投递结果中视为「已投递」的状态：success=本次投递成功，skipped=站点卡片已标"已投递"自动跳过
_APPLIED_STATUSES = ("success", "skipped")


def _applied_job_ids(db) -> set[str]:
    """从全部投递任务的结果中收集已投递的 job_id（逐条结果状态判定）。"""
    applied: set[str] = set()
    for (results,) in db.query(ApplyTask.results).all():
        for r in results or []:
            if r.get("status") in _APPLIED_STATUSES and r.get("job_id"):
                applied.add(r["job_id"])
    return applied

_SORT_FIELDS: dict[str, object] = {
    "publish_time": Job.publish_time,
    "activity_score": Company.activity_score,
}


def _parse_sort(sort: list[str]) -> list:
    """解析 sort=field:direction（可重复，顺序即优先级），非法返回 400。"""
    orders = []
    for spec in sort:
        field, sep, direction = spec.partition(":")
        if field not in _SORT_FIELDS or not sep:
            raise AppError(f"不支持的排序字段或格式: {spec}", 400)
        if direction not in ("asc", "desc"):
            raise AppError(f"不支持的排序方向: {direction}", 400)
        expr = _SORT_FIELDS[field].desc() if direction == "desc" else _SORT_FIELDS[field].asc()
        orders.append(expr.nulls_last())
    return orders


def _with_company(jobs: list[Job], db) -> list[JobOut]:
    """为职位附加公司名称、活跃度、收藏与投递标记。"""
    applied_ids = _applied_job_ids(db) if jobs else set()
    fav_ids: set[str] = set()
    if jobs:
        fav_ids = {
            f.job_id
            for f in db.query(Favorite)
            .filter(Favorite.job_id.in_([j.job_id for j in jobs]))
            .all()
        }
    ids = {j.company_id for j in jobs if j.company_id}
    comp_map = {
        c.company_id: c
        for c in db.query(Company).filter(Company.company_id.in_(ids)).all()
    }
    out = []
    for j in jobs:
        item = JobOut.model_validate(j)
        item.is_favorite = j.job_id in fav_ids
        item.applied = j.job_id in applied_ids
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
    district: str | None = None,
    area: str | None = None,
    company_id: str | None = None,
    keyword: str | None = None,
    tag: str | None = None,
    salary_min: int | None = None,
    salary_max: int | None = None,
    publish_time_from: date | None = None,
    publish_time_to: date | None = None,
    favorite: bool | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    sort: list[str] = Query([]),
    db=Depends(get_db),
    user=Depends(get_current_user),
):
    q = db.query(Job)
    if city:
        q = q.filter(Job.city == city)
    if district:
        q = q.filter(Job.district == district)
    if area:
        q = q.filter(Job.area == area)
    if company_id:
        q = q.filter(Job.company_id == company_id)
    if keyword:
        q = q.filter(or_(Job.title.contains(keyword), Job.area.contains(keyword)))
    if salary_min is not None:
        q = q.filter(Job.salary_min >= salary_min)
    if salary_max is not None:
        q = q.filter(Job.salary_max <= salary_max)
    if publish_time_from:
        q = q.filter(Job.publish_time >= datetime.combine(publish_time_from, time.min))
    if publish_time_to:
        q = q.filter(Job.publish_time < datetime.combine(publish_time_to, time.min) + timedelta(days=1))
    if tag:
        # tags 为 JSON 数组（SQLite 存储为转义文本，LIKE 不可靠），用相关 EXISTS + json_each 精确匹配
        tags_tv = func.json_each(Job.tags).table_valued("value")
        q = q.filter(db.query(tags_tv.c.value).filter(tags_tv.c.value == tag).exists())
    if favorite is True:
        q = q.filter(Job.job_id.in_(db.query(Favorite.job_id)))
    elif favorite is False:
        q = q.filter(~Job.job_id.in_(db.query(Favorite.job_id)))
    orders = _parse_sort(sort)
    needs_company = any(s.startswith("activity_score") for s in sort)
    if needs_company:
        q = q.outerjoin(Company, Job.company_id == Company.company_id)
    total = q.count()
    start = (page - 1) * page_size
    items = (
        q.order_by(*orders, Job.updated_at.desc())
        .offset(start)
        .limit(page_size)
        .all()
    )
    return JobPage(total=total, items=_with_company(items, db))


@jobs_router.get("/filter-options", response_model=JobFilterOptions)
def job_filter_options(
    city: str | None = None,
    db=Depends(get_db),
    user=Depends(get_current_user),
):
    cities = [
        r[0]
        for r in db.query(Job.city)
        .filter(Job.city.isnot(None))
        .group_by(Job.city)
        .order_by(func.count().desc(), Job.city)
        .all()
    ]
    q = db.query(Job.district).filter(Job.district.isnot(None))
    if city:
        q = q.filter(Job.city == city)
    districts = [r[0] for r in q.group_by(Job.district).order_by(Job.district).all()]
    return JobFilterOptions(cities=cities, districts=districts)


@jobs_router.get("/{job_key}", response_model=JobOut)
def get_job(job_key: str, db=Depends(get_db), user=Depends(get_current_user)):
    job = db.query(Job).filter(Job.job_id == job_key).first()
    if job is None:
        raise AppError("职位不存在", 404)
    return _with_company([job], db)[0]


@jobs_router.post("/favorites", response_model=FavoriteAddOut)
def add_favorites(
    body: FavoriteBatchIn,
    db=Depends(get_db),
    user=Depends(get_current_user),
):
    if not body.job_ids:
        raise AppError("job_ids 不能为空", 400)
    ids = list(dict.fromkeys(body.job_ids))
    existing = {
        f.job_id for f in db.query(Favorite).filter(Favorite.job_id.in_(ids)).all()
    }
    valid = {
        jid
        for (jid,) in db.query(Job.job_id).filter(Job.job_id.in_(ids)).all()
    }
    to_add = valid - existing
    db.add_all([Favorite(job_id=jid) for jid in to_add])
    db.commit()
    return FavoriteAddOut(added=len(to_add), skipped=len(body.job_ids) - len(to_add))


@jobs_router.delete("/favorites", response_model=FavoriteRemoveOut)
def remove_favorites(
    body: FavoriteBatchIn,
    db=Depends(get_db),
    user=Depends(get_current_user),
):
    if not body.job_ids:
        raise AppError("job_ids 不能为空", 400)
    ids = list(dict.fromkeys(body.job_ids))
    existing = {
        f.job_id for f in db.query(Favorite).filter(Favorite.job_id.in_(ids)).all()
    }
    db.query(Favorite).filter(Favorite.job_id.in_(existing)).delete(
        synchronize_session=False
    )
    db.commit()
    return FavoriteRemoveOut(removed=len(existing), skipped=len(body.job_ids) - len(existing))
