# job-hunter

按关键字抓取招聘网站（51job 优先）的职位与公司数据，存储到本地 SQLite，用于数据积累与市场分析（薪资、行业、公司画像、时间趋势等）。仅限个人学习/分析用途。

需求以 [docs/PRD.md](docs/PRD.md) 为准。

## 技术栈

| 层 | 技术 |
|---|---|
| 后端 | Python 3.14 + FastAPI + SQLAlchemy + APScheduler + Playwright |
| 抓取 | v1 Playwright（无头浏览器）；v2 预留 Firecrawl（同一 Scraper 接口） |
| 数据库 | SQLite 单文件（`data/`） |
| 前端 | Vue3 + Vite + Element Plus + ECharts + Pinia + Vue Router |
| 认证 | 单用户，用户名+密码，JWT |

## 功能

- 关键字管理、定时任务调度（APScheduler）
- Playwright 抓取 51job 职位与公司详情，失败页重试后跳过、每页进度上报
- 职位/公司数据落库（按 job_id / company_id 去重覆盖）
- 薪资解析（如 `8千-1.2万` → 8000/12000）、统计看板（薪资/公司画像/时间趋势/标签词频）
- 前端任务控制台、职位列表、公司列表、统计看板

## 目录结构

```
backend/app/        FastAPI 后端包
  api/              路由（auth/keywords/tasks/jobs/companies/stats/settings）
  core/             配置、JWT、日志
  models/           SQLAlchemy 模型
  schemas/          Pydantic 模型
  scrapers/         Scraper 抽象 + Playwright v1 + Firecrawl v2 预留
  services/         薪资解析、统计聚合、任务调度
backend/tests/      pytest 测试（fixtures/ 放本地 HTML 样例）
frontend/            Vue3 前端（src/views、src/stores、src/api、src/components）
data/               SQLite 数据库
logs/               日志
```

## 快速开始

```bash
# 安装依赖（Python 3.14 + uv）
uv add fastapi sqlalchemy apscheduler playwright
uv run playwright install chromium                 # 安装浏览器

# 运行后端（main.py 实现后可用）
uv run uvicorn backend.app.main:app --reload

# 前端（Node 24+）
cd frontend && npm install
npm run dev          # 开发：http://localhost:5173（proxy /api → 127.0.0.1:8000）

# 生产：构建后由后端单端口托管
npm run build        # 产出 frontend/dist，直接访问 http://127.0.0.1:8000
```

## 开发

- 依赖管理用 `uv`（`uv add <pkg>`）
- 测试：`uv run pytest backend/tests`
- 前端（frontend/）：`npm run test`（vitest）、`npm run type-check`
- 后端约定见 [AGENTS.md](AGENTS.md)

## 状态

- [x] 依赖安装、目录骨架
- [x] 后端：数据模型 / 认证 / 任务调度 / 抓取引擎 / API / 统计
- [x] 前端：Vue3 脚手架与页面
- [ ] 测试：解析（HTML fixture）、API、薪资解析、统计聚合、前端 vitest
