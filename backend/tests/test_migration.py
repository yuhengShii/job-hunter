from sqlalchemy import create_engine, inspect, text

from backend.app.core import database


def test_migrate_keywords_industry_adds_column(tmp_path):
    eng = create_engine(f"sqlite:///{tmp_path / 'old.db'}")
    with eng.begin() as conn:
        conn.execute(text(
            "CREATE TABLE keywords (id INTEGER NOT NULL PRIMARY KEY, "
            "keyword VARCHAR(128) NOT NULL, city VARCHAR(64) NOT NULL DEFAULT '000000', "
            "enabled BOOLEAN DEFAULT 1, scrape_mode VARCHAR(32) DEFAULT 'playwright', "
            "last_scraped_at DATETIME, created_at DATETIME)"
        ))
        conn.execute(text("INSERT INTO keywords (keyword, city) VALUES ('python', '020000')"))
    database._migrate_keywords_industry(eng)
    cols = {c["name"] for c in inspect(eng).get_columns("keywords")}
    assert "industry" in cols
    with eng.connect() as conn:
        assert conn.execute(text("SELECT industry FROM keywords")).scalar() is None


def test_migrate_keywords_industry_idempotent(tmp_path):
    eng = create_engine(f"sqlite:///{tmp_path / 'old.db'}")
    with eng.begin() as conn:
        conn.execute(text(
            "CREATE TABLE keywords (id INTEGER NOT NULL PRIMARY KEY, "
            "keyword VARCHAR(128) NOT NULL, city VARCHAR(64) NOT NULL DEFAULT '000000', "
            "enabled BOOLEAN DEFAULT 1, scrape_mode VARCHAR(32) DEFAULT 'playwright', "
            "last_scraped_at DATETIME, created_at DATETIME)"
        ))
    database._migrate_keywords_industry(eng)
    database._migrate_keywords_industry(eng)  # 第二次执行不报错


def test_migrate_tasks_login_credential_id_adds_column(tmp_path):
    eng = create_engine(f"sqlite:///{tmp_path / 'old.db'}")
    with eng.begin() as conn:
        conn.execute(text(
            "CREATE TABLE scrape_tasks (id INTEGER NOT NULL PRIMARY KEY, "
            "keyword_id INTEGER NOT NULL, status VARCHAR(32) DEFAULT 'queued')"
        ))
    database._migrate_tasks_login_credential_id(eng)
    cols = {c["name"] for c in inspect(eng).get_columns("scrape_tasks")}
    assert "login_credential_id" in cols


def test_migrate_tasks_login_credential_id_idempotent(tmp_path):
    eng = create_engine(f"sqlite:///{tmp_path / 'old.db'}")
    with eng.begin() as conn:
        conn.execute(text(
            "CREATE TABLE scrape_tasks (id INTEGER NOT NULL PRIMARY KEY, "
            "keyword_id INTEGER NOT NULL, status VARCHAR(32) DEFAULT 'queued')"
        ))
    database._migrate_tasks_login_credential_id(eng)
    database._migrate_tasks_login_credential_id(eng)  # 第二次执行不报错


def test_migrate_job_sources_backfills_from_task_windows(tmp_path):
    """成功任务的窗口内职位回填源条件；不同任务的多条件多行共存；幂等。"""
    eng = create_engine(f"sqlite:///{tmp_path / 'old.db'}")
    with eng.begin() as conn:
        conn.execute(text(
            "CREATE TABLE job_sources (id INTEGER NOT NULL PRIMARY KEY, "
            "job_id VARCHAR(64) NOT NULL, source_keyword VARCHAR(128) NOT NULL, "
            "source_city VARCHAR(64) NOT NULL, source_industry VARCHAR(128), "
            "first_seen_at DATETIME, last_seen_at DATETIME)"
        ))
        conn.execute(text(
            "CREATE TABLE jobs (id INTEGER NOT NULL PRIMARY KEY, job_id VARCHAR(64) NOT NULL, "
            "title VARCHAR(255), updated_at DATETIME)"
        ))
        conn.execute(text(
            "CREATE TABLE scrape_tasks (id INTEGER NOT NULL PRIMARY KEY, keyword_id INTEGER NOT NULL, "
            "status VARCHAR(32), start_time DATETIME, end_time DATETIME)"
        ))
        conn.execute(text(
            "CREATE TABLE keywords (id INTEGER NOT NULL PRIMARY KEY, keyword VARCHAR(128) NOT NULL, "
            "city VARCHAR(64) NOT NULL, industry VARCHAR(128))"
        ))
        conn.execute(text(
            "INSERT INTO keywords VALUES (1, '采购', '020000', '08,46,47'), (2, '医疗采购', '010000', NULL)"
        ))
        conn.execute(text(
            "INSERT INTO scrape_tasks VALUES "
            "(1, 1, 'success', '2026-08-13 21:55:00', '2026-08-13 22:01:00'), "
            "(2, 2, 'success', '2026-08-14 01:00:00', '2026-08-14 01:10:00')"
        ))
        # j1 落在任务1窗口内；j2 落在两个任务窗口内；j3 不在任何窗口
        conn.execute(text(
            "INSERT INTO jobs VALUES "
            "(1, 'j1', '采购专员', '2026-08-13 21:56:00'), "
            "(2, 'j2', '采购员', '2026-08-14 01:05:00'), "
            "(3, 'j3', '无关职位', '2026-08-01 00:00:00')"
        ))
    database._migrate_job_sources(eng)
    with eng.connect() as conn:
        rows = conn.execute(
            text("SELECT job_id, source_keyword, source_city, source_industry FROM job_sources ORDER BY job_id")
        ).fetchall()
        # 回填按 jobs.updated_at 归属最近一次任务窗口（历史无逐次命中记录，多源从新抓取起累积）
        assert rows == [
            ("j1", "采购", "020000", "08,46,47"),
            ("j2", "医疗采购", "010000", None),
        ]
        # j3 无回填
        assert "j3" not in [r[0] for r in rows]
    database._migrate_job_sources(eng)  # 幂等：再跑一次不新增
    with eng.connect() as conn:
        assert conn.execute(text("SELECT COUNT(*) FROM job_sources")).scalar() == len(rows)
