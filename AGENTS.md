# AGENTS.md

51job 职位数据抓取与分析项目（前后端分离，Windows 本机运行）。**`docs/PRD.md` 是唯一权威需求文档**（数据模型、API、统计口径、抓取架构都在里面）；代码规范见 `docs/code-style.md`。两者均经 `opencode.json` 随会话自动加载，修改后需重启 opencode 生效。

## 环境与工具

- Windows + Python 3.14 + uv（`uv.lock` 已提交）。git 身份已配置（Euan <yuhengshi@foxmail.com>），直接 `git commit` 即可。
- 依赖已装：fastapi、sqlalchemy、apscheduler、playwright、firecrawl（v2 预留）。Playwright chromium 已装到 `%LOCALAPPDATA%\ms-playwright`，勿再 `playwright install`。新增依赖用 `uv add`。
- **Windows 编码**：中文系统终端默认 GBK，Python stdout 与 PowerShell 管道均按 GBK 编码，显示端按 UTF-8 解码会乱码。规则：凡执行涉及中文输出的命令（读日志、`uv run python -c` 打印等），一律在命令前设 `$env:PYTHONUTF8 = "1"`；启动服务同理（见 `docs/code-style.md`）。日志文件本身是 UTF-8（`logging.py` 已指定），乱码只发生在终端传输环节。
- 前端见 `frontend/`（Vue3 + Vite + TS，npm scripts：dev/build/type-check/test；dev proxy /api → 127.0.0.1:8000；生产构建产物由后端静态托管）。

## 目录约定

- 后端代码在 `backend/app/` 包内：`api/`（路由，只做校验与响应组装）、`core/`（配置/JWT/日志）、`models/`（SQLAlchemy）、`schemas/`（Pydantic，禁止在路由中暴露 ORM 对象）、`scrapers/`（Scraper 抽象 + Playwright v1 + Firecrawl v2 预留）、`services/`（薪资解析/统计/APScheduler）。
- 测试在 `backend/tests/`，本地 HTML fixture 放 `backend/tests/fixtures/`（pytest，63 项全绿；测试禁止访问真实 51job）。
- SQLite 数据库放 `data/`，日志放 `logs/`（均已被 gitignore，仅保留 `.gitkeep`）。

## 必须遵循的 PRD 规则（实现时）

- jobs 按 `job_id` upsert 覆盖更新；companies 按 `company_id` 唯一。
- 薪资解析规则枚举在 PRD §4（`8千-1.2万`→8000/12000 等），无法解析记日志并置 NULL；tags 优先 sensorsdata 的 jobLabel，为空走 DOM 兜底，仍无则存空数组。
- 所有统计基于**最近一次成功/部分成功任务**覆盖的职位（`jobs.updated_at >= 任务 start_time`）。
- 同一 keyword 同时只允许一个进行中任务，冲突返回 409；进程重启时进行中任务置为失败（v1 不续抓）。
- 解析优先 HTML 中 `sensorsdata` 属性，缺失字段走 DOM 选择器兜底（sensorsdata 样例字段：jobId/jobTitle/jobSalary/jobArea/companyId/jobLabel）。

## 当前状态

后端 v1 已实现（数据模型 / 认证 / 任务调度 / 抓取引擎 / API / 统计，pytest 全绿）；前端 v1 已实现（5 个页面，vitest + type-check + build 通过，手动冒烟通过）。生产模式由后端单端口托管 `frontend/dist`（`uv run uvicorn backend.app.main:app`）。远程 `origin` 指向 https://github.com/yuhengShii/job-hunter.git。
