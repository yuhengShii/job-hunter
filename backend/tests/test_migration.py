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
