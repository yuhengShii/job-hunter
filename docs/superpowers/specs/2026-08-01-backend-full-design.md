# 后端全量实现设计（v1）

日期：2026-08-01
状态：已确认（brainstorming 分节通过）
范围：FastAPI 后端全量（数据模型 / 认证 / 任务调度 / Playwright 抓取 / API / 统计）+ pytest 测试。前端另开一轮。

## 1. 背景与目标

51job 职位抓取与分析项目当前仅目录骨架。本轮实现 PRD 全部后端能力：关键字管理、抓取任务（Playwright v1）、职位/公司落库、薪资解析、统计聚合、单用户 JWT 认证、APScheduler 定时任务。测试基于本地 fixture，不访问真实站点。

关键现实约束（已在 brainstorming 阶段实测确认）：

- 51job 搜索页是 SPA，职位列表在渲染后 DOM 中，每张卡片 `.joblist-item` 上带 `sensorsdata` 属性（JSON，字段 jobId/jobTitle/jobSalary/jobArea/companyId/jobLabel/jobTime 等）。
- 搜索页数据 API（`/api/job/search-pc`）被阿里云 WAF 加密，只能走渲染后 DOM。
- 搜索卡片 DOM 已含公司 name/type/industry/size（`.cname` / `.bc .dc`），公司详情页被 WAF 拦截（安全验证页），因此 v1 公司信息主要取自搜索卡片，`fetch_company` 为 best-effort 补充。

## 2. 总体架构

模块划分（`backend/app/`）：

| 模块 | 职责 |
|---|---|
| `core/config.py` | 首次启动生成 `data/config.ini`；`[auth]` username/password/jwt_secret；`[scraper]` max_pages 上限等 |
| `core/database.py` | SQLAlchemy 2.0 engine/SessionLocal/Base；SQLite 在 `data/`；启动建表 |
| `core/security.py` | pbkdf2 密码哈希（hashlib）、JWT 签发/校验（PyJWT） |
| `core/logging.py` | `logs/` 结构化日志 |
| `models/` | users/keywords/scrape_tasks/jobs/companies/settings（字段见 PRD §4） |
| `services/salary.py` | 薪资解析（PRD §4 规则 + 实测补充） |
| `services/stats.py` | 统计聚合（口径见 PRD） |
| `services/task_runner.py` | 单 worker 线程顺序消费 queued 任务 |
| `services/scheduler.py` | APScheduler 定时入队 |
| `scrapers/base.py` | `Scraper` 抽象接口 |
| `scrapers/parser.py` | 纯函数解析（sensorsdata 优先 + DOM 兜底、公司解析） |
| `scrapers/playwright.py` | Playwright v1 实现 |
| `schemas/` | Pydantic 请求/响应模型 |
| `api/` | FastAPI 路由 |
| `main.py` | app 工厂：建表、崩溃恢复、启 worker/scheduler |

## 3. 数据模型

严格按 PRD §4：

- **users**：id, username(唯一), password_hash, created_at
- **keywords**：id, keyword(唯一), enabled, scrape_mode, last_scraped_at, created_at
- **scrape_tasks**：id, keyword_id, mode, status(queued/in_progress/success/partial_success/failed), total_pages, total_found, success_count, failed_count, last_page, start_time, end_time, error_message, created_at
- **jobs**（job_id 唯一 upsert）：id, job_id, title, salary_raw, salary_min, salary_max, city, district, area, tags(JSON), publish_time, source, company_id, job_url, created_at, updated_at
- **companies**（company_id 唯一）：id, company_id, name, type, industry, size, activity, website, created_at, updated_at
- **settings**：id, key(唯一), value(JSON), updated_at

实现细节：
- `jobs.job_url` = `https://jobs.51job.com/<city>/<job_id>.html`；`city`/`district` 由 `jobArea`（如"上海-长宁区"）拆分，无法拆分时 city=原值、district=NULL、area=原值。
- `jobs.publish_time` 取 sensorsdata 的 `jobTime`；`source` = "51job"。
- companies 的 type/industry/size 来自搜索卡片 DOM，activity 默认 NULL（WAF 限制，best-effort 补充）；type 做归一化映射（民营/国企/外企/合资/外资/上市公司/事业单位等，未匹配保留原文）。
- settings 存全局配置：`schedule`（频率/启停/目标关键字）、`scraper.max_pages` 默认上限。

## 4. 认证与配置

- 登录 `POST /api/auth/login`（无 JWT）→ `{access_token, token_type}`；`GET /api/auth/me`。
- JWT 有效期 24h；`get_current_user` 依赖注入解析 Bearer token，失败/过期 401。
- 密码 pbkdf2（`hashlib.pbkdf2_hmac` + 随机盐，不引入 passlib/bcrypt）。
- `data/config.ini` 首次生成：`[auth] username=admin, password=<随机>, jwt_secret=<随机>`，初始密码打印到日志一次（`logger.warning`），用户改后重启生效。

## 5. 抓取模块

### Scraper 抽象（`scrapers/base.py`）

```python
class Scraper(ABC):
    @abstractmethod
    async def search(self, keyword, pages): ...   # AsyncGenerator[PageResult]
    @abstractmethod
    async def fetch_company(self, company_id, company_url): ...  # CompanyDraft | None
    @abstractmethod
    async def close(self): ...
```

- `PageResult`: page_num, total_pages, jobs: list[JobDraft], failed: bool
- `JobDraft`: job_id, title, salary_raw, salary_min, salary_max, city, district, area, tags, publish_time, company_id, job_url
- `CompanyDraft`: company_id, name, type, industry, size, activity, website

### 解析器（`scrapers/parser.py`，纯函数）

- `parse_search_page(html, page_num) -> PageResult`：
  - 每个 `.joblist-item` 卡片，优先读 `sensorsdata` 属性（JSON）：jobId/jobTitle/jobSalary/jobArea/companyId/jobLabel/jobTime/jobSource。
  - 缺失字段 DOM 兜底：标题 `.jname`、薪资 `.sal`、公司 `.cname`、地区 `.area`、标签 `.joblist-item-tags .tag`、job_url 从卡片内 `a[href*='jobs.51job.com']` 解析 job_id。
  - tags：sensorsdata `jobLabel` 非空用之；为空用 `.tag` 列表；仍无则空数组。
  - 总页数：`.el-pager li.number` 末位数字。
  - 公司信息从卡片 `.bc .dc`（三格：行业/类型/规模）与 `.cname` 提取。
  - 页面若为 WAF 验证页（无可解析卡片且含"验证"特征），记 failed。
- `parse_company_page(html) -> CompanyDraft | None`：best-effort；遇安全验证页返回 None。

### Playwright 实现（`scrapers/playwright.py`）

- 无头 Chromium 访问 `https://we.51job.com/pc/search?keyword=<kw>&searchType=2&sortType=0`。
- 等待 `.joblist-item` 渲染；翻页改 URL `&pageNum=N`，页面刷新后重新等待。
- 随机延时、模拟滚动、UA 轮换；单页失败重试 3 次后跳过记 failed。
- headful 降级开关预留（配置 `[scraper] headful=false`）。
- 每页调用 `parser.parse_search_page` 产出结果。

### 薪资解析（`services/salary.py`）

规则（PRD §4 枚举 + 实测补充）：
- `8千-1.2万` → 8000/12000
- `1.5-2万/月` → 15000/20000（`/月` 前缀直接剥）
- `15-20K` → 15000/20000
- `年薪20-30万` → 按年折算（÷12）
- `1-2万`、`1.2-1.9万` → 直接 ×10000
- `x-y千` → ×1000；`x-yK/k` → ×1000
- 后缀剥离：`13薪`/`14薪`/`·13薪` 等先剥掉再解析
- `面议` → NULL；无法解析 → 记日志 + NULL
- 接口：`parse_salary(raw) -> tuple[salary_min, salary_max]`，纯函数可单测。

## 6. 任务编排

- `services/task_runner.py`：后台线程 + asyncio loop，轮询 DB 中 `queued` 任务，逐个执行（天然互斥，同一时刻仅一个任务）。
- 执行流程：标记 `in_progress` + `start_time` → 调 scraper.search 逐页 → 每页后事务内 upsert jobs（按 job_id）/companies（按 company_id），更新 success_count/failed_count/last_page → 结束标 `success`（全页成功）/`partial_success`（部分页失败）/`failed`（首页即失败）+ end_time + total_found。
- 任务创建（API `POST /api/tasks`）：若该 keyword 已有 `queued/in_progress` 任务 → 409。
- `services/scheduler.py`：APScheduler（BackgroundScheduler），按 settings 中 schedule 配置把启用的关键字定时入队。
- 崩溃恢复：`main.py` 启动时，把所有 `queued/in_progress` 任务置 `failed`，error_message="进程重启中断"。

## 7. API 层

- 认证：`POST /api/auth/login`、`GET /api/auth/me`
- 关键字：`GET/POST /api/keywords`、`PUT/DELETE /api/keywords/{id}`、`POST /api/keywords/{id}/toggle`
- 任务：`POST /api/tasks`（keyword_id、mode 可选、max_pages 可选且 ≤ 全局上限；409 冲突）、`GET /api/tasks`、`GET /api/tasks/{id}`、`DELETE /api/tasks/{id}`
- 数据：`GET /api/jobs`（keyword/city/salary 区间/company/tag 筛选 + 分页 + 排序）、`GET /api/jobs/{id}`、`GET /api/companies`（type/industry/size 筛选）
- 统计：`GET /api/stats/overview|salary|company|trend|tags`
- 配置：`GET/PUT /api/settings/schedule`
- 全部响应经 schemas；路由不暴露 ORM。全局 exception handler 映射业务异常到状态码（409 冲突、404、401、400）。

统计口径（PRD）：基于最近一次 `success/partial_success` 任务的 `start_time`，过滤 `jobs.updated_at >= start_time`。
- overview：职位总数、城市数、公司数、薪资可解析数、最近任务状态
- salary：按城市/关键词分组，min/max/中位数
- company：行业/类型/规模占比
- trend：按天新增职位（更新时间）折线
- tags：词频 Top N

## 8. 测试

- pytest + FastAPI TestClient；`backend/tests/`。
- fixture：`backend/tests/fixtures/51job_search.html`（真实抓取）、`51job_company.html`（合成）、`51job_search_api.json` 仅作参考不用于断言。
- 覆盖用例：
  - 薪资解析枚举全规则 + 后缀 + 无法解析
  - 解析器：sensorsdata 优先 / DOM 兜底 / jobLabel 空兜底 / 总页数 / WAF 页
  - upsert 去重（job_id 覆盖更新、company_id 唯一）
  - 统计口径边界（updated_at 窗口）
  - API：登录 401/成功、任务 409 冲突、CRUD、统计
  - 崩溃恢复：启动时 queued/in_progress → failed
- 测试禁用真实网络（Playwright 不启动浏览器，解析纯函数直接用 fixture 字符串）。

## 9. 版本与验证

- 开发依赖：uv add pytest、httpx（TestClient 需要）、pyjwt。
- 验证命令：`uv run pytest backend/tests`；手动冒烟：`uv run uvicorn backend.app.main:app`。
