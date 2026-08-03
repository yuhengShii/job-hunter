# 职位分布统计 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 统计看板新增「职位分布」：后端新增 `/api/stats/distribution` 统计接口（按城市，或指定城市后按区），前端新增职位分布柱状图卡片（城市选择器联动）。

**Architecture:** 后端在现有 `stats.py` 窗口统计体系上新增 `distribution_stats`（复用 `get_window_start`/`_windowed_jobs`），路由与现有统计接口同构；前端 `api/stats.ts` 加封装，`Stats.vue` 新增整行卡片 + 城市选择器（选项取自全部城市视图响应）。

**Tech Stack:** Python 3.14 + FastAPI + SQLAlchemy；Vue3 + ECharts（沿用 useChart）。

## Global Constraints

- 唯一权威需求：`docs/PRD.md`；实现严格对齐 spec `docs/superpowers/specs/2026-08-02-job-distribution-design.md`。
- 统计口径：一律基于最近一次成功/部分成功任务 `start_time` 窗口（`jobs.updated_at >= start_time`）。
- 空值（city/district 为 NULL/空串）→ 归入 `"未知"`，与 salary_stats 兜底一致；items 按 count 降序。
- 路由只做校验与响应组装；响应为裸 dict（与现有 stats 接口一致，不走 Pydantic schema）。
- 前端：组件不直接发请求走 `api/` 封装；页面/组件不新增自动化测试；`statsApi` 命名与现有风格一致。
- 验收命令：仓库根 `$env:PYTHONUTF8 = "1"; uv run pytest backend/tests`；frontend/ 下 `npm run type-check`、`npm run test`（23 项保持绿）、`npm run build`。
- 提交信息沿用仓库风格（`feat:` + 中文描述）；分支 `feat/job-distribution`。
- 测试禁止访问真实 51job。

---

### Task 1: 后端 distribution 统计接口 + pytest

**Files:**
- Modify: `backend/app/services/stats.py`
- Modify: `backend/app/api/stats.py`
- Test: `backend/tests/test_stats.py`、`backend/tests/test_stats_api.py`（若无此文件则新建 `test_stats_api.py`；已有 `test_stats.py` 检查后追加或新建）

**Interfaces:**
- Consumes: 现有 `get_window_start(db, keyword_id)`、`_windowed_jobs(db, window)`、`_counts` 模式。
- Produces: `distribution_stats(db: Session, window: datetime | None, city: str | None = None) -> dict`（返回 `{"city": city|None, "items": [{"key", "count"}]}`，降序）；路由 `GET /api/stats/distribution?keyword_id=&city=`（JWT）。

- [ ] **Step 1: 写失败测试**

在 `backend/tests/test_stats.py` 追加（先用 grep 确认该文件现有内容与 fixture 模式，conftest 已提供 db session fixture；若 test_stats.py 已有 build_stats 等辅助函数则复用）：
```python
def test_distribution_by_city(db, sample_jobs):
    from datetime import datetime, timedelta
    from backend.app.models import Job
    base = datetime.now() - timedelta(days=30)
    db.add_all([
        Job(job_id="d1", title="t", city="上海", district="浦东新区", updated_at=base + timedelta(hours=1)),
        Job(job_id="d2", title="t", city="上海", district="闵行区", updated_at=base + timedelta(hours=2)),
        Job(job_id="d3", title="t", city="北京", district="海淀区", updated_at=base + timedelta(hours=3)),
        Job(job_id="d4", title="t", city=None, district=None, updated_at=base + timedelta(hours=4)),
        Job(job_id="d5", title="t", city="上海", district=None, updated_at=base - timedelta(days=1)),
    ])
    db.commit()
    from backend.app.services import stats as stats_service
    res = stats_service.distribution_stats(db, base)
    by_key = {i["key"]: i["count"] for i in res["items"]}
    assert res["city"] is None
    assert by_key == {"上海": 2, "北京": 1, "未知": 1}
    # 窗口过滤：窗口外的 d5 不计入
    assert "上海" not in [i["key"] for i in res["items"]] or by_key["上海"] == 2
```
（窗口过滤断言以 d5 排除为准：d5 的 updated_at 早于 base，不计入。）

```python
def test_distribution_by_district(db):
    from datetime import datetime, timedelta
    from backend.app.models import Job
    from backend.app.services import stats as stats_service
    base = datetime.now() - timedelta(days=30)
    db.add_all([
        Job(job_id="e1", title="t", city="上海", district="浦东新区", updated_at=base + timedelta(hours=1)),
        Job(job_id="e2", title="t", city="上海", district="闵行区", updated_at=base + timedelta(hours=2)),
        Job(job_id="e3", title="t", city="上海", district=None, updated_at=base + timedelta(hours=3)),
        Job(job_id="e4", title="t", city="北京", district="海淀区", updated_at=base + timedelta(hours=4)),
    ])
    db.commit()
    res = stats_service.distribution_stats(db, base, city="上海")
    by_key = {i["key"]: i["count"] for i in res["items"]}
    assert res["city"] == "上海"
    assert by_key == {"浦东新区": 1, "闵行区": 1, "未知": 1}
    assert "海淀区" not in by_key
    counts = [i["count"] for i in res["items"]]
    assert counts == sorted(counts, reverse=True)
```

API 测试（`backend/tests/test_stats_api.py` 新建，参考现有 API 测试的 auth fixture 模式——先 grep `test_tasks_api.py`/`test_stats.py` 中如何获取 token 与 client）：
```python
def test_distribution_api(client, auth_headers):
    resp = client.get("/api/stats/distribution", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "city" in data and "items" in data


def test_distribution_api_requires_auth(client):
    resp = client.get("/api/stats/distribution")
    assert resp.status_code == 401
```

- [ ] **Step 2: 运行测试确认失败**

Run（仓库根，先 `$env:PYTHONUTF8 = "1"`）: `uv run pytest backend/tests/test_stats.py backend/tests/test_stats_api.py -q`
Expected: FAIL（`distribution_stats` 不存在 / 路由 404）。

- [ ] **Step 3: 实现服务函数与路由**

`backend/app/services/stats.py` 末尾追加：
```python
def distribution_stats(db: Session, window: datetime | None, city: str | None = None) -> dict:
    jobs = _windowed_jobs(db, window).all()
    counter: Counter = Counter()
    for j in jobs:
        if city is None:
            key = j.city
        else:
            if j.city != city:
                continue
            key = j.district
        counter[key or "未知"] += 1
    items = [{"key": k, "count": n} for k, n in counter.most_common()]
    return {"city": city, "items": items}
```

`backend/app/api/stats.py` 追加（现有路由之后）：
```python
@stats_router.get("/distribution")
def get_distribution(keyword_id: int | None = None, city: str | None = None, db=Depends(get_db), user=Depends(get_current_user)):
    window = stats_service.get_window_start(db, keyword_id)
    return stats_service.distribution_stats(db, window, city=city)
```

- [ ] **Step 4: 运行测试确认通过**

Run（仓库根）: `uv run pytest backend/tests -q`
Expected: 全部 PASS（原 63 项 + 新增 ≥4 项）。

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/stats.py backend/app/api/stats.py backend/tests/test_stats.py backend/tests/test_stats_api.py
git commit -m "feat: job distribution stats endpoint"
```

---

### Task 2: 前端职位分布卡片

**Files:**
- Modify: `frontend/src/api/stats.ts`
- Modify: `frontend/src/views/Stats.vue`

**Interfaces:**
- Consumes: Task 1 的 `GET /api/stats/distribution`（`{"city": city|null, "items": [{"key","count"}]}`）；现有 `statsApi`、`useChart`、`useKeywordsStore`、页面 `keywordId` ref。
- Produces: `statsApi.distribution(keyword_id?, city?)`；Stats.vue「职位分布」卡片（header 城市选择器 + 柱状图，与 keywordId 联动）。

- [ ] **Step 1: 扩展 api/stats.ts**

`frontend/src/api/stats.ts` 追加类型与方法：
```ts
export interface DistributionItem {
  key: string
  count: number
}

export interface DistributionResult {
  city: string | null
  items: DistributionItem[]
}
```
`statsApi` 对象内追加：
```ts
  distribution: (keyword_id?: number | null, city?: string | null) =>
    http.get<DistributionResult>('/stats/distribution', { params: { keyword_id, city } }).then((r) => r.data),
```

- [ ] **Step 2: Stats.vue 新增职位分布卡片**

`frontend/src/views/Stats.vue`：
- template：在薪资分布 `el-card` 之后、`<el-row class="charts-row">`（公司画像）之前插入：
```html
    <el-card class="chart-card">
      <template #header>
        <div class="chart-header">
          <span>职位分布{{ distCity ? `（${distCity}）` : '（按城市）' }}</span>
          <el-select v-model="distCity" placeholder="全部城市" clearable style="width: 160px" @change="loadDistribution">
            <el-option v-for="c in distCityOptions" :key="c" :label="c" :value="c" />
          </el-select>
        </div>
      </template>
      <div ref="distEl" class="chart" />
    </el-card>
```
- script：
  - 新增 ref 与数据：
```ts
const distEl = ref<HTMLElement | null>(null)
const distCity = ref<string | null>(null)
const distCityOptions = ref<string[]>([])
const dist = ref<DistributionResult | null>(null)
```
  - import 增加 `type DistributionResult`；`import { statsApi, type CompanyStats, type SalaryStats, type DistributionResult } from '@/api/stats'`
  - option 计算属性：
```ts
const distOption = computed<EChartsOption>(() => ({
  tooltip: { trigger: 'axis' },
  grid: { left: 90, right: 24, top: 40, bottom: 80 },
  xAxis: { type: 'category', data: (dist.value?.items ?? []).map((i) => i.key), axisLabel: { interval: 0, rotate: 30 } },
  yAxis: { type: 'value', name: '职位数' },
  series: [{ type: 'bar', data: (dist.value?.items ?? []).map((i) => i.count), barMaxWidth: 40 }],
}))
useChart(distEl, distOption)
```
  - 加载函数：
```ts
async function loadDistribution() {
  dist.value = await statsApi.distribution(keywordId.value, distCity.value)
  if (!distCity.value) {
    distCityOptions.value = (dist.value?.items ?? []).map((i) => i.key).filter((k) => k !== '未知')
  }
}
```
  - `reload()` 的 `Promise.all` 中追加 `statsApi.distribution(kw, distCity.value)` 并赋值 dist（同时保持选择器选项同步——全部城市视图时更新 distCityOptions；放在 reload 里统一处理，loadDistribution 保留给 @change 单独调用）。`onMounted` 不变。

- [ ] **Step 3: 验证**

Run（frontend/）: `npm run type-check` → 无错误。
Run（frontend/）: `npm run test` → 23 项全绿。
Run（frontend/）: `npm run build` → 成功。
手动冒烟（后端运行 + 已有数据）：默认「全部城市」柱状图（上海/远程办公…）；选「上海」→ 各区柱状图（浦东新区…）；顶部关键字筛选切换后分布卡片联动刷新；空数据不报错。

- [ ] **Step 4: Commit**

```bash
git add frontend/src/api/stats.ts frontend/src/views/Stats.vue
git commit -m "feat: frontend job distribution chart"
```

---

## Self-Review 记录

- **Spec 覆盖**：spec §2.1 服务函数（Task 1）、§2.2 路由（Task 1）、§2.3 响应形态（Task 1/2 契约一致）、§3.1 api 封装（Task 2）、§3.2 卡片与联动（Task 2）、§4 测试（Task 1 pytest + Task 2 验证）、§5 验收（Task 1/2 验证步骤）。无遗漏。
- **占位符扫描**：Task 1 测试代码需按既有 fixture 模式微调（conftest fixture 名与 auth fixture 以现有测试为准，brief 已注明先 grep 再写），其余含完整代码。
- **类型一致性**：`DistributionResult`/`DistributionItem` 与后端响应 `{"city": city|null, "items": [{"key","count"}]}` 一致；`statsApi.distribution(keyword_id, city)` 参数顺序与现有 `statsApi.salary(keyword_id, group_by)` 风格一致；`distCity`/`distCityOptions`/`distEl`/`distOption` 命名在 Task 2 内自洽。
- **已知取舍**：城市选择器选项仅在「全部城市」视图刷新时更新（选城市后不更新选项，切换回全部城市时刷新）——简单且满足需求；`未知` 城市名不出现在选择器选项（该桶是 null 兜底，不可作为筛选目标）。
