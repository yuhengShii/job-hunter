# AGENTS.md

51job 职位数据抓取与分析项目（前后端分离，Windows 本机运行）。**`docs/PRD.md` 是唯一权威需求文档**（数据模型、API、统计口径、抓取架构都在里面）；代码规范见 `docs/code-style.md`。两者均经 `opencode.json` 随会话自动加载，修改后需重启 opencode 生效。

## 环境与工具

- Windows + Python 3.14 + uv（`uv.lock` 已提交）。git 身份已配置（Euan <yuhengshi@foxmail.com>），直接 `git commit` 即可。
- 依赖已装：fastapi、sqlalchemy、apscheduler、playwright、firecrawl（v2 预留）。Playwright chromium 已装到 `%LOCALAPPDATA%\ms-playwright`，勿再 `playwright install`。新增依赖用 `uv add`。
- 前端完全没有脚手架（无 package.json），按 PRD 规划为 Vue3 + Vite + Element Plus + ECharts + Pinia + Vue Router。

## 目录约定

- 后端代码在 `backend/app/` 包内：`api/`（路由，只做校验与响应组装）、`core/`（配置/JWT/日志）、`models/`（SQLAlchemy）、`schemas/`（Pydantic，禁止在路由中暴露 ORM 对象）、`scrapers/`（Scraper 抽象 + Playwright v1 + Firecrawl v2 预留）、`services/`（薪资解析/统计/APScheduler）。
- 测试在 `backend/tests/`，本地 HTML fixture 放 `backend/tests/fixtures/`（pytest，计划中未实现；测试禁止访问真实 51job）。
- SQLite 数据库放 `data/`，日志放 `logs/`（均已被 gitignore，仅保留 `.gitkeep`）。

## 必须遵循的 PRD 规则（实现时）

- jobs 按 `job_id` upsert 覆盖更新；companies 按 `company_id` 唯一。
- 薪资解析规则枚举在 PRD §4（`8千-1.2万`→8000/12000 等），无法解析记日志并置 NULL；tags 优先 sensorsdata 的 jobLabel，为空走 DOM 兜底，仍无则存空数组。
- 所有统计基于**最近一次成功/部分成功任务**覆盖的职位（`jobs.updated_at >= 任务 start_time`）。
- 同一 keyword 同时只允许一个进行中任务，冲突返回 409；进程重启时进行中任务置为失败（v1 不续抓）。
- 解析优先 HTML 中 `sensorsdata` 属性，缺失字段走 DOM 选择器兜底（sensorsdata 样例字段：jobId/jobTitle/jobSalary/jobArea/companyId/jobLabel）。

## 当前状态

仓库处于起步阶段：仅目录骨架（.gitkeep）+ 依赖，无业务代码；全部改动已提交，工作区干净。远程 `origin` 指向 https://github.com/yuhengShii/job-hunter.git。
