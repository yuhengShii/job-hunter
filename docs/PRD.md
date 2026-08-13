# 需求文档

## 1. 项目定位

- **目标**：按关键字抓取招聘网站（51job 优先）的职位与公司数据，存储到本地 SQLite，用于数据积累与市场分析（薪资、行业、公司画像、时间趋势等）。
- **范围**：v1 仅实现 51job 抓取；架构上预留智联招聘、Boss直聘的扩展位。
- **部署**：本机 Windows 运行，前后端分离。

## 2. 技术栈

| 层 | 技术 |
|---|---|
| 后端 | Python 3.14 + FastAPI + SQLAlchemy + APScheduler + Playwright |
| 抓取 | v1 用 Playwright（无头浏览器）；v2 预留 firecrawl（同一 Scraper 接口） |
| 数据库 | SQLite 单文件 |
| 前端 | Vue3 + Vite + Element Plus + ECharts + Pinia + Vue Router |
| 认证 | 单用户，用户名+密码，JWT |

> 依赖清单（pyproject.toml）需包含：fastapi、sqlalchemy、apscheduler、playwright；firecrawl 为 v2 预留，v1 可先不装。

## 3. 系统架构

前后端分离：Vue3 前端通过 REST/JWT 调 FastAPI。

后端包含：
- 认证模块（单用户 + JWT）
- 任务调度（APScheduler 进程内定时任务）
- 抓取引擎（Scraper 抽象接口，PlaywrightScraper v1 实现、FirecrawlScraper v2 预留）
- 数据层（SQLAlchemy + SQLite）

前端创建抓取任务时可选择抓取方式。

## 4. 数据模型（SQLite）

- **users**：id, username, password_hash, created_at
- **keywords**：id, keyword, city(51job 城市编码，000000=全国), enabled, scrape_mode(默认抓取方式), industry(逗号分隔行业编码，NULL=不过滤), last_scraped_at, created_at —— **(keyword, city) 联合唯一**，同一岗位词可分别抓不同城市
- **scrape_tasks**：id, keyword_id, mode, status(排队/进行中/成功/失败/部分成功), total_pages, total_found, success_count, failed_count, last_page(已抓到的最大页号), start_time, end_time, error_message, created_at
- **jobs**（job_id 唯一，覆盖更新）：id, job_id, title, salary_raw, salary_min, salary_max, city, district, area, degree(学历), year(工作年限), tags(JSON), publish_time, source, company_id, job_url, created_at, updated_at
- **companies**（company_id 唯一）：id, company_id, name, type(民营/国企/外企), industry, size, activity, activity_score(0-10 活跃值，-1=未知，由 activity 文案按固定规则映射，规则见 §6), created_at, updated_at
- **settings**：id, key(唯一), value(JSON), updated_at —— 存全局配置（如 schedule：频率、启停、目标关键字）

索引与类型：job_id、company_id、(keyword, city)、settings.key 建唯一索引；keyword_id、created_at 建普通索引；publish_time、start_time、end_time、created_at、updated_at 均存 datetime。

说明：
- city 使用 51job 6 位城市编码（如 010000 北京 / 020000 上海 / 030200 广州 / 040000 深圳 / 080200 杭州 / 170200 郑州），000000 表示全国；前端维护编码表，后端仅存编码。
- industry 为 51job 行业字典叶子编码（如 47=医疗设备/器械），逗号分隔多选，最多 5 个（与搜索页"其他筛选"行为一致）；空串与 NULL 均视为不过滤；行业筛选通过搜索 URL 的 `industry` 参数生效（SPA 读取该参数并透传搜索 API，翻页保持）。
- salary_raw 解析为 salary_min/max，规则枚举：`8千-1.2万`→8000/12000、`1.5-2万/月`→15000/20000、`15-20K`→15000/20000、`年薪20-30万`→按年折算、`面议`→NULL（统计时跳过），无法解析的格式记入 error 日志并置 NULL。
- tags：优先取 sensorsdata 的 jobLabel，为空时走 DOM 兜底，仍无则存空数组。
- degree/year：优先取 sensorsdata 的 jobDegree/jobYear，缺失时按卡片文本中"本科/大专/硕士…"与"N年及以上/N-M年…"关键词兜底，仍无则 NULL（历史数据无法回填，重抓后补齐）。
- activity 由搜索卡片 `.joblist-item-jobinfo .tip` 的全部文案（`、` 拼接）构成；activity_score 按固定规则映射（规则见 §6），多标签取各标签最高分，无法识别或为空记 -1。
- `GET /api/jobs` 响应中携带 `company_activity_score`（0-10，-1 表示未知）。

### 统计口径

所有统计（overview/salary/company/trend/tags）均基于**最近一次成功或部分成功的任务**覆盖的职位：`jobs.updated_at >= 该任务 start_time`。已下架职位自然被排除；部分成功任务可能混入少量旧职位，属可接受误差，任务状态会在界面标识。

### 4.1 站点凭据与登录抓取

- **site_credentials**（站点登录凭据，为「一键投简历」与「登录后抓取」提供账号来源）：id, site(站点标识，v1 仅 51job), username, password_enc(AES-GCM 加密), remark, created_at, updated_at —— (site, username) 联合唯一。
- **密码安全**：密码用 AES-GCM 加密存储（密钥在 data/config.ini 的 [site] secret，32 字节随机），任何 API 响应不回传密码，仅返回 has_password。
- **scrape_tasks** 增加 login_credential_id（NULL=匿名/全局默认）。
- **登录后抓取开关**：默认不登录。`POST /api/tasks` 可选 login_credential_id（任务级优先）；全局默认存 settings 表 scraper_login（enabled + credential_id），未指定任务且全局开启时自动采用。登录失败自动降级为匿名抓取并记日志。
- **测试登录**：`POST /api/site-credentials/{id}/test-login` 实际登录验证凭据可用性。
- **删除限制**：凭据被进行中/排队中任务引用时删除返回 409；已完成/失败任务引用置 NULL。

## 5. API 设计

除 `POST /api/auth/login` 外，所有接口均需携带 JWT（`Authorization: Bearer`）。

- 认证：`POST /api/auth/login`、`GET /api/auth/me`
- 关键字：`GET/POST /api/keywords`（POST 支持 `keyword`、`city`，缺省 000000、`industry`，缺省 NULL=不过滤）、`PUT/DELETE /api/keywords/{id}`、`POST /api/keywords/{id}/toggle`
  - 唯一性：同 keyword 不同 city 可共存；同 keyword 同 city 返回 409
- 任务：`POST /api/tasks`、`GET /api/tasks`、`GET /api/tasks/{id}`、`DELETE /api/tasks/{id}`
  - `POST /api/tasks` 请求参数：`keyword_id`、`mode`（可选，默认取 keywords.scrape_mode）、`max_pages`（可选，默认取配置，需 ≤ 全局上限）
  - `POST /api/tasks` 响应：任务 id 与状态；若该 keyword 已有进行中任务，返回 409 与冲突说明
- 数据：`GET /api/jobs`（筛选/分页/排序）、`GET /api/jobs/{id}`、`GET /api/companies`
- 统计：`GET /api/stats/overview`、`/api/stats/salary`、`/api/stats/company`、`/api/stats/trend`、`/api/stats/tags`
- 配置：`GET/PUT /api/settings/schedule`（持久化到 settings 表）
- 凭据：`GET/POST /api/site-credentials`、`PUT/DELETE /api/site-credentials/{id}`、`POST /api/site-credentials/{id}/test-login`

## 6. 抓取模块（v1 Playwright）

- `Scraper` 抽象接口：`search(keyword, pages, area, industry)` 逐页产出解析结果。
- PlaywrightScraper 实现：
  - 无头 Chromium 访问 51job 搜索页并翻页，遍历所有页（单任务最大页数可配置）。
  - 搜索 URL 携带 `jobArea={area}`（来自 keywords.city），不指定时默认 000000（51job 站点默认上海，注意区分）；`industry`（来自 keywords.industry）存在时追加 `&industry={编码}` 参数（SPA 读取该参数透传搜索 API，翻页保持）。
  - 优先解析 HTML 中 `sensorsdata` 属性（jobId/jobTitle/jobSalary/jobArea/companyId 等，见 tt.py 样例），缺失字段走 DOM 选择器兜底。
  - activity_score 映射规则：`刚刚活跃`→10、`今日回复10+次`→10、`今日回复N次`→min(N,10)（受 0-10 刻度约束，N>10 时截断为 10）、`今日活跃`→9、`N分钟前回复`/`N分钟前处理简历`→max(0, 10-⌈N/2⌉)（1 分钟→10）、`回复率高`→8、`简历处理快`→7、`喜欢聊天`→6、`N天内处理简历`/活跃天数`N天`→max(1, 11-N)；多标签取各标签最高分，全部无法识别或为空记 -1。
  - 反爬策略：随机延时（3-8 秒）、模拟滚动、User-Agent 轮换、反自动化指纹（`--disable-blink-features=AutomationControlled` + init script 抹除 navigator.webdriver 等）；失败页重试 3 次后跳过并记失败。
  - **自动降级**：解析到 WAF 标记（安全验证/验证码）时立即、或无标记连续 2 页失败时，自动切换为有头模式并重试当前页（预留 headful 降级开关亦保留）。
  - **滑块验证应对**：检测到滑块验证码（aliyunCaptcha）时自动拟人轨迹拖动尝试通过（best-effort，阿里云行为验证对自动化轨迹通过率低）；失败则冷却等待（90 秒）后重试该页，再失败跳过并记失败。实测：51job 风控为滚动窗口，冷却后自动解除（无需人工介入）；headful 模式下可人工拖动兜底。
  - 每页抓完上报一次进度（成功/失败计数、last_page）到 scrape_tasks。
  - 按 job_id upsert 覆盖更新。
  - **并发互斥**：同一 keyword 同时只允许一个进行中任务；创建任务时若已存在进行中任务则拒绝（API 返回 409）。
  - **崩溃恢复**：进程重启时，将所有 status=进行中 的任务置为失败并记录 error_message（v1 不续抓，人工重新触发；last_page 字段为 v2 断点续抓预留）。
  - **进度**：total_pages 在抓取首页解析出总页数后才有值，此前前端进度显示为"已抓 N 页"。
- FirecrawlScraper（v2 预留）：实现同一 Scraper 接口，抓取页面后复用同一套解析逻辑。

## 7. 前端页面

1. **登录页**：用户名 + 密码，本地单用户；首次启动若无用户则自动创建默认账号（用户名/密码从环境变量或配置文件读取）。
2. **任务控制台**：关键字管理（增删改查、启停定时）、新建抓取任务（选关键字 + 抓取方式，v1 仅开放 Playwright）、任务列表（状态/进度条/耗时）、定时任务设置（频率、启停、目标关键字）。
3. **职位列表页**：表格展示职位/薪资/城市/公司/标签/发布时间，顶部按关键字/城市/薪资区间/公司/标签筛选排序，点击查看详情。
4. **公司列表页**：表格 + 按类型/行业/规模筛选。
5. **统计看板**：薪资分布（按城市/关键词柱状图）、公司画像（行业/类型/规模占比饼图）、时间趋势（折线图）、标签词频 Top N（条形图/词云）。
6. **站点账号页**：招聘网站登录凭据管理（增删改查、测试登录），为「登录后抓取」与后续「一键投简历」提供账号。

## 8. 非功能需求

- **错误处理**：单页失败重试 3 次后跳过；单任务内部分页失败仍入库成功页，任务状态标"部分成功"；进程崩溃重启后将进行中的任务置为失败（详见 §6 崩溃恢复）。
- **日志**：结构化日志，记录抓取任务每个阶段的耗时、失败原因。
- **限速与合规**：请求间隔随机化（防封）、单任务最大页数可配置；遇到风控（滑块验证）时自动解验证并冷却等待，仍失败则跳过不纠缠；仅限个人学习/分析，遵守网站 robots 与 ToS，频率克制。
- **测试**：pytest + Playwright 覆盖解析（本地 HTML fixture）、API（TestClient）、去重、薪资解析、统计聚合边界用例。
- **版本规划**：v1 = Playwright 抓取 + 全流程界面；v2 = 接入 firecrawl 抓取方式（界面选项已预留）。
