# 关键字行业筛选（industry filter）实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为 51job 抓取增加行业筛选——keywords 表持久化逗号分隔的行业编码，搜索 URL 拼 `industry=` 参数（已实测 SPA 读取该参数、翻页保持），前端关键字管理支持多选行业。

**Architecture:** 后端在 keywords 模型加 `industry` 列（幂等迁移），schemas/API 透传并校验；`Scraper.search()` 接口增加 `industry` 参数，Playwright 实现用 `build_search_url()` 纯函数拼 URL；task_runner 从 keyword 透传。前端新增 `utils/industries.ts`（官方行业树 + 名称映射），Tasks.vue 关键字弹窗用 el-cascader 多选。

**Tech Stack:** Python 3.14 + FastAPI + SQLAlchemy + Playwright；Vue3 + Element Plus + Vitest。

## Global Constraints

- 行业编码格式：`^\d{2}(,\d{2})*$`，数量 ≤5；**空字符串与 None 均归一为 NULL（不过滤）**。
- URL 参数用 `urllib.parse.quote()` 编码（逗号 → %2C）。
- 唯一约束 (keyword, city) 保持不变，不纳入 industry。
- 测试禁止访问真实 51job；遵循现有迁移模式（幂等 DDL）。
- 前端行业树为常量（前端维护编码表，与 `utils/cities.ts` 模式一致），后端不存行业字典。

---

### Task 1: keywords 模型加 industry 列 + 幂等迁移

**Files:**
- Modify: `backend/app/models/keyword.py`
- Modify: `backend/app/core/database.py`
- Test: `backend/tests/test_models.py`（或新增 `backend/tests/test_migration.py`）

**Interfaces:**
- Consumes: 现有 `Base`、`inspect/text`、`logger` 模式。
- Produces: `Keyword.industry: Mapped[str | None]`（列 `industry VARCHAR(128)`，NULL=不过滤）；`database._migrate_keywords_industry(engine)`；`init_db` 调用之。

- [ ] **Step 1: 写失败测试**（新建 `backend/tests/test_migration.py`，模拟旧库无 industry 列）

```python
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
        conn.execute(text("CREATE TABLE keywords (id INTEGER NOT NULL PRIMARY KEY, keyword VARCHAR(128) NOT NULL, city VARCHAR(64) NOT NULL DEFAULT '000000', enabled BOOLEAN DEFAULT 1, scrape_mode VARCHAR(32) DEFAULT 'playwright', last_scraped_at DATETIME, created_at DATETIME)"))
    database._migrate_keywords_industry(eng)
    database._migrate_keywords_industry(eng)  # 第二次执行不报错
```

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run pytest backend/tests/test_migration.py -v`
Expected: `AttributeError: module 'backend.app.core.database' has no attribute '_migrate_keywords_industry'`

- [ ] **Step 3: 实现模型列与迁移**

`backend/app/models/keyword.py` 在 `scrape_mode` 行后加：

```python
    industry: Mapped[str | None] = mapped_column(String(128))
```

`backend/app/core/database.py` 在 `_migrate_companies_drop_website` 后新增：

```python
def _migrate_keywords_industry(engine) -> None:
    """轻量迁移：keywords 表增加 industry 列（NULL=不过滤，逗号分隔行业编码）。"""
    insp = inspect(engine)
    if "keywords" not in insp.get_table_names():
        return
    cols = {c["name"] for c in insp.get_columns("keywords")}
    if "industry" in cols:
        return
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE keywords ADD COLUMN industry VARCHAR(128)"))
    logger.info("迁移完成：keywords 增加 industry 列")
```

`init_db` 中 `_migrate_keywords_city(engine)` 之后加 `_migrate_keywords_industry(engine)`。

- [ ] **Step 4: 运行测试确认通过**

Run: `uv run pytest backend/tests/test_migration.py backend/tests/test_models.py -q`
Expected: 全部 PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/models/keyword.py backend/app/core/database.py backend/tests/test_migration.py
git commit -m "feat: keywords 增加 industry 列及幂等迁移"
```

---

### Task 2: schemas 校验 + keywords API 透传

**Files:**
- Modify: `backend/app/schemas/keyword.py`
- Modify: `backend/app/api/keywords.py`
- Test: `backend/tests/test_keywords_api.py`

**Interfaces:**
- Consumes: `Keyword.industry`（Task 1）。
- Produces: `KeywordCreate.industry: str | None = None`、`KeywordUpdate.industry: str | None = None`、`KeywordOut.industry: str | None`；create 存 `industry`，update 用 `model_fields_set` 区分"未传"与"显式置 None（清除）"。

- [ ] **Step 1: 写失败测试**（追加到 `backend/tests/test_keywords_api.py`）

```python
def test_keyword_industry_crud(client):
    resp = client.post("/api/keywords", json={"keyword": "医疗采购", "industry": "08,46,47"})
    assert resp.status_code == 200
    assert resp.json()["industry"] == "08,46,47"
    kid = resp.json()["id"]

    # 非法格式：三位编码
    resp = client.post("/api/keywords", json={"keyword": "x", "industry": "080"})
    assert resp.status_code == 422
    # 非法格式：超过 5 个
    resp = client.post("/api/keywords", json={"keyword": "y", "industry": "01,02,03,04,05,06"})
    assert resp.status_code == 422
    # 空字符串归一为 None
    resp = client.post("/api/keywords", json={"keyword": "z", "industry": ""})
    assert resp.json()["industry"] is None

    # 编辑设置
    resp = client.put(f"/api/keywords/{kid}", json={"industry": "47"})
    assert resp.status_code == 200
    assert resp.json()["industry"] == "47"
    # 未传 industry 不清除已有值
    resp = client.put(f"/api/keywords/{kid}", json={"city": "020000"})
    assert resp.json()["industry"] == "47"
    # 显式置 null 清除筛选
    resp = client.put(f"/api/keywords/{kid}", json={"industry": None})
    assert resp.json()["industry"] is None
```

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run pytest backend/tests/test_keywords_api.py::test_keyword_industry_crud -v`
Expected: FAIL（industry 字段未定义 / 422 断言不满足）

- [ ] **Step 3: 实现 schemas 与 API**

`backend/app/schemas/keyword.py` 完整替换为：

```python
import re
from datetime import datetime

from pydantic import BaseModel, field_validator

from backend.app.models.keyword import DEFAULT_CITY

_INDUSTRY_RE = re.compile(r"^\d{2}(,\d{2})*$")
_MAX_INDUSTRIES = 5


def _normalize_industry(v: str | None) -> str | None:
    if v is None or not v.strip():
        return None
    v = v.strip()
    if len(v.split(",")) > _MAX_INDUSTRIES or not _INDUSTRY_RE.match(v):
        raise ValueError(f"industry 需为逗号分隔的行业编码（≤{_MAX_INDUSTRIES} 个），如 '08,46,47'")
    return v


class KeywordCreate(BaseModel):
    keyword: str
    scrape_mode: str = "playwright"
    city: str = DEFAULT_CITY
    industry: str | None = None

    _normalize_industry = field_validator("industry")(_normalize_industry)


class KeywordUpdate(BaseModel):
    keyword: str | None = None
    scrape_mode: str | None = None
    city: str | None = None
    industry: str | None = None

    _normalize_industry = field_validator("industry")(_normalize_industry)


class KeywordOut(BaseModel):
    id: int
    keyword: str
    city: str
    enabled: bool
    scrape_mode: str
    industry: str | None
    last_scraped_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}
```

`backend/app/api/keywords.py`：
- `create_keyword` 中 `Keyword(...)` 增加 `industry=body.industry`
- `update_keyword` 在 `if body.scrape_mode is not None:` 之后加：

```python
    if "industry" in body.model_fields_set:
        kw.industry = body.industry
```

- [ ] **Step 4: 运行测试确认通过**

Run: `uv run pytest backend/tests/test_keywords_api.py -q`
Expected: 全部 PASS（含既有用例）

- [ ] **Step 5: Commit**

```bash
git add backend/app/schemas/keyword.py backend/app/api/keywords.py backend/tests/test_keywords_api.py
git commit -m "feat: keywords API 支持 industry 透传与校验"
```

---

### Task 3: Scraper 接口 + URL 构造 + task_runner 透传

**Files:**
- Modify: `backend/app/scrapers/base.py`
- Modify: `backend/app/scrapers/playwright.py`
- Modify: `backend/app/services/task_runner.py`
- Test: `backend/tests/test_playwright_scraper.py`、`backend/tests/test_execute_task.py`

**Interfaces:**
- Consumes: `Keyword.industry`（Task 1）。
- Produces: `Scraper.search(keyword, pages, area="000000", industry=None)`；`playwright.build_search_url(keyword, page_num, area, industry=None) -> str`；`PlaywrightScraper._fetch_page(page, keyword, page_num, area="000000", industry=None)`；`task_runner.execute_task` 以 `industry=keyword.industry` 调用 search。

- [ ] **Step 1: 写失败测试**

追加到 `backend/tests/test_playwright_scraper.py`：

```python
def test_build_search_url_with_industry():
    from backend.app.scrapers.playwright import build_search_url

    url = build_search_url("医疗采购", 2, "020000", "08,46,47")
    assert "keyword=%E5%8C%BB%E7%96%97%E9%87%87%E8%B4%AD" in url
    assert "searchType=2" in url and "pageNum=2" in url and "jobArea=020000" in url
    assert "industry=08%2C46%2C47" in url


def test_build_search_url_without_industry():
    from backend.app.scrapers.playwright import build_search_url

    url = build_search_url("python", 1, "000000", None)
    assert "industry" not in url
```

修改 `test_execute_task.py` 的 `FakeScraper`（加 industry 记录）并追加透传用例：

```python
class FakeScraper:
    def __init__(self, headful: bool = False):
        ...
        self.industry_arg: str | None = None
        ...

    async def search(self, keyword, pages, area="000000", industry=None):
        ...
        self.industry_arg = industry
        ...
```

```python
def test_execute_task_passes_industry(config, monkeypatch):
    init_db(config)
    fake = FakeScraper()
    fake.search_results = [PageResult(page_num=1, jobs=[JobDraft(job_id="j1", title="t1")])]
    _patch(monkeypatch, fake, config)
    with SessionLocal() as s:
        kw = Keyword(keyword="医疗采购", industry="47")
        s.add(kw)
        s.commit()
        kw_id = kw.id
        task = ScrapeTask(keyword_id=kw_id, status=TaskStatus.QUEUED.value)
        s.add(task)
        s.commit()
        task_id = task.id
    asyncio.run(task_runner.execute_task(task_id))
    assert fake.industry_arg == "47"


def test_execute_task_industry_none_when_unset(config, monkeypatch):
    init_db(config)
    fake = FakeScraper()
    fake.search_results = [PageResult(page_num=1, jobs=[JobDraft(job_id="j1", title="t1")])]
    _patch(monkeypatch, fake, config)
    task_id, _ = _seed_task(config.db_path)
    asyncio.run(task_runner.execute_task(task_id))
    assert fake.industry_arg is None
```

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run pytest backend/tests/test_playwright_scraper.py -k build_search_url -q` 与 `uv run pytest backend/tests/test_execute_task.py -q`
Expected: FAIL（`build_search_url` 不存在；`FakeScraper.search` 拒绝 industry 关键字参数）

- [ ] **Step 3: 实现**

`backend/app/scrapers/base.py` 抽象方法签名改为：

```python
    @abstractmethod
    async def search(
        self, keyword: str, pages: int, area: str = "000000", industry: str | None = None
    ) -> AsyncGenerator[PageResult, None]:
        """按关键字搜索职位。area 为 51job 城市编码（000000 = 全国）；industry 为逗号分隔行业编码（如 "08,46,47"，None=不过滤）。"""
        ...
```

`backend/app/scrapers/playwright.py`：
- 在 `_SEARCH_URL` 后新增纯函数：

```python
def build_search_url(
    keyword: str, page_num: int, area: str, industry: str | None = None
) -> str:
    url = _SEARCH_URL.format(kw=quote(keyword), n=page_num, area=area)
    if industry:
        url += f"&industry={quote(industry)}"
    return url
```

- `search()` 中两处 `_fetch_page` 调用（第 88、106、120、130 行）增加 `industry` 实参：
  `await self._fetch_page(page, keyword, n, area, industry)`
- `_fetch_page` 签名改为 `(self, page, keyword: str, page_num: int, area: str = "000000", industry: str | None = None)`，其中 URL 构造行 `url = _SEARCH_URL.format(...)` 替换为 `url = build_search_url(keyword, page_num, area, industry)`。

`backend/app/services/task_runner.py`：
- `execute_task` 中 `kw_area = keyword.city if keyword else "000000"` 后加 `kw_industry = keyword.industry if keyword else None`
- 第 65 行改为 `async for result in scraper.search(kw_text, max_pages, area=kw_area, industry=kw_industry):`

更新 `test_playwright_scraper.py` 中被 `search()` 复用的 `_fetch_page` 桩签名（`_seq_fetch` 与 `_counting_fetch` 的内层 `fetch` 函数）为 `(page, keyword, n, area="000000", industry=None)`。

- [ ] **Step 4: 运行测试确认通过**

Run: `uv run pytest backend/tests/test_playwright_scraper.py backend/tests/test_execute_task.py -q`
Expected: 全部 PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/scrapers/base.py backend/app/scrapers/playwright.py backend/app/services/task_runner.py backend/tests/test_playwright_scraper.py backend/tests/test_execute_task.py
git commit -m "feat: 抓取支持 industry 筛选（URL 参数 + 透传）"
```

---

### Task 4: 前端行业树 utils + 测试

**Files:**
- Create: `frontend/src/utils/industries.ts`
- Create: `frontend/tests/industries.test.ts`

**Interfaces:**
- Consumes: 官方行业树（见 `docs/superpowers/specs/2026-08-13-industry-filter-design.md`，11 顶级 ~50 子项）。
- Produces: `INDUSTRY_TREE: IndustryOption[]`（`{value, label, children?}`）、`industryNames(codes: string | null | undefined): string`（逗号分隔编码 → "、" 拼接名称；空 → `-`；未知编码原样显示）。

- [ ] **Step 1: 写失败测试**（`frontend/tests/industries.test.ts`）

```ts
import { describe, expect, it } from 'vitest'
import { INDUSTRY_TREE, industryNames } from '@/utils/industries'

describe('INDUSTRY_TREE', () => {
  it('包含制药/医疗及其子行业', () => {
    const pharm = INDUSTRY_TREE.find((n) => n.value === '08')
    expect(pharm?.label).toBe('制药/医疗')
    expect(pharm?.children?.map((c) => c.value)).toContain('47')
  })
})

describe('industryNames', () => {
  it('多编码按顿号拼接名称', () => {
    expect(industryNames('08,46,47')).toBe('制药/生物工程、医疗/护理/卫生、医疗设备/器械')
  })
  it('空值返回 -', () => {
    expect(industryNames(null)).toBe('-')
    expect(industryNames('')).toBe('-')
  })
  it('未知编码原样显示', () => {
    expect(industryNames('99')).toBe('99')
  })
})
```

- [ ] **Step 2: 运行测试确认失败**

Run: `npm run test`（或 `npx vitest run tests/industries.test.ts`，workdir `frontend/`）
Expected: FAIL（模块不存在）

- [ ] **Step 3: 实现 `frontend/src/utils/industries.ts`**

```ts
// 51job 行业字典（来源 https://js.51jobcdn.com/in/js/2023/dd/dd_industry.json）。
// 与 keyword.industry 字段对应：存叶子编码，逗号分隔。
export interface IndustryOption {
  value: string
  label: string
  children?: IndustryOption[]
}

export const INDUSTRY_TREE: IndustryOption[] = [
  {
    value: '01',
    label: '计算机/互联网/通信/电子',
    children: [
      { value: '01', label: '计算机软件' },
      { value: '37', label: '计算机硬件' },
      { value: '38', label: '计算机服务(系统、数据服务、维修)' },
      { value: '31', label: '通信/电信/网络设备' },
      { value: '39', label: '通信/电信运营、增值服务' },
      { value: '32', label: '互联网/电子商务' },
      { value: '40', label: '网络游戏' },
      { value: '02', label: '电子技术/半导体/集成电路' },
      { value: '35', label: '仪器仪表/工业自动化' },
    ],
  },
  {
    value: '41',
    label: '会计/金融/银行/保险',
    children: [
      { value: '41', label: '会计/审计' },
      { value: '03', label: '金融/投资/证券' },
      { value: '42', label: '银行' },
      { value: '43', label: '保险' },
      { value: '62', label: '信托/担保/拍卖/典当' },
    ],
  },
  {
    value: '04',
    label: '贸易/消费/制造/营运',
    children: [
      { value: '04', label: '贸易/进出口' },
      { value: '22', label: '批发/零售' },
      { value: '05', label: '快速消费品(食品、饮料、化妆品)' },
      { value: '06', label: '服装/纺织/皮革' },
      { value: '44', label: '家具/家电/玩具/礼品' },
      { value: '60', label: '奢侈品/收藏品/工艺品/珠宝' },
      { value: '45', label: '办公用品及设备' },
      { value: '14', label: '机械/设备/重工' },
      { value: '33', label: '汽车' },
      { value: '65', label: '汽车零配件' },
    ],
  },
  {
    value: '08',
    label: '制药/医疗',
    children: [
      { value: '08', label: '制药/生物工程' },
      { value: '46', label: '医疗/护理/卫生' },
      { value: '47', label: '医疗设备/器械' },
    ],
  },
  {
    value: '12',
    label: '广告/媒体',
    children: [
      { value: '12', label: '广告' },
      { value: '48', label: '公关/市场推广/会展' },
      { value: '49', label: '影视/媒体/艺术/文化传播' },
      { value: '13', label: '文字媒体/出版' },
      { value: '15', label: '印刷/包装/造纸' },
    ],
  },
  {
    value: '26',
    label: '房地产/建筑',
    children: [
      { value: '26', label: '房地产' },
      { value: '09', label: '建筑/建材/工程' },
      { value: '50', label: '家居/室内设计/装潢' },
      { value: '51', label: '物业管理/商业中心' },
      { value: '34', label: '中介服务' },
      { value: '63', label: '租赁服务' },
    ],
  },
  {
    value: '07',
    label: '专业服务/教育/培训',
    children: [
      { value: '07', label: '专业服务(咨询、人力资源、财会)' },
      { value: '59', label: '外包服务' },
      { value: '52', label: '检测，认证' },
      { value: '18', label: '法律' },
      { value: '23', label: '教育/培训/院校' },
      { value: '24', label: '学术/科研' },
    ],
  },
  {
    value: '11',
    label: '服务业',
    children: [
      { value: '11', label: '餐饮业' },
      { value: '53', label: '酒店/旅游' },
      { value: '17', label: '娱乐/休闲/体育' },
      { value: '54', label: '美容/保健' },
      { value: '27', label: '生活服务' },
    ],
  },
  {
    value: '21',
    label: '物流/运输',
    children: [
      { value: '21', label: '交通/运输/物流' },
      { value: '55', label: '航天/航空' },
    ],
  },
  {
    value: '19',
    label: '能源/环保/化工',
    children: [
      { value: '19', label: '石油/化工/矿产/地质' },
      { value: '16', label: '采掘业/冶炼' },
      { value: '36', label: '电气/电力/水利' },
      { value: '61', label: '新能源' },
      { value: '56', label: '原材料和加工' },
      { value: '20', label: '环保' },
    ],
  },
  {
    value: '28',
    label: '政府/非营利组织/其他',
    children: [
      { value: '28', label: '政府/公共事业' },
      { value: '57', label: '非营利组织' },
      { value: '29', label: '农/林/牧/渔' },
      { value: '58', label: '多元化业务集团公司' },
    ],
  },
]

const INDUSTRY_NAME_MAP: Record<string, string> = (() => {
  const m: Record<string, string> = {}
  const walk = (nodes: IndustryOption[]) => {
    for (const n of nodes) {
      m[n.value] = n.label
      if (n.children?.length) walk(n.children)
    }
  }
  walk(INDUSTRY_TREE)
  return m
})()

export function industryNames(codes: string | null | undefined): string {
  if (!codes) return '-'
  return codes
    .split(',')
    .map((c) => INDUSTRY_NAME_MAP[c.trim()] ?? c.trim())
    .join('、')
}
```

- [ ] **Step 4: 运行测试确认通过**

Run: `npm run test`（workdir `frontend/`）
Expected: 全部 PASS（23 项既有 + 3 项新增）

- [ ] **Step 5: Commit**

```bash
git add frontend/src/utils/industries.ts frontend/tests/industries.test.ts
git commit -m "feat: 前端行业树与名称映射工具"
```

---

### Task 5: 关键字管理 UI（api 类型 + 表格列 + 弹窗级联）

**Files:**
- Modify: `frontend/src/api/keywords.ts`
- Modify: `frontend/src/views/Tasks.vue`

**Interfaces:**
- Consumes: `INDUSTRY_TREE`、`industryNames`（Task 4）；后端 `KeywordOut.industry`（Task 2）。
- Produces: `KeywordOut.industry: string | null`；create/update 参数含 `industry?: string | null`；Tasks.vue 表格"行业"列 + 弹窗 el-cascader 多选（`emitPath: false`、`limit: 5`）。

- [ ] **Step 1: 改 api 类型**（`frontend/src/api/keywords.ts`）

```ts
export interface KeywordOut {
  id: number
  keyword: string
  city: string
  enabled: boolean
  scrape_mode: string
  industry: string | null
  last_scraped_at: string | null
  created_at: string
}

export const keywordsApi = {
  list: () => http.get<KeywordOut[]>('/keywords').then((r) => r.data),
  create: (data: { keyword: string; scrape_mode?: string; city?: string; industry?: string | null }) =>
    http.post<KeywordOut>('/keywords', data).then((r) => r.data),
  update: (id: number, data: { keyword?: string; scrape_mode?: string; city?: string; industry?: string | null }) =>
    http.put<KeywordOut>(`/keywords/${id}`, data).then((r) => r.data),
  remove: (id: number) => http.delete(`/keywords/${id}`),
  toggle: (id: number) => http.post<KeywordOut>(`/keywords/${id}/toggle`).then((r) => r.data),
}
```

- [ ] **Step 2: 改 Tasks.vue**

模板部分：
- 关键字表格"地区"列之后加：

```html
            <el-table-column label="行业筛选" min-width="150">
              <template #default="{ row }">{{ industryNames(row.industry) }}</template>
            </el-table-column>
```

- 关键字弹窗"抓取方式"之前加：

```html
        <el-form-item label="行业筛选">
          <el-cascader
            v-model="keywordDialog.industry"
            :options="INDUSTRY_TREE"
            :props="{ multiple: true, emitPath: false, limit: 5, collapseTags: true }"
            clearable
            style="width: 100%"
            placeholder="不限（最多 5 个）"
          />
        </el-form-item>
```

脚本部分：
- import 加 `import { INDUSTRY_TREE, industryNames } from '@/utils/industries'`
- `keywordDialog` 加 `industry: [] as string[]`
- `openCreate()` 加 `keywordDialog.industry = []`
- `openEdit(row)` 加 `keywordDialog.industry = row.industry ? row.industry.split(',') : []`
- `saveKeyword()` 的 create/update 数据加 `industry: keywordDialog.industry.length ? keywordDialog.industry.join(',') : null`

- [ ] **Step 3: 验证**

Run（workdir `frontend/`）: `npm run type-check`
Expected: 无类型错误
Run: `npm run test`
Expected: 全部 PASS
Run: `npm run build`
Expected: 构建成功

- [ ] **Step 4: Commit**

```bash
git add frontend/src/api/keywords.ts frontend/src/views/Tasks.vue
git commit -m "feat: 关键字管理支持行业筛选（多选级联）"
```

---

### Task 6: PRD 文档更新

**Files:**
- Modify: `docs/PRD.md`

- [ ] **Step 1: 更新 PRD**

- §4 keywords 表：在 `scrape_mode` 后加 `industry(逗号分隔行业编码，NULL=不过滤)`；在"说明"中补充：industry 为 51job 行业字典叶子编码（如 47=医疗设备/器械），空串与 NULL 均视为不过滤；唯一约束仍为 (keyword, city)。
- §5 关键字 API：POST 支持 `industry`（可选，逗号分隔 ≤5 个）、PUT 支持更新/置空；GET 返回 industry。
- §6 抓取模块：搜索 URL 增加 `industry` 参数说明（SPA 读取 URL 参数，翻页保持）。

- [ ] **Step 2: 复核一致性**

Run: `uv run pytest backend/tests -q`
Expected: 全部 PASS（含新增）
Run（workdir `frontend/`）: `npm run type-check && npm run test`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add docs/PRD.md
git commit -m "docs: PRD 补充行业筛选字段与 URL 参数"
```
