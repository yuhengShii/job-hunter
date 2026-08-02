# 前端 v1 实现设计

日期：2026-08-02
状态：已确认（brainstorming 分节通过）
范围：Vue3 + Vite + Element Plus + ECharts + Pinia + Vue Router 前端全量（登录 / 任务控制台 / 职位列表 / 公司列表 / 统计看板），对接已有后端 v1；含轻量 vitest 单测；后端仅加静态托管挂载一处小改动。

## 1. 背景与目标

后端 v1 已全部实现并通过 pytest（模型 / JWT 认证 / 关键字 / 任务调度 / Playwright 抓取 / 职位公司 API / 统计 / APScheduler），`frontend/` 仍为目录骨架（仅 `.gitkeep`）。本轮实现 PRD §7 全部前端页面，产出可用的前后端分离应用。

已实测确认的后端事实（供前端对接依据）：

- 后端无 CORS 中间件 → 开发期走 Vite proxy（`/api` → `http://127.0.0.1:8000`）。
- 错误响应统一为 `{"detail": "<message>"}`（`core/exceptions.py` 的 AppError handler）；JWT 失败/过期返回 401。
- `POST /api/tasks` 对同一 keyword 已有进行中任务返回 409。
- 分页响应：`JobPage` / `CompanyPage` 为 `{total, items}`；`GET /api/jobs` 支持 city/company_id/keyword/tag/salary_min/salary_max/page/page_size；`GET /api/companies` 同构（待实现后以实际为准，如后端无筛选参数则由前端过滤）。
- 统计接口均为裸 dict：`/api/stats/overview` → `{total_jobs, total_cities, total_companies, salary_parsed}`；`/api/stats/salary?group_by=city` → `{group_by, items: [{key, count, min, max, median}]}`；`/api/stats/company` → `{industry|type|size: [{key, count, ratio}]}`；`/api/stats/trend?days=30` → `{days: [{date, count}]}`；`/api/stats/tags?top_n=10` → `[{tag, count}]`；均支持 `keyword_id`。
- 定时设置：`GET/PUT /api/settings/schedule` ↔ `{enabled, interval_minutes, keyword_ids}`。
- 任务状态枚举：`queued / in_progress / success / partial_success / failed`；`total_pages` 未解析出前为 null（进度显示「已抓 N 页」）。

## 2. 技术选型与脚手架

- 方案 A：**手写最小脚手架**（无官方模板），目录贴合 `docs/code-style.md` 既定结构。
- 依赖（`npm install`）：vue、vue-router、pinia、element-plus、@element-plus/icons-vue、echarts、axios。
- 开发依赖：vite、@vitejs/plugin-vue、typescript、vitest、jsdom、@vue/test-utils。
- 语言：TypeScript（仅前端自约束，不产生共享类型契约）。

### 目录结构

```
frontend/
├── index.html
├── package.json
├── tsconfig.json
├── vite.config.ts          # @ 别名 + dev proxy /api → http://127.0.0.1:8000
├── src/
│   ├── main.ts             # createApp + Pinia + Router + ElementPlus(zh-cn locale)
│   ├── App.vue             # <router-view> 壳
│   ├── env.d.ts
│   ├── api/
│   │   ├── http.ts         # axios 实例 + 拦截器（token 注入 / 401 / 错误提示）
│   │   ├── auth.ts / keywords.ts / tasks.ts / jobs.ts / companies.ts / stats.ts / settings.ts
│   ├── stores/
│   │   ├── auth.ts         # token + username，localStorage 持久化
│   │   └── keywords.ts     # 关键字列表共享状态
│   ├── router/index.ts     # 路由表 + 登录守卫
│   ├── utils/format.ts     # 薪资/时间/任务状态 格式化与文案映射
│   ├── composables/useChart.ts  # ECharts 封装（init/resize/销毁）
│   ├── components/
│   │   ├── Layout.vue      # 侧边栏导航 + 顶栏（用户/退出）
│   │   └── JobDetailDialog.vue
│   └── views/
│       ├── Login.vue
│       ├── Tasks.vue       # 任务控制台
│       ├── Jobs.vue
│       ├── Companies.vue
│       └── Stats.vue
└── tests/
    ├── format.test.ts
    ├── http.test.ts
    └── auth.store.test.ts
```

## 3. 页面与数据流

### 3.1 路由与守卫

- 路由：`/login`、`/tasks`（默认重定向目标）、`/jobs`、`/companies`、`/stats`。
- `router.beforeEach`：无 token 且目标非 `/login` → 重定向 `/login`；已登录访问 `/login` → `/tasks`。
- token 有效期 24h；任意请求 401 → 清 auth store → 跳 `/login`。

### 3.2 Login.vue

- 表单（用户名/密码）→ `POST /api/auth/login` → 存 auth store → 跳 `/tasks`；错误经统一拦截提示。

### 3.3 Tasks.vue（任务控制台，四区）

1. **关键字管理**：表格（keyword/enabled/scrape_mode/last_scraped_at/操作）；新增 `POST /api/keywords`；编辑 `PUT /api/keywords/{id}`（弹窗编辑，修改 keyword/scrape_mode）；启停 `POST /api/keywords/{id}/toggle`；删除 `DELETE /api/keywords/{id}`（确认框）。重复关键字 409、删除不存在 404 均走统一错误提示。
2. **新建任务**：关键字下拉（keywords store）+ 抓取方式（仅 playwright）+ max_pages 可选 → `POST /api/tasks`；409 时 ElMessage 展示冲突说明。
3. **任务列表**：`GET /api/tasks` 表格（关键字/状态/进度/计数/耗时/错误）；进行中任务 3 秒轮询（仅 in_progress 时拉取，组件卸载停止）；`total_pages` 为 null 时进度显示「已抓 N 页」；状态文案/颜色映射：queued 排队 / in_progress 进行中 / success 成功 / partial_success 部分成功（警告色）/ failed 失败。
4. **定时设置**：`GET/PUT /api/settings/schedule`，enabled 开关 + interval_minutes + keyword_ids 多选（el-select multiple）。

### 3.4 Jobs.vue

- 筛选栏：关键字 / 城市 / 薪资区间（min-max）/ 公司 / 标签 → 后端查询参数。
- `GET /api/jobs` 分页表格（page_size=20），列：职位/公司/城市/薪资/标签/发布时间/来源；行点击 → JobDetailDialog（`GET /api/jobs/{job_id}` 展示全字段，job_url 外链）。
- 薪资列展示 `salary_raw`；详情弹窗展示解析后 min/max。

### 3.5 Companies.vue

- `GET /api/companies` 分页表格（page_size=20）+ 类型/行业/规模筛选（后端原生支持 type/industry/size/page/page_size 参数）。

### 3.6 Stats.vue

- 顶部 overview 卡片四个（职位数/城市数/公司数/薪资可解析数）。
- 顶部关键字筛选（全部 / 单关键字，`keyword_id` 参数，选择后刷新全部图表）。
- 图表：
  - 薪资分布：`/api/stats/salary?group_by=city` 柱状图（median），group_by 下拉切换 city / district / area（后端 `getattr(Job, group_by)` 均有效）。
  - 公司画像：`/api/stats/company` 三个环形饼图（行业/类型/规模，key/count/ratio）。
  - 时间趋势：`/api/stats/trend?days=30` 折线图。
  - 标签词频：`/api/stats/tags?top_n=10` 条形图。

## 4. 关键实现细节

- **http.ts**：axios 实例 `baseURL: '/api'`；请求拦截器从 auth store 读 token 注入 `Authorization: Bearer`；响应拦截器 401 → 清 store 跳登录，400/404/409 → `err.response.data.detail` → `ElMessage.error`，网络错误 → 「无法连接服务器」。
- **auth store**：token/username 持久化到 localStorage（`job_hunter_token` / `job_hunter_username`），初始化恢复；`login/logout` actions。
- **keywords store**：`fetch()` 拉列表；任务页/定时设置页复用。
- **任务轮询**：Tasks 页 `onMounted` 启动 3s 轮询，`onUnmounted` 清除；仅在列表存在 in_progress 任务时发请求。
- **format.ts**：`formatSalaryRaw`（原样展示/面议兜底）、`formatSalaryParsed`、`formatTime`（`YYYY-MM-DD HH:mm`，null → `-`）、`taskStatusText/Type` 映射。
- **useChart.ts**：`useChart(el: Ref<HTMLElement>, option: Ref<EChartsOption>)`；watch option → setOption；resize 监听；卸载 dispose；饼图环形 `radius: ['40%','70%']`。
- **Loading**：列表接口统一 `v-loading`。

## 5. 测试策略（vitest + jsdom）

- `format.test.ts`：薪资/时间/任务状态文案边界。
- `http.test.ts`：mock axios adapter 验证 token 注入、401 跳转、错误 detail 提示。
- `auth.store.test.ts`：login/logout/localStorage 持久化。
- 组件与页面不做自动化测试（人工冒烟 + 后端 pytest 保证 API 正确性）。

## 6. 后端改动（仅一处）

- `backend/app/main.py`：在注册 API 路由之后，若 `frontend/dist` 目录存在且非测试模式，`app.mount("/", StaticFiles(directory=..., html=True))`，实现单端口托管构建产物。
- 新增 npm script：`dev` / `build` / `test` / `type-check`。

## 7. 联调与验收

- 开发：`uv run uvicorn backend.app.main:app`（8000）+ `npm run dev`（5173，proxy /api）。
- 生产：`npm run build` 后直接访问 8000。
- 验收命令：`npm run test`、`npm run build` 通过；`uv run pytest backend/tests` 不受影响（现有测试在 JOB_HUNTER_TESTING=1 下运行，静态挂载不影响）。
- 手动冒烟：登录 → 建关键字 → 发任务 → 观察进度 → 职位/公司/统计页有数据 → 统计图渲染正确。
