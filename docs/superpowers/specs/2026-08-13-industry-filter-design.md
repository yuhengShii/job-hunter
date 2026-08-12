# 行业筛选（industry filter）设计

日期：2026-08-13
状态：已批准

## 背景

关键字 `医疗采购` 抓到的数据大量与医疗无关。根因已查明：51job 关键词搜索是**分词 OR 模糊匹配**（`医疗采购` 被拆成 `医疗` OR `采购`，实测 859 条中仅 20 条标题含"医疗"），非爬虫 bug。

真实页面"其他筛选"面板提供**行业领域**筛选（模态级联对话框，可多选 ≤5 个）。实测发现 51job SPA 会读取 URL 查询参数 `industry=` 并传给搜索 API（`we.51job.com/api/job/search-pc`），翻页后筛选保持（点击下一页仍携带 industry 参数）。因此**无需模拟点击筛选 UI，直接在搜索 URL 拼参数即可**，稳定可靠。

## 行业编码

51job 官方字典（`https://js.51jobcdn.com/in/js/2023/dd/dd_industry.json`），顶级 11 类，约 50 子项。示例：

| 顶级 | 编码 | 子项 | 编码 |
|---|---|---|---|
| 制药/医疗 | 08 | 制药/生物工程 | 08 |
| | | 医疗/护理/卫生 | 46 |
| | | 医疗设备/器械 | 47 |

API 参数：多行业逗号分隔（URL 编码后如 `industry=08%2C46%2C47`），上限 5 个（与页面对话框一致）。

## 数据模型（PRD §4 修改）

- `keywords` 表新增 `industry VARCHAR(128) NULL`：存逗号分隔行业编码（如 `08,46,47`），NULL=不过滤。
- 唯一约束**不变**：(keyword, city)。行业是可编辑的筛选属性；同词同城多行业并存属边缘场景，不做（YAGNI）。
- 迁移：`core/database.py` 新增 `_migrate_keywords_industry()`，幂等 `ALTER TABLE keywords ADD COLUMN industry`，沿用 `_migrate_tasks_max_pages` 模式。

## 后端改动

- `scrapers/base.py`：`Scraper.search(keyword, pages, area="000000", industry: str | None = None)` 接口扩展。
- `scrapers/playwright.py`：`_SEARCH_URL` 拼 `&industry={quote(industry)}`（逗号编码为 %2C，已实测）。industry 为空时不带参数。
- `services/task_runner.py`：`execute_task` 读取 `keyword.industry` 透传给 `scraper.search(...)`。
- `schemas/keyword.py`：`KeywordCreate.industry: str | None = None`、`KeywordUpdate.industry: str | None = None`、`KeywordOut.industry: str | None`；校验格式 `^\d{2}(,\d{2})*$` 且数量 ≤5；**空字符串与 None 均视为不过滤**（入库前归一为 NULL）。
- `api/keywords.py`：create/update 透传 industry。

## 前端改动

- `src/utils/industries.ts`：行业树常量（取自官方 dd_industry.json）+ `industryNames(codes)` 辅助函数（与 `utils/cities.ts` 模式一致，PRD"前端维护编码表"约定）。
- `Tasks.vue`：
  - 关键字创建/编辑弹窗加 el-cascader（`multiple`、`limit=5`、`collapse-tags`），options=行业树。
  - 关键字表格加"行业"列，显示 `industryNames` 名称或 `-`。

## 测试

- 后端 pytest：
  - URL 构造：industry 存在/缺失两种场景（纯函数测试，不访问真实 51job）。
  - API：create/update/out 透传 industry；非法格式（超 5 个、非编码）校验 422。
- 前端 vitest：`industryNames` 多选/空值用例；type-check + build。

## 文档

- `docs/PRD.md` §4 keywords 表补充 industry 字段、§5 API 参数说明、§6 抓取 URL 增加 industry 说明。
