import logging
from collections import Counter
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from backend.app.models import Company, Job, JobSource, Keyword, ScrapeTask, TaskStatus

logger = logging.getLogger("job_hunter")

_DONE = (TaskStatus.SUCCESS.value, TaskStatus.PARTIAL_SUCCESS.value)


def get_window_start(db: Session, keyword_id: int | None = None) -> datetime | None:
    q = db.query(ScrapeTask).filter(ScrapeTask.status.in_(_DONE))
    if keyword_id is not None:
        q = q.filter(ScrapeTask.keyword_id == keyword_id)
    task = q.order_by(ScrapeTask.start_time.desc()).first()
    return task.start_time if task else None


def _keyword_scope(db: Session, keyword_id: int | None, since: datetime | None):
    """返回限定到某关键字命中职位（job_sources）的子查询；keyword 不存在时返回 None（不附加过滤）。

    窗口内命中按 last_seen_at 判定：job_sources 与 jobs.updated_at 在同一任务提交中写入，
    时间口径一致；仅按 (source_keyword, source_city) 匹配，industry 变化不影响归属。
    """
    if keyword_id is None:
        return None
    kw = db.get(Keyword, keyword_id)
    if kw is None:
        return None
    src = db.query(JobSource.job_id).filter(
        JobSource.source_keyword == kw.keyword,
        JobSource.source_city == kw.city,
    )
    if since is not None:
        src = src.filter(JobSource.last_seen_at >= since)
    return src


def _windowed_jobs(db: Session, window: datetime | None, keyword_id: int | None = None):
    q = db.query(Job)
    if window is not None:
        q = q.filter(Job.updated_at >= window)
    scope = _keyword_scope(db, keyword_id, window)
    if scope is not None:
        q = q.filter(Job.job_id.in_(scope))
    return q


def overview(db: Session, window: datetime | None, keyword_id: int | None = None) -> dict:
    jobs = _windowed_jobs(db, window, keyword_id).all()
    companies = {j.company_id for j in jobs if j.company_id}
    salary_parsed = sum(1 for j in jobs if j.salary_min is not None and j.salary_max is not None)
    return {
        "total_jobs": len(jobs),
        "total_cities": len({j.city for j in jobs if j.city}),
        "total_companies": len(companies),
        "salary_parsed": salary_parsed,
    }


def _median(values: list[int]) -> int:
    ordered = sorted(values)
    n = len(ordered)
    if n % 2 == 1:
        return ordered[n // 2]
    return (ordered[n // 2 - 1] + ordered[n // 2]) // 2


def salary_stats(db: Session, window: datetime | None, group_by: str = "city", keyword_id: int | None = None) -> dict:
    jobs = [j for j in _windowed_jobs(db, window, keyword_id).all() if j.salary_min is not None and j.salary_max is not None]
    groups: dict[str, list[tuple[int, int]]] = {}
    for j in jobs:
        key = getattr(j, group_by, None) or "未知"
        groups.setdefault(key, []).append((j.salary_min, j.salary_max))
    result = []
    for key, pairs in sorted(groups.items()):
        mids = [(a + b) // 2 for a, b in pairs]
        result.append({
            "key": key,
            "count": len(pairs),
            "min": min(mids),
            "max": max(mids),
            "median": _median(mids),
            "median_max": _median([b for _, b in pairs]),
            "median_min": _median([a for a, _ in pairs]),
        })
    return {"group_by": group_by, "items": result}


def company_stats(db: Session, window: datetime | None, keyword_id: int | None = None) -> dict:
    jobs = _windowed_jobs(db, window, keyword_id).all()
    company_ids = {j.company_id for j in jobs if j.company_id}
    if not company_ids:
        return {"industry": [], "type": [], "size": []}
    comps = db.query(Company).filter(Company.company_id.in_(company_ids)).all()
    return {
        "industry": _counts(c.industry for c in comps),
        "type": _counts(c.type for c in comps),
        "size": _counts(c.size for c in comps),
    }


def _counts(values) -> list[dict]:
    counter = Counter(v for v in values if v)
    total = sum(counter.values()) or 1
    return [{"key": k, "count": n, "ratio": round(n / total, 4)} for k, n in counter.most_common()]


def trend_stats(
    db: Session,
    window: datetime | None,
    days: int = 30,
    group_by: str | None = None,
    keyword_id: int | None = None,
) -> dict:
    start = window or datetime.now() - timedelta(days=days)
    q = db.query(Job).filter(Job.updated_at >= start)
    scope = _keyword_scope(db, keyword_id, start)
    if scope is not None:
        q = q.filter(Job.job_id.in_(scope))
    jobs = q.all()

    def day_of(j: Job) -> str:
        return (j.publish_time or j.updated_at).date().isoformat()

    if group_by is None:
        per_day: Counter = Counter()
        for j in jobs:
            per_day[day_of(j)] += 1
        return {"group_by": None, "days": [{"date": d, "count": n} for d, n in sorted(per_day.items())]}
    per_key: dict[str, Counter] = {}
    for j in jobs:
        key = getattr(j, group_by, None) or "未知"
        per_key.setdefault(key, Counter())[day_of(j)] += 1
    dates = sorted({d for c in per_key.values() for d in c})
    series = [
        {"key": k, "points": [{"date": d, "count": c.get(d, 0)} for d in dates]}
        for k, c in sorted(per_key.items())
    ]
    return {"group_by": group_by, "series": series}


def tag_stats(db: Session, window: datetime | None, top_n: int = 10, keyword_id: int | None = None) -> list[dict]:
    counter: Counter = Counter()
    for j in _windowed_jobs(db, window, keyword_id).all():
        for t in j.tags or []:
            counter[t] += 1
    return [{"tag": t, "count": n} for t, n in counter.most_common(top_n)]


def distribution_stats(db: Session, window: datetime | None, group_by: str = "city", keyword_id: int | None = None) -> dict:
    jobs = _windowed_jobs(db, window, keyword_id).all()
    counter: Counter = Counter()
    for j in jobs:
        key = getattr(j, group_by, None) or "未知"
        counter[key] += 1
    items = [{"key": k, "count": n} for k, n in counter.most_common()]
    return {"group_by": group_by, "items": items}
