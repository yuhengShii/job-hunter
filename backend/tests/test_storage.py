from backend.app.core.database import SessionLocal, init_db
from backend.app.models import Company, Job
from backend.app.scrapers.base import CompanyDraft, JobDraft
from backend.app.services.storage import upsert_companies, upsert_jobs


def test_upsert_jobs_updates_existing(config):
    init_db(config)
    with SessionLocal() as s:
        upsert_jobs(s, [JobDraft(job_id="j1", title="旧标题", salary_raw="1-2万", tags=["a"])])
        s.commit()
        upsert_jobs(s, [JobDraft(job_id="j1", title="新标题", salary_raw="3-5万", tags=["b"])])
        s.commit()
        assert s.query(Job).count() == 1
        job = s.query(Job).filter_by(job_id="j1").one()
        assert job.title == "新标题"
        assert job.tags == ["b"]


def test_upsert_jobs_stores_degree_and_year(config):
    init_db(config)
    with SessionLocal() as s:
        upsert_jobs(s, [JobDraft(job_id="j2", title="T", degree="本科", year="3-4年")])
        s.commit()
        job = s.query(Job).filter_by(job_id="j2").one()
        assert job.degree == "本科"
        assert job.year == "3-4年"
    with SessionLocal() as s:
        upsert_jobs(s, [JobDraft(job_id="j2", title="T2", degree="硕士", year="5-10年")])
        s.commit()
        job = s.query(Job).filter_by(job_id="j2").one()
        assert job.degree == "硕士"
        assert job.year == "5-10年"


def test_upsert_companies_keeps_existing_fields(config):
    init_db(config)
    with SessionLocal() as s:
        upsert_companies(s, [CompanyDraft(company_id="c1", name="A公司", type="民营", industry="软件", size="100人")])
        s.commit()
        upsert_companies(s, [CompanyDraft(company_id="c1", name="A公司", type=None, industry=None, size=None)])
        s.commit()
        comp = s.query(Company).filter_by(company_id="c1").one()
        assert comp.type == "民营"
        assert comp.industry == "软件"
        assert comp.size == "100人"


def test_upsert_companies_stores_activity_score(config):
    init_db(config)
    with SessionLocal() as s:
        upsert_companies(s, [CompanyDraft(company_id="c2", name="B公司", activity="今日回复10+次")])
        s.commit()
        comp = s.query(Company).filter_by(company_id="c2").one()
        assert comp.activity_score == 10
    with SessionLocal() as s:
        upsert_companies(s, [CompanyDraft(company_id="c2", name="B公司", activity="回复率高、5分钟前处理简历")])
        s.commit()
        comp = s.query(Company).filter_by(company_id="c2").one()
        assert comp.activity_score == 8
    with SessionLocal() as s:
        upsert_companies(s, [CompanyDraft(company_id="c2", name="B公司", activity=None)])
        s.commit()
        comp = s.query(Company).filter_by(company_id="c2").one()
        assert comp.activity_score == 8


def test_upsert_companies_default_score_unknown(config):
    init_db(config)
    with SessionLocal() as s:
        upsert_companies(s, [CompanyDraft(company_id="c3", name="C公司", activity=None)])
        s.commit()
        comp = s.query(Company).filter_by(company_id="c3").one()
        assert comp.activity_score == -1
