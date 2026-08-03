# 职位分布统计设计

日期：2026-08-02
状态：已确认（brainstorming 分节通过）；2026-08-02 修订——按用户反馈改为与薪资分布一致的三档分组（按城市/按区域/按地区），并由同一个下拉框同时控制薪资分布与职位分布（移除原 city 参数与城市选择器）。
范围：统计看板新增「职位分布」——按城市/区域/地区统计职位数；与薪资分布共用分组下拉。

## 1. 背景

现有统计看板有薪资分布（median，支持按城市/区域/地区分组）、公司画像、时间趋势、标签词频。用户需要职位数量分布（例如「上海每个区分别有几个职位」），并要求与薪资分布一致的三档分组 + 共享下拉。数据已具备：jobs.city/district/area 由 jobArea（如"上海-长宁区"）拆分，实测 173 条职位中 district 已填充 144 条（浦东新区 55、闵行区 23…），29 条为空需兜底。

## 2. 后端

### 2.1 服务层 `services/stats.py`

```python
def distribution_stats(db: Session, window: datetime | None, group_by: str = "city") -> dict:
    jobs = _windowed_jobs(db, window).all()
    counter: Counter = Counter()
    for j in jobs:
        key = getattr(j, group_by, None) or "未知"
        counter[key] += 1
    items = [{"key": k, "count": n} for k, n in counter.most_common()]
    return {"group_by": group_by, "items": items}
```

- 与 `salary_stats` 完全同构（group_by 取值 city/district/area，getattr + 未知兜底 + 降序）。
- 统计口径与现有接口一致：基于最近一次成功/部分成功任务的 `start_time` 窗口（`get_window_start` + `_windowed_jobs`）。
- 空值 → `"未知"`，与 salary_stats 一致。

### 2.2 路由 `api/stats.py`

```python
@stats_router.get("/distribution")
def get_distribution(keyword_id: int | None = None, group_by: str = "city", db=Depends(get_db), user=Depends(get_current_user)):
    window = stats_service.get_window_start(db, keyword_id)
    return stats_service.distribution_stats(db, window, group_by=group_by)
```

JWT 保护（与现有统计路由一致）。

### 2.3 响应形态

```json
{"group_by": "district", "items": [{"key": "浦东新区", "count": 55}, {"key": "未知", "count": 29}]}
```

## 3. 前端

### 3.1 `api/stats.ts`

```ts
export interface DistributionItem {
  key: string
  count: number
}

export interface DistributionResult {
  group_by: string
  items: DistributionItem[]
}

distribution: (keyword_id?: number | null, group_by = 'city') =>
  http.get<DistributionResult>('/stats/distribution', { params: { keyword_id, group_by } }).then((r) => r.data),
```

### 3.2 `Stats.vue`

- 顶部筛选行新增共享「分组」下拉（按城市/按区域/按地区），与关键字筛选并排；`@change="reload"` 同时刷新薪资分布与职位分布两张图（与关键字切换同路径，共享 statsSeq 守卫）。
- 薪资分布卡片 header 移除原内嵌下拉；职位分布卡片移除原城市选择器，标题固定「职位分布」。
- 删除 `distCity`/`distCityOptions`/`loadSalary`/`loadDistribution`（由 `reload()` 统一覆盖）。
- 图表：两张竖向柱状图，`useChart` 复用，空 items 时 `?? []` 空渲染不报错。

## 4. 测试

### 后端 pytest

- 窗口过滤：窗口外职位不计入。
- 按城市（默认 group_by=city）：分组计数正确。
- 按区域（group_by=district）与按地区（group_by=area）：分组计数正确，未知兜底（空值计入"未知"）。
- 排序：items 按 count 降序。
- API：TestClient 带 JWT 调用 `/api/stats/distribution`，参数 keyword_id/group_by 生效；未认证 401。

### 前端

- 不新增自动化测试（沿用项目约定：组件/页面不测）；`npm run type-check`、`npm run test`（23 项保持绿）、`npm run build`。
- 手动冒烟：顶部共享分组下拉切换「按城市/按区域/按地区」→ 薪资分布与职位分布两图同时刷新；关键字筛选联动。

## 5. 验收

- `uv run pytest backend/tests` 全绿（含新增用例）。
- `npm run type-check` / `npm run test` / `npm run build` 通过。
- 浏览器冒烟：共享下拉切换三档分组，两张图均正确刷新。
