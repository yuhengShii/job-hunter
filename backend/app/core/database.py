import logging
from collections.abc import Generator

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from backend.app.core.config import Config
from backend.app.services.activity import score_activity

logger = logging.getLogger("job_hunter")

engine: object = None
SessionLocal: sessionmaker = sessionmaker(autoflush=False, expire_on_commit=False)


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


def init_db(config: Config) -> None:
    global engine
    engine = create_engine(config.database_url, connect_args={"check_same_thread": False})
    SessionLocal.configure(bind=engine)
    import backend.app.models  # noqa: F401 确保模型注册

    Base.metadata.create_all(engine)
    _migrate_keywords_city(engine)
    _migrate_companies_activity_score(engine)
