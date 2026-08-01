# 后端全量实现（v1）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现 51job 职位抓取项目后端全量（数据模型/认证/任务调度/Playwright 抓取/API/统计）+ pytest 测试。

**Architecture:** FastAPI 单体 + SQLAlchemy 2.0 + SQLite；单 worker 线程顺序消费 queued 任务（天然互斥）；APScheduler 定时入队；PlaywrightScraper 解析渲染后 DOM（sensorsdata 优先 + DOM 兜底）；统计基于最近一次成功/部分成功任务 start_time 窗口。

**Tech Stack:** Python 3.14、FastAPI、SQLAlchemy 2.0（Mapped 风格）、PyJWT、APScheduler、Playwright、beautifulsoup4、pytest + httpx（TestClient）。

## Global Constraints

- 唯一权威需求：`docs/PRD.md`；实现严格对齐 spec `docs/superpowers/specs/2026-08-01-backend-full-design.md`。
- Python 3.14，依赖一律 `uv add`（测试依赖 `uv add --dev`），提交 `uv.lock`。
- SQLAlchemy 2.0 `Mapped[...]` + `mapped_column`；模型字段名与 PRD §4 表结构一一对应。
- 路由只做校验与响应组装，禁止暴露 ORM 对象；全部经 `schemas/` Pydantic。
- 统计口径：`jobs.updated_at >= 最近一次 success/partial_success 任务的 start_time`。
- 同一 keyword 同时只允许一个进行中任务，冲突返回 409；启动时 queued/in_progress 任务置 failed（error_message="进程重启中断"）。
- 薪资解析规则枚举 PRD §4：`8千-1.2万`→8000/12000、`1.5-2万/月`→15000/20000、`15-20K`→15000/20000、`年薪20-30万`→按年÷12 折算月薪、`面议`→NULL；实测补充：`x-y万`、`x-y千`、`x-yK` 直接换算，先剥离 `13薪/14薪` 等后缀；无法解析记日志置 NULL。
- 测试禁止访问真实 51job；解析测试只用 `backend/tests/fixtures/51job_search.html`（真实抓取）与合成 `51job_company.html`。
- 时间一律 datetime（naive 本地时区）；`tags`、`settings.value` 用 SQLAlchemy JSON 列。
- 命令（仓库根目录）：`uv run pytest backend/tests`；启动 `uv run uvicorn backend.app.main:app`。
- 路由前缀 `/api`；除 login 外全部 JWT（`Authorization: Bearer`）。
- 从卡片无法获得职位详情链接（卡片仅含公司链接），`jobs.job_url` 存 NULL（v1 不伪造）。

---

### Task 1: 依赖、配置骨架与 fixtures

**Files:**
- Modify: `pyproject.toml`（pytest 配置）
- Create: `backend/app/__init__.py`、`backend/app/core/__init__.py`、`backend/app/core/config.py`、`backend/app/core/logging.py`
- Create: `backend/tests/conftest.py`、`backend/tests/test_config.py`
- Test: `backend/tests/test_config.py`
- Fixture: 提交 `backend/tests/fixtures/51job_search.html`（已存在未跟踪）；删除 `backend/tests/fixtures/51job_search_api.json`、`backend/tests/fixtures/51job_company.html`（均为 WAF 验证页，误导）

**Interfaces:**
- Produces: `Config`（属性 `auth_username/auth_password/jwt_secret/max_pages/headful/database_url/log_dir`，构造参数 `repo_root/config_path/db_path` 可注入）；`setup_logging(log_dir)`。

- [ ] **Step 1: 添加依赖**

Run（仓库根目录）:
```bash
uv add pyjwt beautifulsoup4
uv add --dev pytest httpx
```

- [ ] **Step 2: pyproject 添加 pytest 配置**

```toml
[tool.pytest.ini_options]
testpaths = ["backend/tests"]
```

- [ ] **Step 3: 写失败测试**

`backend/tests/conftest.py`：
```python
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

# 阻止 main.py 模块级 app=create_app() 在测试 import 时创建真实 data/config.ini
os.environ["JOB_HUNTER_TESTING"] = "1"

from backend.app.core.config import Config  # noqa: E402


@pytest.fixture()
def config(tmp_path):
    return Config(
        repo_root=tmp_path,
        config_path=tmp_path / "config.ini",
        db_path=tmp_path / "test.db",
    )
```

`backend/tests/test_config.py`：
```python
import configparser

from backend.app.core.config import Config


def test_config_creates_file_with_random_secrets(tmp_path):
    cfg = Config(repo_root=tmp_path, config_path=tmp_path / "config.ini", db_path=tmp_path / "test.db")
    assert cfg.config_path.exists()
    parser = configparser.ConfigParser()
    parser.read(cfg.config_path, encoding="utf-8")
    assert parser["auth"]["username"] == "admin"
    assert len(parser["auth"]["password"]) >= 12
    assert len(parser["auth"]["jwt_secret"]) >= 32
    assert cfg.auth_username == "admin"
    assert cfg.database_url == f"sqlite:///{tmp_path / 'test.db'}"


def test_config_reuse_existing_file(tmp_path):
    path = tmp_path / "config.ini"
    p = configparser.ConfigParser()
    p["auth"] = {"username": "me", "password": "pw123", "jwt_secret": "s" * 40}
    p["scraper"] = {"max_pages": "30", "headful": "false"}
    with open(path, "w", encoding="utf-8") as f:
        p.write(f)
    cfg = Config(repo_root=tmp_path, config_path=path, db_path=tmp_path / "t.db")
    assert cfg.auth_username == "me"
    assert cfg.max_pages == 30
    assert cfg.headful is False
```

- [ ] **Step 4: 运行测试确认失败**

Run: `uv run pytest backend/tests/test_config.py -v` — Expected: FAIL（模块不存在）

- [ ] **Step 5: 实现 config.py 与 logging.py**

`backend/app/core/config.py`：
```python
import configparser
import logging
import secrets
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
logger = logging.getLogger("job_hunter")


class Config:
    def __init__(
        self,
        repo_root: Path = REPO_ROOT,
        config_path: Path | None = None,
        db_path: Path | None = None,
    ):
        self.repo_root = repo_root
        self.config_path = config_path or repo_root / "data" / "config.ini"
        self.db_path = db_path or repo_root / "data" / "job_hunter.db"
        self._ensure()

    def _ensure(self) -> None:
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.config_path.exists():
            p = configparser.ConfigParser()
            p["auth"] = {
                "username": "admin",
                "password": secrets.token_urlsafe(12),
                "jwt_secret": secrets.token_urlsafe(32),
            }
            p["scraper"] = {"max_pages": "50", "headful": "false"}
            with open(self.config_path, "w", encoding="utf-8") as f:
                p.write(f)
            logger.warning(
                "已生成 %s，初始密码：%s（可修改文件后重启生效）",
                self.config_path, p["auth"]["password"],
            )
        self._parser = configparser.ConfigParser()
        self._parser.read(self.config_path, encoding="utf-8")

    @property
    def auth_username(self) -> str:
        return self._parser["auth"]["username"]

    @property
    def auth_password(self) -> str:
        return self._parser["auth"]["password"]

    @property
    def jwt_secret(self) -> str:
        return self._parser["auth"]["jwt_secret"]

    @property
    def max_pages(self) -> int:
        return int(self._parser["scraper"]["max_pages"])

    @property
    def headful(self) -> bool:
        return self._parser.getboolean("scraper", "headful")

    @property
    def database_url(self) -> str:
        return f"sqlite:///{self.db_path}"

    @property
    def log_dir(self) -> Path:
        return self.repo_root / "logs"
```

`backend/app/core/logging.py`：
```python
import logging
from pathlib import Path

_CONFIGURED = False


def setup_logging(log_dir: Path) -> None:
    global _CONFIGURED
    if _CONFIGURED:
        return
    log_dir.mkdir(parents=True, exist_ok=True)
    root = logging.getLogger("job_hunter")
    root.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
    fh = logging.FileHandler(log_dir / "app.log", encoding="utf-8")
    fh.setFormatter(fmt)
    sh = logging.StreamHandler()
    sh.setFormatter(fmt)
    root.addHandler(fh)
    root.addHandler(sh)
    _CONFIGURED = True
```

`backend/app/__init__.py`、`backend/app/core/__init__.py`：空文件。

- [ ] **Step 6: 运行测试确认通过**

Run: `uv run pytest backend/tests/test_config.py -v` — Expected: 2 passed

- [ ] **Step 7: 清理 fixtures 并提交**

```bash
git rm --cached backend/tests/fixtures/51job_search_api.json backend/tests/fixtures/51job_company.html 2>$null
Remove-Item backend/tests/fixtures/51job_search_api.json, backend/tests/fixtures/51job_company.html -ErrorAction SilentlyContinue
git add pyproject.toml uv.lock backend/app backend/tests
git commit -m "chore: add config/logging skeleton, pytest setup, search fixtures"
```

---

### Task 2: 数据库与模型

**Files:**
- Create: `backend/app/core/database.py`、`backend/app/models/__init__.py`、`backend/app/models/user.py`、`backend/app/models/keyword.py`、`backend/app/models/scrape_task.py`、`backend/app/models/job.py`、`backend/app/models/company.py`、`backend/app/models/setting.py`
- Create: `backend/tests/test_models.py`
- Test: `backend/tests/test_models.py`

**Interfaces:**
- Consumes: `Config.database_url`
- Produces: `Base`、`engine`、`SessionLocal`、`init_db()`；模型类 `User/Keyword/ScrapeTask/Job/Company/Setting`（字段见 PRD §4）；`TaskStatus` 枚举（queued/in_progress/success/partial_success/failed）

- [ ] **Step 1: 写失败测试**

`backend/tests/test_models.py`：
```python
from datetime import datetime

import pytest
from sqlalchemy.exc import IntegrityError

from backend.app.core.database import SessionLocal, init_db
from backend.app.models import Company, Job, Keyword, Setting, User


def test_tables_created_and_unique_keys(config):
    init_db(config)
    with SessionLocal() as s:
        s.add_all([
            Keyword(keyword="python"),
            User(username="u1", password_hash="h"),
            Company(company_id="c1", name="A公司"),
            Setting(key="schedule", value={"enabled": False}),
        ])
        s.commit()
        assert s.query(Keyword).count() == 1
        with pytest.raises(IntegrityError):
            s.add(Keyword(keyword="python"))
            s.commit()
        s.rollback()
        assert s.query(Job).count() == 0


def test_job_upsert_by_unique_job_id(config):
    init_db(config)
    with SessionLocal() as s:
        now = datetime.now()
        s.add(Job(job_id="171875192", title="旧", salary_raw="1-2万", tags=[], created_at=now, updated_at=now))
        s.commit()
    with SessionLocal() as s:
        job = s.query(Job).filter_by(job_id="171875192").one()
        assert job.title == "旧"
```
（upsert 覆盖逻辑在 Task 10 实现，本任务仅验证唯一约束与建表。）

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run pytest backend/tests/test_models.py -v` — Expected: FAIL（模块不存在）

- [ ] **Step 3: 实现 database.py 与全部模型**

`backend/app/core/database.py`：
```python
from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from backend.app.core.config import Config

engine: object = None
SessionLocal: sessionmaker = None


class Base(DeclarativeBase):
    pass


def init_db(config: Config) -> None:
    global engine, SessionLocal
    engine = create_engine(config.database_url, connect_args={"check_same_thread": False})
    SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    import backend.app.models  # noqa: F401 确保模型注册

    Base.metadata.create_all(engine)
```

`backend/app/models/user.py`：
```python
from datetime import datetime

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.core.database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
```

`backend/app/models/keyword.py`：
```python
from datetime import datetime

from sqlalchemy import Boolean, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.core.database import Base


class Keyword(Base):
    __tablename__ = "keywords"

    id: Mapped[int] = mapped_column(primary_key=True)
    keyword: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    scrape_mode: Mapped[str] = mapped_column(String(32), default="playwright")
    last_scraped_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
```

`backend/app/models/scrape_task.py`：
```python
from datetime import datetime
from enum import Enum

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.core.database import Base


class TaskStatus(str, Enum):
    QUEUED = "queued"
    IN_PROGRESS = "in_progress"
    SUCCESS = "success"
    PARTIAL_SUCCESS = "partial_success"
    FAILED = "failed"


class ScrapeTask(Base):
    __tablename__ = "scrape_tasks"
    __table_args__ = (
        Index("ix_scrape_tasks_keyword_id", "keyword_id"),
        Index("ix_scrape_tasks_created_at", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    keyword_id: Mapped[int] = mapped_column(ForeignKey("keywords.id"), nullable=False)
    mode: Mapped[str] = mapped_column(String(32), default="playwright")
    status: Mapped[str] = mapped_column(String(32), default=TaskStatus.QUEUED.value)
    total_pages: Mapped[int | None] = mapped_column(Integer)
    total_found: Mapped[int] = mapped_column(Integer, default=0)
    success_count: Mapped[int] = mapped_column(Integer, default=0)
    failed_count: Mapped[int] = mapped_column(Integer, default=0)
    last_page: Mapped[int] = mapped_column(Integer, default=0)
    start_time: Mapped[datetime | None] = mapped_column(DateTime)
    end_time: Mapped[datetime | None] = mapped_column(DateTime)
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
```

`backend/app/models/job.py`：
```python
from datetime import datetime

from sqlalchemy import JSON, DateTime, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.core.database import Base


class Job(Base):
    __tablename__ = "jobs"
    __table_args__ = (Index("ix_jobs_created_at", "created_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    title: Mapped[str] = mapped_column(String(255))
    salary_raw: Mapped[str | None] = mapped_column(String(64))
    salary_min: Mapped[int | None] = mapped_column()
    salary_max: Mapped[int | None] = mapped_column()
    city: Mapped[str | None] = mapped_column(String(64))
    district: Mapped[str | None] = mapped_column(String(64))
    area: Mapped[str | None] = mapped_column(String(128))
    tags: Mapped[list] = mapped_column(JSON, default=list)
    publish_time: Mapped[datetime | None] = mapped_column(DateTime)
    source: Mapped[str] = mapped_column(String(32), default="51job")
    company_id: Mapped[str | None] = mapped_column(String(64))
    job_url: Mapped[str | None] = mapped_column(String(512))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)
```

`backend/app/models/company.py`：
```python
from datetime import datetime

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.core.database import Base


class Company(Base):
    __tablename__ = "companies"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255))
    type: Mapped[str | None] = mapped_column(String(32))
    industry: Mapped[str | None] = mapped_column(String(128))
    size: Mapped[str | None] = mapped_column(String(64))
    activity: Mapped[str | None] = mapped_column(String(64))
    website: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)
```

`backend/app/models/setting.py`：
```python
from datetime import datetime

from sqlalchemy import JSON, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.core.database import Base


class Setting(Base):
    __tablename__ = "settings"

    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    value: Mapped[dict] = mapped_column(JSON)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)
```

`backend/app/models/__init__.py`：
```python
from backend.app.models.company import Company
from backend.app.models.job import Job
from backend.app.models.keyword import Keyword
from backend.app.models.scrape_task import ScrapeTask, TaskStatus
from backend.app.models.setting import Setting
from backend.app.models.user import User

__all__ = ["Company", "Job", "Keyword", "ScrapeTask", "Setting", "TaskStatus", "User"]
```

- [ ] **Step 4: 运行测试确认通过**

Run: `uv run pytest backend/tests/test_models.py -v` — Expected: 2 passed

- [ ] **Step 5: 提交**

```bash
git add backend/app backend/tests
git commit -m "feat: add SQLAlchemy models and database init"
```

---

### Task 3: 安全模块（密码哈希 + JWT）

**Files:**
- Create: `backend/app/core/security.py`
- Create: `backend/tests/test_security.py`
- Test: `backend/tests/test_security.py`

**Interfaces:**
- Consumes: `Config.jwt_secret`
- Produces: `hash_password(pw: str) -> str`、`verify_password(pw: str, hashed: str) -> bool`、`create_access_token(username: str, secret: str, expires_hours: int = 24) -> str`、`decode_access_token(token: str, secret: str) -> str`（返回 username，失败抛 `AppError(401)`）

- [ ] **Step 1: 写失败测试**

`backend/tests/test_security.py`：
```python
import pytest

from backend.app.core.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)
from backend.app.core.exceptions import AppError


def test_password_hash_roundtrip():
    h = hash_password("secret123")
    assert h != "secret123"
    assert verify_password("secret123", h)
    assert not verify_password("wrong", h)


def test_token_roundtrip():
    token = create_access_token("admin", "test-secret-key-0123456789abcdef")
    assert decode_access_token(token, "test-secret-key-0123456789abcdef") == "admin"


def test_token_bad_signature():
    token = create_access_token("admin", "test-secret-key-0123456789abcdef")
    with pytest.raises(AppError):
        decode_access_token(token, "other-secret-key-0123456789abcdef")


def test_token_expired():
    token = create_access_token("admin", "test-secret-key-0123456789abcdef", expires_hours=-1)
    with pytest.raises(AppError):
        decode_access_token(token, "test-secret-key-0123456789abcdef")
```

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run pytest backend/tests/test_security.py -v` — Expected: FAIL（模块不存在）

- [ ] **Step 3: 实现 core/exceptions.py 与 core/security.py**

`backend/app/core/exceptions.py`：
```python
from fastapi import Request
from fastapi.responses import JSONResponse


class AppError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.message})
```

`backend/app/core/security.py`：
```python
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone

import jwt

from backend.app.core.exceptions import AppError

_PBKDF2_ITERATIONS = 200_000


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), _PBKDF2_ITERATIONS)
    return f"{salt}${digest.hex()}"


def verify_password(password: str, hashed: str) -> bool:
    try:
        salt, digest_hex = hashed.split("$")
        digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), _PBKDF2_ITERATIONS)
        return hmac.compare_digest(digest.hex(), digest_hex)
    except (ValueError, TypeError):
        return False


def create_access_token(username: str, secret: str, expires_hours: int = 24) -> str:
    payload = {
        "sub": username,
        "exp": datetime.now(timezone.utc) + timedelta(hours=expires_hours),
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, secret, algorithm="HS256")


def decode_access_token(token: str, secret: str) -> str:
    try:
        payload = jwt.decode(token, secret, algorithms=["HS256"])
        sub = payload.get("sub")
        if not sub:
            raise AppError("无效 token", 401)
        return sub
    except jwt.ExpiredSignatureError:
        raise AppError("token 已过期", 401)
    except jwt.InvalidTokenError:
        raise AppError("无效 token", 401)
```

- [ ] **Step 4: 运行测试确认通过**

Run: `uv run pytest backend/tests/test_security.py -v` — Expected: 4 passed

- [ ] **Step 5: 提交**

```bash
git add backend/app backend/tests
git commit -m "feat: add password hashing and JWT auth core"
```

---

### Task 4: 薪资解析

**Files:**
- Create: `backend/app/services/__init__.py`、`backend/app/services/salary.py`
- Create: `backend/tests/test_salary.py`
- Test: `backend/tests/test_salary.py`

**Interfaces:**
- Produces: `parse_salary(raw: str | None) -> tuple[int | None, int | None]`

- [ ] **Step 1: 写失败测试**

`backend/tests/test_salary.py`：
```python
from backend.app.services.salary import parse_salary


def test_prd_rules():
    assert parse_salary("8千-1.2万") == (8000, 12000)
    assert parse_salary("1.5-2万/月") == (15000, 20000)
    assert parse_salary("15-20K") == (15000, 20000)
    assert parse_salary("15-20k") == (15000, 20000)
    assert parse_salary("年薪20-30万") == (200000 // 12, 300000 // 12)
    assert parse_salary("面议") == (None, None)
    assert parse_salary(None) == (None, None)


def test_live_formats():
    assert parse_salary("1-2万") == (10000, 20000)
    assert parse_salary("1.2-1.9万") == (12000, 19000)
    assert parse_salary("8千-1万") == (8000, 10000)
    assert parse_salary("8千-1.2万") == (8000, 12000)
    assert parse_salary("3-5万13薪") == (30000, 50000)
    assert parse_salary("1-2万/月·13薪") == (10000, 20000)


def test_unparseable_returns_none():
    assert parse_salary("按天结算") == (None, None)
    assert parse_salary("") == (None, None)
```

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run pytest backend/tests/test_salary.py -v` — Expected: FAIL（模块不存在）

- [ ] **Step 3: 实现 salary.py**

`backend/app/services/salary.py`：
```python
import logging
import re

logger = logging.getLogger("job_hunter")

_PATTERNS: list[tuple[re.Pattern, int, bool]] = [
    (re.compile(r"^年薪([\d.]+)-([\d.]+)万"), 10000, True),
    (re.compile(r"^([\d.]+)-([\d.]+)万(?:/月)?"), 10000, False),
    (re.compile(r"^([\d.]+)-([\d.]+)千(?:/月)?"), 1000, False),
    (re.compile(r"^([\d.]+)-([\d.]+)\s*[Kk](?:/月)?"), 1000, False),
]
_MIXED_KWAN_RE = re.compile(r"^([\d.]+)千-([\d.]+)万(?:/月)?")
_SUFFIX_RE = re.compile(r"[\s·*]*\d+薪.*$")


def parse_salary(raw: str | None) -> tuple[int | None, int | None]:
    if not raw:
        return None, None
    text = raw.strip()
    if text == "面议":
        return None, None
    text = _SUFFIX_RE.sub("", text).strip()
    m = _MIXED_KWAN_RE.match(text)
    if m:
        lo, hi = float(m.group(1)), float(m.group(2))
        if lo >= 1 and hi >= 1:
            return int(lo * 1000), int(hi * 10000)
    for pat, unit, annual in _PATTERNS:
        m = pat.match(text)
        if m:
            lo, hi = float(m.group(1)), float(m.group(2))
            if lo < 1 or hi < lo:
                continue
            factor = unit / 12 if annual else unit
            return int(lo * factor), int(hi * factor)
    logger.warning("无法解析薪资: %r", raw)
    return None, None
```

- [ ] **Step 4: 运行测试确认通过**

Run: `uv run pytest backend/tests/test_salary.py -v` — Expected: 3 passed

- [ ] **Step 5: 提交**

```bash
git add backend/app backend/tests
git commit -m "feat: add salary parser with PRD rules"
```

---

### Task 5: 抓取解析器（sensorsdata 优先 + DOM 兜底）

**Files:**
- Create: `backend/app/scrapers/__init__.py`、`backend/app/scrapers/base.py`、`backend/app/scrapers/parser.py`
- Create: `backend/tests/fixtures/51job_company.html`（合成）
- Create: `backend/tests/test_parser.py`
- Test: `backend/tests/test_parser.py`

**Interfaces:**
- Consumes: `parse_salary`
- Produces: dataclasses `JobDraft`（job_id/title/salary_raw/salary_min/salary_max/city/district/area/tags/publish_time/company_id/job_url）、`CompanyDraft`（company_id/name/type/industry/size/activity/website）、`PageResult`（page_num/total_pages/jobs/companies/failed）；
  `parse_search_page(html: str, page_num: int) -> PageResult`、`parse_company_page(html: str) -> CompanyDraft | None`

- [ ] **Step 1: 写失败测试**

`backend/tests/test_parser.py`：
```python
from pathlib import Path
from datetime import datetime

from backend.app.scrapers.parser import parse_company_page, parse_search_page

FIXTURES = Path(__file__).parent / "fixtures"
SEARCH_HTML = (FIXTURES / "51job_search.html").read_text(encoding="utf-8")
COMPANY_HTML = (FIXTURES / "51job_company.html").read_text(encoding="utf-8")


def test_search_page_parse_first_card():
    result = parse_search_page(SEARCH_HTML, page_num=1)
    assert not result.failed
    assert result.total_pages == 50
    assert len(result.jobs) == 20
    job = result.jobs[0]
    assert job.job_id == "171875192"
    assert "Python" in job.title
    assert job.salary_raw == "1-2万"
    assert job.salary_min == 10000 and job.salary_max == 20000
    assert job.city == "上海" and job.district == "黄浦区"
    assert job.area == "上海·黄浦区"
    assert job.company_id == "2543553"
    assert job.tags == ["五险一金", "餐饮补贴", "带薪年假", "做五休二"]
    assert job.publish_time == datetime(2026, 4, 30, 16, 53, 19)
    assert job.job_url is None


def test_search_page_company_from_card():
    result = parse_search_page(SEARCH_HTML, page_num=1)
    # fixture 实测 20 张卡片中 companyId 有 2 对重复（2543553、2274319 各 ×2），去重后 18 个唯一公司
    assert len(result.companies) == 18
    comp = next(c for c in result.companies if c.company_id == "2543553")
    assert comp.name == "立信会计师事务所（特殊普通合伙）"
    assert comp.type == "民营"
    assert comp.industry == "其他专业服务丨财务/审计/税务"
    assert comp.size == "5000-10000人"


def test_search_page_tags_fallback():
    result = parse_search_page(SEARCH_HTML, page_num=1)
    tagged = [j for j in result.jobs if j.tags]
    # fixture 实测 20 张卡片中第 17 张无 tags（jobLabel 与 DOM 均无），其余 19 张有
    assert len(tagged) == 19
    assert tagged[0].tags == ["五险一金", "餐饮补贴", "带薪年假", "做五休二"]


def test_waf_page_marks_failed():
    html = '<html><body>安全验证页面</body></html>'
    result = parse_search_page(html, page_num=1)
    assert result.failed
    assert result.jobs == []


def test_search_page_card_with_single_dc_cell():
    html = """
    <html><body>
      <div class="joblist-item">
        <div class="joblist-item-job" sensorsdata='{"jobId":"1","jobTitle":"缺类型职位","jobSalary":"1-2万","jobArea":"上海","companyId":"999"}'>
        </div>
        <div class="bc"><span class="dc">计算机软件</span></div>
      </div>
    </body></html>
    """
    result = parse_search_page(html, page_num=1)
    assert not result.failed
    assert len(result.jobs) == 1
    assert result.jobs[0].job_id == "1"
    comp = result.companies[0]
    assert comp.type is None
    assert comp.size is None


def test_company_page_synthetic():
    comp = parse_company_page(COMPANY_HTML)
    assert comp is not None
    assert comp.name == "示例科技"
    assert comp.type == "民营"
    assert comp.industry == "计算机软件"
    assert comp.size == "500-1000人"
    assert comp.activity == "30天"


def test_company_page_verification_returns_none():
    assert parse_company_page("<html><body>安全验证</body></html>") is None
```

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run pytest backend/tests/test_parser.py -v` — Expected: FAIL（模块不存在）

- [ ] **Step 3: 创建合成公司 fixture，实现 base.py 与 parser.py**

`backend/tests/fixtures/51job_company.html`（合成，模拟 51job 公司详情页结构）：
```html
<html><body>
  <div class="company-info">
    <h1>示例科技</h1>
    <div class="com_detail1">
      <div class="t1">公司类型</div><div class="t2">民营</div>
      <div class="t1">所属行业</div><div class="t2">计算机软件</div>
      <div class="t1">公司规模</div><div class="t2">500-1000人</div>
      <div class="t1">活跃天数</div><div class="t2">30天</div>
    </div>
  </div>
</body></html>
```

`backend/app/scrapers/base.py`：
```python
from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class JobDraft:
    job_id: str
    title: str
    salary_raw: str | None = None
    salary_min: int | None = None
    salary_max: int | None = None
    city: str | None = None
    district: str | None = None
    area: str | None = None
    tags: list[str] = field(default_factory=list)
    publish_time: datetime | None = None
    company_id: str | None = None
    job_url: str | None = None


@dataclass
class CompanyDraft:
    company_id: str
    name: str | None = None
    type: str | None = None
    industry: str | None = None
    size: str | None = None
    activity: str | None = None
    website: str | None = None


@dataclass
class PageResult:
    page_num: int
    jobs: list[JobDraft]
    companies: list[CompanyDraft] = field(default_factory=list)
    total_pages: int | None = None
    failed: bool = False


class Scraper(ABC):
    @abstractmethod
    async def search(self, keyword: str, pages: int) -> AsyncGenerator[PageResult, None]:
        ...

    @abstractmethod
    async def fetch_company(self, company_id: str, company_url: str) -> CompanyDraft | None:
        ...

    @abstractmethod
    async def close(self) -> None:
        ...
```

`backend/app/scrapers/parser.py`：
```python
import json
import logging
import re
from datetime import datetime

from bs4 import BeautifulSoup

from backend.app.scrapers.base import CompanyDraft, JobDraft, PageResult
from backend.app.services.salary import parse_salary

logger = logging.getLogger("job_hunter")

_JOB_TIME_FMT = "%Y-%m-%d %H:%M:%S"
# 注意：不能包含裸 "waf"——真实搜索页的压缩 JS 里存在 "waf" 子串（如 li1wafet），会误伤正常页面
_VERIFY_MARKERS = ("安全验证", "验证码", "renderData")
_TYPE_MAP = {
    "民营": "民营", "国企": "国企", "外企": "外企", "外资企业": "外企",
    "合资": "合资", "上市公司": "上市公司", "事业单位": "事业单位",
    "外资(欧美)": "外企", "外资(非欧美)": "外企",
}


def _is_verification(html: str) -> bool:
    return any(m in html for m in _VERIFY_MARKERS)


def _split_area(area: str) -> tuple[str | None, str | None]:
    if not area:
        return None, None
    if "-" in area:
        city, district = area.split("-", 1)
        return city.strip(), district.strip() or None
    if "·" in area:
        city, district = area.split("·", 1)
        return city.strip(), district.strip() or None
    return area.strip(), None


def _parse_job_time(text: str | None) -> datetime | None:
    if not text:
        return None
    try:
        return datetime.strptime(text.strip(), _JOB_TIME_FMT)
    except ValueError:
        return None


def _extract_sensors(el) -> dict:
    raw = el.get("sensorsdata") if el else None
    if not raw:
        return {}
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        logger.warning("sensorsdata JSON 解析失败")
        return {}


def _parse_company_from_card(card, sdata: dict) -> CompanyDraft | None:
    company_id = sdata.get("companyId")
    if not company_id:
        logo = card.select_one(".comlogo")
        m = re.search(r"/CompLogo/\d+/\d+/(\d+)_", logo.get("src", "")) if logo else None
        if m:
            company_id = m.group(1)
    if not company_id:
        return None
    name_el = card.select_one(".cname")
    name = name_el.get_text(strip=True) if name_el else None
    dcs = [el for el in card.select(".bc .dc")]
    industry = dcs[0].get_text(strip=True) if len(dcs) > 0 else None
    if len(dcs) > 1:
        type_raw = dcs[1].get("title") or dcs[1].get_text(strip=True)
    else:
        type_raw = None
    size = dcs[2].get_text(strip=True) if len(dcs) > 2 else None
    return CompanyDraft(
        company_id=company_id,
        name=name,
        type=_TYPE_MAP.get(type_raw or "", type_raw) if type_raw else None,
        industry=industry,
        size=size,
    )


def parse_search_page(html: str, page_num: int) -> PageResult:
    if _is_verification(html):
        return PageResult(page_num=page_num, jobs=[], failed=True)
    soup = BeautifulSoup(html, "html.parser")
    cards = soup.select(".joblist-item")
    if not cards:
        return PageResult(page_num=page_num, jobs=[], failed=True)
    jobs: list[JobDraft] = []
    companies: list[CompanyDraft] = []
    seen_company: set[str] = set()
    for card in cards:
        el = card.select_one(".joblist-item-job")
        sdata = _extract_sensors(el)
        job_id = sdata.get("jobId")
        if not job_id:
            logger.warning("卡片缺少 jobId，跳过")
            continue
        title = sdata.get("jobTitle") or (
            card.select_one(".jname").get_text(strip=True) if card.select_one(".jname") else ""
        )
        salary_raw = sdata.get("jobSalary") or (
            card.select_one(".sal").get_text(strip=True) if card.select_one(".sal") else None
        )
        salary_min, salary_max = parse_salary(salary_raw)
        area = sdata.get("jobArea") or (
            card.select_one(".area").get_text(strip=True) if card.select_one(".area") else None
        )
        city, district = _split_area(area)
        tags_raw = sdata.get("jobLabel")
        if not tags_raw:
            tags = [t.get_text(strip=True) for t in card.select(".joblist-item-tags .tag")]
        else:
            tags = [tags_raw]
        tags = [t for t in tags if t]
        publish_time = _parse_job_time(sdata.get("jobTime"))
        company_id = sdata.get("companyId")
        jobs.append(
            JobDraft(
                job_id=job_id,
                title=title,
                salary_raw=salary_raw,
                salary_min=salary_min,
                salary_max=salary_max,
                city=city,
                district=district,
                area=area,
                tags=tags,
                publish_time=publish_time,
                company_id=company_id,
                job_url=None,
            )
        )
        comp = _parse_company_from_card(card, sdata)
        if comp and comp.company_id not in seen_company:
            seen_company.add(comp.company_id)
            companies.append(comp)
    total_pages = None
    pager_nums = soup.select(".el-pager li.number")
    if pager_nums:
        try:
            total_pages = int(pager_nums[-1].get_text(strip=True))
        except ValueError:
            total_pages = None
    return PageResult(page_num=page_num, jobs=jobs, companies=companies, total_pages=total_pages)


def parse_company_page(html: str) -> CompanyDraft | None:
    if _is_verification(html):
        return None
    soup = BeautifulSoup(html, "html.parser")
    info = soup.select_one(".company-info")
    if not info:
        return None
    name_el = info.select_one("h1")
    pairs: dict[str, str] = {}
    for t1, t2 in zip(info.select(".t1"), info.select(".t2")):
        pairs[t1.get_text(strip=True)] = t2.get_text(strip=True)
    return CompanyDraft(
        company_id="",
        name=name_el.get_text(strip=True) if name_el else None,
        type=pairs.get("公司类型"),
        industry=pairs.get("所属行业"),
        size=pairs.get("公司规模"),
        activity=pairs.get("活跃天数"),
    )
```

- [ ] **Step 4: 运行测试确认通过**

Run: `uv run pytest backend/tests/test_parser.py -v` — Expected: 6 passed

- [ ] **Step 5: 提交**

```bash
git add backend/app backend/tests
git commit -m "feat: add search/company page parsers with sensorsdata priority"
```

---

### Task 6: PlaywrightScraper 实现

**Files:**
- Create: `backend/app/scrapers/playwright.py`
- Create: `backend/tests/test_playwright_scraper.py`
- Test: `backend/tests/test_playwright_scraper.py`

**Interfaces:**
- Consumes: `Scraper`、`parse_search_page`、`parse_company_page`、`Config.headful`
- Produces: `PlaywrightScraper(headful: bool = False)` 实现 `search(keyword, pages)`（AsyncGenerator[PageResult]）、`fetch_company(company_id, company_url)`、`close()`

- [ ] **Step 1: 写失败测试（仅验证导入与签名，不启动浏览器）**

`backend/tests/test_playwright_scraper.py`：
```python
import inspect
from collections.abc import AsyncGenerator

from backend.app.scrapers.base import PageResult, Scraper
from backend.app.scrapers.playwright import PlaywrightScraper


def test_playwright_scraper_implements_interface():
    assert issubclass(PlaywrightScraper, Scraper)
    sig = inspect.signature(PlaywrightScraper.search)
    assert sig.return_annotation == AsyncGenerator[PageResult, None]


def test_scraper_is_async_generator():
    s = PlaywrightScraper(headful=False)
    assert inspect.isasyncgenfunction(s.search)
    assert inspect.iscoroutinefunction(s.fetch_company)
    assert inspect.iscoroutinefunction(s.close)
```

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run pytest backend/tests/test_playwright_scraper.py -v` — Expected: FAIL（模块不存在）

- [ ] **Step 3: 实现 playwright.py**

`backend/app/scrapers/playwright.py`：
```python
import asyncio
import logging
import random
from collections.abc import AsyncGenerator
from urllib.parse import quote

from playwright.async_api import TimeoutError as PWTimeoutError
from playwright.async_api import async_playwright

from backend.app.scrapers.base import CompanyDraft, PageResult, Scraper
from backend.app.scrapers.parser import parse_company_page, parse_search_page

logger = logging.getLogger("job_hunter")

_SEARCH_URL = "https://we.51job.com/pc/search?keyword={kw}&searchType=2&sortType=0&pageNum={n}"
_JOB_CARD_SELECTOR = ".joblist-item"
_MAX_RETRIES = 3


class PlaywrightScraper(Scraper):
    def __init__(self, headful: bool = False):
        self._headful = headful
        self._playwright = None
        self._browser = None

    async def _ensure_browser(self):
        if self._browser:
            return
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(headless=not self._headful)

    async def _new_page(self):
        ua = random.choice(
            [
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
            ]
        )
        page = await self._browser.new_page(user_agent=ua, viewport={"width": 1600, "height": 1000})
        return page

    async def search(self, keyword: str, pages: int) -> AsyncGenerator[PageResult, None]:
        await self._ensure_browser()
        for n in range(1, pages + 1):
            result = await self._fetch_page(keyword, n)
            if result.failed:
                logger.warning("第 %s 页抓取失败（已重试）: keyword=%s", n, keyword)
            yield result
            await asyncio.sleep(random.uniform(2.0, 5.0))

    async def _fetch_page(self, keyword: str, page_num: int) -> PageResult:
        last_result: PageResult | None = None
        for attempt in range(1, _MAX_RETRIES + 1):
            page = await self._new_page()
            try:
                url = _SEARCH_URL.format(kw=quote(keyword), n=page_num)
                await page.goto(url, wait_until="domcontentloaded", timeout=60000)
                try:
                    await page.wait_for_selector(_JOB_CARD_SELECTOR, timeout=30000)
                except PWTimeoutError:
                    html = await page.content()
                    last_result = parse_search_page(html, page_num)
                    if last_result.failed:
                        raise
                if page_num == 1:
                    for _ in range(3):
                        await page.mouse.wheel(0, 1200)
                        await page.wait_for_timeout(random.randint(400, 900))
                    await page.wait_for_timeout(1500)
                html = await page.content()
                last_result = parse_search_page(html, page_num)
                return last_result
            except Exception as exc:
                logger.warning("第 %s 页第 %s 次尝试失败: %s", page_num, attempt, exc)
                await asyncio.sleep(attempt * 2.0)
            finally:
                await page.close()
        if last_result is None:
            return PageResult(page_num=page_num, jobs=[], failed=True)
        return last_result

    async def fetch_company(self, company_id: str, company_url: str) -> CompanyDraft | None:
        if not company_url:
            return None
        await self._ensure_browser()
        page = await self._new_page()
        try:
            await page.goto(company_url, wait_until="domcontentloaded", timeout=60000)
            await page.wait_for_timeout(5000)
            html = await page.content()
            draft = parse_company_page(html)
            if draft:
                draft.company_id = company_id
            return draft
        except Exception as exc:
            logger.warning("公司详情抓取失败 company_id=%s: %s", company_id, exc)
            return None
        finally:
            await page.close()

    async def close(self) -> None:
        if self._browser:
            await self._browser.close()
            self._browser = None
        if self._playwright:
            await self._playwright.stop()
            self._playwright = None
```

- [ ] **Step 4: 运行测试确认通过**

Run: `uv run pytest backend/tests/test_playwright_scraper.py -v` — Expected: 2 passed

- [ ] **Step 5: 提交**

```bash
git add backend/app backend/tests
git commit -m "feat: add Playwright scraper with retry and anti-bot measures"
```

---

### Task 7: 认证 API（schemas + deps + auth 路由）

**Files:**
- Create: `backend/app/schemas/__init__.py`、`backend/app/schemas/auth.py`、`backend/app/api/__init__.py`、`backend/app/api/deps.py`、`backend/app/api/auth.py`
- Create: `backend/tests/test_auth_api.py`
- Test: `backend/tests/test_auth_api.py`

**Interfaces:**
- Consumes: `Config`、`SessionLocal`、`init_db`、`User`、security 函数、`AppError`
- Produces: `get_db()`（yield Session）、`get_current_user`（FastAPI Depends）、`auth_router`（`POST /login`、`GET /me`）；`TokenResponse`、`UserOut` schema；`create_app` 需要的 `ensure_admin(config)` 函数（放 `api/deps.py` 或 `main.py`，本任务先放 `api/deps.py`）

- [ ] **Step 1: 写失败测试**

`backend/tests/test_auth_api.py`：
```python
from fastapi.testclient import TestClient

from backend.app.api.deps import ensure_admin
from backend.app.core.database import SessionLocal, init_db
from backend.app.main import create_app


def _client(config):
    init_db(config)
    with SessionLocal() as s:
        ensure_admin(s, config)
    app = create_app(config)
    return TestClient(app)


def test_login_success(config):
    client = _client(config)
    resp = client.post("/api/auth/login", json={"username": config.auth_username, "password": config.auth_password})
    assert resp.status_code == 200
    assert resp.json()["token_type"] == "bearer"
    assert resp.json()["access_token"]


def test_login_wrong_password(config):
    client = _client(config)
    resp = client.post("/api/auth/login", json={"username": config.auth_username, "password": "wrong"})
    assert resp.status_code == 401


def test_me_with_token(config):
    client = _client(config)
    token = client.post("/api/auth/login", json={"username": config.auth_username, "password": config.auth_password}).json()["access_token"]
    resp = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert resp.json()["username"] == config.auth_username


def test_me_without_token(config):
    client = _client(config)
    resp = client.get("/api/auth/me")
    assert resp.status_code == 401
```

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run pytest backend/tests/test_auth_api.py -v` — Expected: FAIL（main 模块不存在）

- [ ] **Step 3: 实现 schemas、deps、auth 路由与 main 骨架**

`backend/app/schemas/__init__.py`、`backend/app/schemas/auth.py`：
```python
from datetime import datetime

from pydantic import BaseModel


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserOut(BaseModel):
    id: int
    username: str
    created_at: datetime

    model_config = {"from_attributes": True}
```

`backend/app/api/deps.py`：
```python
from collections.abc import Generator

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from backend.app.core.config import Config
from backend.app.core.database import SessionLocal
from backend.app.core.exceptions import AppError
from backend.app.core.security import decode_access_token, hash_password, verify_password
from backend.app.models import User

_bearer = HTTPBearer(auto_error=False)
_current_config: Config | None = None


def set_current_config(config: Config) -> None:
    global _current_config
    _current_config = config


def get_db() -> Generator:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def ensure_admin(db, config: Config) -> None:
    if db.query(User).count() == 0:
        db.add(User(username=config.auth_username, password_hash=hash_password(config.auth_password)))
        db.commit()


def authenticate(db, username: str, password: str) -> User:
    user = db.query(User).filter_by(username=username).first()
    if not user or not verify_password(password, user.password_hash):
        raise AppError("用户名或密码错误", 401)
    return user


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db=Depends(get_db),
) -> User:
    if credentials is None or _current_config is None:
        raise AppError("未认证", 401)
    username = decode_access_token(credentials.credentials, _current_config.jwt_secret)
    user = db.query(User).filter_by(username=username).first()
    if user is None:
        raise AppError("用户不存在", 401)
    return user
```

`backend/app/api/auth.py`：
```python
from fastapi import APIRouter, Depends

from backend.app.api.deps import _current_config, authenticate, get_current_user, get_db
from backend.app.core.security import create_access_token
from backend.app.schemas.auth import LoginRequest, TokenResponse, UserOut

auth_router = APIRouter(prefix="/api/auth", tags=["auth"])


@auth_router.post("/login", response_model=TokenResponse)
def login(body: LoginRequest, db=Depends(get_db)):
    user = authenticate(db, body.username, body.password)
    token = create_access_token(user.username, _current_config.jwt_secret)
    return TokenResponse(access_token=token)


@auth_router.get("/me", response_model=UserOut)
def me(user=Depends(get_current_user)):
    return user
```

`backend/app/api/__init__.py`、`backend/app/schemas/__init__.py`：空文件。

`backend/app/main.py`（本任务最小骨架，后续任务扩充）：
```python
import os

from fastapi import FastAPI

from backend.app.api.auth import auth_router
from backend.app.api.deps import ensure_admin, set_current_config
from backend.app.core.config import REPO_ROOT, Config
from backend.app.core.database import SessionLocal, init_db
from backend.app.core.exceptions import AppError, app_error_handler
from backend.app.core.logging import setup_logging

_config: Config | None = None


def create_app(config: Config | None = None) -> FastAPI:
    global _config
    cfg = config or Config(repo_root=REPO_ROOT)
    _config = cfg
    set_current_config(cfg)
    setup_logging(cfg.log_dir)
    init_db(cfg)
    with SessionLocal() as db:
        ensure_admin(db, cfg)
    app = FastAPI(title="job-hunter")
    app.add_exception_handler(AppError, app_error_handler)
    app.include_router(auth_router)
    return app


# 测试通过 conftest 设置 JOB_HUNTER_TESTING=1，避免污染真实 data/
if not os.environ.get("JOB_HUNTER_TESTING"):
    app = create_app()
```

- [ ] **Step 4: 运行测试确认通过**

Run: `uv run pytest backend/tests/test_auth_api.py -v` — Expected: 4 passed

- [ ] **Step 5: 提交**

```bash
git add backend/app backend/tests
git commit -m "feat: add auth API with JWT login and me endpoints"
```

---

### Task 8: 关键字与配置 API

**Files:**
- Create: `backend/app/schemas/keyword.py`、`backend/app/schemas/settings.py`、`backend/app/api/keywords.py`、`backend/app/api/settings.py`
- Create: `backend/tests/test_keywords_api.py`
- Test: `backend/tests/test_keywords_api.py`

**Interfaces:**
- Consumes: `get_db`、`get_current_user`、`Keyword`、`Setting` 模型
- Produces: `keywords_router`（GET/POST /api/keywords、PUT/DELETE /api/keywords/{id}、POST /api/keywords/{id}/toggle）、`settings_router`（GET/PUT /api/settings/schedule）；schema `KeywordCreate/KeywordUpdate/KeywordOut`、`ScheduleIn/ScheduleOut`

- [ ] **Step 1: 写失败测试**

`backend/tests/test_keywords_api.py`：
```python
import pytest
from fastapi.testclient import TestClient

from backend.app.api.deps import ensure_admin
from backend.app.core.database import SessionLocal, init_db
from backend.app.main import create_app


@pytest.fixture()
def client(config):
    init_db(config)
    with SessionLocal() as s:
        ensure_admin(s, config)
    app = create_app(config)
    with TestClient(app) as c:
        token = c.post("/api/auth/login", json={"username": config.auth_username, "password": config.auth_password}).json()["access_token"]
        c.headers.update({"Authorization": f"Bearer {token}"})
        yield c


def test_keyword_crud(client):
    resp = client.post("/api/keywords", json={"keyword": "python"})
    assert resp.status_code == 200
    kid = resp.json()["id"]
    assert resp.json()["enabled"] is True
    assert resp.json()["scrape_mode"] == "playwright"

    resp = client.post("/api/keywords", json={"keyword": "python"})
    assert resp.status_code == 409

    resp = client.put(f"/api/keywords/{kid}", json={"scrape_mode": "playwright"})
    assert resp.status_code == 200

    resp = client.post(f"/api/keywords/{kid}/toggle")
    assert resp.status_code == 200
    assert resp.json()["enabled"] is False

    resp = client.get("/api/keywords")
    assert resp.status_code == 200
    assert len(resp.json()) == 1

    resp = client.delete(f"/api/keywords/{kid}")
    assert resp.status_code == 200
    assert client.get("/api/keywords").json() == []


def test_keyword_requires_auth(config):
    init_db(config)
    with SessionLocal() as s:
        ensure_admin(s, config)
    app = create_app(config)
    with TestClient(app) as c:
        assert c.get("/api/keywords").status_code == 401
```

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run pytest backend/tests/test_keywords_api.py -v` — Expected: FAIL（路由不存在）

- [ ] **Step 3: 实现 schemas 与路由**

`backend/app/schemas/keyword.py`：
```python
from datetime import datetime

from pydantic import BaseModel


class KeywordCreate(BaseModel):
    keyword: str
    scrape_mode: str = "playwright"


class KeywordUpdate(BaseModel):
    keyword: str | None = None
    scrape_mode: str | None = None


class KeywordOut(BaseModel):
    id: int
    keyword: str
    enabled: bool
    scrape_mode: str
    last_scraped_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}
```

`backend/app/schemas/settings.py`：
```python
from pydantic import BaseModel


class ScheduleIn(BaseModel):
    enabled: bool
    interval_minutes: int
    keyword_ids: list[int] = []


class ScheduleOut(ScheduleIn):
    pass
```

`backend/app/api/keywords.py`：
```python
from fastapi import APIRouter, Depends

from backend.app.api.deps import get_current_user, get_db
from backend.app.core.exceptions import AppError
from backend.app.models import Keyword
from backend.app.schemas.keyword import KeywordCreate, KeywordOut, KeywordUpdate

keywords_router = APIRouter(prefix="/api/keywords", tags=["keywords"])


@keywords_router.get("", response_model=list[KeywordOut])
def list_keywords(db=Depends(get_db), user=Depends(get_current_user)):
    return db.query(Keyword).order_by(Keyword.id).all()


@keywords_router.post("", response_model=KeywordOut)
def create_keyword(body: KeywordCreate, db=Depends(get_db), user=Depends(get_current_user)):
    if db.query(Keyword).filter_by(keyword=body.keyword).first():
        raise AppError(f"关键字已存在: {body.keyword}", 409)
    kw = Keyword(keyword=body.keyword, scrape_mode=body.scrape_mode)
    db.add(kw)
    db.commit()
    db.refresh(kw)
    return kw


@keywords_router.put("/{keyword_id}", response_model=KeywordOut)
def update_keyword(keyword_id: int, body: KeywordUpdate, db=Depends(get_db), user=Depends(get_current_user)):
    kw = db.get(Keyword, keyword_id)
    if kw is None:
        raise AppError("关键字不存在", 404)
    if body.keyword is not None:
        if db.query(Keyword).filter(Keyword.keyword == body.keyword, Keyword.id != keyword_id).first():
            raise AppError(f"关键字已存在: {body.keyword}", 409)
        kw.keyword = body.keyword
    if body.scrape_mode is not None:
        kw.scrape_mode = body.scrape_mode
    db.commit()
    db.refresh(kw)
    return kw


@keywords_router.delete("/{keyword_id}")
def delete_keyword(keyword_id: int, db=Depends(get_db), user=Depends(get_current_user)):
    kw = db.get(Keyword, keyword_id)
    if kw is None:
        raise AppError("关键字不存在", 404)
    db.delete(kw)
    db.commit()
    return {"ok": True}


@keywords_router.post("/{keyword_id}/toggle", response_model=KeywordOut)
def toggle_keyword(keyword_id: int, db=Depends(get_db), user=Depends(get_current_user)):
    kw = db.get(Keyword, keyword_id)
    if kw is None:
        raise AppError("关键字不存在", 404)
    kw.enabled = not kw.enabled
    db.commit()
    db.refresh(kw)
    return kw
```

`backend/app/api/settings.py`：
```python
from fastapi import APIRouter, Depends

from backend.app.api.deps import get_current_user, get_db
from backend.app.models import Setting
from backend.app.schemas.settings import ScheduleIn, ScheduleOut

settings_router = APIRouter(prefix="/api/settings", tags=["settings"])

_SCHEDULE_KEY = "schedule"
_DEFAULT_SCHEDULE = {"enabled": False, "interval_minutes": 60, "keyword_ids": []}


@settings_router.get("/schedule", response_model=ScheduleOut)
def get_schedule(db=Depends(get_db), user=Depends(get_current_user)):
    row = db.query(Setting).filter_by(key=_SCHEDULE_KEY).first()
    value = row.value if row else _DEFAULT_SCHEDULE
    return ScheduleOut(**value)


@settings_router.put("/schedule", response_model=ScheduleOut)
def put_schedule(body: ScheduleIn, db=Depends(get_db), user=Depends(get_current_user)):
    row = db.query(Setting).filter_by(key=_SCHEDULE_KEY).first()
    if row is None:
        row = Setting(key=_SCHEDULE_KEY, value=body.model_dump())
        db.add(row)
    else:
        row.value = body.model_dump()
    db.commit()
    return body
```

- [ ] **Step 4: 在 main.py 挂载新路由并运行测试**

`backend/app/main.py` 追加：
```python
from backend.app.api.keywords import keywords_router
from backend.app.api.settings import settings_router

app.include_router(keywords_router)
app.include_router(settings_router)
```

Run: `uv run pytest backend/tests/test_keywords_api.py -v` — Expected: 2 passed

- [ ] **Step 5: 提交**

```bash
git add backend/app backend/tests
git commit -m "feat: add keywords and settings APIs"
```

---

### Task 9: 任务 API（创建 409 互斥/列表/详情/删除）

**Files:**
- Create: `backend/app/schemas/task.py`、`backend/app/api/tasks.py`
- Create: `backend/tests/test_tasks_api.py`
- Test: `backend/tests/test_tasks_api.py`

**Interfaces:**
- Consumes: `TaskStatus`、`get_db`、`get_current_user`、`Config.max_pages`
- Produces: `tasks_router`（POST/GET /api/tasks、GET/DELETE /api/tasks/{id}）；`TaskCreate/TaskOut` schema

- [ ] **Step 1: 写失败测试**

`backend/tests/test_tasks_api.py`：
```python
import pytest
from fastapi.testclient import TestClient

from backend.app.api.deps import ensure_admin
from backend.app.core.database import SessionLocal, init_db
from backend.app.main import create_app
from backend.app.models import ScrapeTask


@pytest.fixture()
def client(config):
    init_db(config)
    with SessionLocal() as s:
        ensure_admin(s, config)
        kw = __import__("backend.app.models", fromlist=["Keyword"]).Keyword(keyword="python")
        s.add(kw)
        s.commit()
    app = create_app(config)
    with TestClient(app) as c:
        token = c.post("/api/auth/login", json={"username": config.auth_username, "password": config.auth_password}).json()["access_token"]
        c.headers.update({"Authorization": f"Bearer {token}"})
        yield c


def test_create_task(client):
    resp = client.post("/api/tasks", json={"keyword_id": 1})
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "queued"
    assert data["mode"] == "playwright"


def test_create_task_conflict_409(client):
    assert client.post("/api/tasks", json={"keyword_id": 1}).status_code == 200
    resp = client.post("/api/tasks", json={"keyword_id": 1})
    assert resp.status_code == 409


def test_create_task_max_pages_cap(client):
    resp = client.post("/api/tasks", json={"keyword_id": 1, "max_pages": 9999})
    assert resp.status_code == 400


def test_list_and_delete_task(client):
    client.post("/api/tasks", json={"keyword_id": 1})
    tasks = client.get("/api/tasks").json()
    assert len(tasks) == 1
    tid = tasks[0]["id"]
    resp = client.delete(f"/api/tasks/{tid}")
    assert resp.status_code == 200
    assert client.get("/api/tasks").json() == []


def test_delete_running_task_400(client):
    tid = client.post("/api/tasks", json={"keyword_id": 1}).json()["id"]
    with SessionLocal() as s:
        t = s.get(ScrapeTask, tid)
        t.status = "in_progress"
        s.commit()
    resp = client.delete(f"/api/tasks/{tid}")
    assert resp.status_code == 400
```

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run pytest backend/tests/test_tasks_api.py -v` — Expected: FAIL（路由不存在）

- [ ] **Step 3: 实现 schemas/task.py 与 api/tasks.py**

`backend/app/schemas/task.py`：
```python
from datetime import datetime

from pydantic import BaseModel


class TaskCreate(BaseModel):
    keyword_id: int
    mode: str = "playwright"
    max_pages: int | None = None


class TaskOut(BaseModel):
    id: int
    keyword_id: int
    mode: str
    status: str
    total_pages: int | None
    total_found: int
    success_count: int
    failed_count: int
    last_page: int
    start_time: datetime | None
    end_time: datetime | None
    error_message: str | None
    created_at: datetime

    model_config = {"from_attributes": True}
```

`backend/app/api/tasks.py`：
```python
from fastapi import APIRouter, Depends

from backend.app.api.deps import _current_config, get_current_user, get_db
from backend.app.core.exceptions import AppError
from backend.app.models import Keyword, ScrapeTask, TaskStatus
from backend.app.schemas.task import TaskCreate, TaskOut

tasks_router = APIRouter(prefix="/api/tasks", tags=["tasks"])

_RUNNING = (TaskStatus.QUEUED.value, TaskStatus.IN_PROGRESS.value)


@tasks_router.post("", response_model=TaskOut)
def create_task(body: TaskCreate, db=Depends(get_db), user=Depends(get_current_user)):
    kw = db.get(Keyword, body.keyword_id)
    if kw is None:
        raise AppError("关键字不存在", 404)
    if body.mode != "playwright":
        raise AppError("v1 仅支持 playwright 模式", 400)
    if body.max_pages is not None and (body.max_pages < 1 or body.max_pages > _current_config.max_pages):
        raise AppError(f"max_pages 需在 1-{_current_config.max_pages} 之间", 400)
    if db.query(ScrapeTask).filter(ScrapeTask.keyword_id == body.keyword_id, ScrapeTask.status.in_(_RUNNING)).first():
        raise AppError("该关键字已有进行中的任务", 409)
    task = ScrapeTask(
        keyword_id=body.keyword_id,
        mode=body.mode,
        status=TaskStatus.QUEUED.value,
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


@tasks_router.get("", response_model=list[TaskOut])
def list_tasks(db=Depends(get_db), user=Depends(get_current_user)):
    return db.query(ScrapeTask).order_by(ScrapeTask.created_at.desc()).all()


@tasks_router.get("/{task_id}", response_model=TaskOut)
def get_task(task_id: int, db=Depends(get_db), user=Depends(get_current_user)):
    task = db.get(ScrapeTask, task_id)
    if task is None:
        raise AppError("任务不存在", 404)
    return task


@tasks_router.delete("/{task_id}")
def delete_task(task_id: int, db=Depends(get_db), user=Depends(get_current_user)):
    task = db.get(ScrapeTask, task_id)
    if task is None:
        raise AppError("任务不存在", 404)
    # 只禁 in_progress：queued 可删（视为取消）——计划测试 test_list_and_delete_task 裁定
    if task.status == TaskStatus.IN_PROGRESS.value:
        raise AppError("进行中的任务不能删除", 400)
    db.delete(task)
    db.commit()
    return {"ok": True}
```

- [ ] **Step 4: 挂载路由并运行测试**

`backend/app/main.py` 追加：
```python
from backend.app.api.tasks import tasks_router

app.include_router(tasks_router)
```

Run: `uv run pytest backend/tests/test_tasks_api.py -v` — Expected: 5 passed

- [ ] **Step 5: 提交**

```bash
git add backend/app backend/tests
git commit -m "feat: add tasks API with 409 concurrency guard"
```

---

### Task 10: 存储 upsert + 任务执行器 + 崩溃恢复

**Files:**
- Create: `backend/app/services/storage.py`、`backend/app/services/task_runner.py`
- Create: `backend/tests/test_storage.py`、`backend/tests/test_task_runner.py`
- Test: `backend/tests/test_storage.py`、`backend/tests/test_task_runner.py`

**Interfaces:**
- Consumes: `JobDraft/CompanyDraft/PageResult`、`Scraper`、`TaskStatus`、`Job/Company/ScrapeTask/Keyword` 模型
- Produces: `upsert_jobs(db, jobs: list[JobDraft]) -> int`、`upsert_companies(db, companies: list[CompanyDraft]) -> int`（缺失字段不覆盖已有值——companies 若已存在且新值为 None，保留旧值）、`execute_task(task_id: int)`（异步，完整执行一个任务）、`recover_interrupted_tasks()`（启动时调用，queued/in_progress → failed）

- [ ] **Step 1: 写失败测试**

`backend/tests/test_storage.py`：
```python
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
```

`backend/tests/test_task_runner.py`：
```python
from backend.app.core.database import SessionLocal, init_db
from backend.app.models import Keyword, ScrapeTask, TaskStatus
from backend.app.services.task_runner import recover_interrupted_tasks


def test_recover_interrupted_tasks(config):
    init_db(config)
    with SessionLocal() as s:
        kw = Keyword(keyword="python")
        s.add(kw)
        s.commit()
        s.add_all([
            ScrapeTask(keyword_id=kw.id, status=TaskStatus.QUEUED.value),
            ScrapeTask(keyword_id=kw.id, status=TaskStatus.IN_PROGRESS.value),
            ScrapeTask(keyword_id=kw.id, status=TaskStatus.SUCCESS.value),
        ])
        s.commit()
    recover_interrupted_tasks()
    with SessionLocal() as s:
        statuses = {t.status for t in s.query(ScrapeTask).all()}
        assert "queued" not in statuses
        assert "in_progress" not in statuses
        failed = s.query(ScrapeTask).filter_by(status=TaskStatus.FAILED.value).all()
        assert len(failed) == 2
        assert failed[0].error_message == "进程重启中断"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run pytest backend/tests/test_storage.py backend/tests/test_task_runner.py -v` — Expected: FAIL（模块不存在）

- [ ] **Step 3: 实现 storage.py 与 task_runner.py**

`backend/app/services/storage.py`：
```python
import logging
from datetime import datetime

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
            # 值未变化时 ORM 不会标脏，onupdate 不触发；显式刷新以保证统计窗口
            existing.updated_at = datetime.now()
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
```

`backend/app/services/task_runner.py`：
```python
import asyncio
import logging
import threading
import time
from datetime import datetime

from sqlalchemy.orm import Session

from backend.app.core.config import REPO_ROOT, Config
from backend.app.core.database import SessionLocal
from backend.app.models import Keyword, ScrapeTask, TaskStatus
from backend.app.scrapers.playwright import PlaywrightScraper
from backend.app.services.storage import upsert_companies, upsert_jobs

logger = logging.getLogger("job_hunter")

_POLL_SECONDS = 5


def recover_interrupted_tasks() -> None:
    with SessionLocal() as db:
        tasks = (
            db.query(ScrapeTask)
            .filter(ScrapeTask.status.in_([TaskStatus.QUEUED.value, TaskStatus.IN_PROGRESS.value]))
            .all()
        )
        for t in tasks:
            t.status = TaskStatus.FAILED.value
            t.error_message = "进程重启中断"
        if tasks:
            db.commit()
            logger.warning("崩溃恢复：%s 个任务置为失败", len(tasks))


def _claim_next_task(db: Session) -> ScrapeTask | None:
    task = (
        db.query(ScrapeTask)
        .filter_by(status=TaskStatus.QUEUED.value)
        .order_by(ScrapeTask.created_at)
        .first()
    )
    if task is None:
        return None
    task.status = TaskStatus.IN_PROGRESS.value
    task.start_time = datetime.now()
    db.commit()
    db.refresh(task)
    return task


async def execute_task(task_id: int) -> None:
    with SessionLocal() as db:
        task = db.get(ScrapeTask, task_id)
        keyword = db.get(Keyword, task.keyword_id)
        kw_text = keyword.keyword if keyword else ""
    # PRD scrape_tasks 无 max_pages 列，per-task 值仅校验不落库，执行统一用全局上限
    max_pages = Config(repo_root=REPO_ROOT).max_pages
    scraper = PlaywrightScraper()
    try:
        first_page = True
        async for result in scraper.search(kw_text, max_pages):
            with SessionLocal() as db:
                task = db.get(ScrapeTask, task_id)
                if result.failed:
                    task.failed_count += 1
                else:
                    task.success_count += 1
                    upsert_jobs(db, result.jobs)
                    upsert_companies(db, result.companies)
                    task.total_found += len(result.jobs)
                task.last_page = result.page_num
                if first_page and result.total_pages:
                    task.total_pages = result.total_pages
                    first_page = False
                db.commit()
    except Exception as exc:
        logger.exception("任务执行异常 task_id=%s", task_id)
        with SessionLocal() as db:
            task = db.get(ScrapeTask, task_id)
            task.status = TaskStatus.FAILED.value
            task.end_time = datetime.now()
            task.error_message = str(exc)[:1000]
            db.commit()
        await scraper.close()
        return
    with SessionLocal() as db:
        task = db.get(ScrapeTask, task_id)
        keyword = db.get(Keyword, task.keyword_id)
        if keyword:
            keyword.last_scraped_at = datetime.now()
        task.end_time = datetime.now()
        if task.failed_count == 0:
            task.status = TaskStatus.SUCCESS.value
        else:
            task.status = TaskStatus.PARTIAL_SUCCESS.value
        db.commit()
        logger.info(
            "任务完成 task_id=%s keyword=%s status=%s success=%s failed=%s",
            task_id, kw_text, task.status, task.success_count, task.failed_count,
        )
    await scraper.close()


class TaskRunner:
    def __init__(self):
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                task = None
                with SessionLocal() as db:
                    task = _claim_next_task(db)
                if task:
                    logger.info("开始执行任务 task_id=%s", task.id)
                    asyncio.run(execute_task(task.id))
                else:
                    self._stop.wait(_POLL_SECONDS)
            except Exception:
                # 任何未捕获异常都不能杀死守护线程，否则任务将永久卡在 in_progress
                logger.exception("任务执行循环异常")
```

- [ ] **Step 4: 运行测试确认通过**

Run: `uv run pytest backend/tests/test_storage.py backend/tests/test_task_runner.py -v` — Expected: 3 passed

- [ ] **Step 5: 提交**

```bash
git add backend/app backend/tests
git commit -m "feat: add storage upsert, task runner and crash recovery"
```

---

### Task 11: 定时调度（APScheduler）

**Files:**
- Create: `backend/app/services/scheduler.py`
- Create: `backend/tests/test_scheduler.py`
- Test: `backend/tests/test_scheduler.py`

**Interfaces:**
- Consumes: `Setting`（key="schedule"）、`ScrapeTask`、`TaskStatus`
- Produces: `SchedulerService`（`start()/stop()/apply_schedule()`）：读 settings，enabled 时按 interval_minutes 为 keyword_ids 创建 queued 任务；`create_scheduled_tasks(keyword_ids: list[int])`（同 keyword 有进行中任务则跳过——幂等）

- [ ] **Step 1: 写失败测试**

`backend/tests/test_scheduler.py`：
```python
from backend.app.core.database import SessionLocal, init_db
from backend.app.models import Keyword, ScrapeTask
from backend.app.services.scheduler import create_scheduled_tasks


def test_create_scheduled_tasks(config):
    init_db(config)
    with SessionLocal() as s:
        k1 = Keyword(keyword="a")
        k2 = Keyword(keyword="b")
        s.add_all([k1, k2])
        s.commit()
        assert create_scheduled_tasks([k1.id, k2.id]) == 2
        assert s.query(ScrapeTask).count() == 2
        # 已排队/进行中的 keyword 跳过——幂等（与 create_scheduled_tasks 实现一致）
        assert create_scheduled_tasks([k1.id, k2.id]) == 0
        assert s.query(ScrapeTask).count() == 2
        task = s.query(ScrapeTask).filter_by(keyword_id=k1.id).first()
        task.status = "in_progress"
        s.commit()
        assert create_scheduled_tasks([k1.id, k2.id]) == 1
        assert s.query(ScrapeTask).count() == 3
        assert s.query(ScrapeTask).filter_by(keyword_id=k2.id).count() == 2
```

> 注：brief 原测试断言二次调用 count==4/5（允许对已排队 keyword 重复入队），与实现（跳过 queued+in_progress）自相矛盾——已按实现+文档语义修正测试（Task 11 裁定，与 Task 9 API 409 语义自洽）。

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run pytest backend/tests/test_scheduler.py -v` — Expected: FAIL（模块不存在）

- [ ] **Step 3: 实现 scheduler.py**

`backend/app/services/scheduler.py`：
```python
import logging

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

from backend.app.core.database import SessionLocal
from backend.app.models import ScrapeTask, Setting, TaskStatus

logger = logging.getLogger("job_hunter")

_SCHEDULE_KEY = "schedule"
_DEFAULT_SCHEDULE = {"enabled": False, "interval_minutes": 60, "keyword_ids": []}


def create_scheduled_tasks(keyword_ids: list[int]) -> int:
    created = 0
    with SessionLocal() as db:
        running = {
            t.keyword_id
            for t in db.query(ScrapeTask).filter(
                ScrapeTask.status.in_([TaskStatus.QUEUED.value, TaskStatus.IN_PROGRESS.value])
            )
        }
        for kid in keyword_ids:
            if kid in running:
                continue
            db.add(ScrapeTask(keyword_id=kid, status=TaskStatus.QUEUED.value))
            created += 1
        db.commit()
    if created:
        logger.info("定时任务入队 %s 个", created)
    return created


def _read_schedule() -> dict:
    with SessionLocal() as db:
        row = db.query(Setting).filter_by(key=_SCHEDULE_KEY).first()
        return row.value if row else _DEFAULT_SCHEDULE


class SchedulerService:
    def __init__(self):
        self._scheduler = BackgroundScheduler(daemon=True)

    def start(self) -> None:
        self.apply_schedule()
        self._scheduler.start()

    def stop(self) -> None:
        self._scheduler.shutdown(wait=False)

    def apply_schedule(self) -> None:
        schedule = _read_schedule()
        job_id = "scheduled_scrape"
        if self._scheduler.get_job(job_id):
            self._scheduler.remove_job(job_id)
        if not schedule.get("enabled"):
            logger.info("定时任务已停用")
            return
        minutes = max(1, int(schedule.get("interval_minutes", 60)))
        keyword_ids = list(schedule.get("keyword_ids", []))
        self._scheduler.add_job(
            create_scheduled_tasks,
            trigger=IntervalTrigger(minutes=minutes),
            args=[keyword_ids],
            id=job_id,
            replace_existing=True,
        )
        logger.info("定时任务已启用 interval=%s 分钟 keywords=%s", minutes, keyword_ids)
```

- [ ] **Step 4: 运行测试确认通过**

Run: `uv run pytest backend/tests/test_scheduler.py -v` — Expected: 1 passed

- [ ] **Step 5: 提交**

```bash
git add backend/app backend/tests
git commit -m "feat: add APScheduler periodic scraping service"
```

---

### Task 12: 职位与公司 API

**Files:**
- Create: `backend/app/schemas/job.py`、`backend/app/schemas/company.py`、`backend/app/api/jobs.py`、`backend/app/api/companies.py`
- Create: `backend/tests/test_jobs_api.py`
- Test: `backend/tests/test_jobs_api.py`

**Interfaces:**
- Consumes: `Job`/`Company` 模型、`get_db`、`get_current_user`
- Produces: `jobs_router`（GET /api/jobs 筛选分页、GET /api/jobs/{id}）、`companies_router`（GET /api/companies 筛选）；`JobOut/CompanyOut` schema

- [ ] **Step 1: 写失败测试**

`backend/tests/test_jobs_api.py`：
```python
import pytest
from fastapi.testclient import TestClient

from backend.app.api.deps import ensure_admin
from backend.app.core.database import SessionLocal, init_db
from backend.app.main import create_app
from backend.app.models import Company, Job


@pytest.fixture()
def client(config):
    init_db(config)
    with SessionLocal() as s:
        ensure_admin(s, config)
        s.add_all([
            Company(company_id="c1", name="A公司", type="民营", industry="软件", size="100人"),
            Job(job_id="j1", title="Python工程师", salary_min=10000, salary_max=20000, city="上海", district="长宁区", area="长宁区", tags=["急招"], company_id="c1"),
            Job(job_id="j2", title="Java工程师", salary_min=15000, salary_max=25000, city="北京", tags=["高薪"], company_id="c1"),
            Job(job_id="j3", title="前端工程师", salary_min=None, salary_max=None, city="上海", tags=[], company_id="c1"),
        ])
        s.commit()
    app = create_app(config)
    with TestClient(app) as c:
        token = c.post("/api/auth/login", json={"username": config.auth_username, "password": config.auth_password}).json()["access_token"]
        c.headers.update({"Authorization": f"Bearer {token}"})
        yield c


def test_list_jobs(client):
    resp = client.get("/api/jobs")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 3
    assert len(data["items"]) == 3


def test_filter_jobs(client):
    resp = client.get("/api/jobs", params={"city": "上海"})
    assert resp.json()["total"] == 2
    resp = client.get("/api/jobs", params={"tag": "急招"})
    assert resp.json()["total"] == 1
    resp = client.get("/api/jobs", params={"salary_min": 12000})
    assert resp.json()["total"] == 1
    resp = client.get("/api/jobs", params={"company_id": "c1"})
    assert resp.json()["total"] == 3
    resp = client.get("/api/jobs", params={"keyword": "工程师"})
    assert resp.json()["total"] == 3
    resp = client.get("/api/jobs", params={"keyword": "Python"})
    assert resp.json()["total"] == 1
    resp = client.get("/api/jobs", params={"keyword": "长宁"})
    assert resp.json()["total"] == 1


def test_get_job_detail(client):
    resp = client.get("/api/jobs/j1")
    assert resp.status_code == 200
    assert resp.json()["title"] == "Python工程师"


def test_companies_filter(client):
    resp = client.get("/api/companies", params={"type": "民营"})
    assert resp.status_code == 200
    assert resp.json()["total"] == 1
```

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run pytest backend/tests/test_jobs_api.py -v` — Expected: FAIL（路由不存在）

- [ ] **Step 3: 实现 schemas 与路由**

`backend/app/schemas/job.py`：
```python
from datetime import datetime

from pydantic import BaseModel


class JobOut(BaseModel):
    id: int
    job_id: str
    title: str
    salary_raw: str | None
    salary_min: int | None
    salary_max: int | None
    city: str | None
    district: str | None
    area: str | None
    tags: list[str]
    publish_time: datetime | None
    source: str
    company_id: str | None
    job_url: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class JobPage(BaseModel):
    total: int
    items: list[JobOut]
```

`backend/app/schemas/company.py`：
```python
from datetime import datetime

from pydantic import BaseModel


class CompanyOut(BaseModel):
    id: int
    company_id: str
    name: str
    type: str | None
    industry: str | None
    size: str | None
    activity: str | None
    website: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class CompanyPage(BaseModel):
    total: int
    items: list[CompanyOut]
```

`backend/app/api/jobs.py`：
```python
from fastapi import APIRouter, Depends, Query
from sqlalchemy import or_

from backend.app.api.deps import get_current_user, get_db
from backend.app.core.exceptions import AppError
from backend.app.models import Job
from backend.app.schemas.job import JobOut, JobPage

jobs_router = APIRouter(prefix="/api/jobs", tags=["jobs"])


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
        # 底薪语义：salary_min 筛选下限（brief 原文列写反，已按自带测试修正）
        q = q.filter(Job.salary_min >= salary_min)
    if salary_max is not None:
        q = q.filter(Job.salary_max <= salary_max)
    items = q.order_by(Job.updated_at.desc()).all()
    if tag:
        items = [j for j in items if tag in (j.tags or [])]
    total = len(items)
    start = (page - 1) * page_size
    return JobPage(total=total, items=items[start : start + page_size])


@jobs_router.get("/{job_key}", response_model=JobOut)
def get_job(job_key: str, db=Depends(get_db), user=Depends(get_current_user)):
    job = db.query(Job).filter(Job.job_id == job_key).first()
    if job is None:
        raise AppError("职位不存在", 404)
    return job
```

`backend/app/api/companies.py`：
```python
from fastapi import APIRouter, Depends, Query

from backend.app.api.deps import get_current_user, get_db
from backend.app.models import Company
from backend.app.schemas.company import CompanyOut, CompanyPage

companies_router = APIRouter(prefix="/api/companies", tags=["companies"])


@companies_router.get("", response_model=CompanyPage)
def list_companies(
    type: str | None = None,
    industry: str | None = None,
    size: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db=Depends(get_db),
    user=Depends(get_current_user),
):
    q = db.query(Company)
    if type:
        q = q.filter(Company.type == type)
    if industry:
        q = q.filter(Company.industry.contains(industry))
    if size:
        q = q.filter(Company.size == size)
    total = q.count()
    items = q.order_by(Company.updated_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
    return CompanyPage(total=total, items=items)
```

- [ ] **Step 4: 挂载路由并运行测试**

`backend/app/main.py` 追加：
```python
from backend.app.api.jobs import jobs_router
from backend.app.api.companies import companies_router

app.include_router(jobs_router)
app.include_router(companies_router)
```

Run: `uv run pytest backend/tests/test_jobs_api.py -v` — Expected: 4 passed

- [ ] **Step 5: 提交**

```bash
git add backend/app backend/tests
git commit -m "feat: add jobs and companies query APIs"
```

---

### Task 13: 统计 service 与 API

**Files:**
- Create: `backend/app/services/stats.py`、`backend/app/api/stats.py`
- Create: `backend/tests/test_stats.py`
- Test: `backend/tests/test_stats.py`

**Interfaces:**
- Consumes: `Job/Company/ScrapeTask/Keyword` 模型、`TaskStatus`
- Produces: `get_window_start(db, keyword_id: int | None = None) -> datetime | None`（最近一次 success/partial_success 任务 start_time）；`overview(db, window)`、`salary_stats(db, window)`、`company_stats(db, window)`、`trend_stats(db, window)`、`tag_stats(db, window)`；`stats_router`（/api/stats/overview|salary|company|trend|tags）

- [ ] **Step 1: 写失败测试**

`backend/tests/test_stats.py`：
```python
from datetime import datetime, timedelta

from fastapi.testclient import TestClient

from backend.app.api.deps import ensure_admin
from backend.app.core.database import SessionLocal, init_db
from backend.app.main import create_app
from backend.app.models import Company, Job, Keyword, ScrapeTask, TaskStatus
from backend.app.services.stats import get_window_start, overview, tag_stats


def _seed(config):
    init_db(config)
    with SessionLocal() as s:
        ensure_admin(s, config)
        kw = Keyword(keyword="python")
        s.add(kw)
        s.commit()
        base = datetime(2026, 7, 1, 10, 0, 0)
        s.add(ScrapeTask(keyword_id=kw.id, status=TaskStatus.SUCCESS.value, start_time=base, end_time=base + timedelta(minutes=5)))
        old = datetime(2026, 6, 1, 10, 0, 0)
        s.add(ScrapeTask(keyword_id=kw.id, status=TaskStatus.SUCCESS.value, start_time=old, end_time=old + timedelta(minutes=5)))
        s.add_all([
            Company(company_id="c1", name="A", type="民营", industry="软件", size="100人"),
            Company(company_id="c2", name="B", type="国企", industry="金融", size="1000人"),
        ])
        s.add_all([
            Job(job_id="j1", title="t1", salary_min=8000, salary_max=12000, city="上海", tags=["急招"], company_id="c1", updated_at=base + timedelta(hours=1)),
            Job(job_id="j2", title="t2", salary_min=15000, salary_max=25000, city="北京", tags=["高薪"], company_id="c2", updated_at=base + timedelta(hours=2)),
            Job(job_id="j3", title="t3", salary_min=9000, salary_max=15000, city="上海", tags=["急招", "双休"], company_id="c1", updated_at=old + timedelta(hours=1)),
        ])
        s.commit()


def test_window_uses_latest_success_task(config):
    _seed(config)
    with SessionLocal() as s:
        window = get_window_start(s)
        assert window == datetime(2026, 7, 1, 10, 0, 0)
        stats = overview(s, window)
        assert stats["total_jobs"] == 2
        assert stats["total_cities"] == 2
        assert stats["total_companies"] == 2
        assert stats["salary_parsed"] == 2


def test_tag_stats_window(config):
    _seed(config)
    with SessionLocal() as s:
        tags = tag_stats(s, get_window_start(s), top_n=2)
        assert [t["tag"] for t in tags] == ["急招", "高薪"]


def test_stats_api_endpoints(config):
    _seed(config)
    app = create_app(config)
    with TestClient(app) as c:
        token = c.post("/api/auth/login", json={"username": config.auth_username, "password": config.auth_password}).json()["access_token"]
        c.headers.update({"Authorization": f"Bearer {token}"})
        for ep in ["overview", "salary", "company", "trend", "tags"]:
            resp = c.get(f"/api/stats/{ep}")
            assert resp.status_code == 200
```

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run pytest backend/tests/test_stats.py -v` — Expected: FAIL（模块不存在）

- [ ] **Step 3: 实现 stats service、schemas 与路由**

`backend/app/services/stats.py`：
```python
import logging
from collections import Counter
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from backend.app.models import Company, Job, ScrapeTask, TaskStatus

logger = logging.getLogger("job_hunter")

_DONE = (TaskStatus.SUCCESS.value, TaskStatus.PARTIAL_SUCCESS.value)


def get_window_start(db: Session, keyword_id: int | None = None) -> datetime | None:
    q = db.query(ScrapeTask).filter(ScrapeTask.status.in_(_DONE))
    if keyword_id is not None:
        q = q.filter(ScrapeTask.keyword_id == keyword_id)
    task = q.order_by(ScrapeTask.start_time.desc()).first()
    return task.start_time if task else None


def _windowed_jobs(db: Session, window: datetime | None):
    q = db.query(Job)
    if window is not None:
        q = q.filter(Job.updated_at >= window)
    return q


def overview(db: Session, window: datetime | None) -> dict:
    jobs = _windowed_jobs(db, window).all()
    companies = {j.company_id for j in jobs if j.company_id}
    salary_parsed = sum(1 for j in jobs if j.salary_min is not None and j.salary_max is not None)
    return {
        "total_jobs": len(jobs),
        "total_cities": len({j.city for j in jobs if j.city}),
        "total_companies": len(companies),
        "salary_parsed": salary_parsed,
    }


def salary_stats(db: Session, window: datetime | None, group_by: str = "city") -> dict:
    jobs = [j for j in _windowed_jobs(db, window).all() if j.salary_min is not None and j.salary_max is not None]
    groups: dict[str, list[int]] = {}
    for j in jobs:
        key = getattr(j, group_by, None) or "未知"
        groups.setdefault(key, []).append((j.salary_min + j.salary_max) // 2)
    result = []
    for key, mids in sorted(groups.items()):
        result.append({
            "key": key,
            "count": len(mids),
            "min": min(mids),
            "max": max(mids),
            "median": sorted(mids)[len(mids) // 2],
        })
    return {"group_by": group_by, "items": result}


def company_stats(db: Session, window: datetime | None) -> dict:
    jobs = _windowed_jobs(db, window).all()
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


def trend_stats(db: Session, window: datetime | None, days: int = 30) -> dict:
    start = window or datetime.now() - timedelta(days=days)
    jobs = db.query(Job).filter(Job.updated_at >= start).all()
    per_day: Counter = Counter()
    for j in jobs:
        per_day[j.updated_at.date().isoformat()] += 1
    return {"days": [{"date": d, "count": n} for d, n in sorted(per_day.items())]}


def tag_stats(db: Session, window: datetime | None, top_n: int = 10) -> list[dict]:
    counter: Counter = Counter()
    for j in _windowed_jobs(db, window).all():
        for t in j.tags or []:
            counter[t] += 1
    return [{"tag": t, "count": n} for t, n in counter.most_common(top_n)]
```

stats 返回 dict，直接使用 dict 响应，无需 Pydantic 模型（FastAPI 自动序列化）。

`backend/app/api/stats.py`：
```python
from fastapi import APIRouter, Depends

from backend.app.api.deps import get_current_user, get_db
from backend.app.services import stats as stats_service

stats_router = APIRouter(prefix="/api/stats", tags=["stats"])


@stats_router.get("/overview")
def get_overview(keyword_id: int | None = None, db=Depends(get_db), user=Depends(get_current_user)):
    window = stats_service.get_window_start(db, keyword_id)
    return stats_service.overview(db, window)


@stats_router.get("/salary")
def get_salary(keyword_id: int | None = None, group_by: str = "city", db=Depends(get_db), user=Depends(get_current_user)):
    window = stats_service.get_window_start(db, keyword_id)
    return stats_service.salary_stats(db, window, group_by=group_by)


@stats_router.get("/company")
def get_company(keyword_id: int | None = None, db=Depends(get_db), user=Depends(get_current_user)):
    window = stats_service.get_window_start(db, keyword_id)
    return stats_service.company_stats(db, window)


@stats_router.get("/trend")
def get_trend(keyword_id: int | None = None, days: int = 30, db=Depends(get_db), user=Depends(get_current_user)):
    window = stats_service.get_window_start(db, keyword_id)
    return stats_service.trend_stats(db, window, days=days)


@stats_router.get("/tags")
def get_tags(keyword_id: int | None = None, top_n: int = 10, db=Depends(get_db), user=Depends(get_current_user)):
    window = stats_service.get_window_start(db, keyword_id)
    return stats_service.tag_stats(db, window, top_n=top_n)
```

- [ ] **Step 4: 挂载路由并运行测试**

`backend/app/main.py` 追加：
```python
from backend.app.api.stats import stats_router

app.include_router(stats_router)
```

Run: `uv run pytest backend/tests/test_stats.py -v` — Expected: 3 passed

- [ ] **Step 5: 提交**

```bash
git add backend/app backend/tests
git commit -m "feat: add stats service and API with PRD window"
```

---

### Task 14: main.py 装配（worker/scheduler/崩溃恢复/冒烟）

**Files:**
- Modify: `backend/app/main.py`
- Create: `backend/tests/test_app_smoke.py`
- Test: `backend/tests/test_app_smoke.py`

**Interfaces:**
- Consumes: `TaskRunner`、`SchedulerService`、`recover_interrupted_tasks`、全部路由
- Produces: `create_app(config)` 完整版：lifespan 启动 worker/scheduler、停止时关闭；启动时崩溃恢复；`app` 单例

- [ ] **Step 1: 写失败测试**

`backend/tests/test_app_smoke.py`：
```python
from fastapi.testclient import TestClient

from backend.app.core.database import SessionLocal, init_db
from backend.app.main import create_app


def test_app_startup_and_shutdown(config):
    init_db(config)
    app = create_app(config)
    with TestClient(app) as client:
        resp = client.get("/api/auth/me")
        assert resp.status_code == 401
    assert app is not None


def test_full_routes_registered(config):
    init_db(config)
    app = create_app(config)
    paths = {r.path for r in app.routes}
    assert "/api/auth/login" in paths
    assert "/api/keywords" in paths
    assert "/api/tasks" in paths
    assert "/api/jobs" in paths
    assert "/api/companies" in paths
    assert "/api/stats/overview" in paths
    assert "/api/settings/schedule" in paths
```

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run pytest backend/tests/test_app_smoke.py -v` — Expected: FAIL（lifespan 未实现）

- [ ] **Step 3: 实现完整 main.py**

`backend/app/main.py`（重写）：
```python
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI

from backend.app.api.auth import auth_router
from backend.app.api.companies import companies_router
from backend.app.api.deps import ensure_admin, set_current_config
from backend.app.api.jobs import jobs_router
from backend.app.api.keywords import keywords_router
from backend.app.api.settings import settings_router
from backend.app.api.stats import stats_router
from backend.app.api.tasks import tasks_router
from backend.app.core.config import REPO_ROOT, Config
from backend.app.core.database import SessionLocal, init_db
from backend.app.core.exceptions import AppError, app_error_handler
from backend.app.core.logging import setup_logging
from backend.app.services.scheduler import SchedulerService
from backend.app.services.task_runner import TaskRunner, recover_interrupted_tasks

_config: Config | None = None
_runner: TaskRunner | None = None
_scheduler: SchedulerService | None = None


def create_app(config: Config | None = None) -> FastAPI:
    global _config, _runner, _scheduler
    cfg = config or Config(repo_root=REPO_ROOT)
    _config = cfg
    set_current_config(cfg)
    setup_logging(cfg.log_dir)
    init_db(cfg)
    recover_interrupted_tasks()
    with SessionLocal() as db:
        ensure_admin(db, cfg)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        global _runner, _scheduler
        _runner = TaskRunner()
        _runner.start()
        _scheduler = SchedulerService()
        _scheduler.start()
        yield
        if _runner:
            _runner.stop()
        if _scheduler:
            _scheduler.stop()

    app = FastAPI(title="job-hunter", lifespan=lifespan)
    app.add_exception_handler(AppError, app_error_handler)
    for router in (auth_router, keywords_router, tasks_router, jobs_router, companies_router, stats_router, settings_router):
        app.include_router(router)
    return app


# 测试通过 conftest 设置 JOB_HUNTER_TESTING=1，避免污染真实 data/
if not os.environ.get("JOB_HUNTER_TESTING"):
    app = create_app()
```

注：`recover_interrupted_tasks()` 在 `create_app` 内调用（非 lifespan），确保测试直接 `create_app(config)` 也生效；worker/scheduler 在 lifespan 内启动。

- [ ] **Step 4: 运行全部测试**

Run: `uv run pytest backend/tests -v` — Expected: 全部通过（约 30 个）

- [ ] **Step 5: 提交**

```bash
git add backend/app backend/tests
git commit -m "feat: wire app factory with worker, scheduler and crash recovery"
```

---

### Task 15: 端到端验证（手动冒烟）

**Files:**
- 无新文件（可选：`backend/tests/test_smoke_manual.md` 说明）

- [ ] **Step 1: 全部测试再次通过**

Run: `uv run pytest backend/tests -v` — Expected: 全部通过

- [ ] **Step 2: 启动服务冒烟**

Run: `uv run uvicorn backend.app.main:app --port 8000`
- `GET http://127.0.0.1:8000/api/auth/me` → 401
- `POST /api/auth/login`（用 `logs/app.log` 中首次生成的初始密码）→ 200 token
- 带 token `POST /api/tasks`（keyword 1）→ 200；再次 POST → 409
- 观察日志：`logs/app.log` 记录任务执行（若真实抓取需要网络与时间，可用真实 51job）

- [ ] **Step 3: 提交（如无代码改动仅记录）**

```bash
git add -A
git commit -m "chore: backend v1 smoke verified" --allow-empty
```

