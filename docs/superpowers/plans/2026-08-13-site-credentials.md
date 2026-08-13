# 站点凭据管理 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 新增站点凭据（账号密码）管理页 + 加密存储 + 测试登录，以及"登录后抓取"开关（任务级选择 + 全局默认，默认不登录）。

**Architecture:** 后端新增 `site_credentials` 表（`(site, username)` 唯一，密码 AES-GCM 加密存储，密钥在 `data/config.ini` 的 `[site] secret`），新增 `/api/site-credentials` CRUD + test-login 路由；`scrape_tasks` 加 `login_credential_id` 列，任务执行时解析凭据（任务级 > 全局默认 > 匿名）传入 PlaywrightScraper，登录失败自动降级匿名抓取。前端新增「站点账号」页面 + 任务控制台登录抓取开关。

**Tech Stack:** Python 3.14 / FastAPI / SQLAlchemy 2.0 / Playwright / cryptography / Vue3 + Element Plus + TypeScript / vitest

## Global Constraints

- 遵循 `docs/PRD.md` 与 `docs/code-style.md`；本计划由 `docs/superpowers/specs/2026-08-13-site-credentials-design.md` 落地。
- 测试禁止访问真实 51job；解析类测试用 `backend/tests/fixtures/` 本地 HTML。
- 密码加密必用 AES-GCM（`cryptography` 库），密钥为 32 字节，存 `data/config.ini` `[site] secret`（hex）。
- **任何 API 响应不得回传密码**；列表/详情仅返回 `has_password`。
- 同一凭据被进行中/排队中任务引用时 DELETE 返回 409；已完成/失败任务引用则置 NULL。
- `POST /api/tasks` 新增 `login_credential_id` 可选参数；缺省取全局默认 `scraper_login`（默认关闭）。
- 登录失败必须降级为匿名抓取并记日志，不得导致任务失败。
- 后端运行测试命令（仓库根目录）：`uv run pytest backend/tests/xxx.py -q`；前端：`cd frontend && npm run test / type-check / build`。

---

### Task 1: 依赖、Config [site] secret 与加密模块

**Files:**
- Modify: `pyproject.toml`（`uv add cryptography` 自动改）
- Modify: `backend/app/core/config.py`
- Test: `backend/tests/test_config.py`、新建 `backend/tests/test_site_security.py`

**Interfaces:**
- Consumes: 无
- Produces: `Config.site_secret_key -> bytes`（32 字节）；`encrypt_password(plain: str, key: bytes) -> str`；`decrypt_password(enc: str, key: bytes) -> str`（失败抛 `AppError`）

- [ ] **Step 1: 添加 cryptography 依赖**

Run: `uv add cryptography`
Expected: `pyproject.toml` dependencies 出现 `cryptography`，`uv.lock` 更新。

- [ ] **Step 2: 写加密模块测试（先失败）**

创建 `backend/tests/test_site_security.py`：

```python
import pytest

from backend.app.core.exceptions import AppError
from backend.app.core.site_security import decrypt_password, encrypt_password

KEY = bytes.fromhex("ab" * 32)


def test_encrypt_decrypt_roundtrip():
    enc = encrypt_password("P@ssw0rd!中文", KEY)
    assert enc != "P@ssw0rd!中文"
    assert decrypt_password(enc, KEY) == "P@ssw0rd!中文"


def test_same_password_encrypts_differently():
    assert encrypt_password("pw", KEY) != encrypt_password("pw", KEY)


def test_wrong_key_fails():
    enc = encrypt_password("pw", KEY)
    other = bytes.fromhex("cd" * 32)
    with pytest.raises(Exception):
        decrypt_password(enc, other)


def test_corrupted_data_fails_with_app_error():
    with pytest.raises(AppError):
        decrypt_password("not-base64!!!", KEY)
```

- [ ] **Step 3: 运行测试确认失败**

Run: `uv run pytest backend/tests/test_site_security.py -q`
Expected: FAIL（`ModuleNotFoundError: site_security`）

- [ ] **Step 4: 写 config.py 扩展测试（先失败）**

在 `backend/tests/test_config.py` 追加：

```python
def test_config_creates_site_secret(tmp_path):
    cfg = Config(repo_root=tmp_path, config_path=tmp_path / "config.ini", db_path=tmp_path / "test.db")
    assert len(cfg.site_secret_key) == 32


def test_config_backfills_site_secret_on_old_file(tmp_path):
    path = tmp_path / "config.ini"
    p = configparser.ConfigParser()
    p["auth"] = {"username": "me", "password": "pw123", "jwt_secret": "s" * 40}
    p["scraper"] = {"max_pages": "30", "headful": "false"}
    with open(path, "w", encoding="utf-8") as f:
        p.write(f)
    cfg = Config(repo_root=tmp_path, config_path=path, db_path=tmp_path / "t.db")
    assert len(cfg.site_secret_key) == 32
    # 再次读取，secret 已持久化（幂等）
    cfg2 = Config(repo_root=tmp_path, config_path=path, db_path=tmp_path / "t.db")
    assert cfg2.site_secret_key == cfg.site_secret_key
```

- [ ] **Step 5: 运行测试确认失败**

Run: `uv run pytest backend/tests/test_config.py -q`
Expected: FAIL（`AttributeError: site_secret_key`）

- [ ] **Step 6: 实现 Config 扩展**

修改 `backend/app/core/config.py`：

```python
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
            p["site"] = {"secret": secrets.token_hex(32)}
            with open(self.config_path, "w", encoding="utf-8") as f:
                p.write(f)
            logger.warning(
                "已生成 %s，初始密码：%s（可修改文件后重启生效）",
                self.config_path, p["auth"]["password"],
            )
        self._parser = configparser.ConfigParser()
        self._parser.read(self.config_path, encoding="utf-8")
        # 旧配置文件缺少 [site] 段时补写，幂等
        if "site" not in self._parser:
            self._parser["site"] = {"secret": secrets.token_hex(32)}
            with open(self.config_path, "w", encoding="utf-8") as f:
                self._parser.write(f)
```

在类内追加 property（放在 `headful` 之后）：

```python
    @property
    def site_secret_key(self) -> bytes:
        return bytes.fromhex(self._parser["site"]["secret"])
```

- [ ] **Step 7: 实现 site_security 模块**

创建 `backend/app/core/site_security.py`：

```python
import base64
import logging

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from backend.app.core.exceptions import AppError

logger = logging.getLogger("job_hunter")

_NONCE_LEN = 12


def encrypt_password(plain: str, key: bytes) -> str:
    aesgcm = AESGCM(key)
    nonce = AESGCM.generate_nonce(_NONCE_LEN)
    ct = aesgcm.encrypt(nonce, plain.encode("utf-8"), None)
    return base64.b64encode(nonce + ct).decode("ascii")


def decrypt_password(enc: str, key: bytes) -> str:
    try:
        raw = base64.b64decode(enc)
        nonce, ct = raw[:_NONCE_LEN], raw[_NONCE_LEN:]
        return AESGCM(key).decrypt(nonce, ct, None).decode("utf-8")
    except Exception as exc:
        logger.error("凭据密码解密失败: %s", exc)
        raise AppError("凭据密码解密失败，凭据可能已损坏", 500) from exc
```

- [ ] **Step 8: 运行全部测试确认通过**

Run: `uv run pytest backend/tests/test_site_security.py backend/tests/test_config.py -q`
Expected: PASS（6 个新测试 + 原 config 测试）

- [ ] **Step 9: 提交**

```bash
git add pyproject.toml uv.lock backend/app/core/config.py backend/app/core/site_security.py backend/tests/test_site_security.py backend/tests/test_config.py
git commit -m "feat: 站点凭据 AES-GCM 加密模块与 [site] secret 配置"
```

---

### Task 2: SiteCredential 模型与 scrape_tasks 迁移

**Files:**
- Create: `backend/app/models/site_credential.py`
- Modify: `backend/app/models/__init__.py`
- Modify: `backend/app/models/scrape_task.py`（加 `login_credential_id` 列）
- Modify: `backend/app/core/database.py`（迁移函数 + `init_db` 注册）
- Test: 新建 `backend/tests/test_site_credential_model.py`、修改 `backend/tests/test_migration.py`

**Interfaces:**
- Consumes: Task 1 的 `Base`
- Produces: `SiteCredential` 模型（字段 `id/site/username/password_enc/remark/created_at/updated_at`，property `has_password -> True`）；`ScrapeTask.login_credential_id: int | None`；`database._migrate_tasks_login_credential_id(engine)`

- [ ] **Step 1: 写模型测试（先失败）**

创建 `backend/tests/test_site_credential_model.py`：

```python
import pytest
from sqlalchemy import create_engine, inspect

from backend.app.core.database import Base
from backend.app.models import SiteCredential


def test_site_credential_table_and_unique_index():
    eng = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(eng)
    idx = {i["name"] for i in inspect(eng).get_indexes("site_credentials")}
    assert "uq_site_credentials_site_username" in idx
    assert "ix_site_credentials_site" in idx
    with eng.begin() as conn:
        conn.execute(SiteCredential.__table__.insert().values(
            site="51job", username="13800000000", password_enc="abc",
        ))
        with pytest.raises(Exception):
            conn.execute(SiteCredential.__table__.insert().values(
                site="51job", username="13800000000", password_enc="def",
            ))
```

（用内存库验证唯一索引，避免依赖 fixtures。）

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run pytest backend/tests/test_site_credential_model.py -q`
Expected: FAIL（表不存在）

- [ ] **Step 3: 实现模型**

创建 `backend/app/models/site_credential.py`：

```python
from datetime import datetime

from sqlalchemy import DateTime, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.core.database import Base


class SiteCredential(Base):
    __tablename__ = "site_credentials"
    __table_args__ = (
        Index("uq_site_credentials_site_username", "site", "username", unique=True),
        Index("ix_site_credentials_site", "site"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    site: Mapped[str] = mapped_column(String(32), nullable=False)
    username: Mapped[str] = mapped_column(String(128), nullable=False)
    password_enc: Mapped[str] = mapped_column(Text, nullable=False)
    remark: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)

    @property
    def has_password(self) -> bool:
        return True
```

修改 `backend/app/models/__init__.py`：import 与 `__all__` 均追加 `SiteCredential`。

- [ ] **Step 4: 运行测试确认通过**

Run: `uv run pytest backend/tests/test_site_credential_model.py -q`
Expected: PASS

- [ ] **Step 5: 写迁移测试（先失败）**

在 `backend/tests/test_migration.py` 追加：

```python
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
```

- [ ] **Step 6: 运行测试确认失败**

Run: `uv run pytest backend/tests/test_migration.py -q`
Expected: FAIL（`AttributeError: _migrate_tasks_login_credential_id`）

- [ ] **Step 7: 实现迁移与模型列**

`backend/app/models/scrape_task.py` 在 `max_pages` 后追加：

```python
    login_credential_id: Mapped[int | None] = mapped_column(Integer)
```

`backend/app/core/database.py` 追加（放在 `_migrate_tasks_max_pages` 之后）：

```python
def _migrate_tasks_login_credential_id(engine) -> None:
    """轻量迁移：scrape_tasks 表增加 login_credential_id 列（登录抓取所用凭据，NULL=匿名/全局默认）。"""
    insp = inspect(engine)
    if "scrape_tasks" not in insp.get_table_names():
        return
    cols = {c["name"] for c in insp.get_columns("scrape_tasks")}
    if "login_credential_id" in cols:
        return
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE scrape_tasks ADD COLUMN login_credential_id INTEGER"))
    logger.info("迁移完成：scrape_tasks 增加 login_credential_id 列")
```

`init_db` 中在 `_migrate_tasks_max_pages(engine)` 之后追加一行 `_migrate_tasks_login_credential_id(engine)`。

- [ ] **Step 8: 运行测试确认通过**

Run: `uv run pytest backend/tests/test_migration.py backend/tests/test_site_credential_model.py backend/tests/test_models.py -q`
Expected: PASS

- [ ] **Step 9: 提交**

```bash
git add backend/app/models/site_credential.py backend/app/models/__init__.py backend/app/models/scrape_task.py backend/app/core/database.py backend/tests/test_site_credential_model.py backend/tests/test_migration.py
git commit -m "feat: SiteCredential 模型与 scrape_tasks.login_credential_id 迁移"
```

---

### Task 3: site-credentials CRUD API

**Files:**
- Create: `backend/app/schemas/site_credential.py`
- Create: `backend/app/api/site_credentials.py`
- Modify: `backend/app/main.py`（注册 router）
- Test: 新建 `backend/tests/test_site_credentials_api.py`

**Interfaces:**
- Consumes: Task 1 `encrypt_password`/`decrypt_password`、`Config.site_secret_key`；Task 2 `SiteCredential`/`ScrapeTask.login_credential_id`
- Produces: router `site_credentials_router`（前缀 `/api/site-credentials`，JWT 保护）；schemas `SiteCredentialCreate/SiteCredentialUpdate/SiteCredentialOut`

- [ ] **Step 1: 写 API 测试（先失败）**

创建 `backend/tests/test_site_credentials_api.py`：

```python
from backend.app.core.database import SessionLocal
from backend.app.core.site_security import decrypt_password
from backend.app.models import ScrapeTask, SiteCredential


def test_crud_flow(client, config):
    # create
    resp = client.post("/api/site-credentials", json={
        "site": "51job", "username": "13800000000", "password": "pw123", "remark": "主账号",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["has_password"] is True
    assert "password" not in data
    assert data["remark"] == "主账号"
    cid = data["id"]
    # list
    lst = client.get("/api/site-credentials").json()
    assert [c["id"] for c in lst] == [cid]
    # site 过滤
    assert client.get("/api/site-credentials", params={"site": "zhilian"}).json() == []
    assert len(client.get("/api/site-credentials", params={"site": "51job"}).json()) == 1
    # update remark
    resp = client.put(f"/api/site-credentials/{cid}", json={"remark": "新备注"})
    assert resp.status_code == 200 and resp.json()["remark"] == "新备注"
    # 密码仍加密存库（校验可解密回明文，且未泄露到响应）
    with SessionLocal() as s:
        row = s.get(SiteCredential, cid)
        assert decrypt_password(row.password_enc, config.site_secret_key) == "pw123"
    # update password 覆盖
    resp = client.put(f"/api/site-credentials/{cid}", json={"password": "newpw"})
    assert resp.status_code == 200
    with SessionLocal() as s:
        row = s.get(SiteCredential, cid)
        assert decrypt_password(row.password_enc, config.site_secret_key) == "newpw"
    # delete
    assert client.delete(f"/api/site-credentials/{cid}").status_code == 200
    assert client.get("/api/site-credentials").json() == []


def test_duplicate_site_username_409(client):
    body = {"site": "51job", "username": "13800000000", "password": "pw123"}
    assert client.post("/api/site-credentials", json=body).status_code == 200
    resp = client.post("/api/site-credentials", json=body)
    assert resp.status_code == 409


def test_duplicate_same_username_different_site_ok(client):
    body = {"site": "51job", "username": "13800000000", "password": "pw123"}
    assert client.post("/api/site-credentials", json=body).status_code == 200
    body["site"] = "zhilian"
    assert client.post("/api/site-credentials", json=body).status_code == 200


def test_update_404(client):
    assert client.put("/api/site-credentials/999", json={"remark": "x"}).status_code == 404
    assert client.delete("/api/site-credentials/999").status_code == 404


def test_requires_auth(client):
    import copy
    headers = copy.deepcopy(dict(client.headers))
    del headers["Authorization"]
    resp = client.get("/api/site-credentials", headers=headers)
    assert resp.status_code == 401


def test_delete_blocked_by_running_task(client):
    cid = client.post("/api/site-credentials", json={
        "site": "51job", "username": "13800000000", "password": "pw123",
    }).json()["id"]
    with SessionLocal() as s:
        s.add(ScrapeTask(keyword_id=1, status="queued", login_credential_id=cid))
        s.commit()
    resp = client.delete(f"/api/site-credentials/{cid}")
    assert resp.status_code == 409


def test_delete_nullifies_finished_task_reference(client):
    cid = client.post("/api/site-credentials", json={
        "site": "51job", "username": "13800000000", "password": "pw123",
    }).json()["id"]
    with SessionLocal() as s:
        t = ScrapeTask(keyword_id=1, status="success", login_credential_id=cid)
        s.add(t)
        s.commit()
        tid = t.id
    assert client.delete(f"/api/site-credentials/{cid}").status_code == 200
    with SessionLocal() as s:
        assert s.get(ScrapeTask, tid).login_credential_id is None
```

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run pytest backend/tests/test_site_credentials_api.py -q`
Expected: FAIL（404 route not found）

- [ ] **Step 3: 实现 schemas**

创建 `backend/app/schemas/site_credential.py`：

```python
from datetime import datetime

from pydantic import BaseModel


class SiteCredentialCreate(BaseModel):
    site: str
    username: str
    password: str
    remark: str | None = None


class SiteCredentialUpdate(BaseModel):
    remark: str | None = None
    password: str | None = None


class SiteCredentialOut(BaseModel):
    id: int
    site: str
    username: str
    remark: str | None
    has_password: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
```

- [ ] **Step 4: 实现 router**

创建 `backend/app/api/site_credentials.py`：

```python
from fastapi import APIRouter, Depends

from backend.app.api import deps
from backend.app.api.deps import get_current_user, get_db
from backend.app.core.exceptions import AppError
from backend.app.core.site_security import decrypt_password, encrypt_password
from backend.app.models import ScrapeTask, SiteCredential, TaskStatus
from backend.app.schemas.site_credential import (
    SiteCredentialCreate,
    SiteCredentialOut,
    SiteCredentialUpdate,
)

site_credentials_router = APIRouter(prefix="/api/site-credentials", tags=["site-credentials"])

_RUNNING = (TaskStatus.QUEUED.value, TaskStatus.IN_PROGRESS.value)


def _key() -> bytes:
    return deps._current_config.site_secret_key


@site_credentials_router.get("", response_model=list[SiteCredentialOut])
def list_credentials(site: str | None = None, db=Depends(get_db), user=Depends(get_current_user)):
    q = db.query(SiteCredential)
    if site:
        q = q.filter(SiteCredential.site == site)
    return q.order_by(SiteCredential.created_at.desc()).all()


@site_credentials_router.post("", response_model=SiteCredentialOut)
def create_credential(body: SiteCredentialCreate, db=Depends(get_db), user=Depends(get_current_user)):
    site = body.site.strip()
    username = body.username.strip()
    if not site or not username or not body.password:
        raise AppError("site/username/password 均不能为空", 400)
    if db.query(SiteCredential).filter_by(site=site, username=username).first():
        raise AppError("该站点已存在同账号", 409)
    cred = SiteCredential(
        site=site,
        username=username,
        password_enc=encrypt_password(body.password, _key()),
        remark=body.remark,
    )
    db.add(cred)
    db.commit()
    db.refresh(cred)
    return cred


@site_credentials_router.put("/{cred_id}", response_model=SiteCredentialOut)
def update_credential(cred_id: int, body: SiteCredentialUpdate, db=Depends(get_db), user=Depends(get_current_user)):
    cred = db.get(SiteCredential, cred_id)
    if cred is None:
        raise AppError("凭据不存在", 404)
    cred.remark = body.remark
    if body.password:
        cred.password_enc = encrypt_password(body.password, _key())
    db.commit()
    db.refresh(cred)
    return cred


@site_credentials_router.delete("/{cred_id}")
def delete_credential(cred_id: int, db=Depends(get_db), user=Depends(get_current_user)):
    cred = db.get(SiteCredential, cred_id)
    if cred is None:
        raise AppError("凭据不存在", 404)
    if db.query(ScrapeTask).filter(
        ScrapeTask.login_credential_id == cred_id,
        ScrapeTask.status.in_(_RUNNING),
    ).first():
        raise AppError("该凭据被进行中/排队中的任务引用，不能删除", 409)
    db.query(ScrapeTask).filter(ScrapeTask.login_credential_id == cred_id).update(
        {ScrapeTask.login_credential_id: None}
    )
    db.delete(cred)
    db.commit()
    return {"ok": True}
```

（test-login 路由与其依赖在 Task 4 一并加入，本任务不引用 auth/playwright 模块。）

- [ ] **Step 5: 注册 router**

`backend/app/main.py` 中：import 追加 `from backend.app.api.site_credentials import site_credentials_router`，第 60 行 router 元组追加 `site_credentials_router`。

- [ ] **Step 6: 运行测试确认通过**

Run: `uv run pytest backend/tests/test_site_credentials_api.py -q`
Expected: PASS（`test_delete_blocked_by_running_task` 依赖 `scrape_tasks` 有 `login_credential_id` 列，Task 2 已加）

- [ ] **Step 7: 提交**

```bash
git add backend/app/schemas/site_credential.py backend/app/api/site_credentials.py backend/app/main.py backend/tests/test_site_credentials_api.py
git commit -m "feat: site-credentials CRUD API（密码不回传、删除冲突 409）"
```

---

### Task 4: 登录模块与 test-login API

**Files:**
- Create: `backend/app/scrapers/auth.py`（仅 `login()`，不依赖 playwright 模块）
- Modify: `backend/app/scrapers/playwright.py`（顶部 import `login` + 文件末尾 `run_test_login`）
- Modify: `backend/app/api/site_credentials.py`（test-login 路由 + import `run_test_login`）
- Test: 新建 `backend/tests/test_auth_login.py`、修改 `backend/tests/test_site_credentials_api.py`

**Interfaces:**
- Consumes: Task 1 `decrypt_password`/`Config.site_secret_key`；Task 3 router；`solve_aliyun_captcha`（已有）
- Produces: `login(page: Page, site: str, username: str, password: str) -> bool`（在 `auth.py`）；`run_test_login(site: str, username: str, password: str, headful: bool = False) -> tuple[bool, str]`（在 `playwright.py`，内部调用模块顶层绑定的 `login`）

> **设计约束（避免循环导入）：** `playwright.py` 顶层 `from backend.app.scrapers.auth import login`；`auth.py` 顶层只 import `captcha`（不 import playwright）。`run_test_login` 放 `playwright.py` 内，故测试对 `playwright_mod.login` 与 `playwright_mod.PlaywrightScraper` 的 monkeypatch 均生效。

- [ ] **Step 1: 写登录模块测试（先失败）**

创建 `backend/tests/test_auth_login.py`：

```python
import asyncio

from backend.app.scrapers import auth
from backend.app.scrapers.auth import login


class _FakeLocator:
    def __init__(self):
        self.filled = None
        self.first = self

    async def fill(self, value):
        self.filled = value

    async def click(self, timeout=None):
        pass

    async def count(self):
        return 0  # 滑块/嵌入容器均不存在 → solve_aliyun_captcha 视为已通过


class _FakePage:
    def __init__(self, url_after="https://we.51job.com/pc/index"):
        self._url = url_after
        self.locators = {}

    def locator(self, sel):
        if sel not in self.locators:
            self.locators[sel] = _FakeLocator()
        return self.locators[sel]

    async def goto(self, url, **kw):
        self.goto_url = url

    async def wait_for_timeout(self, ms):
        pass

    @property
    def url(self):
        return self._url


def _run(coro):
    return asyncio.run(coro)


def test_login_success_fills_credentials():
    page = _FakePage(url_after="https://we.51job.com/pc/index")
    assert _run(login(page, "51job", "13800000000", "pw123")) is True
    assert page.goto_url == "https://login.51job.com/login.php?lang=c"
    assert page.locators["input[placeholder*='手机号'], input[name='phone'], input[type='tel']"].filled == "13800000000"
    assert page.locators["input[placeholder*='密码'], input[type='password']"].filled == "pw123"


def test_login_failure_stays_on_login_page():
    page = _FakePage(url_after="https://login.51job.com/login.php")
    assert _run(login(page, "51job", "u", "w")) is False


def test_login_unsupported_site():
    page = _FakePage()
    assert _run(login(page, "zhilian", "u", "w")) is False
    assert not hasattr(page, "goto_url")  # 未访问页面


def test_login_exception_returns_false(monkeypatch):
    page = _FakePage()

    async def _boom(*a, **k):
        raise RuntimeError("network")

    monkeypatch.setattr(page, "goto", _boom)
    assert _run(login(page, "51job", "u", "w")) is False


def test_run_test_login_delegates_to_login(monkeypatch):
    from backend.app.scrapers import playwright as pw_mod

    calls = []

    async def _fake_login(page, site, username, password):
        calls.append((site, username, password))
        return True

    class _FakeScraper:
        def __init__(self, headful=False):
            self.headful = headful

        async def _ensure_browser(self):
            pass

        async def _new_page(self):
            return object()

        async def close(self):
            pass

    monkeypatch.setattr(pw_mod, "login", _fake_login)
    monkeypatch.setattr(pw_mod, "PlaywrightScraper", lambda headful=False: _FakeScraper(headful))
    ok, msg = _run(pw_mod.run_test_login("51job", "13800000000", "pw", headful=True))
    assert ok is True
    assert calls == [("51job", "13800000000", "pw")]
    assert "成功" in msg


def test_run_test_login_failure_message(monkeypatch):
    from backend.app.scrapers import playwright as pw_mod

    async def _fake_login(page, site, username, password):
        return False

    class _FakeScraper:
        def __init__(self, headful=False):
            pass

        async def _ensure_browser(self):
            pass

        async def _new_page(self):
            return object()

        async def close(self):
            pass

    monkeypatch.setattr(pw_mod, "login", _fake_login)
    monkeypatch.setattr(pw_mod, "PlaywrightScraper", lambda headful=False: _FakeScraper())
    ok, msg = _run(pw_mod.run_test_login("51job", "u", "w"))
    assert ok is False
    assert "失败" in msg
```

（`test_run_test_login_*` 因 `run_test_login` 尚未实现而失败，属预期。）

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run pytest backend/tests/test_auth_login.py -q`
Expected: FAIL（`ModuleNotFoundError: auth`）

- [ ] **Step 3: 实现 auth 模块**

创建 `backend/app/scrapers/auth.py`（注意：**不 import playwright**，避免循环导入）：

```python
import logging

from playwright.async_api import Page

from backend.app.scrapers.captcha import solve_aliyun_captcha

logger = logging.getLogger("job_hunter")

_LOGIN_URL = "https://login.51job.com/login.php?lang=c"
_USER_INPUT = "input[placeholder*='手机号'], input[name='phone'], input[type='tel']"
_PASS_INPUT = "input[placeholder*='密码'], input[type='password']"
_SUBMIT = "button[type='submit'], .login-btn, button:has-text('登 录'), button:has-text('登录')"


async def login(page: Page, site: str, username: str, password: str) -> bool:
    """登录招聘网站。成功返回 True；失败/验证码未过/异常返回 False（不抛出）。"""
    if site != "51job":
        logger.warning("暂不支持的站点登录: %s", site)
        return False
    try:
        await page.goto(_LOGIN_URL, wait_until="domcontentloaded", timeout=60000)
        await page.wait_for_timeout(1500)
        await page.locator(_USER_INPUT).first.fill(username)
        await page.locator(_PASS_INPUT).first.fill(password)
        await page.locator(_SUBMIT).first.click(timeout=15000)
        await page.wait_for_timeout(3000)
        await solve_aliyun_captcha(page)
        await page.wait_for_timeout(2000)
        if "login.51job.com" in page.url:
            return False
        logger.info("站点登录成功: site=%s username=%s", site, username)
        return True
    except Exception as exc:
        logger.warning("站点登录异常: site=%s username=%s err=%s", site, username, exc)
        return False
```

> 注：`login()` 中的 51job 登录页选择器为通用 best-effort 实现（按 placeholder/name/type 匹配），首次真实环境联调时可能需按 51job 实际 DOM 微调 `_USER_INPUT/_PASS_INPUT/_SUBMIT`；判定逻辑（URL 离开 login.51job.com = 成功）保持不变。

- [ ] **Step 4: 在 playwright.py 追加 run_test_login**

`backend/app/scrapers/playwright.py`：
- 顶部 import 区追加：`from backend.app.scrapers.auth import login`
- 文件末尾追加：

```python
async def run_test_login(site: str, username: str, password: str, headful: bool = False) -> tuple[bool, str]:
    """独立验证凭据可用性（test-login API 使用）。测试通过 monkeypatch 本模块的 login/PlaywrightScraper 完成。"""
    scraper = PlaywrightScraper(headful=headful)
    try:
        await scraper._ensure_browser()
        page = await scraper._new_page()
        ok = await login(page, site, username, password)
        msg = "登录成功" if ok else "登录失败（账号密码错误、验证码未通过或风控拦截）"
        return ok, msg
    except Exception as exc:
        logger.warning("test-login 异常: %s", exc)
        return False, f"登录异常: {exc}"
    finally:
        await scraper.close()
```

- [ ] **Step 5: 运行测试确认通过**

Run: `uv run pytest backend/tests/test_auth_login.py -q`
Expected: PASS（6 个测试）

- [ ] **Step 6: 写 test-login API 测试（先失败）**

在 `backend/tests/test_site_credentials_api.py` 追加：

```python
def test_test_login_ok(client, monkeypatch):
    from backend.app.api import site_credentials as sc_mod

    cid = client.post("/api/site-credentials", json={
        "site": "51job", "username": "13800000000", "password": "pw123",
    }).json()["id"]

    async def _fake_run(site, username, password, headful=False):
        assert site == "51job" and username == "13800000000" and password == "pw123"
        return True, "登录成功"

    monkeypatch.setattr(sc_mod, "run_test_login", _fake_run)
    resp = client.post(f"/api/site-credentials/{cid}/test-login")
    assert resp.status_code == 200
    assert resp.json() == {"ok": True, "message": "登录成功"}


def test_test_login_404(client):
    assert client.post("/api/site-credentials/999/test-login").status_code == 404
```

- [ ] **Step 7: 运行测试确认失败**

Run: `uv run pytest backend/tests/test_site_credentials_api.py -q`
Expected: FAIL（test-test-login 404 route not found）

- [ ] **Step 8: 实现 test-login 路由**

修改 `backend/app/api/site_credentials.py`：
- 顶部 import 区追加：`from backend.app.scrapers.playwright import run_test_login`
- 在 `delete_credential` 之后追加：

```python
@site_credentials_router.post("/{cred_id}/test-login")
async def test_login(cred_id: int, db=Depends(get_db), user=Depends(get_current_user)):
    cred = db.get(SiteCredential, cred_id)
    if cred is None:
        raise AppError("凭据不存在", 404)
    password = decrypt_password(cred.password_enc, _key())
    ok, message = await run_test_login(
        site=cred.site,
        username=cred.username,
        password=password,
        headful=deps._current_config.headful,
    )
    return {"ok": ok, "message": message}
```

- [ ] **Step 9: 运行测试确认通过**

Run: `uv run pytest backend/tests/test_site_credentials_api.py backend/tests/test_auth_login.py -q`
Expected: PASS

- [ ] **Step 10: 提交**

```bash
git add backend/app/scrapers/auth.py backend/app/scrapers/playwright.py backend/app/api/site_credentials.py backend/tests/test_auth_login.py backend/tests/test_site_credentials_api.py
git commit -m "feat: 51job 登录模块与凭据 test-login API"
```

---

### Task 5: settings scraper-login（全局默认开关）API

**Files:**
- Modify: `backend/app/schemas/settings.py`
- Modify: `backend/app/api/settings.py`
- Test: 新建 `backend/tests/test_settings_scraper_login.py`

**Interfaces:**
- Consumes: Task 2 `SiteCredential`；Task 3 router（创建凭据的 API 用于测试）
- Produces: schemas `ScraperLoginIn {enabled: bool, credential_id: int | None}`、`ScraperLoginOut`；settings 表 key `scraper_login`（默认 `{"enabled": false, "credential_id": None}`）；`GET/PUT /api/settings/scraper-login`

- [ ] **Step 1: 写 API 测试（先失败）**

创建 `backend/tests/test_settings_scraper_login.py`：

```python
def test_get_default_scraper_login(client):
    resp = client.get("/api/settings/scraper-login")
    assert resp.status_code == 200
    assert resp.json() == {"enabled": False, "credential_id": None}


def test_put_and_get_scraper_login(client):
    cid = client.post("/api/site-credentials", json={
        "site": "51job", "username": "13800000000", "password": "pw123",
    }).json()["id"]
    body = {"enabled": True, "credential_id": cid}
    assert client.put("/api/settings/scraper-login", json=body).status_code == 200
    assert client.get("/api/settings/scraper-login").json() == body


def test_put_invalid_credential_400(client):
    resp = client.put("/api/settings/scraper-login", json={"enabled": True, "credential_id": 999})
    assert resp.status_code == 400


def test_put_disabled_without_credential_ok(client):
    resp = client.put("/api/settings/scraper-login", json={"enabled": False, "credential_id": None})
    assert resp.status_code == 200
```

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run pytest backend/tests/test_settings_scraper_login.py -q`
Expected: FAIL（404 route not found）

- [ ] **Step 3: 实现 schemas**

修改 `backend/app/schemas/settings.py`，追加：

```python
class ScraperLoginIn(BaseModel):
    enabled: bool
    credential_id: int | None = None


class ScraperLoginOut(ScraperLoginIn):
    pass
```

- [ ] **Step 4: 实现 API**

修改 `backend/app/api/settings.py`：
- import 追加：`from backend.app.models import SiteCredential`、`from backend.app.schemas.settings import ScraperLoginIn, ScraperLoginOut`
- 追加常量与路由：

```python
_SCRAPER_LOGIN_KEY = "scraper_login"
_DEFAULT_SCRAPER_LOGIN = {"enabled": False, "credential_id": None}


@settings_router.get("/scraper-login", response_model=ScraperLoginOut)
def get_scraper_login(db=Depends(get_db), user=Depends(get_current_user)):
    row = db.query(Setting).filter_by(key=_SCRAPER_LOGIN_KEY).first()
    return ScraperLoginOut(**(row.value if row else _DEFAULT_SCRAPER_LOGIN))


@settings_router.put("/scraper-login", response_model=ScraperLoginOut)
def put_scraper_login(body: ScraperLoginIn, db=Depends(get_db), user=Depends(get_current_user)):
    if body.credential_id is not None and db.get(SiteCredential, body.credential_id) is None:
        raise AppError("凭据不存在", 400)
    row = db.query(Setting).filter_by(key=_SCRAPER_LOGIN_KEY).first()
    if row is None:
        row = Setting(key=_SCRAPER_LOGIN_KEY, value=body.model_dump())
        db.add(row)
    else:
        row.value = body.model_dump()
    db.commit()
    return body
```

（`AppError` 需 import：`from backend.app.core.exceptions import AppError`。）

- [ ] **Step 5: 运行测试确认通过**

Run: `uv run pytest backend/tests/test_settings_scraper_login.py -q`
Expected: PASS

- [ ] **Step 6: 提交**

```bash
git add backend/app/schemas/settings.py backend/app/api/settings.py backend/tests/test_settings_scraper_login.py
git commit -m "feat: 全局默认登录抓取开关 scraper-login API"
```

---

### Task 6: 任务 API 与执行时凭据解析（登录后抓取）

**Files:**
- Modify: `backend/app/schemas/task.py`
- Modify: `backend/app/api/tasks.py`
- Modify: `backend/app/scrapers/base.py`（`LoginCredential` dataclass）
- Modify: `backend/app/scrapers/playwright.py`（构造参数 + search 登录）
- Modify: `backend/app/services/task_runner.py`（凭据解析 + 传参）
- Test: 修改 `backend/tests/test_tasks_api.py`、`backend/tests/test_execute_task.py`、`backend/tests/test_playwright_scraper.py`

**Interfaces:**
- Consumes: Task 1 `decrypt_password`/`Config.site_secret_key`；Task 2 `SiteCredential`/`ScrapeTask.login_credential_id`；Task 4 `login`；Task 5 `scraper_login` settings key
- Produces: `LoginCredential` dataclass（`site/username/password`）；`PlaywrightScraper(headful=False, login_credential: LoginCredential | None = None)`；`TaskCreate.login_credential_id`；`TaskOut.login_credential_id/login_username`；`task_runner._resolve_login_credential(db, task) -> LoginCredential | None`

- [ ] **Step 1: 写任务 API 测试扩展（先失败）**

在 `backend/tests/test_tasks_api.py` 追加：

```python
def test_create_task_with_login_credential(client):
    cid = client.post("/api/site-credentials", json={
        "site": "51job", "username": "13800000000", "password": "pw123",
    }).json()["id"]
    resp = client.post("/api/tasks", json={"keyword_id": 1, "login_credential_id": cid})
    assert resp.status_code == 200
    data = resp.json()
    assert data["login_credential_id"] == cid
    assert data["login_username"] == "13800000000"


def test_create_task_invalid_credential_400(client):
    resp = client.post("/api/tasks", json={"keyword_id": 1, "login_credential_id": 999})
    assert resp.status_code == 400


def test_list_task_has_login_username(client):
    cid = client.post("/api/site-credentials", json={
        "site": "51job", "username": "13800000000", "password": "pw123",
    }).json()["id"]
    client.post("/api/tasks", json={"keyword_id": 1, "login_credential_id": cid})
    task = client.get("/api/tasks").json()[0]
    assert task["login_credential_id"] == cid
    assert task["login_username"] == "13800000000"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run pytest backend/tests/test_tasks_api.py -q`
Expected: FAIL（`login_credential_id` 不在响应中）

- [ ] **Step 3: 实现 schemas 与 API**

`backend/app/schemas/task.py`：
- `TaskCreate` 追加 `login_credential_id: int | None = None`
- `TaskOut` 追加 `login_credential_id: int | None`、`login_username: str | None = None`

`backend/app/api/tasks.py` 重写为（关键改动：校验凭据存在、统一 `_task_out` 组装响应）：

```python
from fastapi import APIRouter, Depends

from backend.app.api import deps
from backend.app.api.deps import get_current_user, get_db
from backend.app.core.exceptions import AppError
from backend.app.models import Keyword, ScrapeTask, SiteCredential, TaskStatus
from backend.app.schemas.task import TaskCreate, TaskOut

tasks_router = APIRouter(prefix="/api/tasks", tags=["tasks"])

_RUNNING = (TaskStatus.QUEUED.value, TaskStatus.IN_PROGRESS.value)


def _task_out(task: ScrapeTask, db) -> dict:
    data = {
        "id": task.id,
        "keyword_id": task.keyword_id,
        "mode": task.mode,
        "max_pages": task.max_pages,
        "status": task.status,
        "total_pages": task.total_pages,
        "total_found": task.total_found,
        "success_count": task.success_count,
        "failed_count": task.failed_count,
        "last_page": task.last_page,
        "start_time": task.start_time,
        "end_time": task.end_time,
        "error_message": task.error_message,
        "created_at": task.created_at,
        "login_credential_id": task.login_credential_id,
        "login_username": None,
    }
    if task.login_credential_id:
        cred = db.get(SiteCredential, task.login_credential_id)
        data["login_username"] = cred.username if cred else None
    return data


@tasks_router.post("", response_model=TaskOut)
def create_task(body: TaskCreate, db=Depends(get_db), user=Depends(get_current_user)):
    kw = db.get(Keyword, body.keyword_id)
    if kw is None:
        raise AppError("关键字不存在", 404)
    if body.mode != "playwright":
        raise AppError("v1 仅支持 playwright 模式", 400)
    if body.max_pages is not None and (body.max_pages < 1 or body.max_pages > deps._current_config.max_pages):
        raise AppError(f"max_pages 需在 1-{deps._current_config.max_pages} 之间", 400)
    if body.login_credential_id is not None and db.get(SiteCredential, body.login_credential_id) is None:
        raise AppError("登录凭据不存在", 400)
    if db.query(ScrapeTask).filter(ScrapeTask.keyword_id == body.keyword_id, ScrapeTask.status.in_(_RUNNING)).first():
        raise AppError("该关键字已有进行中的任务", 409)
    task = ScrapeTask(
        keyword_id=body.keyword_id,
        mode=body.mode,
        max_pages=body.max_pages,
        login_credential_id=body.login_credential_id,
        status=TaskStatus.QUEUED.value,
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    return _task_out(task, db)


@tasks_router.get("", response_model=list[TaskOut])
def list_tasks(db=Depends(get_db), user=Depends(get_current_user)):
    tasks = db.query(ScrapeTask).order_by(ScrapeTask.created_at.desc()).all()
    return [_task_out(t, db) for t in tasks]


@tasks_router.get("/{task_id}", response_model=TaskOut)
def get_task(task_id: int, db=Depends(get_db), user=Depends(get_current_user)):
    task = db.get(ScrapeTask, task_id)
    if task is None:
        raise AppError("任务不存在", 404)
    return _task_out(task, db)


@tasks_router.delete("/{task_id}")
def delete_task(task_id: int, db=Depends(get_db), user=Depends(get_current_user)):
    task = db.get(ScrapeTask, task_id)
    if task is None:
        raise AppError("任务不存在", 404)
    if task.status == TaskStatus.IN_PROGRESS.value:
        raise AppError("进行中的任务不能删除", 400)
    db.delete(task)
    db.commit()
    return {"ok": True}
```

- [ ] **Step 4: 运行任务 API 测试确认通过**

Run: `uv run pytest backend/tests/test_tasks_api.py backend/tests/test_site_credentials_api.py -q`
Expected: PASS（原测试 `test_create_task` 等仍通过，因 `_task_out` 覆盖全部字段）

- [ ] **Step 5: 写 PlaywrightScraper 登录测试（先失败）**

在 `backend/tests/test_playwright_scraper.py` 追加：

```python
def test_search_calls_login_before_fetch(monkeypatch):
    from backend.app.scrapers.base import LoginCredential

    launches = []
    _setup(monkeypatch, launches)
    login_calls = []

    async def _fake_login(page, site, username, password):
        login_calls.append((site, username, password))
        return True

    monkeypatch.setattr(playwright_mod, "login", _fake_login)
    s = PlaywrightScraper(headful=False, login_credential=LoginCredential("51job", "13800000000", "pw123"))
    monkeypatch.setattr(
        s,
        "_fetch_page",
        _seq_fetch(iter([PageResult(page_num=1, jobs=[]), PageResult(page_num=2, jobs=[])])),
    )

    async def run():
        return [r async for r in s.search("python", 2)]

    out = asyncio.run(run())
    assert login_calls == [("51job", "13800000000", "pw123")]
    assert len(out) == 2


def test_search_login_failure_falls_back_anonymous(monkeypatch):
    from backend.app.scrapers.base import LoginCredential

    launches = []
    _setup(monkeypatch, launches)

    async def _fake_login(page, site, username, password):
        return False

    monkeypatch.setattr(playwright_mod, "login", _fake_login)
    s = PlaywrightScraper(headful=False, login_credential=LoginCredential("51job", "u", "w"))
    monkeypatch.setattr(
        s,
        "_fetch_page",
        _seq_fetch(iter([PageResult(page_num=1, jobs=[]), PageResult(page_num=2, jobs=[])])),
    )

    async def run():
        return [r async for r in s.search("python", 2)]

    out = asyncio.run(run())
    assert len(out) == 2  # 登录失败不中断抓取
    assert not out[0].failed
```

- [ ] **Step 6: 运行测试确认失败**

Run: `uv run pytest backend/tests/test_playwright_scraper.py -q`
Expected: FAIL（`TypeError: PlaywrightScraper.__init__() got an unexpected keyword argument 'login_credential'`）

- [ ] **Step 7: 实现 LoginCredential 与 PlaywrightScraper 扩展**

`backend/app/scrapers/base.py` 追加（`PageResult` 之后）：

```python
@dataclass
class LoginCredential:
    site: str
    username: str
    password: str
```

`backend/app/scrapers/playwright.py`：
- import 追加：`from backend.app.scrapers.base import LoginCredential`（`from backend.app.scrapers.auth import login` 已在 Task 4 添加，勿重复）
- `__init__` 改为：

```python
    def __init__(self, headful: bool = False, login_credential: LoginCredential | None = None):
        self._headful = headful
        self._login_credential = login_credential
        self._playwright = None
        self._browser = None
        self._context = None
```

- `search()` 在 `page = await self._new_page()` 之后、`try:` 之前插入：

```python
        if self._login_credential is not None:
            try:
                logged_in = await login(
                    page,
                    self._login_credential.site,
                    self._login_credential.username,
                    self._login_credential.password,
                )
            except Exception as exc:
                logged_in = False
                logger.warning("登录异常，降级为匿名抓取: %s", exc)
            if not logged_in:
                logger.warning(
                    "登录失败，降级为匿名抓取: site=%s username=%s",
                    self._login_credential.site, self._login_credential.username,
                )
```

- [ ] **Step 8: 运行测试确认通过**

Run: `uv run pytest backend/tests/test_playwright_scraper.py -q`
Expected: PASS（含原 9 个测试）

- [ ] **Step 9: 写 task_runner 测试扩展（先失败）**

在 `backend/tests/test_execute_task.py` 追加（注意 `_patch` 需更新）：

修改现有 `_patch`（**关键**：monkeypatch 的工厂必须把 `login_credential` 转发到 fake 实例，否则断言恒为 None）：

```python
def _patch(monkeypatch, fake: FakeScraper, config):
    def _factory(headful=False, login_credential=None):
        fake.login_credential_arg = login_credential
        return fake

    monkeypatch.setattr(task_runner, "PlaywrightScraper", _factory)
    monkeypatch.setattr(task_runner, "Config", lambda repo_root=REPO_ROOT: config)
```

FakeScraper 增加字段（`__init__` 中）：

```python
        self.login_credential_arg: object | None = None
```

并接收构造参数：

```python
    def __init__(self, headful: bool = False, login_credential=None):
        self.headful = headful
        self.login_credential_arg = login_credential
        ...
```

追加测试（文件顶部 import 追加 `Setting, SiteCredential`：`from backend.app.models import Company, Job, Keyword, ScrapeTask, Setting, SiteCredential, TaskStatus`）：

```python
def _seed_credential(config, username="13800000000") -> int:
    from backend.app.core.site_security import encrypt_password

    with SessionLocal() as s:
        c = SiteCredential(
            site="51job",
            username=username,
            password_enc=encrypt_password("pw123", config.site_secret_key),
        )
        s.add(c)
        s.commit()
        return c.id


def _seed_setting_scraper_login(credential_id: int) -> None:
    with SessionLocal() as s:
        s.add(Setting(key="scraper_login", value={"enabled": True, "credential_id": credential_id}))
        s.commit()


def test_execute_task_uses_task_login_credential(config, monkeypatch):
    init_db(config)
    fake = FakeScraper()
    fake.search_results = [PageResult(page_num=1, jobs=[JobDraft(job_id="j1", title="t1")])]
    _patch(monkeypatch, fake, config)
    cid = _seed_credential(config)
    with SessionLocal() as s:
        kw = Keyword(keyword="python")
        s.add(kw)
        s.commit()
        task = ScrapeTask(keyword_id=kw.id, status=TaskStatus.QUEUED.value, login_credential_id=cid)
        s.add(task)
        s.commit()
        task_id = task.id
    asyncio.run(task_runner.execute_task(task_id))
    assert fake.login_credential_arg is not None
    assert fake.login_credential_arg.username == "13800000000"
    assert fake.login_credential_arg.password == "pw123"


def test_execute_task_uses_global_default_when_task_unset(config, monkeypatch):
    init_db(config)
    fake = FakeScraper()
    fake.search_results = [PageResult(page_num=1, jobs=[JobDraft(job_id="j1", title="t1")])]
    _patch(monkeypatch, fake, config)
    cid = _seed_credential(config)
    _seed_setting_scraper_login(cid)
    task_id, _ = _seed_task(config.db_path)
    asyncio.run(task_runner.execute_task(task_id))
    assert fake.login_credential_arg is not None
    assert fake.login_credential_arg.username == "13800000000"


def test_execute_task_no_login_by_default(config, monkeypatch):
    init_db(config)
    fake = FakeScraper()
    fake.search_results = [PageResult(page_num=1, jobs=[JobDraft(job_id="j1", title="t1")])]
    _patch(monkeypatch, fake, config)
    task_id, _ = _seed_task(config.db_path)
    asyncio.run(task_runner.execute_task(task_id))
    assert fake.login_credential_arg is None
```

- [ ] **Step 10: 运行测试确认失败**

Run: `uv run pytest backend/tests/test_execute_task.py -q`
Expected: FAIL（`_resolve_login_credential` 未实现 / `login_credential_arg` 为 None）

- [ ] **Step 11: 实现 task_runner 凭据解析**

修改 `backend/app/services/task_runner.py`：
- import 追加（`from backend.app.models import Keyword, ScrapeTask, TaskStatus` 这一行改为包含 `Setting, SiteCredential`）：

```python
from backend.app.core.exceptions import AppError
from backend.app.core.site_security import decrypt_password
from backend.app.models import Keyword, ScrapeTask, Setting, SiteCredential, TaskStatus
from backend.app.scrapers.base import LoginCredential
```

- 模块常量区追加：

```python
_SCRAPER_LOGIN_KEY = "scraper_login"
_DEFAULT_SCRAPER_LOGIN = {"enabled": False, "credential_id": None}
```

- 新增函数（放在 `_claim_next_task` 之后）：

```python
def _resolve_login_credential(db: Session, task: ScrapeTask) -> LoginCredential | None:
    """任务级 login_credential_id 优先，其次全局 scraper_login 默认，均无则匿名。"""
    cred_id = task.login_credential_id
    if cred_id is None:
        row = db.query(Setting).filter_by(key=_SCRAPER_LOGIN_KEY).first()
        value = row.value if row else _DEFAULT_SCRAPER_LOGIN
        if not value.get("enabled") or not value.get("credential_id"):
            return None
        cred_id = value["credential_id"]
    cred = db.get(SiteCredential, cred_id)
    if cred is None:
        logger.warning("任务引用的凭据不存在，降级为匿名抓取: task_id=%s cred_id=%s", task.id, cred_id)
        return None
    cfg = Config(repo_root=REPO_ROOT)
    try:
        password = decrypt_password(cred.password_enc, cfg.site_secret_key)
    except AppError:
        logger.error("任务凭据解密失败，降级为匿名抓取: task_id=%s", task.id)
        return None
    return LoginCredential(site=cred.site, username=cred.username, password=password)
```

- `execute_task` 开头改为：

```python
async def execute_task(task_id: int) -> None:
    with SessionLocal() as db:
        task = db.get(ScrapeTask, task_id)
        keyword = db.get(Keyword, task.keyword_id)
        kw_text = keyword.keyword if keyword else ""
        kw_area = keyword.city if keyword else "000000"
        kw_industry = keyword.industry if keyword else None
        task_max_pages = task.max_pages
        login_credential = _resolve_login_credential(db, task)
    cfg = Config(repo_root=REPO_ROOT)
    max_pages = min(task_max_pages, cfg.max_pages) if task_max_pages else cfg.max_pages
    scraper = PlaywrightScraper(headful=cfg.headful, login_credential=login_credential)
    ...
```

- [ ] **Step 12: 运行测试确认通过**

Run: `uv run pytest backend/tests/test_execute_task.py backend/tests/test_tasks_api.py -q`
Expected: PASS

- [ ] **Step 13: 运行全量后端测试回归**

Run: `uv run pytest -q`
Expected: PASS（107 项 + 新增约 15 项）

- [ ] **Step 14: 提交**

```bash
git add backend/app/schemas/task.py backend/app/api/tasks.py backend/app/scrapers/base.py backend/app/scrapers/playwright.py backend/app/services/task_runner.py backend/tests/test_tasks_api.py backend/tests/test_execute_task.py backend/tests/test_playwright_scraper.py
git commit -m "feat: 登录后抓取——任务级凭据选择与匿名降级"
```

---

### Task 7: 前端 API 模块

**Files:**
- Create: `frontend/src/api/siteCredentials.ts`
- Modify: `frontend/src/api/tasks.ts`、`frontend/src/api/settings.ts`
- Test: 新建 `frontend/tests/siteCredentials.test.ts`

**Interfaces:**
- Consumes: 后端 Task 3/4/5 路由；`frontend/src/api/http.ts` 的 `http` 实例
- Produces: `siteCredentialsApi`（list/create/update/remove/testLogin）；`tasksApi.create` 支持 `login_credential_id`；`settingsApi.getScraperLogin/updateScraperLogin`

- [ ] **Step 1: 写 vitest 测试（先失败）**

创建 `frontend/tests/siteCredentials.test.ts`：

```ts
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { http } from '@/api/http'
import { siteCredentialsApi } from '@/api/siteCredentials'

let captured: { method?: string; url?: string; data?: unknown; params?: unknown } = {}

function captureAdapter() {
  http.defaults.adapter = async (config) => {
    captured = { method: config.method, url: config.url, data: config.data, params: config.params }
    return { data: {}, status: 200, statusText: 'OK', headers: {}, config } as never
  }
}

beforeEach(() => {
  vi.clearAllMocks()
  captured = {}
  captureAdapter()
})

describe('siteCredentialsApi', () => {
  it('list 带 site 过滤参数', async () => {
    await siteCredentialsApi.list('51job')
    expect(captured.url).toBe('/site-credentials')
    expect(captured.params).toEqual({ site: '51job' })
  })

  it('list 不带 site 时无参数', async () => {
    await siteCredentialsApi.list()
    expect(captured.params).toBeUndefined()
  })

  it('create 发送 site/username/password/remark', async () => {
    await siteCredentialsApi.create({ site: '51job', username: '138', password: 'pw', remark: '主账号' })
    expect(captured.method).toBe('post')
    expect(captured.url).toBe('/site-credentials')
    expect(captured.data).toEqual({ site: '51job', username: '138', password: 'pw', remark: '主账号' })
  })

  it('update 只发 remark 与 password', async () => {
    await siteCredentialsApi.update(1, { remark: '新备注', password: 'newpw' })
    expect(captured.method).toBe('put')
    expect(captured.url).toBe('/site-credentials/1')
    expect(captured.data).toEqual({ remark: '新备注', password: 'newpw' })
  })

  it('remove 发 DELETE', async () => {
    await siteCredentialsApi.remove(2)
    expect(captured.method).toBe('delete')
    expect(captured.url).toBe('/site-credentials/2')
  })

  it('testLogin 发 POST', async () => {
    await siteCredentialsApi.testLogin(3)
    expect(captured.method).toBe('post')
    expect(captured.url).toBe('/site-credentials/3/test-login')
  })
})
```

- [ ] **Step 2: 运行测试确认失败**

Run（workdir `frontend/`）：`npm run test`
Expected: siteCredentials.test.ts FAIL（module not found）

- [ ] **Step 3: 实现 siteCredentials.ts**

创建 `frontend/src/api/siteCredentials.ts`：

```ts
import { http } from './http'

export interface SiteCredentialOut {
  id: number
  site: string
  username: string
  remark: string | null
  has_password: boolean
  created_at: string
  updated_at: string
}

export interface TestLoginResult {
  ok: boolean
  message: string
}

export const siteCredentialsApi = {
  list: (site?: string) =>
    http.get<SiteCredentialOut[]>('/site-credentials', { params: site ? { site } : undefined }).then((r) => r.data),
  create: (data: { site: string; username: string; password: string; remark?: string | null }) =>
    http.post<SiteCredentialOut>('/site-credentials', data).then((r) => r.data),
  update: (id: number, data: { remark?: string | null; password?: string | null }) =>
    http.put<SiteCredentialOut>(`/site-credentials/${id}`, data).then((r) => r.data),
  remove: (id: number) => http.delete(`/site-credentials/${id}`),
  testLogin: (id: number) =>
    http.post<TestLoginResult>(`/site-credentials/${id}/test-login`).then((r) => r.data),
}
```

- [ ] **Step 4: 修改 tasks.ts 与 settings.ts**

`frontend/src/api/tasks.ts`：
- `TaskOut` 追加 `login_credential_id: number | null`、`login_username: string | null`
- `create` 参数追加 `login_credential_id?: number | null`：

```ts
  create: (data: { keyword_id: number; mode?: string; max_pages?: number | null; login_credential_id?: number | null }) =>
    http.post<TaskOut>('/tasks', data).then((r) => r.data),
```

`frontend/src/api/settings.ts` 追加：

```ts
export interface ScraperLoginOut {
  enabled: boolean
  credential_id: number | null
}
```

并在 `settingsApi` 内追加：

```ts
  getScraperLogin: () => http.get<ScraperLoginOut>('/settings/scraper-login').then((r) => r.data),
  updateScraperLogin: (data: ScraperLoginOut) =>
    http.put<ScraperLoginOut>('/settings/scraper-login', data).then((r) => r.data),
```

- [ ] **Step 5: 运行前端测试与 type-check**

Run（workdir `frontend/`）：`npm run test; npm run type-check`
Expected: 全部 PASS（新增 6 个 + 原 23 个）

- [ ] **Step 6: 提交**

```bash
git add frontend/src/api/siteCredentials.ts frontend/src/api/tasks.ts frontend/src/api/settings.ts frontend/tests/siteCredentials.test.ts
git commit -m "feat: 前端站点凭据 API 模块"
```

---

### Task 8: 前端「站点账号」页面

**Files:**
- Create: `frontend/src/views/SiteCredentials.vue`
- Modify: `frontend/src/router/index.ts`
- Modify: `frontend/src/components/Layout.vue`

**Interfaces:**
- Consumes: Task 7 `siteCredentialsApi`
- Produces: 路由 `/credentials`（title「站点账号」），Layout 菜单项「站点账号」

- [ ] **Step 1: 创建页面**

创建 `frontend/src/views/SiteCredentials.vue`（参照 `Companies.vue` 结构与样式约定）：

```vue
<template>
  <div>
    <el-card class="filter-card">
      <el-form :inline="!isMobile">
        <el-form-item label="站点">
          <el-select v-model="query.site" clearable placeholder="全部站点" :style="inputStyle('160px')" @change="search">
            <el-option v-for="s in SITE_OPTIONS" :key="s.value" :label="s.label" :value="s.value" />
          </el-select>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="openCreate">新建账号</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <el-card>
      <el-table :data="list" v-loading="loading">
        <el-table-column label="站点" width="110">
          <template #default="{ row }">{{ siteName(row.site) }}</template>
        </el-table-column>
        <el-table-column prop="username" label="账号" min-width="160" />
        <el-table-column prop="remark" label="备注" min-width="140">
          <template #default="{ row }">{{ row.remark ?? '-' }}</template>
        </el-table-column>
        <el-table-column label="密码" width="90">
          <template #default="{ row }">{{ row.has_password ? '已设置' : '-' }}</template>
        </el-table-column>
        <el-table-column label="更新时间" width="150">
          <template #default="{ row }">{{ formatTime(row.updated_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="220">
          <template #default="{ row }">
            <el-button size="small" @click="openEdit(row)">编辑</el-button>
            <el-button size="small" :loading="testingId === row.id" @click="testLogin(row)">测试登录</el-button>
            <el-button size="small" type="danger" @click="remove(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-dialog v-model="dialog.visible" :title="dialog.editing ? '编辑账号' : '新建账号'" width="420px">
      <el-form label-width="80px">
        <el-form-item label="站点">
          <el-select v-model="dialog.site" style="width: 100%" :disabled="dialog.editing">
            <el-option v-for="s in SITE_OPTIONS" :key="s.value" :label="s.label" :value="s.value" />
          </el-select>
        </el-form-item>
        <el-form-item label="账号">
          <el-input v-model="dialog.username" :disabled="dialog.editing" placeholder="51job 登录手机号" />
        </el-form-item>
        <el-form-item label="密码">
          <el-input
            v-model="dialog.password"
            type="password"
            show-password
            :placeholder="dialog.editing ? '留空则不修改' : '请输入密码'"
          />
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="dialog.remark" placeholder="可选" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialog.visible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="save">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { siteCredentialsApi, type SiteCredentialOut } from '@/api/siteCredentials'
import { formatTime } from '@/utils/format'
import { useIsMobile } from '@/composables/useIsMobile'

const SITE_OPTIONS = [
  { value: '51job', label: '51job' },
]

const loading = ref(false)
const saving = ref(false)
const testingId = ref<number | null>(null)
const list = ref<SiteCredentialOut[]>([])
const isMobile = useIsMobile()

const query = reactive({ site: '' })

const dialog = reactive({
  visible: false,
  editing: false,
  id: 0,
  site: '51job',
  username: '',
  password: '',
  remark: '',
})

function inputStyle(desktopPx: string) {
  return isMobile.value ? { width: '100%' } : { width: desktopPx }
}

function siteName(site: string): string {
  return SITE_OPTIONS.find((s) => s.value === site)?.label ?? site
}

async function load() {
  loading.value = true
  try {
    list.value = await siteCredentialsApi.list(query.site || undefined)
  } catch {
    // 拦截器已提示
  } finally {
    loading.value = false
  }
}

function search() {
  load()
}

function openCreate() {
  dialog.editing = false
  dialog.id = 0
  dialog.site = '51job'
  dialog.username = ''
  dialog.password = ''
  dialog.remark = ''
  dialog.visible = true
}

function openEdit(row: SiteCredentialOut) {
  dialog.editing = true
  dialog.id = row.id
  dialog.site = row.site
  dialog.username = row.username
  dialog.password = ''
  dialog.remark = row.remark ?? ''
  dialog.visible = true
}

async function save() {
  if (!dialog.username.trim() || (!dialog.password && !dialog.editing)) {
    ElMessage.warning(dialog.editing ? '请输入账号' : '请输入账号和密码')
    return
  }
  saving.value = true
  try {
    if (dialog.editing) {
      await siteCredentialsApi.update(dialog.id, {
        remark: dialog.remark || null,
        password: dialog.password || null,
      })
    } else {
      await siteCredentialsApi.create({
        site: dialog.site,
        username: dialog.username.trim(),
        password: dialog.password,
        remark: dialog.remark || null,
      })
    }
    ElMessage.success('已保存')
    dialog.visible = false
    await load()
  } catch {
    // 拦截器已提示（409 重复）
  } finally {
    saving.value = false
  }
}

async function testLogin(row: SiteCredentialOut) {
  testingId.value = row.id
  try {
    const result = await siteCredentialsApi.testLogin(row.id)
    if (result.ok) {
      ElMessage.success(result.message)
    } else {
      ElMessage.error(result.message)
    }
  } catch {
    // 拦截器已提示
  } finally {
    testingId.value = null
  }
}

async function remove(row: SiteCredentialOut) {
  try {
    await ElMessageBox.confirm(`确认删除账号「${row.username}」？`, '提示', { type: 'warning' })
  } catch {
    return
  }
  try {
    await siteCredentialsApi.remove(row.id)
    await load()
  } catch {
    // 拦截器已提示（409 被引用）
  }
}

onMounted(load)
</script>

<style scoped>
.filter-card { margin-bottom: 16px; }
</style>
```

- [ ] **Step 2: 注册路由**

`frontend/src/router/index.ts` 在 `stats` 路由后追加：

```ts
        { path: 'credentials', component: () => import('@/views/SiteCredentials.vue'), meta: { title: '站点账号' } },
```

`frontend/src/components/Layout.vue`：
- import 追加 `Key`：`import { Menu, Odometer, Files, OfficeBuilding, DataAnalysis, Key, ArrowDown } from '@element-plus/icons-vue'`
- `menuItems` 追加：

```ts
  { path: '/credentials', icon: Key, label: '站点账号' },
```

- [ ] **Step 3: type-check 与测试**

Run（workdir `frontend/`）：`npm run type-check; npm run test`
Expected: PASS

- [ ] **Step 4: 提交**

```bash
git add frontend/src/views/SiteCredentials.vue frontend/src/router/index.ts frontend/src/components/Layout.vue
git commit -m "feat: 站点账号管理页面"
```

---

### Task 9: 任务控制台登录抓取 UI

**Files:**
- Modify: `frontend/src/views/Tasks.vue`
- Modify: `frontend/src/components/TaskCard.vue`（移动端任务卡登录标记）

**Interfaces:**
- Consumes: Task 7 `siteCredentialsApi`/`settingsApi.getScraperLogin/updateScraperLogin`/`tasksApi.create` 新参数
- Produces: 新建任务表单「登录后抓取」开关 + 账号下拉；右栏「登录抓取默认账号」设置卡

- [ ] **Step 1: 修改 Tasks.vue**

改动点（在现有基础上增量修改）：

1. script import 追加：

```ts
import { siteCredentialsApi, type SiteCredentialOut } from '@/api/siteCredentials'
```

2. state 追加：

```ts
const credentials = ref<SiteCredentialOut[]>([])
const scraperLogin = ref({ enabled: false, credential_id: null as number | null })
```

`taskForm` 追加字段：

```ts
const taskForm = reactive<{
  keyword_id: number | null
  mode: string
  max_pages: number | null
  use_login: boolean
  login_credential_id: number | null
}>({
  keyword_id: null,
  mode: 'playwright',
  max_pages: null,
  use_login: false,
  login_credential_id: null,
})
```

3. 桌面端「新建抓取任务」表单（`el-form :inline`）在「最大页数」form-item 后追加：

```vue
            <el-form-item label="登录后抓取">
              <el-switch v-model="taskForm.use_login" />
            </el-form-item>
            <el-form-item v-if="taskForm.use_login" label="登录账号">
              <el-select v-model="taskForm.login_credential_id" placeholder="选择账号" :style="inputStyle('180px')">
                <el-option
                  v-for="c in credentials"
                  :key="c.id"
                  :label="`${siteLabel(c.site)} · ${c.username}`"
                  :value="c.id"
                />
              </el-select>
            </el-form-item>
```

4. 移动端对话框同样追加（在「最大页数」后）：

```vue
        <el-form-item label="登录后抓取">
          <el-switch v-model="taskForm.use_login" />
        </el-form-item>
        <el-form-item v-if="taskForm.use_login" label="登录账号">
          <el-select v-model="taskForm.login_credential_id" placeholder="选择账号" style="width: 100%">
            <el-option
              v-for="c in credentials"
              :key="c.id"
              :label="`${siteLabel(c.site)} · ${c.username}`"
              :value="c.id"
            />
          </el-select>
        </el-form-item>
```

5. `createTask` 中传给后端：

```ts
    await tasksApi.create({
      keyword_id: taskForm.keyword_id,
      mode: taskForm.mode,
      max_pages: taskForm.max_pages,
      login_credential_id: taskForm.use_login ? taskForm.login_credential_id : null,
    })
```

6. 右栏「定时任务设置」卡后追加第二个 `el-card`：

```vue
        <el-card class="section-card">
          <template #header>登录抓取默认账号</template>
          <el-form label-width="110px" :label-position="isMobile ? 'top' : undefined">
            <el-form-item label="默认登录抓取">
              <el-switch v-model="scraperLogin.enabled" @change="saveScraperLogin" />
            </el-form-item>
            <el-form-item v-if="scraperLogin.enabled" label="默认账号">
              <el-select
                v-model="scraperLogin.credential_id"
                style="width: 100%"
                placeholder="选择账号（未指定任务时使用）"
                @change="saveScraperLogin"
              >
                <el-option
                  v-for="c in credentials"
                  :key="c.id"
                  :label="`${siteLabel(c.site)} · ${c.username}`"
                  :value="c.id"
                />
              </el-select>
            </el-form-item>
          </el-form>
        </el-card>
```

7. 任务列表「状态」列后追加「登录抓取」列（桌面表格，`el-table-column label="操作"` 之前）：

```vue
            <el-table-column label="登录抓取" width="150">
              <template #default="{ row }">
                <el-tag v-if="row.login_username" type="warning" size="small">{{ row.login_username }}</el-tag>
                <span v-else class="form-hint">匿名</span>
              </template>
            </el-table-column>
```

8. 移动端任务卡：`TaskCard.vue` 追加可选 prop 并在时间行上显示：

```vue
    <div v-if="loginUsername" class="task-login">已登录：{{ loginUsername }}</div>
```

script 改为 `defineProps<{ task: TaskOut; keywordName: string; loginUsername?: string }>()`，样式追加 `.task-login { margin-top: 6px; font-size: 12px; color: var(--el-color-warning); }`；`Tasks.vue` 移动端 `TaskCard` 用法追加 `:login-username="t.login_username ?? undefined"`。

9. script 追加函数：

```ts
function siteLabel(site: string): string {
  return site === '51job' ? '51job' : site
}

async function loadCredentials() {
  credentials.value = await siteCredentialsApi.list()
}

async function loadScraperLogin() {
  scraperLogin.value = await settingsApi.getScraperLogin()
}

async function saveScraperLogin() {
  try {
    await settingsApi.updateScraperLogin(scraperLogin.value)
    ElMessage.success('登录抓取默认已保存')
  } catch {
    // 拦截器已提示
  }
}
```

10. `onMounted` 的 `Promise.all` 追加 `loadCredentials(), loadScraperLogin()`。

- [ ] **Step 2: type-check 与测试**

Run（workdir `frontend/`）：`npm run type-check; npm run test`
Expected: PASS

- [ ] **Step 3: 构建验证**

Run（workdir `frontend/`）：`npm run build`
Expected: 构建成功（产物进 `frontend/dist`）

- [ ] **Step 4: 提交**

```bash
git add frontend/src/views/Tasks.vue frontend/src/components/TaskCard.vue
git commit -m "feat: 任务控制台登录后抓取开关与全局默认账号设置"
```

---

### Task 10: 全量回归与 PRD 同步

**Files:**
- Modify: `docs/PRD.md`

- [ ] **Step 1: 后端全量回归**

Run: `uv run pytest -q`
Expected: 全部 PASS（约 122 项）

- [ ] **Step 2: 前端全量回归**

Run（workdir `frontend/`）：`npm run test; npm run type-check; npm run build`
Expected: 全部 PASS（29 项 vitest + type-check + build）

- [ ] **Step 3: 同步 PRD**

在 `docs/PRD.md` 追加小节（放 §4 数据模型之后，作为「§4.1 站点凭据与登录抓取」）：

```markdown
### 4.1 站点凭据与登录抓取

- **site_credentials**（站点登录凭据，为「一键投简历」与「登录后抓取」提供账号来源）：id, site(站点标识，v1 仅 51job), username, password_enc(AES-GCM 加密), remark, created_at, updated_at —— (site, username) 联合唯一。
- **密码安全**：密码用 AES-GCM 加密存储（密钥在 data/config.ini 的 [site] secret，32 字节随机），任何 API 响应不回传密码，仅返回 has_password。
- **scrape_tasks** 增加 login_credential_id（NULL=匿名/全局默认）。
- **登录后抓取开关**：默认不登录。`POST /api/tasks` 可选 login_credential_id（任务级优先）；全局默认存 settings 表 scraper_login（enabled + credential_id），未指定任务且全局开启时自动采用。登录失败自动降级为匿名抓取并记日志。
- **测试登录**：`POST /api/site-credentials/{id}/test-login` 实际登录验证凭据可用性。
- **删除限制**：凭据被进行中/排队中任务引用时删除返回 409；已完成/失败任务引用置 NULL。
```

在 §5 API 设计追加一行：

```markdown
- 凭据：`GET/POST /api/site-credentials`、`PUT/DELETE /api/site-credentials/{id}`、`POST /api/site-credentials/{id}/test-login`
```

在 §7 前端页面追加第 6 项：

```markdown
6. **站点账号页**：招聘网站登录凭据管理（增删改查、测试登录），为「登录后抓取」与后续「一键投简历」提供账号。
```

- [ ] **Step 4: 提交**

```bash
git add docs/PRD.md
git commit -m "docs: PRD 同步站点凭据与登录抓取"
```

---

## 执行须知

- 每个任务的 Step 顺序执行，失败即停（TDD：先看测试失败，再实现，再转绿）。
- Windows 终端执行含中文输出的命令前设 `$env:PYTHONUTF8 = "1"`。
- 前端命令一律在 `frontend/` 目录（workdir）执行。
- 真实环境联调 51job 登录（test-login / 登录抓取）不在自动化测试范围，需人工冒烟。
