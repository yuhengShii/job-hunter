# 职位列表筛选增强设计

日期：2026-08-10

## 目标

职位列表页（`Jobs.vue`）新增三个筛选：城市（下拉）、区域（下拉，随城市联动）、发布时间（日历选范围，带快捷项）。

## 背景

- `jobs.city` 存显示名（如"上海"）；`jobs.district` 存不含城市前缀的区名（如"长宁区"）；`jobs.publish_time` 为可空 datetime。
- 现有 `GET /api/jobs` 支持 city（精确匹配）/keyword/company_id/tag/salary 筛选与排序，无 district 与 publish_time 范围参数。
- `Jobs.vue` 城市筛现为自由文本输入框，无区域筛与时间筛。
- 前端编码表 `CITY_OPTIONS` 仅 7 个城市且存 51job 编码，与数据中显示名不一致，故城市/区域选项一律从数据提取。

## 设计

### 1. 后端：筛选选项接口（新增）

`GET /api/jobs/filter-options?city=上海`（需 JWT）

- 响应 `JobFilterOptions { cities: list[str], districts: list[str] }`
- `cities`：jobs 表 distinct 非空 city，按出现次数降序（tiebreak 按 city）。
- `districts`：distinct 非空 district；传了 `city` 参数则只返回该城市的区域（联动必须在后端做，district 不含城市前缀，前端无法映射）。
- **路由注册顺序**：必须声明在 `GET /api/jobs/{job_key}` 之前，否则 `filter-options` 会被当作 job_id 匹配。

### 2. 后端：`GET /api/jobs` 新增参数

- `district: str | None` → `Job.district == district`（精确匹配）
- `publish_time_from: date | None` → `Job.publish_time >= 当天 0 点`
- `publish_time_to: date | None` → `Job.publish_time < 次日 0 点`（含所选最后一天全天）
- 沿用现有路由内联 query 风格；`_SORT_FIELDS`、分页、tag/薪资筛选逻辑不动。NULL publish_time 天然被范围筛选排除。

### 3. 前端 `frontend/src/api/jobs.ts`

- `JobQuery` 增加 `district?`、`publish_time_from?`、`publish_time_to?`
- 新增 `JobFilterOptions` 接口与 `jobsApi.filterOptions(city?: string)`

### 4. 前端 `frontend/src/views/Jobs.vue`

- 城市：`el-input` → `el-select`，选项来自 `filter-options`（onMounted 拉取一次 cities）。
- 区域：新增 `el-select`；城市变化时按当前城市重新拉取 districts，并清空已选 district。
- 发布时间：新增 `el-date-picker type="daterange"`，`value-format="YYYY-MM-DD"`，快捷项：今天 / 近7天 / 近30天 / 近90天。
- `query` 增加 `district`、`publish_time_from/to`；`load()` 组参、`reset()` 一并清空。

### 5. 测试（后端 pytest）

- filter-options：distinct 城市与区域、按 city 联动、路由不被 `/{job_key}` 吞掉（隐含 200 断言）。
- district 精确筛选。
- 发布时间范围：起点/终点都含当天边界、NULL 排除。

前端沿用现有约定（api 层单测 + type-check + build），不引入组件测试框架。

## 验证

- `uv run pytest`（全量绿）
- `npm run type-check`、`npm run test`、`npm run build`
