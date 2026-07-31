# 代码规范

自动随 opencode 会话加载。冲突时以 docs/PRD.md 为准。

## 通用

- Python 3.14，依赖用 `uv add` 管理，提交 `uv.lock`。
- 文件名/包名小写下划线；模块职责单一，大文件及时拆分。
- 时间字段一律 datetime（PRD §4），不存字符串；入参由 Pydantic 校验。
- 不提交敏感信息；`data/`、`logs/` 已被 gitignore。

## 后端（backend/app/）

- **SQLAlchemy 2.0 风格**：`Mapped[...]` + `mapped_column`，模型放 `models/`，字段命名与 PRD §4 表结构一一对应（users / keywords / scrape_tasks / jobs / companies / settings）。
- **分层**：路由（`api/`）只做参数校验与响应组装；业务逻辑在 `services/`；`schemas/` 定义请求/响应 Pydantic 模型，**禁止**在路由中直接暴露 ORM 对象。
- **错误处理**：自定义业务异常 + 全局 exception handler 映射 HTTP 状态码；不裸 `try/except` 吞异常。同一 keyword 并发任务冲突必须返回 409（PRD §5）。
- **抓取**：必须实现 `scrapers/` 的 Scraper 抽象接口（v2 firecrawl 复用同一解析逻辑）；解析优先 sensorsdata，缺失走 DOM 兜底；薪资解析规则严格按 PRD §4 枚举实现，无法解析记日志并置 NULL。
- **日志**：结构化日志输出到 `logs/`，记录任务阶段耗时与失败原因（PRD §8）。
- **统计口径**：一律基于最近一次成功/部分成功任务的 `start_time` 窗口（`jobs.updated_at >= start_time`）。

## 测试（backend/tests/）

- pytest；解析类测试使用 `backend/tests/fixtures/` 的本地 HTML，禁止在测试中访问真实 51job。
- 覆盖：薪资解析、去重 upsert、统计聚合边界、API（TestClient）。

## 前端（frontend/，尚未搭建）

- Vue3 `<script setup>` 组合式 API；页面在 `src/views/`，状态在 `src/stores/`（Pinia），请求封装在 `src/api/`。
- API 调用统一带 JWT；组件不直接发请求，走 `api/` 封装。
