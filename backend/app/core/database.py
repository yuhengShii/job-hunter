import logging
from collections.abc import Generator

from sqlalchemy import Engine, create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from backend.app.core.config import Config
from backend.app.services.activity import score_activity

logger = logging.getLogger("job_hunter")

engine: Engine | None = None
SessionLocal: sessionmaker[Session] = sessionmaker(autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def _migrate_keywords_city(engine) -> None:
    """轻量迁移：keywords 表增加 city 列，唯一约束改为 (keyword, city) 联合唯一。

    create_all 不会修改已有表，故对旧库做幂等 DDL：
    1. 缺 city 列时重建表补列；
    2. 旧模型 unique=True 在 SQLite 生成内联 UNIQUE 约束（sqlite_autoindex_*），
       必须重建表才能移除；重建后改为命名唯一索引 uq_keywords_keyword_city，
       与新建库（create_all 生成）结构一致，避免每次启动重复重建。
    """
    insp = inspect(engine)
    if "keywords" not in insp.get_table_names():
        return
    cols = {c["name"] for c in insp.get_columns("keywords")}
    with engine.connect() as conn:
        # PRAGMA index_list 返回: (seq, name, unique, origin, partial) —— 索引名在第 2 列
        idx_names = [r[1] for r in conn.execute(text("PRAGMA index_list(keywords)"))]
    has_old_unique = "sqlite_autoindex_keywords_1" in idx_names
    # 关键判据：只要旧的内联单列 UNIQUE 约束还在，就必须重建表移除它。
    # （uq_keywords_keyword_city 索引可能存在残留，不能作为跳过重建的理由。）
    if "city" in cols and not has_old_unique:
        return
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE keywords_new (
                    id INTEGER NOT NULL PRIMARY KEY,
                    keyword VARCHAR(128) NOT NULL,
                    city VARCHAR(64) NOT NULL DEFAULT '000000',
                    enabled BOOLEAN DEFAULT 1,
                    scrape_mode VARCHAR(32) DEFAULT 'playwright',
                    last_scraped_at DATETIME,
                    created_at DATETIME
                )
                """
            )
        )
        conn.execute(
            text(
                """
                INSERT INTO keywords_new (id, keyword, enabled, scrape_mode, last_scraped_at, created_at, city)
                SELECT id, keyword, enabled, scrape_mode, last_scraped_at, created_at,
                       COALESCE(city, '000000') FROM keywords
                """
            )
        )
        conn.execute(text("DROP TABLE keywords"))
        conn.execute(text("ALTER TABLE keywords_new RENAME TO keywords"))
        conn.execute(
            text("CREATE UNIQUE INDEX uq_keywords_keyword_city ON keywords (keyword, city)")
        )
    logger.info("迁移完成：keywords 增加 city 列，唯一约束改为 (keyword, city)")


def _migrate_companies_activity_score(engine) -> None:
    """轻量迁移：companies 表增加 activity_score 列（-1 表示未知）并按 activity 回填。

    create_all 不会修改已有表，故对旧库做幂等 DDL：
    缺列时 ALTER TABLE 补列，再按现有 activity 文案计算分数回填。
    """
    insp = inspect(engine)
    if "companies" not in insp.get_table_names():
        return
    cols = {c["name"] for c in insp.get_columns("companies")}
    if "activity_score" in cols:
        return
    with engine.begin() as conn:
        conn.execute(
            text("ALTER TABLE companies ADD COLUMN activity_score INTEGER NOT NULL DEFAULT -1")
        )
        rows = conn.execute(
            text("SELECT id, activity FROM companies WHERE activity IS NOT NULL")
        ).fetchall()
        for row_id, activity in rows:
            conn.execute(
                text("UPDATE companies SET activity_score = :s WHERE id = :i"),
                {"s": score_activity(activity), "i": row_id},
            )
    logger.info("迁移完成：companies 增加 activity_score 列并回填")


def _migrate_jobs_degree_year(engine) -> None:
    """轻量迁移：jobs 表增加 degree（学历）与 year（工作年限）列。

    create_all 不会修改已有表，故对旧库做幂等 DDL；
    历史行无数据可回填，置 NULL，由后续抓取补充。
    """
    insp = inspect(engine)
    if "jobs" not in insp.get_table_names():
        return
    cols = {c["name"] for c in insp.get_columns("jobs")}
    if "degree" in cols and "year" in cols:
        return
    with engine.begin() as conn:
        if "degree" not in cols:
            conn.execute(text("ALTER TABLE jobs ADD COLUMN degree VARCHAR(32)"))
        if "year" not in cols:
            conn.execute(text("ALTER TABLE jobs ADD COLUMN year VARCHAR(32)"))
    logger.info("迁移完成：jobs 增加 degree/year 列")


def _migrate_jobs_job_url(engine) -> None:
    """轻量迁移：为缺失 job_url 的职位按 job_id 构造标准 51job 链接。

    搜索卡片与 sensorsdata 均不含职位链接，按固定格式
    https://jobs.51job.com/all/{job_id}.html 构造；幂等，可反复执行。
    """
    insp = inspect(engine)
    if "jobs" not in insp.get_table_names():
        return
    cols = {c["name"] for c in insp.get_columns("jobs")}
    if "job_url" not in cols:
        return
    with engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE jobs SET job_url = 'https://jobs.51job.com/all/' || job_id || '.html' "
                "WHERE job_url IS NULL OR job_url = ''"
            )
        )
    logger.info("迁移完成：回填缺失的 job_url")


def _migrate_tasks_max_pages(engine) -> None:
    """轻量迁移：scrape_tasks 表增加 max_pages 列（per-task 页数上限，NULL=全局上限）。"""
    insp = inspect(engine)
    if "scrape_tasks" not in insp.get_table_names():
        return
    cols = {c["name"] for c in insp.get_columns("scrape_tasks")}
    if "max_pages" in cols:
        return
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE scrape_tasks ADD COLUMN max_pages INTEGER"))
    logger.info("迁移完成：scrape_tasks 增加 max_pages 列")


def _migrate_companies_drop_website(engine) -> None:
    """轻量迁移：companies 表删除 website 列（公司网址不再抓取，PRD §4 已移除）。"""
    insp = inspect(engine)
    if "companies" not in insp.get_table_names():
        return
    cols = {c["name"] for c in insp.get_columns("companies")}
    if "website" not in cols:
        return
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE companies DROP COLUMN website"))
    logger.info("迁移完成：companies 删除 website 列")


def init_db(config: Config) -> None:
    global engine
    engine = create_engine(config.database_url, connect_args={"check_same_thread": False})
    SessionLocal.configure(bind=engine)
    import backend.app.models  # noqa: F401 确保模型注册

    Base.metadata.create_all(engine)
    _migrate_keywords_city(engine)
    _migrate_companies_activity_score(engine)
    _migrate_jobs_degree_year(engine)
    _migrate_jobs_job_url(engine)
    _migrate_tasks_max_pages(engine)
    _migrate_companies_drop_website(engine)
