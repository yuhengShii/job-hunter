# 站点凭据管理（site_credentials）设计文档

日期：2026-08-13
状态：已确认
关联文档：docs/PRD.md（唯一权威需求文档，本节设计落地后需同步 PRD）

## 1. 背景与目标

为后续「一键投简历」功能储备招聘网站登录凭据；同时为「登录后抓取」提供账号来源，抓取是否登录做成开关、**默认不登录**（保持现状匿名抓取）。

- 本期核心：站点凭据的增删改查管理页 + 加密存储 + 测试登录。
- 本期次核心：「登录后抓取」开关（任务级选择 + 全局默认，默认关闭）。
- 本期不做：一键投简历、凭据轮换、登录态持久化到磁盘。

## 2. 数据模型

### 2.1 新表 `site_credentials`

| 字段 | 类型 | 说明 |
|---|---|---|
| id | int PK | |
| site | String(32) | 站点标识，本期仅 `51job` |
| username | String(128) | 登录账号（51job 为手机号） |
| password_enc | Text | AES-GCM 加密后的密码（base64） |
| remark | String(255) | 备注，可空 |
| created_at / updated_at | DateTime | |

- `(site, username)` 联合唯一索引；`site`、`created_at` 普通索引。
- 文件名 `backend/app/models/site_credential.py`，模型类 `SiteCredential`。

### 2.2 `scrape_tasks` 加列

- `login_credential_id`：int，nullable，指向 `site_credentials.id`（不建硬 FK，SQLite 下沿用项目现有软关联风格，删除凭据时置 NULL）。
- 迁移方式：沿用 `test_migration.py` 现有 ALTER TABLE 幂等模式。

### 2.3 settings 表新 key

- `scraper_login`：`{"enabled": false, "credential_id": null}`。
- GET/PUT 接口 `/api/settings/scraper-login`（模式同现有 `/api/settings/schedule`）。

## 3. 密码加密存储

- 新增依赖：`cryptography`（`uv add cryptography`）。
- 新增 `backend/app/core/site_security.py`：
  - `encrypt_password(plain: str, key: bytes) -> str`：AES-GCM 加密，输出 `base64(nonce + ciphertext + tag)`。
  - `decrypt_password(enc: str, key: bytes) -> str`：反向；解密失败抛 `AppError`（记日志，视为凭据损坏）。
- 密钥来源：`data/config.ini` 新增 `[site] secret` 项，首次启动自动生成 32 字节随机密钥（沿用现有 `core/config.py` 自动生成模式；`data/` 已 gitignore）。
- **任何 API 响应都不回传密码**：列表/详情仅返回 `has_password: true`；PUT 时 `password` 为空表示不改密码，提供则覆盖。

## 4. API 设计

新增 router `backend/app/api/site_credentials.py`（注册进 `main.py` 的 router 元组），全部需 JWT。

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/site-credentials` | 列表，`?site=` 过滤，密码不回传 |
| POST | `/api/site-credentials` | 新建；body：`site`/`username`/`password` 必填、`remark` 可选；同 site+username 返回 409 |
| PUT | `/api/site-credentials/{id}` | 更新 remark；`password` 为空不改，提供则覆盖；不存在返回 404 |
| DELETE | `/api/site-credentials/{id}` | 删除；被进行中任务引用的凭据返回 409 |
| POST | `/api/site-credentials/{id}/test-login` | 实际登录验证，返回 `{ok: bool, message: str}` |

### 4.1 任务接口扩展

- `POST /api/tasks` 新增可选参数 `login_credential_id`（缺省取全局默认 `scraper_login`，默认关闭则为空）。
- `GET /api/tasks`、`GET /api/tasks/{id}` 响应附带 `login_credential_id` 及关联 `username`（便于界面显示"已登录抓取"标记）。
- 删除凭据时：**进行中/排队中任务引用 → 409**；已完成/失败任务引用 → 置 NULL。
- PUT 仅可改 `remark` 与 `password`，`site`/`username` 不可改（改则删后重建）。

## 5. 抓取登录流程

### 5.1 新增 `backend/app/scrapers/auth.py`

- `login(page, site, username, password) -> bool`：打开 51job 登录页 → 必要时切换"密码登录"tab → 填账号密码 → 提交 → 检测登录结果（URL/页面元素）。
- 登录态复用：登录成功即复用同一 browser context 的 cookie，后续搜索页自带登录态，不额外持久化。
- 失败/滑块验证码：记日志，返回失败，不纠缠（沿用现有 captcha 模块 best-effort 策略）。

### 5.2 PlaywrightScraper 扩展

- 构造时可选传入 `login_credential`（site/username/decrypted password）。
- 流程：`login → 搜索页 → 翻页抓取`；登录失败**自动降级为匿名抓取**并记日志（不影响解析逻辑）。
- `TaskRunner` 组装：任务指定 `login_credential_id` → 用该凭据；否则全局开关开启 → 用全局默认凭据；否则不登录（现状）。

## 6. 前端

### 6.1 新页面「站点账号」

- 路由 `/credentials`（Layout 菜单加"站点账号"）。
- `src/views/SiteCredentials.vue` + `src/api/siteCredentials.ts`。
- 表格：站点 / 账号 / 备注 / 更新时间 / 操作（编辑、测试登录、删除）。
- 新建/编辑弹窗：站点下拉（本期仅 51job）、账号、密码（`show-password`，编辑时恒为空=不改）、备注。
- 测试登录：loading + 结果消息。

### 6.2 「登录抓取」开关 UI

- Tasks.vue 新建任务对话框：勾选"登录后抓取"后出现账号下拉。
- 任务控制台设置区：全局默认开关 + 默认账号选择（`/api/settings/scraper-login`）。

## 7. 测试

后端（pytest，禁止访问真实 51job）：

- `test_site_security.py`：加解密 roundtrip、错误密钥失败。
- `test_site_credentials_api.py`：CRUD、409 唯一冲突、404、密码不回传、test-login mock 登录模块。
- `test_auth_login.py`：mock page 测成功/失败/验证码路径。
- `test_tasks_api.py` 扩展：传 login_credential_id 建任务、引用不存在凭据 400、删除被引用凭据 409。
- 迁移测试：`scrape_tasks.login_credential_id` 加列幂等。

前端 vitest：`siteCredentials.ts` API 模块单测；type-check + build 通过。

## 8. 范围外（YAGNI）

- 一键投简历（凭据是它的前置，但本期不做）。
- 账号轮换/负载均衡。
- 登录态落盘复用（cookie 文件）。
- 多站点（仅 51job；`site` 字段已预留扩展）。
