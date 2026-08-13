# 移动端适配设计

日期：2026-08-13

## 1. 背景与目标

现有前端为纯桌面设计：固定 200px 侧边栏、14 列职位表格（约 1890px）、固定宽度对话框（420/640px）、无任何媒体查询与断点适配，手机上体验差。

目标：全部页面（登录/任务/职位/公司/统计）在手机（<768px）上可用且体验良好；桌面端行为保持不变。

## 2. 方案

单代码库响应式改造（方案 A）：新增 `useIsMobile` composable + CSS 媒体查询；列表页表格与卡片**条件渲染**（`v-if` 切换），桌面端完全不变；抽屉式侧边栏；职位筛选移动端改为底部弹出面板；所有对话框移动端宽度 92vw。

不引入移动端 UI 库、不新增依赖、不做 px→vw/rem 适配。

## 3. 基础设施

### 3.1 `useIsMobile` composable（新增 `src/composables/useIsMobile.ts`）

- 基于 `window.matchMedia('(max-width: 768px)')`，响应式跟踪视口变化，返回 reactive `isMobile`
- 与 Element Plus sm 断点（768px）一致
- 新增 vitest 用例（mock matchMedia，验证不同宽度返回值）

### 3.2 Layout.vue 改造

- `el-aside`（200px）：桌面端显示，移动端隐藏
- `el-header`：移动端显示汉堡按钮，点击打开 `el-drawer`，内含与侧边栏**同一份** `el-menu`（复用渲染，避免双份维护）
- `el-main` 内边距：桌面端保持现状（Element Plus 默认 20px）不动，移动端覆盖为 10px

### 3.3 全局 CSS（新增 `src/styles/mobile.css`，main.ts 引入）

- 媒体查询（max-width: 768px）：所有 `el-dialog` 宽度 92vw（全局兜底，不依赖逐个对话框传参）

### 3.4 Login.vue

- `.login-card` 固定 360px → `width: min(92vw, 360px)`

## 4. 列表页卡片化

通用模式：每个列表页模板中同时保留 `el-table` 与卡片列表，`v-if="!isMobile"` / `v-if="isMobile"` 切换；数据源、加载、筛选逻辑完全复用。

### 4.1 新增卡片组件（`src/components/`）

| 组件 | 内容 |
|---|---|
| `JobCard.vue` | 职位名 + 薪资高亮 + 公司名 + 城市/区域 + 标签 + 发布时间 + 活跃度；收藏按钮；点击打开现有 `JobDetailDialog` |
| `CompanyCard.vue` | 名称 + 类型标签（民营/国企/外企）+ 行业 + 规模 + 活跃度 |
| `KeywordCard.vue` | 关键字 + 城市 + 行业 + 启用开关 + 抓取方式 + 最近抓取时间 + 操作（编辑/删除） |
| `TaskCard.vue` | 关键字 + 状态标签（带颜色）+ 进度条 + 成功/失败计数 + 起止时间 + 操作（详情/删除） |

### 4.2 各页面

**Jobs.vue**
- 移动端：顶部工具栏（筛选按钮 + 全选 + 批量收藏）+ 卡片列表 + 分页 `layout="total, prev, next"`
- 筛选：移动端为底部弹出面板（`el-drawer direction="btt"`），11 个筛选项纵向堆叠、宽度 100%；桌面端保持现有内联筛选区
- 详情对话框：移动端 `el-descriptions` 单列（`:column="1"`）

**Companies.vue**
- 移动端：公司卡片列表 + 筛选表单纵向堆叠 + 紧凑分页

**Tasks.vue**
- 移动端：关键字卡片 + 任务卡片 + 新建任务 FAB（固定底部）+ 定时设置卡片（堆叠）
- 桌面端保持 16/8 分栏不变

**分页**：三个列表页移动端统一 `layout="total, prev, next"`

## 5. 统计页（Stats.vue）

- 统计卡片：桌面 4 列（`:span="6"`）→ 移动端 2x2（`:xs="12"`）
- 图表：桌面 1/3 分栏（`:span="8"`）→ 移动端全宽堆叠（`:xs="24"`）
- 图表高度：桌面 340px 不变，移动端 260px（CSS 媒体查询）；宽度由 `useChart` 现有 resize 监听自适应
- 筛选控件移动端纵向堆叠、宽度 100%；跳转职位对话框 92vw（全局兜底已覆盖）

## 6. 桌面端不变

表格列配置、布局、交互在桌面端均不重写；所有改动只作用于移动端分支。

## 7. 验证

- `npm run type-check`、`npm run build`、`npm run test`（现有 23 项 + 新增 useIsMobile 用例）全绿
- Chrome DevTools 设备模拟（iPhone 12 / SE 尺寸）手动冒烟 5 个页面：抽屉、筛选面板、对话框、分页、图表
- 后端无改动，pytest 不受影响
