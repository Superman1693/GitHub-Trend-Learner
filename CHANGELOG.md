# 变更日志

本文件记录项目的重要变更。版本号与 `README.md`「文档状态」保持一致。

格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)。

---

## [1.8.2] - 2026-10-10

工程基建补齐 + 缓存淘汰 + 文档全文检索。**190 项测试全部通过**，`ruff check` 全绿。

### 新增

- **接口清单 / OpenAPI**（`CODE_REVIEW.md` F11）：
  - `server/openapi.py` 从 `Router` **内省**路径与方法，保证「文档里有的代码里一定有」；
    配合人工维护的 `SUMMARIES` 表补充中文说明、查询参数与请求体；
  - `GET /api/openapi.json` 返回 OpenAPI 3.1 文档（16 路径 / 17 操作）；
  - `python main.py api-doc` 生成人读的 `API.md`；
  - 漂移守卫测试：`API.md` 与当前路由表不一致时 CI 直接失败。
- **产出文档批量导出**（`CODE_REVIEW.md` F6）：
  - `GET /api/documents/export[?date=YYYY-MM-DD]` 返回 ZIP（保留 `日期/文件名.md` 结构 +
    `MANIFEST.txt` 清单），响应头用 RFC 5987 双写文件名；
  - CLI：`python main.py export [--date D] [--out F]`；
  - 前端文档页新增「导出全部 / 导出当日」按钮（随日期筛选联动）；
  - 单次导出上限 300 份 / 64 MB，超限截断并在 MANIFEST 中注明。
- **文档全文检索**（`CODE_REVIEW.md` F5）：`GET /api/documents?q=` 现在同时检索**正文**，
  返回 `match_count` 与上下文 `snippet`；前端文档页加 300ms 防抖，命中片段带左侧强调线展示。
  此前只匹配文件名与标题，正文关键词搜不到。
- **缓存淘汰**（`app/maintenance.py`，B7）：按保留期清理 `repo-*.json`（默认 90 天）、
  `trending-*.json`（30 天），`translations.json` 超 5000 条保留最新；支持 `dry_run` 预演。
  明确不触碰 `tasks.json` 与 `candidates-*.json`。
- **CLI**：`python main.py cache [--prune] [--dry-run] [--repo-keep-days N]`。
- **CI**：`.github/workflows/ci.yml`（ruff + pytest + 前端构建）。
- **依赖声明**：`requirements-dev.txt`（pytest/ruff）、`requirements.lock`（pip freeze 精确锁定）。
- **`ruff.toml`**：行宽 100、目标 py311，只启用能抓真实缺陷的规则集。
- **`.gitattributes`**：仓库内统一 LF，Windows 脚本保持 CRLF。
- **版本控制**：`git init` + 首次提交（`.gitignore` 补全 `node_modules`/`.venv`/`dist`/`.history`/
  `_backup_v1.5_20261008`，避免 73M 前端依赖与凭据入库；`.git` 仅 691K）。

### 修复

- 清零 22 处 lint 问题，含 3 处**真实死代码**：
  `app/llm.py` 未使用的 `.log` 导入、`main.py` 未使用的 `pathlib.Path`、
  `app/classify.py` 未使用的局部变量 `name`。
- 移除 `server/config.py` 中已无引用的六模块副本。
- **清理死代码**（`CODE_REVIEW.md` A5）：
  - `app/search.py` 删除 `quote_query`；`build_query` 此前无生产调用，
    改为让 `search_repo` 复用（消除「精确名」规则的两处重复），并补测试锁定生产路径；
  - `app/quality_gate.py` `run_gate()` 移除从未被读取的 `html_url` 参数（`tutor.py` 同步）；
  - `app/orchestrator.py` 移除纯转发的 `_head_sha` 包装，直接调用 client；
  - 前端删除无人调用的 `useCandidateDetail` / `api.candidateDetail` 链路。
- **移除误入库的 Vite 构建临时文件** `frontend/vite.config.ts.timestamp-*.mjs`
  （含本机绝对路径），并在 `frontend/.gitignore` 加规则防复发。
- `run_daily` 结束时自动清理超期缓存（无删除则不产生日志）。
- 测试隔离：`conftest.py` 新增 autouse fixture，测试不再污染真实 `logs/`。

---

## [1.8.1] - 2026-10-10

按 `CODE_REVIEW.md` 的结论系统修复缺陷、补齐边界处理并扩展功能。**171 项测试全部通过**（新增 46 项）。

### 修复（正确性）

- **静态校验恒为 `warning`**（P0）：`DeployAgent` 先渲染完整 M5 正文再调 `static_check.check()`。
  此前传入空串，导致「可复现」项恒失败、`result` 永远不是 `pass`。
- **无 README 的仓库被误报「链接无效/私有」**（P0）：`GitHubClient.get_readme()` 捕获 404 返回空串，
  并在 `collector` 中记为降级原因。此前 404 会冒泡为 `RepoNotFound`，被上层错误归因。
- **产出文档泄漏英文枚举**（P0）：`render.py` 用 `contracts.project_type_label()` 输出中文项目类型；
  已产出的 3 份文档同步回填（`> 项目类型：tool` → `> 项目类型：工具 / 应用`）。
- **目录穿越守卫用字符串前缀比较**（P1）：`server/http/static.py` 与 `document_service.py`
  改用 `Path.is_relative_to()`。此前同级 `dist-evil/` 会被判定为在 `dist/` 内。
- **Search API 降级分支未兜异常**（P1）：`trending.fetch_trending()` 的降级分支包入 try，
  限流时返回空列表而非让整日任务失败。
- **`load_env` 不剥离行内注释**（P1）：新增 `_parse_value()`，仅在 `#` 前为空白时截断，
  不误伤含 `#` 的 token；引号包裹的值整体取用。

### 修复（边界与异常）

- **`top` 参数无上界**（P1）：新增 `MAX_AUTO_PARSE=50`，API 侧返回 400、编排层二次钳制，
  杜绝单次请求放大成巨额 LLM 账单。
- **任务无并发上限、可重复提交**（P1）：`TaskService` 改用固定大小线程池（3），
  并对 `(kind, target)` 做在途幂等去重。
- **并发任务日志串台**（P1）：日志捕获从「替换全局 `sys.stdout`」改为
  `log.capture()`（contextvars 实现），每个任务只收到自己线程的输出。
- **重试粒度错误**（P1）：`_pipeline_repo` 的重试下沉到子阶段（`_stage_retry`），
  已成功的阶段不再被重跑，最坏 LLM 调用数从 15 次降到 9 次。
- **请求体无上限**（P1）：新增 1 MB 上限，超限返回 413 并断开连接。
- **dev 模式 CORS 通配**（P1）：改为来源白名单（仅本机 5173/4173），
  非白名单预检直接 403；非 dev 模式不再返回 CORS 头。
- **500 响应回显异常原文**（P2）：改为通用文案 + 服务端 `traceback`。
- **`log.event` 无异常保护**（P2）：磁盘异常时降级为控制台提示，不再中断流水线。
- **缓存非原子写**（P2）：新增 `app/fsutil.py`（`atomic_write_text/json`），
  `cache` / `candidates` / `translate` / `mailer` 统一走原子写。
- **路径参数未 URL 解码**（P2）：`Router.match` 在参数级 `unquote`，含空格/中文的文档名可正常打开。
- **非法 `UI_PORT` 导致启动崩溃**（P2）：回落默认值并告警。
- **`.env` 中 `UI_*` 不生效**（P1）：`ServerConfig.from_env()` 先调用 `load_env()`。
- **缓存目录两处定义**：`orchestrator` 复用 `config.CACHE_DIR`（顺带修掉误用的海象运算符）。

### 新增

- **任务持久化**：元数据落 `cache/tasks.json`，服务重启后可回溯；重启时未完成任务标记为中断。
- **失败任务一键重试**：`POST /api/tasks/{id}/retry` + 任务中心「重试此任务」按钮，保留 `retried_from` 追溯。
- **候选新鲜度展示**：卡片新增「最近上榜 YYYY-MM-DD」。
- **六模块规范单一来源**：`contracts.module_specs()` 经 `/api/system/config` 下发，前端不再硬编码副本。
- **版本号单一来源**：`app.__version__`，健康检查 / HTTP Server 头 / 配置接口 / 前端包统一取值。
- **安全响应头**：`X-Content-Type-Options: nosniff`。
- 新增测试：`tests/test_v18_fixes.py`、`tests/test_task_service.py`、`tests/test_translate.py`。

### 变更

- **性能优化**（`CODE_REVIEW.md` B3/B4/B5/B6/B8）：
  - **B8 前端分包**：页面改为路由级懒加载 + `manualChunks` 拆出 `react-vendor` 与 `markdown`。
    首屏从「单个 286 KB（gzip 94.5 KB）」降到「`index` 20.5 KB + `react-vendor` 163 KB」
    （gzip 8.1 + 53.3 KB）；`markdown`（66 KB）只在打开文档详情时才加载。
  - **B3** 服务端复用进程级 `GitHubClient`（此前每次候选详情请求都新建 `requests.Session`）。
  - **B4** 搜索模块改用模块级 `requests.Session`（复用连接，省去每次 TCP/TLS 握手）。
  - **B5** `prompts` 的 `_read`/`load_global`/`load_agent` 加 `lru_cache`
    （每日任务此前对 N 个仓库各重读 3 次磁盘）。
  - **B6** `Settings.load()` 加进程内缓存（此前位于搜索预览、运行配置等热点路径），
    新增 `Settings.invalidate()`；`conftest.py` 每测试清空以保证隔离。
- `contracts.PROJECT_TYPES` 补齐 `resource`，`PROJECT_TYPE_LABELS` 与 `project_type_label()` 收敛到此，
  `classify` / `analyst` / `render` 全部引用同一来源（消除 3 套矛盾口径）。

---

## [1.8] - 2026-10-09

候选池扩充、描述中文翻译与更精细的筛选维度；文档详情页交互与整体视觉优化。

### 新增

- **仓库描述中文翻译**（`app/translate.py`）：走免费翻译引擎（有道 → MyMemory 降级链），
  **完全不消耗 LLM token**；内容寻址缓存（`cache/translations.json`）保证同一段文本只翻译一次；
  附专有名词修正表。前端卡片支持「中文 / 原文」一键切换。
- **候选池规模与解析数量解耦**：新增 `CANDIDATE_POOL_SIZE`（默认 60），
  抓取并打标更大的池子供发现页挑选，但仅对 `TRENDING_TOP_N` 个仓库调用 LLM，不放大成本。
- **更精确的分类维度**：`classify.py` 新增 `directions`（技术方向，可多值）与项目类型中文标签；
  候选池新增「上榜态势」（今日新上榜 / 持续在榜）；筛选器扩展为
  **技术方向 / 项目类型 / 上榜态势 / 语言 / 可部署 / 可玩性 / 工具类 / star / 上榜天数 / 关键词**。
- `python main.py collect [--pool N]` —— 仅刷新候选池（抓取 + 打标 + 翻译，**零 LLM**）。
- `python main.py translate` —— 为已有候选池补齐中文描述（免费引擎，带缓存）。
- 前端新增图标 `IconArrowLeft` / `IconLayers` / `IconTag` / `IconFlame`。

### 变更

- **文档详情页返回栏常驻**：`返回列表` 改为 sticky 吸附栏（顶栏下方），滚动到任意位置均可一键返回；
  同步调整正文锚点滚动偏移与右侧目录的吸附位置，避免遮挡。
- **trending 聚合入口扩展**：11 → 24 个（补齐各语言榜与周/月榜），候选池可扩到 60+。
- **视觉整体刷新**：令牌色板升级为靛蓝主色 + 品牌渐变、新增玻璃质感令牌；
  侧栏 / 顶栏 / 卡片 / 按钮 / 徽章 / 筛选器统一交互与阴影层次；新增全局品牌色氛围光。
- 筛选接口 `limit` 上限 200 → 400，默认 60 → 120。

---

## [1.7] - 2026-10-08 / 2026-10-09

仓库发现与两阶段解析，以及可视化界面重构。

### 新增

- **仓库发现与两阶段解析**（`design.md` §16，Req10–Req13）
  - 每日自动维护候选池并做 5 维度规则打标，**零 LLM 成本**
  - 发现页支持按语言 / 可部署 / 可玩性 / 工具类 / star / 关键词组合筛选
  - **阶段一**：只调搜索引擎做轻量摘要，明确标注「非 AI 生成」
  - **阶段二**：仅在用户点击「深入解析」后才调 LLM 做六模块解析
- `app/search.py` —— 搜索引擎可插拔接入（Bing 主 / GitHub Search 兜底）
- `app/classify.py` —— 5 维度规则打标，附判定理由
- `app/candidates.py` —— 候选池快照、跨日合并去重、超期清理
- `server/routes/candidates.py` —— 候选列表 / facets / 详情 / preview / analyze 五个接口
- 前端「发现仓库」页（`pages/DiscoverPage.tsx`）与相关组件
- 多入口 trending 聚合（`AGGREGATE_SOURCES`）：日榜 9 个 → 聚合后 40+ 个
- `start_ui.py` —— 一键启动（装依赖 → 构建 → 起服务 → 开浏览器）

### 变更

- **可视化界面重构**：重写设计令牌（暖中性色板、4 级分层阴影、更细排版尺度）；
  新增 Chip / Skeleton / Segmented / Panel 组件；侧栏改为暖底 + 激活项浮起
- `trending.parse_trending_html` 补齐元信息提取（description / language / stars / forks）
- 检索策略改为「精确仓库名优先」三级递进 + 相关性排序

### 修复

- **「本文目录」遮挡正文**：目录组件被渲染在单列容器内，`position: sticky` 使其吸顶覆盖正文。
  拆分为 `ModuleToc`（桌面网格第二列）与 `ModuleTocMobile`（正文列内折叠面板），
  并为吸顶容器加 `max-height` + `overflow-y`，长目录内部滚动
- **多个服务实例静默共享同一端口**：Windows 下 `SO_REUSEADDR` 允许两个进程同时绑定同一端口，
  导致请求随机落到不同实例、状态不一致（实测出现 3 个实例同时监听 8000）。
  改为按平台设置 `allow_reuse_address`（Windows 关闭），并对 `EADDRINUSE` 给出可操作提示
- **trending 单入口只返回 9 个仓库**：改为多入口聚合（日/周/月榜 + 中文榜 + 各语言榜），
  候选池 9 → 40；并补齐 trending 页面缺失的 topics，否则规则打标大量退化为「待进一步了解」
- `quality_gate` V2 假阳性：`re.I` 子串匹配让「CLI」命中「**Cli**ck」，导致误判降级 → 改英文整词匹配 + 跳过代码块
- `classify._hits` 同类问题：「**rest**」命中「inte**rest**ing」，把资料仓库误判为后端项目 → 改整词匹配
- `search._rank` 的 owner 匹配未限长度：单字符 owner 命中「unrel**a**ted」→ 要求 owner ≥3 字符
- Bing 跳转链未解码 → 补 base64url 解码
- `deploy.py` 丢弃 `env_requirements` / `steps`，导致 M5 残留「待补全」占位符 → 改为结构化确定性渲染
- `quality_gate` V7 拦不住占位符 → 新增 `PLACEHOLDER_PATTERNS` 硬拦
- `quality_gate` V1 未管标题层级：模块正文用 `##` 撑破模块边界（界面切成 17 节）→ 新增判定
- `cache` 两处问题：缓存键不含口径版本（旧结果被复用）、降级结果被写入缓存（永久不重试）

---

## [1.5] - 2026-10-08

范围变更：删除报错大全，强化部署方案。

### 移除

- **Req5「部署报错收集、匹配与修复」** 整体删除
- `app/errors_kb.py`、`knowledge/error-kb.md`、`tests/test_errors_kb.py`
- `main.py fix` 子命令、`Orchestrator.run_fix`、`ERROR_LOG_HINTS`、`error_fix` 路由模式

### 变更

- 模块口径 **7 → 6**：删除原 M6「部署与使用常见报错大全」，原 M7「新手学习提升指南」前移为 M6
- **M5 强化为「可运行 + 小白分步」**：环境准备逐项附安装教程（怎么下载 / 怎么装 / 怎么验证）、
  每步给出执行位置与预期结果、补齐前置操作、新增可运行性自检表
- `DeployPlan` 移除 `error_kb_hits` / `m6_markdown`，新增 `run_check`

---

## [1.4] - 2026-09-27

形态变更：从纯提示词升级为可运行应用。

### 新增

- `app/` 应用代码：编排、采集、缓存、校验、投递
- `main.py` CLI（`daily` / `repo` / `serve` / `doctor`）
- `tests/` 单元测试、`requirements.txt`、`.env.example`

### 变更

- 推翻 Q2「纯提示词形态」；`A1–A3`、`C5` 假设同步修订

---

## [1.3] - 2026-09-27

文档缺陷修复。

### 修复

- 删除术语表重复条目
- 「路由识别」与 Req8.1 补全「报错修复」流程口径
- 追溯矩阵与 `tasks.md` 对齐；核心文件筛选依据引用修正为 `design.md` §5.6

---

## [1.2] - 2026-09-27

落实 Q1–Q7 确认结论。

### 变更

- 纯提示词形态、邮件投递、≤10 分钟、不设 Token 预算、不采用沙箱、并发 3、内容寻址缓存
- 原「待确认事项」章节改为「决策记录」

---

## [1.1] - 2026-09-27

初始修订。

### 修复

- 修正「GitHub Trending API」事实错误（GitHub 无官方 Trending API）
- 补齐 EARS 缺失分支，新增术语表、优先级、NFR、假设约束、追溯矩阵
