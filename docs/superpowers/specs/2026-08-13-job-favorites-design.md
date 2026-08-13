# 职位收藏功能设计

## 1. 目标

职位列表页支持：
- 每行职位前有收藏按钮（星标），点击切换收藏状态
- 批量收藏 / 批量取消收藏（表格多选 + 工具栏按钮）
- 按收藏状态筛选（下拉框三态：全部 / 已收藏 / 未收藏）

## 2. 存储方案（方案 A：独立 favorites 表）

新增 `favorites` 表（`backend/app/models/favorite.py`）：

| 字段 | 类型 | 说明 |
|---|---|---|
| id | int PK | |
| job_id | String(64) | 唯一索引，指向 jobs.job_id（无外键，与 companies 同风格） |
| created_at | DateTime | 默认 now |

- 单用户系统，不加 user_id（PRD §2 认证为单用户，YAGNI）。
- 抓取任务按 `job_id` upsert 职位时不会触碰 favorites 表，收藏在职位被重抓覆盖后依然有效；`services/storage.py` 零改动。
- `Base.metadata.create_all` 自动建新表，无需 `_migrate_*`。

## 3. API 设计（扩展 backend/app/api/jobs.py）

沿用现有风格（AppError、response_model、`Depends(get_current_user)`）。

### 3.1 `POST /api/jobs/favorites`

- 请求体 `FavoriteBatchIn { job_ids: list[str] }`（job_ids 空列表返回 400；非空去重）
- 行为：仅插入 jobs 表中存在的 job_id；已收藏的幂等跳过；不存在于 jobs 表的 job_id 跳过并计入 skipped
- 响应 `FavoriteBatchOut { added: int, skipped: int }`

### 3.2 `DELETE /api/jobs/favorites`

- 请求体同上
- 行为：幂等批量删除，不存在的 job_id 忽略
- 响应 `FavoriteBatchOut { removed: int, skipped: int }`（skipped = 请求中未处于收藏状态的 job_id 数）

### 3.3 `GET /api/jobs` 新增 `favorite` 查询参数

- `favorite: bool | None = None`：None=全部，true=仅已收藏，false=仅未收藏
- 实现：`Job.job_id IN (select job_id from favorites)` 的 EXISTS 子查询（true 时），NOT EXISTS（false 时）

### 3.4 `JobOut` 新增字段

- `is_favorite: bool = False`
- 列表接口按 `_with_company` 同款模式：批量查询当前页 job_ids 的收藏集合后回填（避免 N+1）
- `GET /api/jobs/{job_id}` 详情接口同样回填

### 3.5 Schemas（backend/app/schemas/job.py）

- `FavoriteBatchIn { job_ids: list[str] }`
- `FavoriteBatchOut { added: int, skipped: int }`

## 4. 前端

### 4.1 `frontend/src/api/jobs.ts`

- `JobOut` 接口加 `is_favorite: boolean`
- `JobQuery` 加 `favorite?: boolean`
- 新增 `jobsApi.addFavorites(jobIds: string[])`、`jobsApi.removeFavorites(jobIds: string[])`（`http.post`/`http.delete`，body `{ job_ids }`）

### 4.2 `frontend/src/views/Jobs.vue`

- **收藏列（首列）**：`el-table-column` 内放星标按钮（`el-button link` + `el-icon` StarFilled/Star），点击切换收藏并 `stopPropagation`，不触发行点击打开详情；切换后刷新当前页数据
- **多选列**：`type="selection"` 列（置于收藏列之后），`@selection-change` 记录选中行
- **批量按钮**：表格上方工具栏加"批量收藏 / 批量取消收藏"，无选中时禁用；操作完成后清空选中并刷新
- **筛选**：筛选表单加"收藏"下拉（全部 / 已收藏 / 未收藏），映射为 `favorite` 参数（undefined / true / false）；随查询参数一并提交，重置时清空
- 不做乐观更新，操作成功后重新拉取当前页（与现有页面风格一致）

## 5. 测试

### 后端（backend/tests/，TestClient 模式同 test_jobs_api.py）

- 批量收藏：正常添加、重复添加幂等、不存在的 job_id 跳过计数、空列表 400
- 批量取消：正常移除、幂等
- `GET /api/jobs?favorite=true/false` 筛选正确
- 列表与详情返回 `is_favorite` 正确
- 未认证请求 401

### 前端（frontend/tests/，vitest 纯逻辑模式）

- `jobsQuery` 或 api 层相关纯函数测试（若引入收藏参数映射逻辑）；不引入组件挂载测试（现有项目无 @vue/test-utils）

## 6. 非目标（YAGNI）

- 收藏页独立路由/页面（用户已选择筛选形式，不需要）
- 详情弹窗内收藏按钮
- 多用户收藏隔离
- 收藏列表排序/导出