# AGENTS.md

51job 职位数据抓取与分析项目（前后端分离）。**`docs/PRD.md` 是唯一权威需求文档**（数据模型、API、统计口径、抓取架构都在里面）；`PRD_backup.md` 是旧备份，不要改、不要参考。代码规范见 `docs/code-style.md`（已随会话自动加载）。

## 环境与工具

- Windows + Python 3.14 + uv（`uv.lock` 已存在）。git 身份已配置（Euan <yuhengshi@foxmail.com>），直接 `git commit` 即可。
- 依赖已齐：fastapi、sqlalchemy、apscheduler、playwright、firecrawl（v2 预留）。Playwright chromium 已装到 `%LOCALAPPDATA%\ms-playwright`，不再需要 `playwright install`。新增依赖用 `uv add`。
- 前端完全没有脚手架（无 package.json），按 PRD 规划为 Vue3 + Vite + Element Plus + ECharts + Pinia + Vue Router。

## 目录约定

- 后端代码在 `backend/app/` 包内：`api/`（路由）、`core/`（配置/JWT/日志）、`models/`（SQLAlchemy）、`schemas/`（Pydantic）、`scrapers/`（Scraper 抽象 + Playwright v1 + Firecrawl v2 预留）、`services/`（薪资解析/统计/APScheduler）。
- 测试在 `backend/tests/`，本地 HTML fixture 放 `backend/tests/fixtures/`（pytest + Playwright 计划，未实现）。
- SQLite 数据库放 `data/`，日志放 `logs/`（均已被 gitignore，仅保留 `.gitkeep`）。
- `tt.py` 和 `job.xml` 是 51job 搜索结果页 HTML 样例（含 `sensorsdata` JSON，字段如 jobId/jobTitle/jobSalary/jobArea/companyId/jobLabel）——解析逻辑的参考样例，**不是可执行代码**（tt.py 是残缺文件，勿运行）。

## 必须遵循的 PRD 规则（实现时）

- jobs 按 `job_id` upsert 覆盖更新；companies 按 `company_id` 唯一。
- 薪资解析规则枚举在 PRD §4（`8千-1.2万`→8000/12000 等），无法解析记日志并置 NULL。
- 所有统计基于**最近一次成功/部分成功任务**覆盖的职位（`jobs.updated_at >= 任务 start_time`）。
- 同一 keyword 同时只允许一个进行中任务，冲突返回 409；进程重启时进行中任务置为失败（v1 不续抓）。

## 当前状态

仓库处于起步阶段：仅目录骨架（.gitkeep）+ 依赖，无业务代码。未提交改动：`PRD.md` 已 `git mv` 至 `docs/PRD.md`（已暂存）、`README.md`/`AGENTS.md` 有修改、`docs/code-style.md` 与 `opencode.json` 未跟踪（`opencode.json` 挂载 instructions，修改后需重启 opencode 生效）；`tt.py`、`job.xml`、`PRD_backup.md` 未跟踪（均建议不提交）。远程 `origin` 指向 https://github.com/yuhengShii/job-hunter.git。
