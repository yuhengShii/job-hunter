# 职位分布统计设计

日期：2026-08-02
状态：已确认（brainstorming 分节通过）
范围：统计看板新增「职位分布」——按城市统计职位数；选择某城市后按该市各区（district）统计。后端新增统计接口 + 前端新增图表卡片。

## 1. 背景

现有统计看板有薪资分布（median）、公司画像、时间趋势、标签词频。用户需要职位数量分布：例如「上海每个区分别有几个职位」。数据已具备：jobs.city/district 由 jobArea（如"上海-长宁区"）拆分，实测 173 条职位中 district 已填充 144 条（浦东新区 55、闵行区 23…），29 条为空需兜底。

## 2. 后端

### 2.1 服务层 `services/stats.py`

新增：

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

- 统计口径与现有接口一致：基于最近一次成功/部分成功任务的 `start_time` 窗口（`get_window_start` + `_windowed_jobs`）。
- 无 `city` → 按城市；有 `city` → 仅统计该城市并按区（district）。
- 空值（city/district 为 NULL 或空串）→ 归入 `"未知"`，与 salary_stats 的"未知"兜底一致。
- items 按 count 降序（`Counter.most_common()`）。

### 2.2 路由 `api/stats.py`

```python
@stats_router.get("/distribution")
def get_distribution(keyword_id: int | None = None, city: str | None = None, db=Depends(get_db), user=Depends(get_current_user)):
    window = stats_service.get_window_start(db, keyword_id)
    return stats_service.distribution_stats(db, window, city=city)
```

JWT 保护（与现有统计路由一致）。

### 2.3 响应形态

```json
{"city": "上海", "items": [{"key": "浦东新区", "count": 55}, {"key": "未知", "count": 29}]}
```

无 city 时 `"city": null`，items 为城市分布。

## 3. 前端

### 3.1 `api/stats.ts`

```ts
export interface DistributionItem {
  key: string
  count: number
}

export interface DistributionResult {
  city: string | null
  items: DistributionItem[]
}

distribution: (keyword_id?: number | null, city?: string | null) =>
  http.get<DistributionResult>('/stats/distribution', { params: { keyword_id, city } }).then((r) => r.data),
```

### 3.2 `Stats.vue` 新增「职位分布」卡片

- 位置：薪资分布卡片之后、公司画像行之前，整行宽度 `el-card`。
- header 右侧 `el-select` 城市选择器：「全部城市」+ 各城市名；**选项来自「全部城市」视图的响应 items**（无需额外接口）。
- 交互：默认请求 `distribution(keyword_id)` 渲染各城市柱状图；选择城市后请求 `distribution(keyword_id, city)` 渲染该市各区柱状图。
- 图表：竖向柱状图（与薪资图一致：tooltip axis、x 轴标签 interval 0 rotate 30、`barMaxWidth: 40`、`useChart` 复用）。
- 联动：页面顶部关键字筛选（keywordId ref）改变时一并刷新；空 items 时 `?? []` 空渲染不报错。
- 切换城市后加载中显示 v-loading（跟随现有卡片模式，可复用 `loading` 状态或独立 ref）。

## 4. 测试

### 后端 pytest

- 窗口过滤：窗口外职位不计入。
- 无 city → 按城市分组计数正确。
- 有 city → 仅该城市职位、按区分组；其他城市职位排除。
- 未知兜底：district 为 NULL 计入"未知"。
- 排序：items 按 count 降序。
- API：TestClient 带 JWT 调用 `/api/stats/distribution`，参数 keyword_id/city 生效；未认证 401。

### 前端

- 不新增自动化测试（沿用项目约定：组件/页面不测）；`npm run type-check`、`npm run test`（23 项保持绿）、`npm run build`。
- 手动冒烟：默认城市柱状图 → 选「上海」→ 各区柱状图 → 关键字筛选联动。

## 5. 验收

- `uv run pytest backend/tests` 全绿（含新增用例）。
- `npm run type-check` / `npm run test` / `npm run build` 通过。
- 浏览器冒烟：分布卡片两个视图渲染正确。
