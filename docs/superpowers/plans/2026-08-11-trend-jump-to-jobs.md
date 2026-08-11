# 发布时间趋势跳转职位列表 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 统计看板发布时间趋势图（热力图/折线图）点击后弹出关键字确认框，跳转职位列表并按日期+地区筛选。

**Architecture:** 后端 `GET /api/jobs` 增加 `area` 精确匹配参数；前端 Stats.vue 绑定图表 click 事件 + 弹窗 + `router.push` 携带 query；Jobs.vue 从 route.query 初始化筛选（抽纯函数 `jobsStateFromRoute` 便于单测）。

**Tech Stack:** FastAPI / SQLAlchemy / Vue3 / ECharts / Vitest / pytest

## Global Constraints

- 遵循 `docs/code-style.md`：路由只做校验与响应组装；`schemas/` 禁止暴露 ORM；统计口径不动
- 时间字段一律 datetime/`YYYY-MM-DD` 字符串；趋势图日期格式 `date.isoformat()`（如 `2026-08-11`）
- 中文输出命令前设 `$env:PYTHONUTF8 = "1"`
- 前端测试在 `frontend/tests/`（vitest），后端测试在 `backend/tests/`（pytest，禁真实 51job）
- 每任务末尾 git commit
- 设计文档：`docs/superpowers/specs/2026-08-11-trend-jump-to-jobs-design.md`

---

### Task 0: 保存设计文档与计划

**Files:**
- Create: `docs/superpowers/specs/2026-08-11-trend-jump-to-jobs-design.md`
- Create: `docs/superpowers/plans/2026-08-11-trend-jump-to-jobs.md`（本文件）

- [ ] **Step 1: 写设计文档**（见 spec 文件，内容已批准）
- [ ] **Step 2: 写本计划文件**
- [ ] **Step 3: Commit**

```bash
git add docs/superpowers/
git commit -m "docs: 发布时间趋势跳转职位列表设计与计划"
```

### Task 1: 后端 area 筛选

**Files:**
- Modify: `backend/app/api/jobs.py`（`list_jobs` 签名与过滤体）
- Test: `backend/tests/test_jobs_api.py`

**Interfaces:**
- Produces: `GET /api/jobs?area=<str>` 精确匹配 `Job.area`；不传时行为不变。

- [ ] **Step 1: 写失败测试**

在 `test_jobs_api.py` 的 `test_filter_by_district` 后新增：

```python
def test_filter_by_area(client):
    resp = client.get("/api/jobs", params={"area": "长宁区"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["items"][0]["job_id"] == "j1"
    resp = client.get("/api/jobs", params={"area": "不存在的地区"})
    assert resp.json()["total"] == 0
    resp = client.get("/api/jobs", params={"area": "长宁区", "publish_time_from": "2024-03-02"})
    assert resp.json()["total"] == 0
```

- [ ] **Step 2: 运行确认失败**

Run: `cd backend; uv run pytest tests/test_jobs_api.py::test_filter_by_area -v`
Expected: FAIL（area 参数被忽略，total=6 / 422）

- [ ] **Step 3: 实现**

`list_jobs` 参数区加 `area: str | None = None,`（`district` 参数之后），过滤体加：

```python
    if area:
        q = q.filter(Job.area == area)
```

- [ ] **Step 4: 运行确认通过**

Run: `cd backend; uv run pytest tests/test_jobs_api.py -q`
Expected: PASS（全部 test_jobs_api 用例）

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/jobs.py backend/tests/test_jobs_api.py
git commit -m "feat: jobs api 支持 area 筛选"
```

### Task 2: 前端 JobQuery + 职位页地区输入框

**Files:**
- Modify: `frontend/src/api/jobs.ts`
- Modify: `frontend/src/views/Jobs.vue`

**Interfaces:**
- Consumes: `JobQuery.area`（本任务新增）
- Produces: `query.area: string` 输入框；`load()` 组 `params.area`

- [ ] **Step 1: JobQuery 增加 area**

`frontend/src/api/jobs.ts` `JobQuery` 接口在 `district?: string` 后加：

```ts
  area?: string
```

- [ ] **Step 2: Jobs.vue 新增地区输入框**

筛选栏「公司」form-item 之前加：

```html
        <el-form-item label="地区">
          <el-input v-model="query.area" clearable placeholder="如 上海-长宁区" style="width: 160px" @keyup.enter="search" />
        </el-form-item>
```

`query` reactive 对象加 `area: ''`（`district` 后）；`load()` 中 `if (query.district) params.district = query.district` 之后加 `if (query.area) params.area = query.area`；`reset()` 加 `query.area = ''`（`query.district = ''` 之后）。

- [ ] **Step 3: 类型检查**

Run: `cd frontend; npm run type-check`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add frontend/src/api/jobs.ts frontend/src/views/Jobs.vue
git commit -m "feat(jobs): 职位列表新增地区筛选"
```

### Task 3: jobsStateFromRoute 纯函数（TDD）

**Files:**
- Create: `frontend/src/utils/jobsQuery.ts`
- Test: `frontend/tests/jobsQuery.test.ts`

**Interfaces:**
- Produces: `jobsStateFromRoute(query: Record<string, unknown>): JobsRouteState`

```ts
export interface JobsRouteState {
  city: string
  district: string
  area: string
  keyword: string
  publishRange: [string, string] | null
}
```

- [ ] **Step 1: 写失败测试**

```ts
import { describe, expect, it } from 'vitest'
import { jobsStateFromRoute } from '@/utils/jobsQuery'

describe('jobsStateFromRoute', () => {
  it('完整参数映射', () => {
    expect(
      jobsStateFromRoute({
        city: '上海',
        district: '长宁区',
        area: '上海-长宁区',
        keyword: 'Python',
        publish_time_from: '2026-08-01',
        publish_time_to: '2026-08-01',
      }),
    ).toEqual({
      city: '上海',
      district: '长宁区',
      area: '上海-长宁区',
      keyword: 'Python',
      publishRange: ['2026-08-01', '2026-08-01'],
    })
  })
  it('日期缺失或非法返回 null', () => {
    expect(
      jobsStateFromRoute({ publish_time_from: '2026-08-01' }).publishRange,
    ).toBeNull()
    expect(
      jobsStateFromRoute({ publish_time_from: 'bad', publish_time_to: '2026-08-01' }).publishRange,
    ).toBeNull()
  })
  it('空对象返回全空', () => {
    expect(jobsStateFromRoute({})).toEqual({
      city: '',
      district: '',
      area: '',
      keyword: '',
      publishRange: null,
    })
  })
})
```

- [ ] **Step 2: 运行确认失败**

Run: `cd frontend; npm run test -- jobsQuery`
Expected: FAIL（模块不存在）

- [ ] **Step 3: 实现**

```ts
export interface JobsRouteState {
  city: string
  district: string
  area: string
  keyword: string
  publishRange: [string, string] | null
}

const DATE_RE = /^\d{4}-\d{2}-\d{2}$/

export function jobsStateFromRoute(query: Record<string, unknown>): JobsRouteState {
  const str = (k: string) => (typeof query[k] === 'string' ? (query[k] as string) : '')
  const from = str('publish_time_from')
  const to = str('publish_time_to')
  return {
    city: str('city'),
    district: str('district'),
    area: str('area'),
    keyword: str('keyword'),
    publishRange: DATE_RE.test(from) && DATE_RE.test(to) ? [from, to] : null,
  }
}
```

- [ ] **Step 4: 运行确认通过**

Run: `cd frontend; npm run test -- jobsQuery`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/utils/jobsQuery.ts frontend/tests/jobsQuery.test.ts
git commit -m "feat: route query 转职位筛选状态纯函数"
```

### Task 4: 职位页读取 route.query

**Files:**
- Modify: `frontend/src/views/Jobs.vue`

**Interfaces:**
- Consumes: `jobsStateFromRoute`（Task 3）
- Produces: onMounted 时按 route.query 初始化筛选；reset 清 URL query

- [ ] **Step 1: 引入依赖与初始化逻辑**

`<script setup>` 顶部：

```ts
import { useRoute, useRouter } from 'vue-router'
import { jobsStateFromRoute } from '@/utils/jobsQuery'

const route = useRoute()
const router = useRouter()
```

`onMounted` 改为：

```ts
onMounted(() => {
  const s = jobsStateFromRoute(route.query as Record<string, unknown>)
  query.city = s.city
  query.district = s.district
  query.area = s.area
  query.keyword = s.keyword
  publishRange.value = s.publishRange
  loadFilterOptions()
  load()
})
```

`reset()` 末尾（`search()` 之前或之后均可）加：

```ts
  router.replace({ path: '/jobs' })
```

- [ ] **Step 2: 类型检查**

Run: `cd frontend; npm run type-check`
Expected: PASS

- [ ] **Step 3: 手动冒烟**

启动后端 `$env:PYTHONUTF8="1"; uv run uvicorn backend.app.main:app` 与前端 dev（或构建后经后端托管），浏览器访问 `http://localhost:5173/jobs?city=%E4%B8%8A%E6%B5%B7&publish_time_from=2026-08-01&publish_time_to=2026-08-01&keyword=Python`，确认筛选自动生效；点「重置」后 URL query 被清空。

- [ ] **Step 4: Commit**

```bash
git add frontend/src/views/Jobs.vue
git commit -m "feat(jobs): 从 route query 初始化筛选"
```

### Task 5: 统计页趋势点击 + 弹窗跳转

**Files:**
- Modify: `frontend/src/views/Stats.vue`

**Interfaces:**
- Consumes: 现有 `trend.value`（`days`/`series`）、`groupBy`、`keywordsStore.list`、`keywordId`
- Produces: 图表 click → 弹窗 → `router.push({ path: '/jobs', query })`

- [ ] **Step 1: 弹窗模板与状态**

`<template>` 在最后（`</div>` 前）加：

```html
    <el-dialog v-model="jumpVisible" title="跳转职位列表" width="420px">
      <div class="jump-summary">
        <div>时间：{{ jumpDate }}</div>
        <div v-if="jumpRegion">地区：{{ jumpRegion }}</div>
      </div>
      <el-input v-model="jumpKeyword" placeholder="关键字（留空则不过滤）" clearable style="margin-top: 12px" />
      <template #footer>
        <el-button @click="jumpVisible = false">取消</el-button>
        <el-button type="primary" @click="jumpToJobs">确认跳转</el-button>
      </template>
    </el-dialog>
```

`<script setup>` 加：

```ts
import { useRouter } from 'vue-router'

const router = useRouter()
const jumpVisible = ref(false)
const jumpDate = ref('')
const jumpRegion = ref('')
const jumpKeyword = ref('')
```

- [ ] **Step 2: 绑定 click 事件**

`useChart(trendEl, trendOption)` 改为捕获实例并注册 click（在 `onMounted` 中，useChart 内部 onMounted 先于组件 onMounted 执行）：

```ts
const trendChart = useChart(trendEl, trendOption)
```

在 `onMounted` 中（现有 try 之前）加：

```ts
  trendChart.value?.on('click', (params: unknown) => {
    const p = params as { value?: [number, number, number]; dataIndex?: number }
    let date: string | null = null
    let region = ''
    if (trend.value?.series?.length) {
      const [xi, yi] = p.value as [number, number, number]
      const dates = (trend.value.series[0]?.points ?? []).map((pt) => pt.date)
      const keys = trend.value.series.map((s) => s.key)
      date = dates[xi] ?? null
      region = keys[yi] ?? ''
    } else {
      const days = trend.value?.days ?? []
      const idx = p.dataIndex ?? -1
      date = idx >= 0 ? (days[idx]?.date ?? null) : null
    }
    if (!date) return
    jumpDate.value = date
    jumpRegion.value = region
    const kw = keywordsStore.list.find((k) => k.id === keywordId.value)
    jumpKeyword.value = kw?.keyword ?? ''
    jumpVisible.value = true
  })
```

- [ ] **Step 3: 跳转逻辑**

```ts
function jumpToJobs() {
  const query: Record<string, string> = {
    publish_time_from: jumpDate.value,
    publish_time_to: jumpDate.value,
  }
  const gb = groupBy.value
  if (gb === 'city' && jumpRegion.value && jumpRegion.value !== '未知') query.city = jumpRegion.value
  else if (gb === 'district' && jumpRegion.value && jumpRegion.value !== '未知') query.district = jumpRegion.value
  else if (gb === 'area' && jumpRegion.value && jumpRegion.value !== '未知') query.area = jumpRegion.value
  const kw = jumpKeyword.value.trim()
  if (kw) query.keyword = kw
  jumpVisible.value = false
  router.push({ path: '/jobs', query })
}
```

注意：热力图聚合行 key 为 `其他`，groupBy 映射条件已排除 `未知`，`其他` 由 `jumpRegion.value !== '未知'` 之外还需排除——改为统一判断：

```ts
  const skip = !jumpRegion.value || jumpRegion.value === '未知' || jumpRegion.value === '其他'
  if (!skip && gb === 'city') query.city = jumpRegion.value
  else if (!skip && gb === 'district') query.district = jumpRegion.value
  else if (!skip && gb === 'area') query.area = jumpRegion.value
```

样式 `.jump-summary { line-height: 24px; color: var(--el-text-color-regular); }` 加入 `<style scoped>`。

- [ ] **Step 4: 类型检查 + 构建**

Run: `cd frontend; npm run type-check; npm run build`
Expected: PASS

- [ ] **Step 5: 手动冒烟**

按 groupBy 全部/按城市 切换后分别点击折线点与热力格子：弹窗出现、时间/地区正确、关键字默认值正确；确认后跳转 `/jobs` 且筛选生效；取消不跳转；关键字清空后跳转不带 keyword。

- [ ] **Step 6: Commit**

```bash
git add frontend/src/views/Stats.vue
git commit -m "feat(stats): 趋势图点击跳转职位列表"
```

### Task 6: 全量验证

- [ ] **Step 1: 后端全量**

Run: `cd backend; $env:PYTHONUTF8="1"; uv run pytest -q`
Expected: 全绿（原 107 + 新增）

- [ ] **Step 2: 前端全量**

Run: `cd frontend; npm run test; npm run type-check; npm run build`
Expected: 全绿（原 23 + 新增 3）

- [ ] **Step 3: 收尾**

`git status` 确认无遗留改动；如有则 commit。
