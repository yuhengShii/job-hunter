# 发布时间趋势跳转职位列表设计

日期：2026-08-11

## 目标

统计看板（`Stats.vue`）的「发布时间趋势」图支持点击跳转职位列表：按点击的日期与地区（城市/区域/地区分组对应）预筛选，关键字可选预填。

## 背景

- 趋势图两种形态：`group_by=all` 时为折线图（每日计数）；`group_by=city/district/area` 时为热力图（行=地区 key，列=日期）。
- 趋势图中每天归属 `(publish_time or updated_at).date()`；跳转后列表按 `publish_time` 过滤，无 publish_time 的职位不会出现在结果中（多数数据有 publish_time，可接受）。
- `GET /api/jobs` 现有 city/district 精确筛选，但**无 `area` 参数**（趋势可按地区分组），需补。
- `jobs.city` 存显示名（"上海"）、`jobs.district` 存区名（"长宁区"）、`jobs.area` 存"上海-长宁区"式自由格式 → 地区筛选用文本输入框。

## 设计

### 交互流程

1. 点击热力图格子（某天×某地区）或折线图数据点（某天）→ 弹出对话框。
2. 对话框展示将应用的筛选（时间、地区），含关键字输入框，默认值 = 统计页当前选中的关键字文本（可修改/清空）。
3. 确认 → `router.push('/jobs')` 携带 query；取消 → 不跳转。
4. 职位列表页 onMounted 读取 route.query 初始化筛选并自动加载。

### query 组装规则（Stats.vue）

- `publish_time_from = publish_time_to = 点击日期`（`YYYY-MM-DD`）。
- 热力图模式按当前 groupBy 映射地区参数：`city`→`city`、`district`→`district`、`area`→`area`；行 key 为 `未知`/`其他` 时跳过地区参数；折线图模式不传地区参数。
- 关键字去空格后非空才传 `keyword`。

### 后端（backend/app/api/jobs.py）

`list_jobs` 新增 `area: str | None` → `Job.area == area`（精确匹配），与 city/district 同模式。

### 前端

- `api/jobs.ts`：`JobQuery` 增加 `area?`。
- `Jobs.vue`：筛选栏新增「地区」文本框（参照"公司 ID"输入模式，clearable）；`query.area` 组参；reset 清空；onMounted 读取 route.query 初始化（city/district/area/keyword/publish_time_from/to），reset 时 `router.replace` 清 URL query 防刷新复活。
- 新增纯函数 `src/utils/jobsQuery.ts`：`jobsStateFromRoute(query)` 将 route.query 转初始筛选状态（含日期格式校验 `^\d{4}-\d{2}-\d{2}$`），便于 vitest 单测。
- `Stats.vue`：捕获 trend chart 实例并绑定 `click` 事件（热力图取 `params.value[0]/[1]` → 日期/行 key；折线图取 `params.dataIndex` → days 数组）；新增跳转对话框（时间/地区展示 + 关键字输入）。

## 测试

- 后端 pytest：`test_filter_by_area`（精确命中 / 无命中 / 与发布时间组合）。
- 前端 vitest：`jobsStateFromRoute`（正常映射 / 非法日期对 / 空对象）。
- 全量：`uv run pytest`、`npm run test`、`npm run type-check`、`npm run build`。

## 验证

- 后端全量 pytest 绿；前端 vitest/type-check/build 绿。
- 手动冒烟：热力图点格子、折线图点数据点、弹窗取消、关键字预填/清空、跳转后筛选生效、刷新保留筛选。
