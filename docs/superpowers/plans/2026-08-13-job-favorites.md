# 职位收藏功能 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 职位列表页支持逐条/批量收藏、按收藏状态三态筛选（全部/已收藏/未收藏）。

**Architecture:** 新增独立 `favorites` 表（以 `jobs.job_id` 字符串为唯一键，不建外键），抓取 upsert 不触碰收藏数据；`GET /api/jobs` 新增 `favorite` 查询参数（bool|None）与 `JobOut.is_favorite` 字段（批量回填）；前端 Jobs.vue 加星标列、多选列、批量按钮与筛选下拉。单用户系统，不加 user_id。

**Tech Stack:** Python 3.14 / FastAPI / SQLAlchemy 2.0 / SQLite；Vue3 `<script setup>` / Element Plus / axios。

## Global Constraints

- 设计文档：`docs/superpowers/specs/2026-08-13-job-favorites-design.md`（唯一权威，冲突以此为准）
- 收藏以 `job_id`（字符串）为键；不修改 `services/storage.py` 的 upsert 逻辑
- SQLAlchemy 2.0 风格 `Mapped[...]` + `mapped_column`；模型注册进 `backend/app/models/__init__.py`
- 路由只做校验与响应组装，错误用 `AppError(message, status_code)`；schemas 在 `backend/app/schemas/`，不在路由暴露 ORM 对象
- 所有接口需 `Depends(get_current_user)`（未认证 401）
- 前端 API 调用走 `frontend/src/api/` 封装（统一 JWT）；组件不直接发请求
- Windows 终端执行涉及中文输出的命令前设 `$env:PYTHONUTF8 = "1"`
- 后端测试 `pytest`（testpaths = backend/tests）；前端 `npm test`（vitest）、`npm run type-check`、`npm run build`
- 提交信息沿用仓库风格：`feat(jobs): 中文描述`
- Windows 行尾：提交时 Git 自动处理 CRLF/LF，无需干预

---

### Task 1: Favorite 模型 + 批次 Schemas + 共享测试 fixture

**Files:**
- Create: `backend/app/models/favorite.py`
- Modify: `backend/app/models/__init__.py`（注册导出）
- Modify: `backend/app/schemas/job.py`（FavoriteBatchIn / FavoriteBatchOut）
- Modify: `backend/tests/conftest.py`（把 `client` fixture 从 test_jobs_api.py 移入，供所有测试文件共用）
- Modify: `backend/tests/test_jobs_api.py`（删除本地 `client` fixture 定义及其相关 import，改用 conftest 版本）
- Test: `backend/tests/test_favorites_api.py`（新建，含 `client` 复用与首批测试）

**Interfaces:**
- Produces:
  - `class Favorite(Base)`：`__tablename__ = "favorites"`，字段 `id: Mapped[int]`（PK）、`job_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)`、`created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)`
  - `class FavoriteBatchIn(BaseModel)`：`job_ids: list[str]`
  - `class FavoriteBatchOut(BaseModel)`：`added: int = 0`、`skipped: int = 0`
  - conftest 级 `client(config)` fixture（签名与现 test_jobs_api.py 中完全一致）

- [ ] **Step 1: 移动 `client` fixture 到 conftest.py**

把 `backend/tests/test_jobs_api.py` 第 11–31 行的 `client` fixture 原样移动到 `backend/tests/conftest.py`，同时把 fixture 所需的 import（`pytest`、`TestClient`、`ensure_admin`、`SessionLocal`、`init_db`、`create_app`、`Company`、`Job`）移到 conftest.py。conftest.py 现内容开头保留（sys.path、JOB_HUNTER_TESTING、`config` fixture）。

- [ ] **Step 2: 从 test_jobs_api.py 删除本地 fixture**

删除 `backend/tests/test_jobs_api.py` 中的 `client` fixture 定义（第 11–31 行），并删除仅被该 fixture 使用的 import：`pytest`、`TestClient`、`ensure_admin`、`SessionLocal`、`init_db`、`create_app`。保留 `Company, Job` import（`test_companies_filter` 等测试仍用到）。

- [ ] **Step 3: 新建 Favorite 模型**

`backend/app/models/favorite.py`：

```python
from datetime import datetime

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.core.database import Base


class Favorite(Base):
    __tablename__ = "favorites"

    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
```

- [ ] **Step 4: 注册模型**

`backend/app/models/__init__.py` 加入：

```python
from backend.app.models.favorite import Favorite
```

并在 `__all__` 中追加 `"Favorite"`。

- [ ] **Step 5: 新增 Schemas**

`backend/app/schemas/job.py` 文件末尾追加：

```python
class FavoriteBatchIn(BaseModel):
    job_ids: list[str]


class FavoriteBatchOut(BaseModel):
    added: int = 0
    skipped: int = 0
```

- [ ] **Step 6: 写失败测试**

`backend/tests/test_favorites_api.py`：

```python
import pytest
from fastapi.testclient import TestClient
from datetime import datetime

from backend.app.core.database import SessionLocal, init_db
from backend.app.main import create_app
from backend.app.models import Company, Job


@pytest.fixture()
def client(config):
    init_db(config)
    with SessionLocal() as s:
        s.add_all([
            Company(company_id="c1", name="A公司", type="民营", industry="软件", size="100-499人", activity="今日回复8次", activity_score=8),
            Job(job_id="j1", title="Python工程师", salary_min=10000, salary_max=20000, city="上海", degree="本科", tags=["急招"], company_id="c1", publish_time=datetime(2024, 3, 1)),
            Job(job_id="j2", title="Java工程师", salary_min=15000, salary_max=25000, city="北京", tags=["高薪"], company_id="c1", publish_time=datetime(2024, 2, 1)),
            Job(job_id="j3", title="前端工程师", salary_min=None, salary_max=None, city="上海", tags=[], publish_time=datetime(2024, 1, 15)),
            Job(job_id="j4", title="测试工程师", city="上海", publish_time=datetime(2024, 1, 1)),
        ])
        s.commit()
    app = create_app(config)
    with TestClient(app) as c:
        token = c.post("/api/auth/login", json={"username": config.auth_username, "password": config.auth_password}).json()["access_token"]
        c.headers.update({"Authorization": f"Bearer {token}"})
        yield c


def test_favorites_table_created(config):
    init_db(config)
    from sqlalchemy import inspect

    from backend.app.core.database import engine
    tables = inspect(engine).get_table_names()
    assert "favorites" in tables
```

注意：fixture 里 `init_db(config)` 会在 Task 1 结束时自动创建 favorites 表（`Base.metadata.create_all`），此测试在 Task 2 前先验证表结构存在。此文件中的 `client` fixture 在 conftest 已提供同名 fixture 后会产生 shadowing 警告——**不要**在 conftest 保留同名 fixture，本文件自带 fixture 即可（conftest 中的 fixture 是为 test_jobs_api.py 等服务；本文件覆盖为本地数据）。若运行出现 duplicate fixture 冲突，将本文件 fixture 重命名为 `fav_client` 并在用例使用 `fav_client`。

- [ ] **Step 7: 运行测试确认通过**

Run: `cd backend; $env:PYTHONUTF8 = "1"; pytest tests/test_favorites_api.py tests/test_jobs_api.py -q`
Expected: 所有用例 PASS（test_favorites_api 含 1 个新建用例；test_jobs_api 原有 12 个用例在新 fixture 位置下仍通过）。

- [ ] **Step 8: 全量回归**

Run: `cd backend; $env:PYTHONUTF8 = "1"; pytest -q`
Expected: 108 个用例 PASS（107 原有 + 1 新增）。

- [ ] **Step 9: Commit**

```bash
git add backend/app/models/favorite.py backend/app/models/__init__.py backend/app/schemas/job.py backend/tests/conftest.py backend/tests/test_jobs_api.py backend/tests/test_favorites_api.py
git commit -m "feat: favorites 表与批次收藏 schemas，共享测试 fixture 上移 conftest"
```

---

### Task 2: 批量收藏 / 批量取消收藏 API

**Files:**
- Modify: `backend/app/api/jobs.py`（新增 POST/DELETE `/favorites`，`_with_company` 暂不改）
- Test: `backend/tests/test_favorites_api.py`（追加用例）

**Interfaces:**
- Consumes: `Favorite`（Task 1）、`FavoriteBatchIn` / `FavoriteBatchOut`（Task 1）
- Produces:
  - `POST /api/jobs/favorites`，请求体 `FavoriteBatchIn`，响应 `FavoriteBatchOut`：`added` = 实际新增数，`skipped` = 去重后总数 − added（含已收藏、jobs 表不存在两种情况）；`job_ids` 去重（保留首现顺序）；空列表返回 `AppError("job_ids 不能为空", 400)`
  - `DELETE /api/jobs/favorites`，请求体 `FavoriteBatchIn`，响应 `FavoriteBatchOut`：`removed` = 实际删除数，`skipped` = 去重后总数 − removed；空列表返回 400

- [ ] **Step 1: 写失败测试（追加到 test_favorites_api.py）**

```python
def test_add_favorites(client):
    resp = client.post("/api/jobs/favorites", json={"job_ids": ["j1", "j2", "j1"]})
    assert resp.status_code == 200
    assert resp.json() == {"added": 2, "skipped": 1}


def test_add_favorites_skip_missing_job(client):
    resp = client.post("/api/jobs/favorites", json={"job_ids": ["j1", "no_such_job"]})
    assert resp.json() == {"added": 1, "skipped": 1}


def test_add_favorites_idempotent(client):
    client.post("/api/jobs/favorites", json={"job_ids": ["j1"]})
    resp = client.post("/api/jobs/favorites", json={"job_ids": ["j1", "j2"]})
    assert resp.json() == {"added": 1, "skipped": 1}


def test_add_favorites_empty_400(client):
    resp = client.post("/api/jobs/favorites", json={"job_ids": []})
    assert resp.status_code == 400


def test_remove_favorites(client):
    client.post("/api/jobs/favorites", json={"job_ids": ["j1", "j2"]})
    resp = client.delete("/api/jobs/favorites", json={"job_ids": ["j1", "j1"]})
    assert resp.status_code == 200
    assert resp.json() == {"removed": 1, "skipped": 1}


def test_remove_favorites_idempotent(client):
    resp = client.delete("/api/jobs/favorites", json={"job_ids": ["j1"]})
    assert resp.json() == {"removed": 0, "skipped": 1}


def test_favorites_require_auth(config):
    app = create_app(config)
    with TestClient(app) as c:
        assert c.post("/api/jobs/favorites", json={"job_ids": ["j1"]}).status_code == 401
        assert c.delete("/api/jobs/favorites", json={"job_ids": ["j1"]}).status_code == 401
```

- [ ] **Step 2: 运行确认失败**

Run: `cd backend; $env:PYTHONUTF8 = "1"; pytest tests/test_favorites_api.py -q`
Expected: FAIL（404 — 路由不存在，`/api/jobs/favorites` 会落入 `GET /api/jobs/{job_key}` 的 404 或 method 不支持）。

- [ ] **Step 3: 实现端点**

`backend/app/api/jobs.py`：import 处追加 `Favorite`，schemas import 追加 `FavoriteBatchIn, FavoriteBatchOut`。在 `get_job` 之后（文件末尾）追加：

```python
@jobs_router.post("/favorites", response_model=FavoriteBatchOut)
def add_favorites(
    body: FavoriteBatchIn,
    db=Depends(get_db),
    user=Depends(get_current_user),
):
    ids = list(dict.fromkeys(body.job_ids))
    if not ids:
        raise AppError("job_ids 不能为空", 400)
    existing = {
        f.job_id for f in db.query(Favorite).filter(Favorite.job_id.in_(ids)).all()
    }
    valid = {
        jid
        for (jid,) in db.query(Job.job_id).filter(Job.job_id.in_(ids)).all()
    }
    to_add = valid - existing
    db.add_all([Favorite(job_id=jid) for jid in to_add])
    db.commit()
    return FavoriteBatchOut(added=len(to_add), skipped=len(ids) - len(to_add))


@jobs_router.delete("/favorites", response_model=FavoriteBatchOut)
def remove_favorites(
    body: FavoriteBatchIn,
    db=Depends(get_db),
    user=Depends(get_current_user),
):
    ids = list(dict.fromkeys(body.job_ids))
    if not ids:
        raise AppError("job_ids 不能为空", 400)
    existing = {
        f.job_id for f in db.query(Favorite).filter(Favorite.job_id.in_(ids)).all()
    }
    db.query(Favorite).filter(Favorite.job_id.in_(existing)).delete(
        synchronize_session=False
    )
    db.commit()
    return FavoriteBatchOut(removed=len(existing), skipped=len(ids) - len(existing))
```

路由顺序说明：POST/DELETE `/favorites` 与 GET `/{job_key}` 方法不同、路径更具体，FastAPI 无冲突。

- [ ] **Step 4: 运行测试确认通过**

Run: `cd backend; $env:PYTHONUTF8 = "1"; pytest tests/test_favorites_api.py -q`
Expected: 全部 PASS。

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/jobs.py backend/tests/test_favorites_api.py
git commit -m "feat(jobs): 批量收藏/取消收藏 API（幂等，跳过不存在职位）"
```

---

### Task 3: favorite 筛选参数 + is_favorite 回填

**Files:**
- Modify: `backend/app/api/jobs.py`（`list_jobs` 加 `favorite` 参数；`_with_company` 回填 `is_favorite`）
- Modify: `backend/app/schemas/job.py`（`JobOut` 加 `is_favorite: bool = False`）
- Test: `backend/tests/test_favorites_api.py`（追加用例）

**Interfaces:**
- Consumes: `Favorite`（Task 1）、`JobOut`（Task 1 起存在）
- Produces:
  - `GET /api/jobs?favorite=true|false`（省略=全部）：true 时 `Job.job_id IN (SELECT favorites.job_id)`，false 时 NOT IN
  - `JobOut.is_favorite: bool`：列表与 `GET /api/jobs/{job_key}` 详情均回填（批量查询当前页 job_ids 的收藏集合，避免 N+1）

- [ ] **Step 1: 写失败测试（追加到 test_favorites_api.py）**

```python
def test_list_is_favorite_flag(client):
    client.post("/api/jobs/favorites", json={"job_ids": ["j1", "j3"]})
    resp = client.get("/api/jobs", params={"page_size": 100})
    flags = {i["job_id"]: i["is_favorite"] for i in resp.json()["items"]}
    assert flags == {"j1": True, "j2": False, "j3": True, "j4": False}


def test_filter_favorite_true(client):
    client.post("/api/jobs/favorites", json={"job_ids": ["j1"]})
    resp = client.get("/api/jobs", params={"favorite": "true"})
    assert resp.json()["total"] == 1
    assert resp.json()["items"][0]["job_id"] == "j1"


def test_filter_favorite_false(client):
    client.post("/api/jobs/favorites", json={"job_ids": ["j1"]})
    resp = client.get("/api/jobs", params={"favorite": "false"})
    assert resp.json()["total"] == 3
    assert {i["job_id"] for i in resp.json()["items"]} == {"j2", "j3", "j4"}


def test_filter_favorite_with_other_filters(client):
    client.post("/api/jobs/favorites", json={"job_ids": ["j1"]})
    resp = client.get("/api/jobs", params={"favorite": "true", "city": "上海"})
    assert resp.json()["total"] == 1


def test_detail_is_favorite(client):
    client.post("/api/jobs/favorites", json={"job_ids": ["j2"]})
    resp = client.get("/api/jobs/j1")
    assert resp.json()["is_favorite"] is False
    resp = client.get("/api/jobs/j2")
    assert resp.json()["is_favorite"] is True
```

- [ ] **Step 2: 运行确认失败**

Run: `cd backend; $env:PYTHONUTF8 = "1"; pytest tests/test_favorites_api.py -q`
Expected: FAIL（`is_favorite` 键不存在；`favorite` 参数被当作未知查询参数忽略，total 不符）。

- [ ] **Step 3: Schema 加字段**

`backend/app/schemas/job.py` 的 `JobOut` 中 `company_activity_score: int = -1` 之后追加：

```python
    is_favorite: bool = False
```

- [ ] **Step 4: list_jobs 加 favorite 参数**

`backend/app/api/jobs.py` 的 `list_jobs` 签名（`sort` 参数之前）追加：

```python
    favorite: bool | None = None,
```

在 `if tag:` 过滤块之后追加：

```python
    if favorite is True:
        q = q.filter(Job.job_id.in_(db.query(Favorite.job_id)))
    elif favorite is False:
        q = q.filter(~Job.job_id.in_(db.query(Favorite.job_id)))
```

- [ ] **Step 5: _with_company 回填 is_favorite**

`backend/app/api/jobs.py` 的 `_with_company` 开头追加：

```python
    fav_ids: set[str] = set()
    if jobs:
        fav_ids = {
            f.job_id
            for f in db.query(Favorite)
            .filter(Favorite.job_id.in_([j.job_id for j in jobs]))
            .all()
        }
```

并在 `item = JobOut.model_validate(j)` 之后追加：

```python
        item.is_favorite = j.job_id in fav_ids
```

（`_with_company` 同时服务列表与详情，两者均获得 `is_favorite`。）

- [ ] **Step 6: 运行测试确认通过**

Run: `cd backend; $env:PYTHONUTF8 = "1"; pytest -q`
Expected: 全部 PASS（原 108 + Task 3 新增 5 + Task 2 新增 7）。

- [ ] **Step 7: Commit**

```bash
git add backend/app/api/jobs.py backend/app/schemas/job.py backend/tests/test_favorites_api.py
git commit -m "feat(jobs): favorite 三态筛选与列表/详情 is_favorite 回填"
```

---

### Task 4: 前端 api 层 + 收藏参数映射纯函数

**Files:**
- Modify: `frontend/src/api/jobs.ts`
- Modify: `frontend/src/utils/jobsQuery.ts`（新增 `favoriteParam` 纯函数）
- Test: `frontend/tests/jobsQuery.test.ts`（追加用例）

**Interfaces:**
- Produces:
  - `JobOut.is_favorite: boolean`
  - `JobQuery.favorite?: boolean`
  - `jobsApi.addFavorites(jobIds: string[]): Promise<{ added: number; skipped: number }>` — `http.post('/jobs/favorites', { job_ids })`
  - `jobsApi.removeFavorites(jobIds: string[]): Promise<{ removed: number; skipped: number }>` — `http.delete('/jobs/favorites', { data: { job_ids } })`（axios DELETE 必须用 `data` 配置项携带 body）
  - `favoriteParam(value: '' | 'yes' | 'no'): boolean | undefined` — `'yes'`→`true`、`'no'`→`false`、`''`→`undefined`

- [ ] **Step 1: 写失败测试**

`frontend/tests/jobsQuery.test.ts` 追加：

```typescript
import { favoriteParam } from '@/utils/jobsQuery'

describe('favoriteParam', () => {
  it('maps select value to api param', () => {
    expect(favoriteParam('yes')).toBe(true)
    expect(favoriteParam('no')).toBe(false)
    expect(favoriteParam('')).toBeUndefined()
  })
})
```

（若文件已 import `jobsStateFromRoute`，把 `favoriteParam` 并入同一 import 行。）

- [ ] **Step 2: 运行确认失败**

Run: `cd frontend; npm test -- --run tests/jobsQuery.test.ts`
Expected: FAIL（favoriteParam 未导出 / TypeScript 编译报错）。

- [ ] **Step 3: 实现纯函数**

`frontend/src/utils/jobsQuery.ts` 追加：

```typescript
export function favoriteParam(value: '' | 'yes' | 'no'): boolean | undefined {
  if (value === 'yes') return true
  if (value === 'no') return false
  return undefined
}
```

- [ ] **Step 4: 扩展 api 层**

`frontend/src/api/jobs.ts`：

`JobOut` 接口在 `company_activity_score?: number` 之后加：

```typescript
  is_favorite: boolean
```

`JobQuery` 接口在 `sort?: string[]` 之后加：

```typescript
  favorite?: boolean
```

`jobsApi` 对象追加：

```typescript
  addFavorites: (jobIds: string[]) =>
    http.post<{ added: number; skipped: number }>('/jobs/favorites', { job_ids: jobIds }).then((r) => r.data),
  removeFavorites: (jobIds: string[]) =>
    http.delete<{ removed: number; skipped: number }>('/jobs/favorites', { data: { job_ids: jobIds } }).then((r) => r.data),
```

- [ ] **Step 5: 运行测试确认通过**

Run: `cd frontend; npm test`
Expected: 全部 PASS（原 23 + 新增 1）。

- [ ] **Step 6: Commit**

```bash
git add frontend/src/api/jobs.ts frontend/src/utils/jobsQuery.ts frontend/tests/jobsQuery.test.ts
git commit -m "feat(jobs): 前端收藏 api 与 favorite 参数映射"
```

---

### Task 5: Jobs.vue 收藏 UI（星标列 / 多选 / 批量按钮 / 筛选下拉）

**Files:**
- Modify: `frontend/src/views/Jobs.vue`

**Interfaces:**
- Consumes: `jobsApi.addFavorites` / `jobsApi.removeFavorites` / `JobOut.is_favorite` / `JobQuery.favorite` / `favoriteParam`（Task 4）
- Produces: 无（终端任务，TypeScript 类型检查通过即交付）

- [ ] **Step 1: template 加筛选下拉（收藏三态）**

`frontend/src/views/Jobs.vue` 的 `<el-form-item label="标签">` 之后插入：

```html
        <el-form-item label="收藏">
          <el-select v-model="query.favorite" style="width: 120px" @change="search">
            <el-option label="全部" value="" />
            <el-option label="已收藏" value="yes" />
            <el-option label="未收藏" value="no" />
          </el-select>
        </el-form-item>
```

- [ ] **Step 2: template 加多选列 + 星标列 + 批量按钮**

`<el-table :data="page.items" v-loading="loading" @row-click="openDetail">` 改为：

```html
      <el-table :data="page.items" v-loading="loading" @selection-change="onSelectionChange" @row-click="onRowClick">
        <el-table-column type="selection" width="40" />
        <el-table-column label="收藏" width="70" align="center">
          <template #default="{ row }">
            <el-button link :type="row.is_favorite ? 'warning' : 'info'" @click.stop="toggleFavorite(row)">
              <el-icon :size="16"><StarFilled v-if="row.is_favorite" /><Star v-else /></el-icon>
            </el-button>
          </template>
        </el-table-column>
```

`<el-table>` 之前插入工具栏（放在 `<el-card>` 内、表格上方）：

```html
      <div class="toolbar">
        <span class="selected-info">已选 {{ selection.length }} 项</span>
        <el-button type="primary" :disabled="selection.length === 0" @click="batchFavorite(true)">批量收藏</el-button>
        <el-button :disabled="selection.length === 0" @click="batchFavorite(false)">批量取消收藏</el-button>
      </div>
```

- [ ] **Step 3: script 逻辑**

`import { jobsApi, type JobOut, type JobPage, type JobQuery } from '@/api/jobs'` 追加图标与纯函数 import：

```typescript
import { Star, StarFilled } from '@element-plus/icons-vue'
import { favoriteParam } from '@/utils/jobsQuery'
```

`const publishRange = ref<[string, string] | null>(null)` 之后追加：

```typescript
const selection = ref<JobOut[]>([])
```

`query` reactive 类型与初值追加：

```typescript
  favorite: '' | 'yes' | 'no'
```
初值 `favorite: '',`（放在 `tag: '',` 之后）。

`load()` 中 `if (query.tag) params.tag = query.tag` 之后追加：

```typescript
    const fav = favoriteParam(query.favorite)
    if (fav !== undefined) params.favorite = fav
```

`reset()` 中 `query.tag = ''` 之后追加：

```typescript
  query.favorite = ''
```

`onPage` 定义后追加以下函数：

```typescript
function onRowClick(row: JobOut, column: { type?: string }) {
  if (column.type === 'selection') return
  openDetail(row)
}

function onSelectionChange(rows: JobOut[]) {
  selection.value = rows
}

async function toggleFavorite(row: JobOut) {
  try {
    if (row.is_favorite) {
      await jobsApi.removeFavorites([row.job_id])
    } else {
      await jobsApi.addFavorites([row.job_id])
    }
    load()
  } catch {
    // 拦截器已提示
  }
}

async function batchFavorite(add: boolean) {
  const ids = selection.value.map((r) => r.job_id)
  if (ids.length === 0) return
  try {
    if (add) {
      await jobsApi.addFavorites(ids)
    } else {
      await jobsApi.removeFavorites(ids)
    }
    selection.value = []
    load()
  } catch {
    // 拦截器已提示
  }
}
```

- [ ] **Step 4: 样式**

`<style scoped>` 追加：

```css
.toolbar { margin-bottom: 12px; }
.selected-info { margin-right: 12px; color: var(--el-text-color-secondary); }
```

- [ ] **Step 5: 类型检查与构建**

Run: `cd frontend; npm run type-check; if ($?) { npm run build }`
Expected: 无类型错误，build 成功产出 dist。

- [ ] **Step 6: 前端全量测试**

Run: `cd frontend; npm test`
Expected: 全部 PASS（24 项）。

- [ ] **Step 7: Commit**

```bash
git add frontend/src/views/Jobs.vue
git commit -m "feat(jobs): 职位列表收藏星标、批量收藏/取消与三态筛选"
```

---

### Task 6: 全量验证

**Files:** 无

- [ ] **Step 1: 后端全量测试**

Run: `cd backend; $env:PYTHONUTF8 = "1"; pytest -q`
Expected: 全部 PASS（原 107 + 收藏相关 13 = 120）。

- [ ] **Step 2: 前端全量验证**

Run: `cd frontend; npm test; if ($?) { npm run type-check }`
Expected: vitest 24 项 PASS，type-check 无错误。

- [ ] **Step 3: 手动冒烟（可选但建议）**

启动后端 `$env:PYTHONUTF8 = "1"; uv run uvicorn backend.app.main:app`（另一终端 `cd frontend; npm run dev` 或直接访问生产托管端口），在职位列表页验证：星标点击切换、批量收藏/取消、三态筛选、翻页/筛选组合后收藏状态不丢。结束后停掉服务进程。

- [ ] **Step 4: 确认工作区干净**

Run: `git status --short`
Expected: 无未提交改动（或仅本次 feature 已提交的改动）。

---

## Self-Review 记录

- **Spec 覆盖**：§3.1 POST（Task 2）、§3.2 DELETE（Task 2）、§3.3 favorite 参数（Task 3）、§3.4 JobOut.is_favorite（Task 3）、§3.5 Schemas（Task 1）、§4.1 api/jobs.ts（Task 4）、§4.2 Jobs.vue（Task 5）、§5 测试（Task 2/3/4）、§6 非目标（未实现，符合）
- **类型一致性**：`favoriteParam('' | 'yes' | 'no')` 在 Task 4 定义、Task 5 消费；`FavoriteBatchIn{job_ids}` / `FavoriteBatchOut{added,skipped}` 在 Task 1 定义、Task 2 消费；`is_favorite` 后端 Task 3 产出、前端 Task 4 声明、Task 5 使用；`addFavorites/removeFavorites` Task 4 产出、Task 5 使用——均已核对签名一致
- **注意点**：axios DELETE 携带 body 需 `{ data: ... }`（Task 4 已含）；el-table 选中列点击会触发 row-click，用 `column.type === 'selection'` 拦截（Task 5 已含）；Star/StarFilled 图标来自 @element-plus/icons-vue（package.json 已依赖，无需 uv/npm add）
