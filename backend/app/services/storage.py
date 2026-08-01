import logging

from sqlalchemy.orm import Session

from backend.app.models import Company, Job
from backend.app.scrapers.base import CompanyDraft, JobDraft

logger = logging.getLogger("job_hunter")


def upsert_jobs(db: Session, jobs: list[JobDraft]) -> int:
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
            existing.tags = j.tags
            existing.publish_time = j.publish_time
            existing.company_id = j.company_id
            existing.job_url = j.job_url
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
                    website=c.website,
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
            if c.website is not None:
                existing.website = c.website
        count += 1
    db.commit()
    return count
