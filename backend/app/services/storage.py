import logging
from datetime import datetime

from sqlalchemy.orm import Session

from backend.app.models import Company, Job, JobSource
from backend.app.scrapers.base import CompanyDraft, JobDraft
from backend.app.services.activity import score_activity

logger = logging.getLogger("job_hunter")


def upsert_job_source(db: Session, job_id: str, source: tuple[str, str, str | None]) -> int:
    """记录「某职位被某组搜索条件命中过」：同条件只刷新 last_seen_at，不同条件新增一行。"""
    keyword, city, industry = source
    row = (
        db.query(JobSource)
        .filter_by(
            job_id=job_id,
            source_keyword=keyword,
            source_city=city,
            source_industry=industry,
        )
        .first()
    )
    if row is None:
        db.add(
            JobSource(
                job_id=job_id,
                source_keyword=keyword,
                source_city=city,
                source_industry=industry,
            )
        )
        return 1
    row.last_seen_at = datetime.now()
    return 0


def upsert_jobs(
    db: Session, jobs: list[JobDraft], source: tuple[str, str, str | None] | None = None
) -> int:
    count = 0
    for j in jobs:
        existing = db.query(Job).filter_by(job_id=j.job_id).first()
        if existing is None:
            db.add(
                Job(
                    job_id=j.job_id,
                    title=j.title,
                    salary_raw=j.salary_raw,
                    salary_min=j.salary_min,
                    salary_max=j.salary_max,
                    city=j.city,
                    district=j.district,
                    area=j.area,
                    degree=j.degree,
                    year=j.year,
                    tags=j.tags,
                    publish_time=j.publish_time,
                    company_id=j.company_id,
                    job_url=j.job_url,
                )
            )
        else:
            existing.title = j.title
            existing.salary_raw = j.salary_raw
            existing.salary_min = j.salary_min
            existing.salary_max = j.salary_max
            existing.city = j.city
            existing.district = j.district
            existing.area = j.area
            existing.degree = j.degree
            existing.year = j.year
            existing.tags = j.tags
            existing.publish_time = j.publish_time
            existing.company_id = j.company_id
            existing.job_url = j.job_url
            existing.updated_at = datetime.now()
        if source is not None:
            upsert_job_source(db, j.job_id, source)
        count += 1
    db.commit()
    return count


def upsert_companies(db: Session, companies: list[CompanyDraft]) -> int:
    count = 0
    for c in companies:
        existing = db.query(Company).filter_by(company_id=c.company_id).first()
        if existing is None:
            db.add(
                Company(
                    company_id=c.company_id,
                    name=c.name,
                    type=c.type,
                    industry=c.industry,
                    size=c.size,
                    activity=c.activity,
                    activity_score=score_activity(c.activity),
                )
            )
        else:
            if c.name is not None:
                existing.name = c.name
            if c.type is not None:
                existing.type = c.type
            if c.industry is not None:
                existing.industry = c.industry
            if c.size is not None:
                existing.size = c.size
            if c.activity is not None:
                existing.activity = c.activity
                existing.activity_score = score_activity(c.activity)
        count += 1
    db.commit()
    return count
