# 移动端适配 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 job-hunter 前端全部 5 个页面在手机（≤768px）上可用且体验良好，桌面端行为完全不变。

**Architecture:** 单代码库响应式改造：`useIsMobile` composable（matchMedia 768px）+ CSS 媒体查询；列表页 el-table 与卡片列表用 `v-if` 切换（数据/逻辑复用）；Layout 侧边栏移动端改 el-drawer；Jobs 筛选移动端改底部弹出抽屉；所有 el-dialog 移动端 92vw。

**Tech Stack:** Vue3 `<script setup>`、Element Plus（el-drawer/el-col 断点/el-checkbox）、vitest（jsdom）。

## Global Constraints

- 断点统一 768px（与 Element Plus `sm` 一致）：`useIsMobile` 用 `matchMedia('(max-width: 768px)')`。
- 桌面端（>768px）渲染与交互一律不变：不改表格列配置、不改 el-col 桌面 span、不改对话框宽度传参（全局 CSS 兜底）。
- 不新增依赖、不引入移动端 UI 库、不做 px→vw/rem 适配。
- 卡片与表格共享同一数据源与逻辑，禁止复制数据加载代码。
- 验证命令：`npm run type-check`、`npm run test`（vitest）、`npm run build`（含 type-check）。
- 提交信息风格：`feat(mobile): <中文描述>`。
- 设计文档：`docs/superpowers/specs/2026-08-13-mobile-responsive-design.md`（已提交，实现以它为准）。

---

### Task 1: useIsMobile composable + 单元测试

**Files:**
- Create: `frontend/src/composables/useIsMobile.ts`
- Test: `frontend/tests/useIsMobile.test.ts`

**Interfaces:**
- Produces: `useIsMobile(): Ref<boolean>` —— 组件挂载后为响应式布尔值；matchMedia 的 `change` 事件会更新它；在组件内调用时自动注册清理（卸载时移除监听）。

- [ ] **Step 1: 写失败测试**

`frontend/tests/useIsMobile.test.ts`（新建）：

```ts
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { useIsMobile } from '@/composables/useIsMobile'

type Listener = (e: { matches: boolean }) => void

function stubMatchMedia(initialMatches: boolean) {
  const listeners = new Set<Listener>()
  const mql = {
    matches: initialMatches,
    addEventListener: vi.fn((_type: string, cb: Listener) => {
      listeners.add(cb)
    }),
    removeEventListener: vi.fn((_type: string, cb: Listener) => {
      listeners.delete(cb)
    }),
  }
  vi.stubGlobal('matchMedia', vi.fn(() => mql))
  return { mql, listeners }
}

describe('useIsMobile', () => {
  beforeEach(() => {
    vi.unstubAllGlobals()
  })

  it('宽度 ≤768px 返回 true', () => {
    stubMatchMedia(true)
    expect(useIsMobile().value).toBe(true)
  })

  it('宽度 >768px 返回 false', () => {
    stubMatchMedia(false)
    expect(useIsMobile().value).toBe(false)
  })

  it('matchMedia change 事件更新状态', () => {
    const { listeners } = stubMatchMedia(false)
    const isMobile = useIsMobile()
    expect(isMobile.value).toBe(false)
    listeners.forEach((cb) => cb({ matches: true }))
    expect(isMobile.value).toBe(true)
  })

  it('查询字符串为 (max-width: 768px)', () => {
    const { mql } = stubMatchMedia(false)
    useIsMobile()
    expect(window.matchMedia).toHaveBeenCalledWith('(max-width: 768px)')
  })
})
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd frontend; npm run test -- --run tests/useIsMobile.test.ts`
Expected: FAIL（`Cannot find module '@/composables/useIsMobile'`）

- [ ] **Step 3: 实现 composable**

`frontend/src/composables/useIsMobile.ts`（新建）：

```ts
import { getCurrentInstance, onBeforeUnmount, ref } from 'vue'

const MOBILE_QUERY = '(max-width: 768px)'

export function useIsMobile() {
  const isMobile = ref(false)
  const mq = window.matchMedia(MOBILE_QUERY)
  isMobile.value = mq.matches
  const onChange = (e: MediaQueryListEvent) => {
    isMobile.value = e.matches
  }
  mq.addEventListener('change', onChange)
  if (getCurrentInstance()) {
    onBeforeUnmount(() => mq.removeEventListener('change', onChange))
  }
  return isMobile
}
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd frontend; npm run test -- --run tests/useIsMobile.test.ts`
Expected: PASS（4 项）

- [ ] **Step 5: 提交**

```bash
git add frontend/src/composables/useIsMobile.ts frontend/tests/useIsMobile.test.ts
git commit -m "feat(mobile): useIsMobile composable 与单元测试"
```

---

### Task 2: 全局移动端 CSS + Login 卡片宽度

**Files:**
- Create: `frontend/src/styles/mobile.css`
- Modify: `frontend/src/main.ts:6`（在 `import 'element-plus/dist/index.css'` 后加一行）
- Modify: `frontend/src/views/Login.vue:60`

**Interfaces:**
- Consumes: 无
- Produces: 全局兜底样式：移动端所有 `.el-dialog` 宽度 92vw、`.el-main` 内边距 10px。后续所有对话框任务依赖此兜底。

- [ ] **Step 1: 创建全局样式**

`frontend/src/styles/mobile.css`（新建）：

```css
/* 移动端全局适配（<=768px，与 useIsMobile 断点一致） */
@media (max-width: 768px) {
  /* el-dialog 的 width 由内联 --el-dialog-width 控制，需 !important 覆盖 */
  .el-dialog {
    --el-dialog-width: 92vw !important;
  }
  .el-main {
    padding: 10px;
  }
}
```

- [ ] **Step 2: main.ts 引入**

`frontend/src/main.ts`：在 `import 'element-plus/dist/index.css'` 之后新增一行：

```ts
import '@/styles/mobile.css'
```

- [ ] **Step 3: Login 卡片宽度响应式**

`frontend/src/views/Login.vue` 第 60 行：

```css
.login-card { width: 360px; }
```

改为：

```css
.login-card { width: min(92vw, 360px); }
```

- [ ] **Step 4: 验证**

Run: `cd frontend; npm run type-check`
Expected: PASS，无类型错误

- [ ] **Step 5: 提交**

```bash
git add frontend/src/styles/mobile.css frontend/src/main.ts frontend/src/views/Login.vue
git commit -m "feat(mobile): 全局移动端样式（对话框 92vw / main 内边距）与登录卡片适配"
```

---

### Task 3: Layout 抽屉式侧边栏

**Files:**
- Modify: `frontend/src/components/Layout.vue`（整文件重写）

**Interfaces:**
- Consumes: `useIsMobile()`（Task 1）
- Produces: 移动端汉堡按钮 + `el-drawer`（内含与侧边栏同一份菜单）；`el-aside` 仅在桌面显示。后续所有页面共用此外壳。

- [ ] **Step 1: 重写 Layout.vue**

`frontend/src/components/Layout.vue`（整文件替换为）：

```vue
<template>
  <el-container class="layout">
    <el-aside v-if="!isMobile" width="200px">
      <el-menu :default-active="$route.path" router>
        <el-menu-item v-for="item in menuItems" :key="item.path" :index="item.path">
          <el-icon><component :is="item.icon" /></el-icon>
          <span>{{ item.label }}</span>
        </el-menu-item>
      </el-menu>
    </el-aside>
    <el-container>
      <el-header class="layout-header">
        <div class="header-left">
          <el-button v-if="isMobile" class="menu-btn" text @click="drawerVisible = true">
            <el-icon :size="20"><Menu /></el-icon>
          </el-button>
          <span class="page-title">{{ $route.meta.title }}</span>
        </div>
        <el-dropdown @command="onCommand">
          <span class="user-name">{{ auth.username }}<el-icon><ArrowDown /></el-icon></span>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="logout">退出登录</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
      </el-header>
      <el-main><router-view /></el-main>
    </el-container>
    <el-drawer v-if="isMobile" v-model="drawerVisible" direction="ltr" size="200px" :with-header="false">
      <el-menu :default-active="$route.path" router @select="drawerVisible = false">
        <el-menu-item v-for="item in menuItems" :key="item.path" :index="item.path">
          <el-icon><component :is="item.icon" /></el-icon>
          <span>{{ item.label }}</span>
        </el-menu-item>
      </el-menu>
    </el-drawer>
  </el-container>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { Menu, Odometer, Files, OfficeBuilding, DataAnalysis, ArrowDown } from '@element-plus/icons-vue'
import { useAuthStore } from '@/stores/auth'
import { useIsMobile } from '@/composables/useIsMobile'

const router = useRouter()
const auth = useAuthStore()
const isMobile = useIsMobile()
const drawerVisible = ref(false)

const menuItems = [
  { path: '/tasks', icon: Odometer, label: '任务控制台' },
  { path: '/jobs', icon: Files, label: '职位列表' },
  { path: '/companies', icon: OfficeBuilding, label: '公司列表' },
  { path: '/stats', icon: DataAnalysis, label: '统计看板' },
]

function onCommand(cmd: string) {
  if (cmd === 'logout') {
    auth.logout()
    router.push('/login')
  }
}
</script>

<style scoped>
.layout { min-height: 100vh; }
.layout-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  border-bottom: 1px solid var(--el-border-color-light);
}
.header-left { display: flex; align-items: center; gap: 4px; }
.user-name { display: inline-flex; align-items: center; gap: 4px; cursor: pointer; }
</style>
```

注意：`ArrowDown`、`Menu` 等图标组件显式 import（原文件依赖全局注册，这里显式引入更稳妥，模板中 `<component :is="item.icon" />` 需要真实组件对象）。

- [ ] **Step 2: 验证**

Run: `cd frontend; npm run type-check; npm run test`
Expected: type-check PASS；vitest 现有用例 + useIsMobile 4 项全 PASS

- [ ] **Step 3: 提交**

```bash
git add frontend/src/components/Layout.vue
git commit -m "feat(mobile): Layout 移动端抽屉式侧边栏"
```

---

### Task 4: JobCard 移动端职位卡片组件

**Files:**
- Create: `frontend/src/components/JobCard.vue`

**Interfaces:**
- Consumes: `JobOut`（`frontend/src/api/jobs.ts`）、`formatSalaryRaw`/`formatTime`（`frontend/src/utils/format.ts`）
- Produces: props `{ job: JobOut; selectable?: boolean; selected?: boolean }`；emits `click`、`toggle-favorite`、`select: [boolean]`。Task 5 使用。

- [ ] **Step 1: 创建 JobCard.vue**

`frontend/src/components/JobCard.vue`（新建）：

```vue
<template>
  <el-card class="job-card" :class="{ 'is-selected': selected }" shadow="hover" @click="emit('click')">
    <div class="job-card-header">
      <el-checkbox
        v-if="selectable"
        class="job-check"
        :model-value="selected"
        @click.stop
        @change="(v: string | number | boolean) => emit('select', Boolean(v))"
      />
      <span class="job-title">{{ job.title }}</span>
      <span class="job-salary">{{ formatSalaryRaw(job.salary_raw) }}</span>
    </div>
    <div class="job-card-company">
      <el-icon class="company-icon"><OfficeBuilding /></el-icon>
      <span class="company-name">{{ job.company_name ?? job.company_id ?? '-' }}</span>
      <el-button
        class="fav-btn"
        link
        :type="job.is_favorite ? 'warning' : 'info'"
        @click.stop="emit('toggle-favorite')"
      >
        <el-icon :size="16"><StarFilled v-if="job.is_favorite" /><Star v-else /></el-icon>
      </el-button>
    </div>
    <div class="job-card-meta">
      <span>{{ job.city ?? '-' }}{{ job.district ? ` · ${job.district}` : '' }}</span>
      <span v-if="job.degree || job.year">{{ job.degree ?? '-' }} · {{ job.year ?? '-' }}</span>
      <span v-if="job.company_activity">{{ job.company_activity }}</span>
      <span>{{ formatTime(job.publish_time) }}</span>
    </div>
    <div v-if="(job.tags ?? []).length" class="job-card-tags">
      <el-tag v-for="t in job.tags" :key="t" size="small" class="tag">{{ t }}</el-tag>
    </div>
  </el-card>
</template>

<script setup lang="ts">
import { Star, StarFilled, OfficeBuilding } from '@element-plus/icons-vue'
import type { JobOut } from '@/api/jobs'
import { formatSalaryRaw, formatTime } from '@/utils/format'

defineProps<{ job: JobOut; selectable?: boolean; selected?: boolean }>()
const emit = defineEmits<{ click: []; 'toggle-favorite': []; select: [boolean] }>()
</script>

<style scoped>
.job-card { margin-bottom: 10px; cursor: pointer; }
.job-card.is-selected { outline: 1px solid var(--el-color-primary); }
.job-card-header { display: flex; align-items: center; gap: 8px; }
.job-check { margin-right: 2px; }
.job-title {
  flex: 1;
  font-size: 15px;
  font-weight: 600;
  color: var(--el-text-color-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.job-salary { color: #f56c6c; font-weight: 600; white-space: nowrap; }
.job-card-company {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-top: 6px;
  color: var(--el-text-color-regular);
  font-size: 13px;
}
.company-icon { color: var(--el-text-color-secondary); }
.company-name { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.fav-btn { flex-shrink: 0; }
.job-card-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 4px 10px;
  margin-top: 6px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.job-card-tags { margin-top: 8px; }
.tag { margin-right: 4px; }
</style>
```

- [ ] **Step 2: 验证**

Run: `cd frontend; npm run type-check`
Expected: PASS

- [ ] **Step 3: 提交**

```bash
git add frontend/src/components/JobCard.vue
git commit -m "feat(mobile): JobCard 职位卡片组件"
```

---

### Task 5: JobFilters 组件抽取（桌面端行为不变）

**Files:**
- Create: `frontend/src/views/JobFilters.vue`
- Modify: `frontend/src/views/Jobs.vue`（只替换模板首部的 filter-card 区域与 script 中 query 定义/相关函数）

**Interfaces:**
- Consumes: `cityOptions`/`districtOptions`（Jobs.vue 现有 ref）
- Produces:
  - `export interface JobFilterState`（含 `publishRange` 字段）
  - `export function createDefaultJobFilterState(): JobFilterState`
  - `<JobFilters mode="inline"|"stack" :state :city-options :district-options @search @reset @city-change />` —— state 为父级 reactive 对象，组件内直接修改其属性（Vue 对对象属性修改合法）；`stack` 模式下控件宽度 100%、label 置顶，`inline` 模式完全复刻现有桌面内联表单。

- [ ] **Step 1: 创建 JobFilters.vue**

`frontend/src/views/JobFilters.vue`（新建）：

```vue
<template>
  <el-form
    :inline="mode === 'inline'"
    :label-position="mode === 'stack' ? 'top' : undefined"
    @submit.prevent
  >
    <el-form-item label="关键字">
      <el-input
        v-model="state.keyword"
        clearable
        placeholder="职位/地区包含"
        :style="ctl('180px')"
        @keyup.enter="emit('search')"
      />
    </el-form-item>
    <el-form-item label="城市">
      <el-select
        v-model="state.city"
        clearable
        placeholder="全部"
        :style="ctl('140px')"
        @change="emit('city-change')"
      >
        <el-option v-for="c in cityOptions" :key="c" :label="c" :value="c" />
      </el-select>
    </el-form-item>
    <el-form-item label="区域">
      <el-select
        v-model="state.district"
        clearable
        placeholder="全部"
        :style="ctl('140px')"
        :disabled="districtOptions.length === 0"
        @change="emit('search')"
      >
        <el-option v-for="d in districtOptions" :key="d" :label="d" :value="d" />
      </el-select>
    </el-form-item>
    <el-form-item label="地区">
      <el-input
        v-model="state.area"
        clearable
        placeholder="如 上海-长宁区"
        :style="ctl('160px')"
        @keyup.enter="emit('search')"
      />
    </el-form-item>
    <el-form-item label="公司">
      <el-input
        v-model="state.company_id"
        clearable
        placeholder="公司 ID"
        :style="ctl('160px')"
        @keyup.enter="emit('search')"
      />
    </el-form-item>
    <el-form-item label="标签">
      <el-input v-model="state.tag" clearable :style="ctl('140px')" @keyup.enter="emit('search')" />
    </el-form-item>
    <el-form-item label="收藏">
      <el-select v-model="state.favorite" :style="ctl('120px')" @change="emit('search')">
        <el-option label="全部" value="" />
        <el-option label="已收藏" value="yes" />
        <el-option label="未收藏" value="no" />
      </el-select>
    </el-form-item>
    <el-form-item label="薪资区间">
      <el-input-number
        v-model="state.salary_min"
        :min="0"
        :step="1000"
        placeholder="最低"
        @change="emit('search')"
      />
      <span class="sep">~</span>
      <el-input-number
        v-model="state.salary_max"
        :min="0"
        :step="1000"
        placeholder="最高"
        @change="emit('search')"
      />
    </el-form-item>
    <el-form-item label="排序">
      <el-select v-model="state.primary_sort" :style="ctl('130px')" @change="emit('search')">
        <el-option label="默认" value="" />
        <el-option label="活跃值" value="activity_score" />
        <el-option label="发布时间" value="publish_time" />
      </el-select>
      <el-select
        v-model="state.primary_dir"
        :style="ctl('90px')"
        :disabled="!state.primary_sort"
        @change="emit('search')"
      >
        <el-option label="降序" value="desc" />
        <el-option label="升序" value="asc" />
      </el-select>
      <span class="sep">+</span>
      <el-select
        v-model="state.secondary_sort"
        :style="ctl('130px')"
        :disabled="!state.primary_sort"
        @change="emit('search')"
      >
        <el-option label="无" value="" />
        <el-option label="活跃值" value="activity_score" />
        <el-option label="发布时间" value="publish_time" />
      </el-select>
      <el-select
        v-model="state.secondary_dir"
        :style="ctl('90px')"
        :disabled="!state.primary_sort"
        @change="emit('search')"
      >
        <el-option label="降序" value="desc" />
        <el-option label="升序" value="asc" />
      </el-select>
    </el-form-item>
    <el-form-item label="发布时间">
      <el-date-picker
        v-model="state.publishRange"
        type="daterange"
        start-placeholder="开始日期"
        end-placeholder="结束日期"
        value-format="YYYY-MM-DD"
        :shortcuts="dateShortcuts"
        :style="ctl('240px')"
        @change="emit('search')"
      />
    </el-form-item>
    <el-form-item>
      <el-button type="primary" @click="emit('search')">查询</el-button>
      <el-button @click="emit('reset')">重置</el-button>
    </el-form-item>
  </el-form>
</template>

<script setup lang="ts">
export interface JobFilterState {
  page: number
  page_size: number
  keyword: string
  city: string
  district: string
  area: string
  company_id: string
  tag: string
  favorite: '' | 'yes' | 'no'
  salary_min: number | undefined
  salary_max: number | undefined
  primary_sort: '' | 'activity_score' | 'publish_time'
  primary_dir: 'asc' | 'desc'
  secondary_sort: '' | 'activity_score' | 'publish_time'
  secondary_dir: 'asc' | 'desc'
  publishRange: [string, string] | null
}

export function createDefaultJobFilterState(): JobFilterState {
  return {
    page: 1,
    page_size: 20,
    keyword: '',
    city: '',
    district: '',
    area: '',
    company_id: '',
    tag: '',
    favorite: '',
    salary_min: undefined,
    salary_max: undefined,
    primary_sort: '',
    primary_dir: 'desc',
    secondary_sort: '',
    secondary_dir: 'desc',
    publishRange: null,
  }
}

const props = defineProps<{
  mode: 'inline' | 'stack'
  state: JobFilterState
  cityOptions: string[]
  districtOptions: string[]
}>()

const emit = defineEmits<{ search: []; reset: []; 'city-change': [] }>()

function ctl(desktopPx: string) {
  return props.mode === 'stack' ? { width: '100%' } : { width: desktopPx }
}

function daysAgo(n: number): Date {
  const d = new Date()
  d.setDate(d.getDate() - n)
  return d
}

const dateShortcuts: Array<{ text: string; value: () => [Date, Date] }> = [
  { text: '今天', value: () => [new Date(), new Date()] },
  { text: '近7天', value: () => [daysAgo(6), new Date()] },
  { text: '近30天', value: () => [daysAgo(29), new Date()] },
  { text: '近90天', value: () => [daysAgo(89), new Date()] },
]
</script>

<style scoped>
.sep { margin: 0 8px; color: var(--el-text-color-secondary); }
</style>
```

- [ ] **Step 2: Jobs.vue 接入抽取后的组件**

`frontend/src/views/Jobs.vue` 修改点：

(a) 模板：把现有 `<el-card class="filter-card">` 内整个 `<el-form inline>…</el-form>` 替换为：

```vue
    <el-card v-if="!isMobile" class="filter-card">
      <JobFilters
        mode="inline"
        :state="query"
        :city-options="cityOptions"
        :district-options="districtOptions"
        @search="search"
        @reset="reset"
        @city-change="onCityChange"
      />
    </el-card>
```

(b) script：`import { onMounted, reactive, ref } from 'vue'` 不变；新增 import 与 query 定义：

```ts
import JobFilters, { createDefaultJobFilterState, type JobFilterState } from './JobFilters.vue'
import { useIsMobile } from '@/composables/useIsMobile'

const isMobile = useIsMobile()

const query = reactive<JobFilterState>(createDefaultJobFilterState())
```

删除原 `publishRange` ref（已并入 query）与 `daysAgo`/`dateShortcuts` 定义（已移入 JobFilters.vue）。

(c) `load()`：`if (publishRange.value)` 改为 `if (query.publishRange)`，内部 `publishRange.value[0]` / `[1]` 改为 `query.publishRange[0]` / `[1]`。

(d) `reset()`：删除对 `publishRange.value = null` 的赋值（query 重建已含），函数体改为：

```ts
function reset() {
  Object.assign(query, createDefaultJobFilterState())
  router.replace({ path: '/jobs' })
  loadFilterOptions()
  search()
}
```

(e) `onMounted`：`publishRange.value = s.publishRange` 改为 `query.publishRange = s.publishRange`。

- [ ] **Step 3: 验证**

Run: `cd frontend; npm run type-check; npm run test`
Expected: type-check PASS；全部测试 PASS（现有 23 项 + useIsMobile 4 项）

- [ ] **Step 4: 提交**

```bash
git add frontend/src/views/JobFilters.vue frontend/src/views/Jobs.vue
git commit -m "feat(mobile): 抽取 JobFilters 组件，inline/stack 双模式"
```

---

### Task 6: Jobs 页面移动端（卡片列表 + 底部筛选面板 + 紧凑分页）

**Files:**
- Modify: `frontend/src/views/Jobs.vue`
- Modify: `frontend/src/components/JobDetailDialog.vue`

**Interfaces:**
- Consumes: `JobCard`（Task 4）、`JobFilters`（Task 5）、`useIsMobile`（Task 1）
- Produces: 移动端工具栏（筛选/全选/收藏/取消收藏）、JobCard 列表（勾选互斥于桌面表格 selection）、`el-drawer direction="btt"` 筛选面板、分页 `layout="total, prev, next"`；JobDetailDialog 移动端单列。

- [ ] **Step 1: Jobs.vue 模板增加移动端分支**

`frontend/src/views/Jobs.vue`：把现有桌面表格所在的 `<el-card>`（含 el-table 与 el-pagination）包一层 `v-if="!isMobile"`，并在此 el-card 之后新增移动端分支（在 filter-card 与 JobDetailDialog 之间）：

```vue
    <el-card v-if="!isMobile">
      <div class="toolbar">
        <span class="selected-info">已选 {{ selection.length }} 项</span>
        <el-button type="primary" :disabled="selection.length === 0" @click="batchFavorite(true)">批量收藏</el-button>
        <el-button :disabled="selection.length === 0" @click="batchFavorite(false)">批量取消收藏</el-button>
      </div>
      <el-table :data="page.items" v-loading="loading" @selection-change="onSelectionChange" @row-click="onRowClick">
        <!-- 现有 14 列 el-table-column 原样保留，不做任何修改 -->
      </el-table>
      <el-pagination
        class="pager"
        layout="total, prev, pager, next"
        :total="page.total"
        :page-size="query.page_size"
        :current-page="query.page"
        @current-change="onPage"
      />
    </el-card>

    <div v-else>
      <div class="mobile-toolbar">
        <el-button type="primary" size="small" @click="filterVisible = true">
          <el-icon><Filter /></el-icon>
          <span class="btn-text">筛选</span>
        </el-button>
        <el-button size="small" :type="allSelected ? 'primary' : 'default'" @click="toggleSelectAll">全选</el-button>
        <el-button size="small" type="primary" plain :disabled="selection.length === 0" @click="batchFavorite(true)">
          收藏
        </el-button>
        <el-button size="small" plain :disabled="selection.length === 0" @click="batchFavorite(false)">
          取消收藏
        </el-button>
        <span class="selected-info">已选 {{ selection.length }}</span>
      </div>
      <div v-loading="loading" class="mobile-list">
        <JobCard
          v-for="job in page.items"
          :key="job.job_id"
          :job="job"
          selectable
          :selected="selection.some((r) => r.job_id === job.job_id)"
          @click="openDetail(job)"
          @toggle-favorite="toggleFavorite(job)"
          @select="(v: boolean) => onCardSelect(job, v)"
        />
      </div>
      <el-pagination
        v-if="page.total > 0"
        class="pager"
        layout="total, prev, next"
        :total="page.total"
        :page-size="query.page_size"
        :current-page="query.page"
        @current-change="onPage"
      />
    </div>

    <el-drawer v-model="filterVisible" direction="btt" size="70%" :with-header="false">
      <div class="mobile-filter">
        <JobFilters
          mode="stack"
          :state="query"
          :city-options="cityOptions"
          :district-options="districtOptions"
          @search="mobileSearch"
          @reset="mobileReset"
          @city-change="onCityChange"
        />
      </div>
    </el-drawer>
```

- [ ] **Step 2: Jobs.vue script 增加移动端逻辑**

`frontend/src/views/Jobs.vue` script 修改：

(a) imports 增加：

```ts
import { computed } from 'vue'
import JobCard from '@/components/JobCard.vue'
```

(b) 新增状态：

```ts
const filterVisible = ref(false)
```

(c) 新增函数（放在 `onSelectionChange` 之后）：

```ts
const allSelected = computed(
  () =>
    page.value.items.length > 0 &&
    page.value.items.every((j) => selection.value.some((r) => r.job_id === j.job_id)),
)

function toggleSelectAll() {
  selection.value = allSelected.value ? [] : [...page.value.items]
}

function onCardSelect(job: JobOut, selected: boolean) {
  if (selected) {
    if (!selection.value.some((r) => r.job_id === job.job_id)) {
      selection.value.push(job)
    }
  } else {
    selection.value = selection.value.filter((r) => r.job_id !== job.job_id)
  }
}

function mobileSearch() {
  filterVisible.value = false
  search()
}

function mobileReset() {
  filterVisible.value = false
  reset()
}
```

- [ ] **Step 3: Jobs.vue 样式补充**

`<style scoped>` 追加：

```css
.mobile-toolbar {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  margin-bottom: 12px;
}
.mobile-toolbar .btn-text { margin-left: 4px; }
.mobile-list { min-height: 60px; }
.mobile-filter { padding: 4px 8px 20px; }
```

- [ ] **Step 4: JobDetailDialog 移动端单列**

`frontend/src/components/JobDetailDialog.vue`：
(a) script 增加 `import { useIsMobile } from '@/composables/useIsMobile'` 与 `const isMobile = useIsMobile()`；
(b) 模板 `:column="2"` 改为 `:column="isMobile ? 1 : 2"`。

- [ ] **Step 5: 验证**

Run: `cd frontend; npm run type-check; npm run test`
Expected: type-check PASS；全部测试 PASS

- [ ] **Step 6: 提交**

```bash
git add frontend/src/views/Jobs.vue frontend/src/components/JobDetailDialog.vue
git commit -m "feat(mobile): 职位页移动端卡片列表、底部筛选面板与紧凑分页"
```

---

### Task 7: 公司页移动端（CompanyCard + 堆叠筛选）

**Files:**
- Create: `frontend/src/components/CompanyCard.vue`
- Modify: `frontend/src/views/Companies.vue`

**Interfaces:**
- Consumes: `CompanyOut`（`frontend/src/api/companies.ts`）、`formatTime`
- Produces: `CompanyCard` props `{ company: CompanyOut }`；Companies.vue 移动端卡片列表 + 同一 el-form 双模式（`:inline="!isMobile"`）。

- [ ] **Step 1: 创建 CompanyCard.vue**

`frontend/src/components/CompanyCard.vue`（新建）：

```vue
<template>
  <el-card class="company-card" shadow="hover">
    <div class="company-header">
      <span class="company-name">{{ company.name }}</span>
      <el-tag v-if="company.type" size="small" :type="typeTagType(company.type)">{{ company.type }}</el-tag>
    </div>
    <div class="company-meta">
      <span v-if="company.industry" class="meta-item">{{ company.industry }}</span>
      <span v-if="company.size" class="meta-item">{{ company.size }}</span>
      <span v-if="company.activity" class="meta-item">{{ company.activity }}</span>
    </div>
    <div class="company-footer">更新于 {{ formatTime(company.updated_at) }}</div>
  </el-card>
</template>

<script setup lang="ts">
import type { CompanyOut } from '@/api/companies'
import { formatTime } from '@/utils/format'

defineProps<{ company: CompanyOut }>()

function typeTagType(t: string): '' | 'success' | 'warning' {
  if (t === '国企') return 'success'
  if (t === '外企') return 'warning'
  return ''
}
</script>

<style scoped>
.company-card { margin-bottom: 10px; }
.company-header { display: flex; align-items: center; gap: 8px; }
.company-name { flex: 1; font-size: 15px; font-weight: 600; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.company-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 4px 10px;
  margin-top: 6px;
  font-size: 12px;
  color: var(--el-text-color-regular);
}
.meta-item {
  padding: 1px 6px;
  background: var(--el-fill-color-light);
  border-radius: 4px;
}
.company-footer { margin-top: 8px; font-size: 12px; color: var(--el-text-color-secondary); }
</style>
```

- [ ] **Step 2: Companies.vue 双模式**

`frontend/src/views/Companies.vue` 修改：

(a) 模板：filter-card 内 `el-form inline` 改为 `el-form :inline="!isMobile"`，三个输入的固定宽度 `style="width: 140px"` 等改为 `:style="inputStyle('140px')"`（180px/160px 同理）；表格所在的 `<el-card>` 拆成双分支：

```vue
    <el-card v-if="!isMobile">
      <el-table :data="page.items" v-loading="loading">
        <!-- 现有 6 列原样保留 -->
      </el-table>
      <el-pagination
        class="pager"
        layout="total, prev, pager, next"
        :total="page.total"
        :page-size="query.page_size"
        :current-page="query.page"
        @current-change="onPage"
      />
    </el-card>
    <div v-else>
      <div v-loading="loading" class="card-list">
        <CompanyCard v-for="c in page.items" :key="c.company_id" :company="c" />
      </div>
      <el-pagination
        v-if="page.total > 0"
        class="pager"
        layout="total, prev, next"
        :total="page.total"
        :page-size="query.page_size"
        :current-page="query.page"
        @current-change="onPage"
      />
    </div>
```

(b) script 增加：

```ts
import CompanyCard from '@/components/CompanyCard.vue'
import { useIsMobile } from '@/composables/useIsMobile'

const isMobile = useIsMobile()

function inputStyle(desktopPx: string) {
  return isMobile.value ? { width: '100%' } : { width: desktopPx }
}
```

(c) 样式追加：

```css
.card-list { min-height: 60px; }
```

- [ ] **Step 3: 验证**

Run: `cd frontend; npm run type-check; npm run test`
Expected: type-check PASS；全部测试 PASS

- [ ] **Step 4: 提交**

```bash
git add frontend/src/components/CompanyCard.vue frontend/src/views/Companies.vue
git commit -m "feat(mobile): 公司页移动端卡片列表与堆叠筛选"
```

---

### Task 8: 任务页移动端（关键字/任务卡片 + 新建任务对话框 + FAB）

**Files:**
- Create: `frontend/src/components/KeywordCard.vue`
- Create: `frontend/src/components/TaskCard.vue`
- Modify: `frontend/src/views/Tasks.vue`

**Interfaces:**
- Consumes: `KeywordOut`（`frontend/src/api/keywords.ts`）、`TaskOut`（`frontend/src/api/tasks.ts`）、`cityName`/`industryNames`/`formatTime`/`taskStatusText`/`taskStatusType`
- Produces: `KeywordCard` props `{ kw: KeywordOut }`，emits `toggle`/`edit`/`remove`；`TaskCard` props `{ task: TaskOut; keywordName: string }`，emits `remove`；Tasks.vue 移动端：el-col 断点、卡片列表、FAB + 新建任务 el-dialog。

- [ ] **Step 1: 创建 KeywordCard.vue**

`frontend/src/components/KeywordCard.vue`（新建）：

```vue
<template>
  <el-card class="keyword-card" shadow="hover">
    <div class="keyword-header">
      <span class="keyword-name">{{ kw.keyword }}</span>
      <el-switch :model-value="kw.enabled" @change="emit('toggle')" />
    </div>
    <div class="keyword-meta">
      <span class="meta-item">{{ cityName(kw.city) }}</span>
      <span v-if="kw.industry" class="meta-item">{{ industryNames(kw.industry) }}</span>
      <span class="meta-item">{{ kw.scrape_mode }}</span>
      <span class="meta-item">最近抓取 {{ formatTime(kw.last_scraped_at) }}</span>
    </div>
    <div class="keyword-actions">
      <el-button size="small" @click="emit('edit')">编辑</el-button>
      <el-button size="small" type="danger" @click="emit('remove')">删除</el-button>
    </div>
  </el-card>
</template>

<script setup lang="ts">
import type { KeywordOut } from '@/api/keywords'
import { cityName } from '@/utils/cities'
import { industryNames } from '@/utils/industries'
import { formatTime } from '@/utils/format'

defineProps<{ kw: KeywordOut }>()
const emit = defineEmits<{ toggle: []; edit: []; remove: [] }>()
</script>

<style scoped>
.keyword-card { margin-bottom: 10px; }
.keyword-header { display: flex; align-items: center; gap: 8px; }
.keyword-name { flex: 1; font-size: 15px; font-weight: 600; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.keyword-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 4px 10px;
  margin-top: 6px;
  font-size: 12px;
  color: var(--el-text-color-regular);
}
.meta-item {
  padding: 1px 6px;
  background: var(--el-fill-color-light);
  border-radius: 4px;
}
.keyword-actions { margin-top: 8px; }
</style>
```

- [ ] **Step 2: 创建 TaskCard.vue**

`frontend/src/components/TaskCard.vue`（新建）：

```vue
<template>
  <el-card class="task-card" shadow="hover">
    <div class="task-header">
      <span class="task-keyword">{{ keywordName }}</span>
      <el-tag :type="taskStatusType(task.status)">{{ taskStatusText(task.status) }}</el-tag>
    </div>
    <div v-if="task.status === 'queued' || task.status === 'in_progress'" class="task-progress">
      <div class="progress-text">
        已抓 {{ task.last_page }} 页{{ task.total_pages ? ` / 共 ${task.total_pages} 页` : '' }}
      </div>
      <el-progress v-if="task.total_pages" :percentage="progressPct" :stroke-width="6" />
    </div>
    <div v-else-if="task.status === 'success' || task.status === 'partial_success'" class="task-progress">
      成功 {{ task.success_count }} / 失败 {{ task.failed_count }}（共 {{ task.total_pages ?? '-' }} 页）
    </div>
    <div v-else class="task-progress">{{ task.error_message ?? '-' }}</div>
    <div class="task-time">{{ formatTime(task.start_time) }} / {{ formatTime(task.end_time) }}</div>
    <div class="task-actions">
      <el-button size="small" type="danger" @click="emit('remove')">删除</el-button>
    </div>
  </el-card>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { TaskOut } from '@/api/tasks'
import { formatTime, taskStatusText, taskStatusType } from '@/utils/format'

const props = defineProps<{ task: TaskOut; keywordName: string }>()
const emit = defineEmits<{ remove: [] }>()

const progressPct = computed(() => {
  if (!props.task.total_pages) return 0
  return Math.min(100, Math.round((props.task.last_page / props.task.total_pages) * 100))
})
</script>

<style scoped>
.task-card { margin-bottom: 10px; }
.task-header { display: flex; align-items: center; gap: 8px; }
.task-keyword { flex: 1; font-size: 15px; font-weight: 600; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.task-progress { margin-top: 8px; font-size: 13px; color: var(--el-text-color-regular); }
.progress-text { margin-bottom: 4px; }
.task-time { margin-top: 8px; font-size: 12px; color: var(--el-text-color-secondary); }
.task-actions { margin-top: 8px; }
</style>
```

- [ ] **Step 3: Tasks.vue 改造**

`frontend/src/views/Tasks.vue` 修改：

(a) 模板——el-col 加断点（`:span="16"` → `:span="16" :xs="24"`；`:span="8"` → `:span="8" :xs="24"`）：

```vue
      <el-col :span="16" :xs="24">
      ...
      <el-col :span="8" :xs="24">
```

(b) 关键字管理卡片内，el-table 包 `v-if="!isMobile"` 并在其后加卡片分支：

```vue
          <el-table :data="keywordsStore.list" v-if="!isMobile" v-loading="keywordsStore.loading">
            <!-- 现有 7 列原样保留 -->
          </el-table>
          <div v-else class="card-list" v-loading="keywordsStore.loading">
            <KeywordCard
              v-for="kw in keywordsStore.list"
              :key="kw.id"
              :kw="kw"
              @toggle="toggle(kw)"
              @edit="openEdit(kw)"
              @remove="removeKeyword(kw)"
            />
          </div>
```

(c) 新建抓取任务卡片内 `<el-form inline>` 改为 `<el-form :inline="!isMobile" :label-position="isMobile ? 'top' : undefined">`，三个控件的固定宽度改为 `:style="inputStyle('200px')"`（140px 同理），`max_pages` 的 hint 文案保留。

(d) 任务列表卡片内 el-table 包 `v-if="!isMobile"`，其后加卡片分支：

```vue
          <el-table :data="tasks" v-if="!isMobile" v-loading="tasksLoading">
            <!-- 现有 5 列原样保留 -->
          </el-table>
          <div v-else class="card-list" v-loading="tasksLoading">
            <TaskCard
              v-for="t in tasks"
              :key="t.id"
              :task="t"
              :keyword-name="keywordName(t.keyword_id)"
              @remove="removeTask(t)"
            />
          </div>
```

(e) 定时任务卡片内 el-form 加 `:label-position="isMobile ? 'top' : undefined"`。

(f) 在 JobDetailDialog 之前（`</el-row>` 之后）加 FAB 与移动端新建任务对话框（对话框内表单为 stack 版，仅移动端渲染）：

```vue
    <el-button v-if="isMobile" class="task-fab" type="primary" round @click="taskDialogVisible = true">
      <el-icon><Plus /></el-icon>
    </el-button>

    <el-dialog v-if="isMobile" v-model="taskDialogVisible" title="新建抓取任务" width="420px">
      <el-form label-width="80px">
        <el-form-item label="关键字">
          <el-select v-model="taskForm.keyword_id" placeholder="选择关键字" style="width: 100%">
            <el-option v-for="kw in keywordsStore.list" :key="kw.id" :label="`${kw.keyword} · ${cityName(kw.city)}`" :value="kw.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="方式">
          <el-select v-model="taskForm.mode" style="width: 100%">
            <el-option label="Playwright" value="playwright" />
          </el-select>
        </el-form-item>
        <el-form-item label="最大页数">
          <el-input-number v-model="taskForm.max_pages" :min="1" :max="scraperConfig.max_pages" />
          <div class="form-hint">留空 = 全局上限 {{ scraperConfig.max_pages }} 页</div>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="taskDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="creating" @click="createTask">创建</el-button>
      </template>
    </el-dialog>
```

(g) script 增加：

```ts
import KeywordCard from '@/components/KeywordCard.vue'
import TaskCard from '@/components/TaskCard.vue'
import { useIsMobile } from '@/composables/useIsMobile'

const isMobile = useIsMobile()
const taskDialogVisible = ref(false)

function inputStyle(desktopPx: string) {
  return isMobile.value ? { width: '100%' } : { width: desktopPx }
}
```

(h) `createTask` 成功后关闭对话框：在 `ElMessage.success('任务已创建')` 后加 `taskDialogVisible.value = false`。

(i) 样式追加：

```css
.card-list { min-height: 60px; }
.task-fab {
  position: fixed;
  right: 16px;
  bottom: 24px;
  z-index: 10;
}
```

- [ ] **Step 4: 验证**

Run: `cd frontend; npm run type-check; npm run test`
Expected: type-check PASS；全部测试 PASS

- [ ] **Step 5: 提交**

```bash
git add frontend/src/components/KeywordCard.vue frontend/src/components/TaskCard.vue frontend/src/views/Tasks.vue
git commit -m "feat(mobile): 任务页移动端卡片、FAB 与新建任务对话框"
```

---

### Task 9: 统计页响应式

**Files:**
- Modify: `frontend/src/views/Stats.vue`

**Interfaces:**
- Consumes: `useIsMobile`（Task 1）
- Produces: 统计卡片 2x2（`:xs="12"`）、图表卡片全宽（`:xs="24"`）、图表高度移动端 260px、筛选控件宽度自适应。

- [ ] **Step 1: Stats.vue 修改**

`frontend/src/views/Stats.vue` 修改：

(a) script 增加：

```ts
import { useIsMobile } from '@/composables/useIsMobile'

const isMobile = useIsMobile()

function selStyle(desktopPx: string, withGap = false) {
  if (isMobile.value) return { width: '100%' }
  return { width: desktopPx, ...(withGap ? { marginLeft: '16px' } : {}) }
}
```

(b) 模板筛选卡：两个 el-select 的 style 改为：

```vue
        :style="selStyle('240px')"
```
```vue
        :style="selStyle('140px', true)"
```

(c) 统计卡片行：`<el-col :span="6" v-for="card in cards" :key="card.label">` 改为 `<el-col :span="6" :xs="12" v-for="card in cards" :key="card.label">`。

(d) 饼图行：`<el-col :span="8" v-for="pie in pies" :key="pie.title">` 改为 `<el-col :span="8" :xs="24" v-for="pie in pies" :key="pie.title">`。

(e) 样式：`.chart-header` 增加换行能力，`.chart` 增加移动端高度：

```css
.chart-header { display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 8px; }
```

```css
@media (max-width: 768px) {
  .chart { height: 260px; }
}
```

- [ ] **Step 2: 验证**

Run: `cd frontend; npm run type-check; npm run test`
Expected: type-check PASS；全部测试 PASS

- [ ] **Step 3: 提交**

```bash
git add frontend/src/views/Stats.vue
git commit -m "feat(mobile): 统计页响应式（2x2 卡片、全宽图表、移动端高度）"
```

---

### Task 10: 最终验证

**Files:** 无（只运行命令）

- [ ] **Step 1: 全量检查**

Run: `cd frontend; npm run build; npm run test`
Expected: build（含 vue-tsc type-check + vite build）PASS；vitest 全部 PASS（23 旧 + 4 新 = 27 项）

- [ ] **Step 2: 手动冒烟清单（Chrome DevTools 设备模拟）**

在 `npm run dev` 下用 DevTools 设备模式（iPhone 12 = 390px 宽 / iPhone SE = 375px 宽）逐项验证：

- [ ] 登录页：卡片不溢出，输入框可用
- [ ] 布局：无侧边栏，汉堡按钮打开抽屉，抽屉菜单可跳转并自动关闭
- [ ] 任务页：关键字卡片（开关/编辑/删除可用）、新建任务 FAB 打开对话框且创建成功、任务卡片显示状态与进度、定时设置卡片可编辑
- [ ] 职位页：筛选按钮打开底部面板，查询/重置生效并自动关闭面板；卡片勾选/全选/批量收藏/取消收藏生效；点击卡片打开详情（单列描述）；分页为 total/prev/next
- [ ] 公司页：筛选堆叠可用，卡片列表展示完整
- [ ] 统计页：4 个统计卡片 2x2，图表全宽无横向滚动，高度合理，切换筛选/指标正常，热力图点击仍可跳转
- [ ] 对话框（关键字编辑/任务详情等）宽度 ≤ 92vw 不溢出
- [ ] 桌面端回归：切回 >768px 宽度，确认 5 个页面与改造前一致（表格全列、内联筛选、侧边栏、16/8 分栏、4 列统计卡）

- [ ] **Step 3: 总结提交（如有遗留修复则单独提交）**

```bash
git log --oneline -10
```

确认 9 个功能提交齐全后结束；冒烟发现的问题在新 commit 中修复并说明。

---

## Self-Review 记录

- **Spec 覆盖**：§3.1 useIsMobile（Task 1）；§3.2 Layout 抽屉（Task 3）；§3.3 全局 CSS（Task 2）；§3.4 Login（Task 2）；§4.1 四个卡片组件（Task 4/7/8）；§4.2 Jobs 卡片+底部筛选+单列详情（Task 5/6）、Companies（Task 7）、Tasks FAB（Task 8）、分页三页统一（Task 6/7/8）；§5 Stats（Task 9）；§6 桌面端不变（各任务约束）；§7 验证（Task 10）。无缺口。
- **类型一致性**：`JobFilterState`/`createDefaultJobFilterState` 在 Task 5 定义并被 Task 5/6 使用；`useIsMobile` 在 Task 1 定义，Task 3/6/7/8/9 消费；JobCard props/emits 在 Task 4 定义、Task 6 使用；KeywordCard/TaskCard props/emits 在 Task 8 内定义并使用。无跨任务命名冲突。
- **占位符扫描**：无 TBD/TODO；所有代码步骤含完整代码或精确替换目标。
