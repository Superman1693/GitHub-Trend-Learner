# Design: GitHub-Trend-Learner

> **版本**：v1.6
> **上游**：`requirements.md` ｜ **规范来源**：`global.md`
> **变更说明**：
> - v1.1 修正「并行调用多 Agent」与串行依赖链的矛盾；新增 OrchestratorAgent；补齐数据契约、数据源方案、可执行校验规则。
> - v1.2 按需求方确认结论调整：确定为**纯提示词形态**；新增 GitHub MCP Server 具体配置；**移除沙箱方案**改为静态校验；缓存改为内容寻址；新增**邮件推送**设计。
> - v1.3 文档缺陷修复：核心文件筛选规则独立为 §5.6；DeployAgent 与 TutorAgent 明确为**串行**；缓存键统一为 `full_name + head_sha`；邮件正文口径统一。
> - v1.4 **形态变更（需求方 2026-09-27 确认）**：升级为 **Python 3.10+ 可运行应用**。§6.1 标注实现采用 REST API 直连；新增 §14 实现设计；§11 交付物清单更新。
> - v1.5 **范围变更（需求方 2026-10-08 确认）**：**删除报错大全（原 M6）**，模块 7 → 6；**强化 M5 部署方案为「可运行 + 小白分步」**。§1 资产表、§2 架构图、§3 Agent 职责、§4 时序、§5 数据契约、§6.1 工具集、§7 产物文件、§9 异常、§11 交付物、§14 实现设计同步修订；报错知识库与 `error_fix` 路由模式整体移除。
> - v1.6 **新增可视化界面（需求方 2026-10-08 确认）**：新增 `server/`（分层后端 API，零新增 Python 依赖）与 `frontend/`（Vite + React + TypeScript 企业级前端工程），并提供 `start_ui.py` 一键启动。§11 交付物清单、§14 实现设计同步扩充；新增 §15 可视化界面设计。

---

## 1. 设计目标与系统形态

**系统形态：可运行的 Python 应用（v1.4 修订，需求方 2026-09-27 确认）**

> v1.2 曾按当时确认结论定为「纯提示词系统」。v1.4 需求方推翻该结论，升级为可运行应用：**编排与采集逻辑由 Python 代码承载，Agent 提示词资产作为 LLM 调用的系统提示词**。原「纯提示词」下的 Agent 分工、数据契约、门禁、降级规则全部保留，只是执行者从「人工在宿主平台编排」变为「代码编排 + LLM 调用」。

本系统由以下五类资产构成，不含数据库或外部任务队列：

| 资产类型 | 内容 | 文件 |
| --- | --- | --- |
| 应用代码 | 编排、采集、缓存、静态校验、质量门禁、邮件投递 | `app/`、`main.py` |
| Agent 提示词 | 5 个 Agent 的角色、契约与约束（LLM 系统提示词） | `agent/*.md` |
| 全局规则 | 输出结构、命名、安全、门禁 | `global.md` |
| 模板 | 六模块输出模板、邮件模板 | `templates/*.md` |

**系统边界**：只帮助用户**理解仓库内容**（读懂用途、原理、教程、源码、部署方式），**不代替用户执行部署命令**，也不在用户机器上安装任何东西。**不提供报错修复服务**（v1.5 起，原 M6 报错大全已移除）。

---

## 2. 总体架构

```
                       ┌──────────────────────┐
   定时触发(Cron) ────► │  OrchestratorAgent   │ ◄──── 用户输入（仓库链接）
   用户输入       ────► │  识别·路由·调度·聚合  │
                       └──────────┬───────────┘
                                  │ 任务信封 TaskEnvelope
                 ┌────────────────┴─────────────────┐
                 │  单仓库串行流水线（仓库维度并行×3）  │
                 └────────────────┬─────────────────┘
                                  ▼
                    ① TrendCollectorAgent   采集 + 校验 + 结构化
                                  │ RepoMeta
                                  ▼
                    ② RepoAnalystAgent      生成 M1–M4、M6 草稿 + M5 骨架
                                  │ DraftDoc
                                  ▼
                    ③ DeployAgent           补全 M5（可运行 + 小白分步）
                                  │ DeployPlan（含 M5 完整内容）
                                  ▼
                    ④ TutorAgent            新手转译 + 终审门禁
                                  │ FinalDoc
                       OrchestratorAgent 聚合
                                  ▼
                    邮件投递 + 本地归档（outputs/YYYY-MM-DD/）
```

**关键约束**：①→②→③→④ 之间存在强数据依赖（TutorAgent 的输入含 DeployAgent 产出的 `DeployPlan`），因此**单仓库内部串行**；并行发生在**仓库与仓库之间**，上限 3。

---

## 3. Agent 划分与职责

| Agent | 输入 | 输出 | 失败处理 | 提示词文件 |
| --- | --- | --- | --- | --- |
| OrchestratorAgent | 用户输入 / 定时信号 | FinalDoc + 任务日志 | 捕获全部子任务异常，单独重试 | `agent/OrchestratorAgent.md` |
| TrendCollectorAgent | 触发信号 / 仓库 URL | `RepoMeta` | 重试 ≤3 次，尊重限流 | `agent/TrendCollectorAgent.md` |
| RepoAnalystAgent | `RepoMeta` | `DraftDoc`（M1–M4、M6 + M5 骨架） | 上下文超限时降级解析 | `agent/RepoAnalystAgent.md` |
| DeployAgent | `RepoMeta` + `DraftDoc` | `DeployPlan`（含 M5 完整内容） | 无沙箱，静态校验 | `agent/DeployAgent.md` |
| TutorAgent | `DraftDoc` + `DeployPlan` | `FinalDoc` | 严重问题退回，上限 2 次 | `agent/TutorAgent.md` |

职责边界以 `global.md` §5.1 为准。

---

## 4. 数据流与时序

**单仓库串行时序**

```
Orchestrator → Collector : 采集请求
Collector → Orchestrator : RepoMeta（README、目录树、元信息、核心文件）
Orchestrator → Analyst   : 解析请求 + RepoMeta
Analyst → Orchestrator   : DraftDoc（M1–M4、M6 + M5 骨架）
Orchestrator → Deploy    : 部署编排请求 + RepoMeta + DraftDoc
Deploy → Orchestrator    : DeployPlan（含 M5 完整内容）
Orchestrator → Tutor     : 终审请求 + DraftDoc + DeployPlan
Tutor → Orchestrator     : FinalDoc（或退回单）
Orchestrator → 邮件      : 投递 + 本地归档
```

**并行策略**

| 层级 | 是否并行 | 说明 |
| --- | --- | --- |
| 仓库与仓库之间 | 并行 | 上限 3（见 §8） |
| 单仓库内 4 个 Agent | 串行 | 存在强数据依赖 |
| DeployAgent 与 TutorAgent | 串行 | TutorAgent 的输入契约含 `DeployPlan`（M5 完整内容），必须等待 DeployAgent 完成后才能终审 |

---

## 5. Agent 间信息交接约定

Agent 之间通过结构化数据交接（v1.4 起由 `app/contracts.py` 落为 dataclass 契约）。以下字段为**交接约定**，上游必须产出、下游必须消费；缺字段视为交接违约。

### 5.1 任务信封（Orchestrator → 各 Agent）

```
task_id: 任务唯一标识
trace_id: 链路追踪标识
mode: daily_trend | custom_repo
repo_full_name: owner/repo
attempt: 第几次尝试
payload: 该 Agent 所需的具体输入
```

> v1.5：原 `error_fix` 模式已随 Req5 删除。

### 5.2 RepoMeta（TrendCollectorAgent → RepoAnalystAgent）

```
full_name / html_url / description / stars / forks / language / license / topics
default_branch / head_sha / fetched_at / source(trending_page|search_api)
readme（全文或摘要）
tree（目录树）
core_files: [{path, content}]   ← 按 §5.6 规则筛选
deploy_hints: [{path, content}] ← 依赖文件/启动脚本/配置项（DeployAgent §2 输入，v1.4 实现补充）
degraded / degrade_reason
```

### 5.3 DraftDoc（RepoAnalystAgent → DeployAgent / TutorAgent）

```
project_type: tool | ai_model | framework | script | template | unknown
modules: { intro, principle, tutorial, source-code, deploy, growth }
notes: ["【注意】不确定项 + 风险"]
open_questions: []
```

> `deploy` 键由 RepoAnalystAgent 写入**骨架**（环境准备与步骤说明），由 DeployAgent 补全为可运行方案。

### 5.4 DeployPlan（DeployAgent）

```
env_requirements: [{name, version, install_guide}]   ← install_guide 必填（怎么装、怎么验证装好）
steps: { windows[], macos[], linux[] }               ← 每步含：做什么 → 完整命令 → 在哪执行 → 预期看到什么
one_click_script
static_check: { verified_by, result, unverified_reason }   ← 无沙箱，见 §10
run_check: [{step, expect}]                          ← 可运行性自检（对应 V7 ③）
risks: []
m5_markdown: "M5 完整正文（design.md §4 时序载体）"
```

> v1.5：`error_kb_hits` 已随 Req5 删除；新增 `run_check` 承载「每步预期结果」，支撑 `global.md` §6.4 校验项 V7。

### 5.5 FinalDoc（TutorAgent → Orchestrator）

```
task_id / repo_full_name / generated_at
modules: { intro, principle, tutorial, source-code, deploy, growth }
gate_result: pass | degraded
rejected_items: [{module, issue, attempts}]
glossary: [{term, explain}]
```

### 5.6 核心文件筛选规则（M4 用）

按「目录重要性（src/、core/、lib/）+ 文件名命中关键词（main、index、app、engine、core）+ 被 README 提及 + 体积适中」四项加权排序，取前 10 个；单文件截断至 300 行（`global.md` §8.2）。`RepoMeta.core_files` 的筛选与 RepoAnalystAgent 的 M4 分析均以本规则为准。

---

## 6. 数据源与工具

### 6.1 GitHub 数据访问（v1.4 实现口径：REST API 直连）

> **v1.4 实现决策**：本项目自身即宿主，数据读取采用 **GitHub REST API v3 直连**（只读语义：GET 请求 + 可选 PAT，能力与下表 MCP 只读模式等价），免去 Docker 依赖。**github-mcp-server 保留为可选接入方式**，以下对照表继续有效。

**结论（回答 Q5）：本项目不需要沙箱 MCP。** 数据读取与命令执行的用途区分如下：

| 对比项 | GitHub MCP Server | 沙箱 MCP |
| --- | --- | --- |
| 作用 | 读取 GitHub 上的仓库、文件、Issue、PR 等**数据** | 在隔离环境**执行 shell 命令** |
| 本项目是否需要 | **需要**（Req2 的核心依赖） | **不需要**（系统不执行部署命令） |
| 是否具备 shell 执行能力 | **不具备** | 具备 |

**来源**：https://github.com/github/github-mcp-server （GitHub 官方维护）

**本项目需要的能力与对应工具集**

| 用途 | 工具集 | 主要工具 |
| --- | --- | --- |
| 读取 README 与任意文件内容 | `repos` | `get_file_contents` |
| 读取仓库元信息（star、语言、License、topics） | `repos` | repos 工具集 |
| 搜索仓库 | `repos` | 仓库搜索工具 |
| 读取目录树（用于核心文件筛选） | `git` | `get_repository_tree` |
| 获取当前用户与上下文 | `context` | context 工具集 |

> v1.5：原用于 M6 报错知识库的 `issues` 工具集已不再需要。

**推荐启动配置**

```bash
# 只读模式 + 按需工具集，最小权限
docker run -i --rm \
  -e GITHUB_PERSONAL_ACCESS_TOKEN=<YOUR_TOKEN> \
  -e GITHUB_TOOLSETS="repos,git,context" \
  ghcr.io/github/github-mcp-server --read-only
```

**配置要点**

- **必须使用 `--read-only`**：本项目只需读取，不需要任何写操作，可避免误改用户仓库（对应 NFR6）。
- 认证优先用 `GITHUB_PERSONAL_ACCESS_TOKEN`（PAT）；权限最小化（`repo` 只读即可，无需 `write`）。**Token 不得写入任何输出或日志**（`global.md` §4.2）。
- 若仅解析公开仓库，可不配 Token，但会受未认证限流约束（60 次/小时）。
- 远程托管地址 `https://api.githubcopilot.com/mcp/` 亦可，取决于宿主支持情况。
- 工具集名称与工具名请以该仓库 `docs/` 为准，配置前建议实际校验一次。

### 6.2 热门榜单数据源

> **事实前提**：GitHub **没有官方 Trending API**。

| 方案 | 说明 | 采用 |
| --- | --- | --- |
| A. 解析 `https://github.com/trending` 页面（**多入口聚合**） | 语义最贴近「热门」，含今日新增 star | **主方案** |
| B. GitHub Search API `created:>YYYY-MM-DD&sort=stars&order=desc` | 官方接口、结构稳定，但只表达「新建且高星」，非趋势；分页上限 1000 条 | **降级备选** |

**多入口聚合（v1.7）**

GitHub 的 `?since=daily` 目前只返回约 **9** 个仓库，单一入口会让候选池过小。
实测各入口返回量（2026-10-09）：

| 入口 | 仓库数 |
| --- | --- |
| `/trending?since=daily` | 9 |
| `/trending?since=weekly` | 11 |
| `/trending?since=monthly` | 24 |
| `/trending?spoken_language_code=zh&since=daily` | 18 |
| `/trending/python?since=daily` | 12 |
| `/trending/typescript?since=daily` | 17 |

因此改为依次抓取 `AGGREGATE_SOURCES`（日/周/中文/各语言/月榜），
按 `full_name` 去重合并、按「今日 star → 总 star」排序，凑够 `top_n` 即停止。
实测可把候选池从 9 扩到 **40+**，耗时约 16 秒（HTML 抓取，不占 API 配额）。

**元信息补齐**

trending 页面**不含 topics**，而规则打标（`design.md` §16.4）高度依赖它，
不补会让大量候选退化为「待进一步了解」。故聚合后对每个仓库补一次 `/repos/{full_name}`
（1 次调用/仓库，并发 5，失败不影响主流程），实测可把 topics 覆盖率从 0 提升到 5/9（其余仓库本身未设置 topics）。

**实现要点**

- 主方案失败自动降级到 B，并在输出标注数据源（Req1.6）。
- 抓取请求带 `User-Agent`，请求间隔 ≥1s。
- 触发限流时读取 `X-RateLimit-Reset` 等待后重试，**禁止无脑重试**（`global.md` §7.2）。
- 单个聚合入口失败不影响其他入口（逐个容错）。

---

## 7. 产物文件与目录

不引入数据库，需要持久化的内容以**文件**承载。

| 文件/目录 | 作用 | 维护方式 |
| --- | --- | --- |
| `templates/six-module-template.md` | 六模块输出模板，保证结构统一 | 随 `global.md` §2.1 变更同步 |
| `templates/email-template.md` | 邮件正文模板 | 按 §12 投递策略调整 |
| `outputs/YYYY-MM-DD/` | 每日解读结果归档 | 由 OrchestratorAgent 写入 |
| `cache/` | 内容寻址缓存，见 §8 | 按 `head_sha` 命中复用 |
| `logs/` | JSONL 运行日志（NFR4） | 运行时生成 |

> **v1.5 变更**：原 `knowledge/error-kb.md` 报错知识库及其三级匹配策略已随 Req5 删除，不再产出报错大全类内容。

---

## 8. 并发与缓存

### 8.1 并发上限 = 3（已确认）

**取值依据**：

- GitHub 未认证限流为 60 次/小时，认证后 5000 次/小时。单个仓库解析约需 6–10 次请求（元信息 + README + 目录树 + 若干核心文件）。
- 并发 3 时，单轮约 18–30 次请求，留足余量，不会触发限流。
- 上下文窗口限制：同时处理过多仓库会导致上下文拥挤，降低单个仓库的解读质量。
- 每日热门榜通常取 Top 5–10，并发 3 分批处理可在 NFR1（单仓库 ≤10 分钟）约束内完成。

### 8.2 缓存：内容寻址（已确认）

**不采用时间 TTL，改用内容寻址**，这是更优解：

- **缓存键**：`full_name + head_sha`（`head_sha` 已唯一定位一次提交，无需叠加分支字段；与 `global.md` §8.5、`requirements.md` Q7 口径一致）
- **命中逻辑**：若目标仓库的 `head_sha` 与缓存记录一致，说明仓库自上次解析后**没有新提交**，直接复用既有解析结果，无需重新抓取与解析。
- **失效逻辑**：`head_sha` 变化即视为新版本；**模块口径变更亦视为失效**（`Cache._schema_compatible` 校验缓存文档的模块键是否等于当前 `MODULE_KEYS`，防止七模块时代的旧结果被继续复用）。
- **不缓存未达标结果**：仅 `gate_result == "pass"` 的终稿写入缓存。降级交付的文档质量未达标，若写进缓存会因 `head_sha` 未变而永久复用，再也不会重试。
- **兜底**：仅对「热门榜单列表本身」设当日有效（榜单是每日快照，跨日必须重取）；仓库解析结果不受时间限制。
- **收益**：显著减少重复请求，规避限流，且保证同一 commit 的解读结果稳定可复现。

### 8.3 上下文裁剪（强制）

- README 超过 20K 字符时按章节摘要。
- 目录树超过 500 条时按目录聚合。
- 核心文件限 10 个 × 单文件 300 行。
- `RepoMeta` 只构建一次，全流程复用（`global.md` §8.1）。

---

## 9. 异常与降级策略

| 场景 | 处理 |
| --- | --- |
| GitHub 限流 | 读取 `X-RateLimit-Reset` 等待后重试，≤3 次 |
| 网络超时 | 指数退避重试，≤3 次 |
| 仓库 404 / 私有 | 提示「链接无效，或为私有/已删除」；**未授权状态下无法区分二者，不得断言是私有仓库** |
| 仓库过大 | 降级解析：限定文件数与行数，`degraded=true` 并在输出标注 |
| 子 Agent 失败 | Orchestrator 只重试该子任务，≤3 次后降级交付 |
| 质量门禁不通过 | TutorAgent 退回 ≤2 次，仍不通过则降级交付并列出未达标项 |
| 邮件发送失败 | 重试 ≤3 次；仍失败则本地归档并提示用户（Req1.9） |

---

## 10. 命令校验策略（无沙箱）

**结论（回答 Q5）：不采用沙箱执行环境。**

**原因**：

1. 系统定位是帮用户「了解仓库」，不代替用户执行部署命令（`requirements.md` C2）。
2. GitHub MCP Server 本身不含 shell 执行能力，无法承担该职责。
3. 引入沙箱会显著增加部署复杂度，而收益仅用于「验证命令语法」这一件事。

**替代方案：静态校验 + 风险标注**

| 校验项 | 静态判定方式 |
| --- | --- |
| 命令格式 | 检查是否为完整可执行命令、是否含占位符、是否含明显拼写错误 |
| 平台适配 | 检查 Windows/macOS/Linux 命令是否用错（如 `apt` 用于 Windows） |
| 危险操作 | 命中 `rm -rf`、`sudo`、`chmod 777`、开放端口等关键词时强制附风险提示 |
| 依赖版本 | 检查是否给出明确版本或版本范围，禁止「安装最新版」 |
| 可复现性 | 检查是否给出执行位置与预期结果 |

校验结果写入 `DeployPlan.static_check`，并注明「本命令未经实际执行验证」。

---

## 11. 交付物清单与技术栈

```
GitHub-Trend-Learner/
├── README.md                        文档地图与阅读顺序
├── global.md                        全局强制规则（结构/命名权威来源）
├── requirements.md                  需求与决策记录
├── design.md                        本文件
├── tasks.md                         任务拆解与验收标准
├── agent/
│   ├── OrchestratorAgent.md         主调度
│   ├── TrendCollectorAgent.md       采集
│   ├── RepoAnalystAgent.md          解析
│   ├── DeployAgent.md               部署编排
│   └── TutorAgent.md                新手转译 + 终审
├── templates/
│   ├── six-module-template.md       六模块输出模板
│   └── email-template.md            邮件模板
├── app/                             应用代码（v1.4，见 §14）
├── main.py                          CLI 入口（v1.4，见 §14）
├── server/                          控制台后端 API（v1.6，见 §14/§15）
├── frontend/                        可视化前端工程（v1.6，见 §15）
│   ├── src/
│   │   ├── api/                     HTTP 客户端与类型契约
│   │   ├── components/              layout / ui / documents / tasks
│   │   ├── config/                  导航配置
│   │   ├── hooks/                   数据与响应式 Hook
│   │   ├── pages/                   页面级组件
│   │   ├── styles/                  设计令牌与基础样式
│   │   └── utils/                   格式化工具
│   ├── index.html
│   ├── vite.config.ts
│   └── package.json
├── start_ui.py                      一键启动（构建前端 + 起服务 + 开浏览器）
├── tests/                           单元测试（v1.4）
├── requirements.txt                 Python 依赖（v1.4）
├── .env.example                     配置样例（v1.4）
├── cache/                           内容寻址缓存（运行时生成）
├── logs/                            JSONL 运行日志（运行时生成）
└── outputs/YYYY-MM-DD/              每日归档（运行时生成）
```

**技术栈（v1.4 修订）：Python 3.10+ 单机应用。** 采集/编排/校验/投递由 Python 代码实现（仅依赖 `requests`），内容生成由 LLM 完成（提示词即 `agent/*.md`），无数据库、无外部任务队列。

## 12. 邮件推送设计（已确认）

### 12.1 依赖

需要宿主环境提供**邮件发送能力**（SMTP 配置或邮件连接器）。这是外部依赖，需在环境侧确认可用的发送方式与发件账号。

### 12.2 邮件结构

| 部分 | 内容 |
| --- | --- |
| 主题 | `GitHub 今日热点解读 · YYYY-MM-DD` |
| 开篇 | 当日技术热点总结（趋势方向、亮点） |
| 正文 | Top 3 仓库的要点速览（一句话定位、原理类比、极简三步、部署要点） |
| 其余 | 剩余仓库提供 M1 摘要 + 指向归档文件的路径 |
| 结尾 | 数据来源与获取时间（Req1.6）、数据源标注（主方案/降级） |
| 附件 | 当日完整 Markdown 文档（避免正文过长被截断） |

**设计理由**：邮件正文过长会被客户端截断或折叠，因此采用「正文放核心 + 附件放全文」的策略，同时正文自身必须可独立阅读。

### 12.3 投递与兜底

1. 生成 `FinalDoc` 后按模板组装邮件。
2. 发送失败重试 ≤3 次。
3. 仍失败则写入 `outputs/YYYY-MM-DD/` 并提示用户手动取用，**保证内容不丢失**（Req1.9）。

---

## 13. 后续可优化项

以下为可选增强，不影响当前交付：

| 项 | 说明 |
| --- | --- |
| 多语言输出 | 目前固定简体中文，可扩展英文 |
| 个性化订阅 | 按用户关注的语言/技术方向筛选热门仓库 |
| 部署方案实操验证 | 对高热度仓库的 M5 做人工实操验证，沉淀为可信样例，反哺提示词质量 |

---

## 14. 实现设计（v1.4 新增，v1.5 修订）

**模块划分**

| 模块 | 承载文档规则 | 职责 |
| --- | --- | --- |
| `app/config.py` | NFR6 | `.env` 加载与设置；敏感信息脱敏，不进日志 |
| `app/contracts.py` | §5 | `TaskEnvelope` / `RepoMeta` / `DraftDoc` / `DeployPlan` / `FinalDoc` 数据契约 |
| `app/github_client.py` | §6.1、§9 | REST v3 直连：元信息、README、目录树、文件内容、搜索；限流尊重 `X-RateLimit-Reset`、重试 ≤3、404 语义（无法区分私有/不存在） |
| `app/trending.py` | §6.2 | trending **多入口聚合**（日/周/月榜 + 中文榜 + 各语言榜，去重按热度排序）+ Search API 降级；元信息补齐；输出标注来源 |
| `app/selection.py` | §5.6、§8.3 | 核心文件四项加权筛选（≤10×300 行）；README >20K 按章节摘要；目录树 >500 条按目录聚合 |
| `app/cache.py` | §8.2 | 内容寻址缓存（`full_name + head_sha`）+ **模块口径校验**；榜单当日快照 |
| `app/llm.py` | A5 | OpenAI 兼容 Chat Completions 客户端；未配置时抛 `LLMNotConfigured`，由编排层降级 |
| `app/prompts.py` | agent/*.md、global.md | 装载提示词资产，组装三环节的系统提示词 |
| `app/agents/analyst.py` | RepoAnalystAgent | 项目类型识别 + **M1–M4、M6 生成 + M5 要点**，输出 `DraftDoc` |
| `app/agents/deploy.py` | DeployAgent、§10 | **M5 结构化渲染**（环境准备/分系统步骤/一键脚本/可运行性自检/风险）、静态校验五项 |
| `app/agents/tutor.py` | TutorAgent、global §6.4 | 术语转译 + 终审门禁 V1–V7；退回 ≤2 次后降级交付 |
| `app/static_check.py` | §10 | 格式/平台适配/危险操作/版本明确/可复现 五项静态校验 |
| `app/quality_gate.py` | global §6.4 | V1–V7 可自动判定项的代码实现（含占位符硬拦、术语整词匹配、标题层级判定） |
| `app/render.py` | templates/*.md | **六模块**文档与邮件正文组装 |
| `app/mailer.py` | §12 | SMTP 发送（重试 ≤3）+ `outputs/YYYY-MM-DD/` 归档兜底 |
| `app/orchestrator.py` | §2–§4、Req6/Req8 | 路由、TaskEnvelope、并发 3（线程池）、子任务重试、降级四件套、JSONL 日志（NFR4） |
| `main.py` | — | CLI：`daily` / `repo <url>` / `serve` / `doctor` |

> **v1.5 变更**：`app/errors_kb.py` 及 `tests/test_errors_kb.py` 随 Req5 删除；`main.py` 移除 `fix` 子命令；`analyst` / `deploy` / `render` / `quality_gate` 的模块清单由七模块改为六模块。
> **v1.5 缺陷修复（2026-10-08）**：① `deploy.py` 此前只追加一键脚本、丢弃 `env_requirements` 与 `steps`，导致 M5 残留「待补全」占位符 —— 现改为**结构化字段确定性渲染**成完整 M5 正文；② `quality_gate` 的 V2 用裸 `re.I` 子串匹配，「CLI」误命中「Click」造成假阳性降级 —— 改为英文整词匹配并跳过代码块；③ V1 新增「模块正文不得含 `##`」判定；④ V7 扩为五项判定并新增占位符硬拦；⑤ `cache.get` 新增**模块口径校验**，口径变更后旧缓存自动失效；⑥ 降级交付结果**不再写入缓存**，避免永久复用未达标文档。

**配置项（`.env`，敏感值不落文档与日志）**

| 变量 | 说明 |
| --- | --- |
| `GITHUB_TOKEN` | 可选；未配置时受未认证限流（60 次/小时） |
| `LLM_BASE_URL` / `LLM_API_KEY` / `LLM_MODEL` | OpenAI 兼容接口三要素，内容生成必需 |
| `SMTP_HOST` / `SMTP_PORT` / `SMTP_USER` / `SMTP_PASSWORD` / `MAIL_FROM` / `MAIL_TO` | 邮件投递；`MAIL_TO` 逗号分隔；未配置时降级为仅归档 |
| `TRENDING_TOP_N`（默认 10） | 每日解析仓库数 |

**调度方式**：`daily` 单次执行（配系统计划任务）或 `serve --at HH:MM` 内置每日循环；两者触发同一编排入口。

**缓存与归档目录**：`cache/`（内容寻址结果）、`outputs/YYYY-MM-DD/`（六模块文档 + 当日邮件草稿）、`logs/`（JSONL 运行日志）。均为运行时生成。

---

## 15. 可视化界面设计（v1.6 新增）

### 15.1 目标与边界

为 CLI 提供一套浏览器可视化控制台，用于**浏览产出、发起任务、查看运行状态**。

- **只读 + 触发**：界面不修改产出文件；任务触发复用现有 `Orchestrator`，不复制业务逻辑。
- **零新增 Python 依赖**：后端仅用标准库 `http.server`，避免为界面引入 FastAPI/Flask 等框架。
- **前后端分离**：前端为独立工程（Vite + React + TypeScript），构建产物由后端托管，部署形态仍是单进程单端口。

### 15.2 架构

```
浏览器
  │  /            → frontend/dist/index.html（静态资源，SPA 回退）
  │  /api/*       → server/ 路由层 → 服务层 → app/ 编排器
  ▼
server/  (标准库 HTTP 服务，默认 127.0.0.1:8000)
  ├── http/      路由表 · 请求解析 · 响应封装 · 静态托管
  ├── routes/    system · documents · tasks
  └── services/  document_service · task_service
```

**任务执行模型**：`POST /api/tasks` 在后台线程运行 `Orchestrator`，日志经 `stdout` 重定向捕获进任务记录，前端每 1.5s 轮询 `GET /api/tasks/{id}` 获取进度。任务记录为**内存态**，服务重启即清空。

### 15.3 后端 API 契约

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/health` | 服务与前端产物状态 |
| GET | `/api/system/config` | 运行配置（敏感值只报是否配置） |
| GET | `/api/system/overview` | 文档统计 + 任务计数 |
| GET | `/api/documents` | 文档列表，支持 `?date=` `?q=` |
| GET | `/api/documents/stats` | 日期分布统计 |
| GET | `/api/documents/{date}/{name}` | 文档详情（含模块切分与头部元信息） |
| POST | `/api/tasks` | 提交任务 `{kind: repo\|daily, url?, top?}` |
| GET | `/api/tasks` | 任务列表 `?limit=` |
| GET | `/api/tasks/{task_id}` | 单任务状态与日志 |

**错误契约**：统一 `{"error": {"code", "message"}}`。

### 15.4 请求分发与 404 修复

请求按以下顺序处理，这是「打开页面 404」问题的根治方案：

1. 命中 API 路由 → 执行业务处理器
2. 路径存在但方法不匹配 → **405**（而非 404，便于定位）
3. `/api/*` 未命中 → **JSON 404**（绝不被静态回退伪装成 200 HTML）
4. 其他路径命中 dist 内真实文件 → 直接返回
5. 其他路径未命中 → **回退 `index.html`**（SPA 客户端路由刷新、深链接直接访问不再 404）
6. dist 未构建 → 返回 **HTTP 200 的构建引导页**（而非 404，让用户一眼看出是「没构建」而非「服务坏了」）

**安全**：静态路径解析强制限定在 `frontend/dist` 内，越界返回 None，杜绝目录穿越（实测 `/../main.py` 返回应用外壳而非源码）。

### 15.5 前端工程结构

```
frontend/src/
├── api/          client.ts（统一请求/错误归一/超时） · types.ts（与后端契约对齐）
├── components/
│   ├── layout/   AppShell · Sidebar · Topbar（桌面侧栏 / 移动抽屉 + 底部导航）
│   ├── ui/       Button · Badge · Card · EmptyState · Spinner · Alert · Field · StatusDot · icons
│   ├── documents/ DocumentList · DocumentViewer · ModuleToc · MarkdownView
│   └── tasks/    TaskLauncher · TaskLogPanel
├── config/       navigation.ts（侧栏与底部导航共用来源）
├── hooks/        useAsync · useMediaQuery · useDocuments · useTasks · useSystem
├── pages/        Dashboard · Documents · Document · Tasks · Settings
├── styles/       tokens.css（设计令牌）· base.css · pages.css
└── utils/        format.ts
```

**分层原则**：`pages` 只做编排；`components` 只做展示与交互；数据获取集中在 `hooks`；HTTP 细节收敛在 `api/`。组件不直接调用 `fetch`。

### 15.6 响应式策略

| 断点 | 布局 |
| --- | --- |
| ≥1024px | 固定侧栏 + 内容区 + 文档目录常驻右侧 |
| 768–1023px | 固定侧栏 + 单列内容（目录折叠为顶部面板） |
| <768px | 侧栏收起为**抽屉**（汉堡按钮唤起）+ **底部导航** + 单列内容 |

断点语义在 CSS（媒体查询）与 JS（`useMediaQuery`）两侧共用同一份常量，避免两处漂移。

### 15.7 启动方式

| 方式 | 命令 | 说明 |
| --- | --- | --- |
| 一键启动 | `python start_ui.py` | 自动装依赖 → 构建 → 起服务 → 开浏览器 |
| 仅起后端 | `python -m server` | 默认 127.0.0.1:8000，可用 `--port` 覆盖 |
| 前端开发 | `cd frontend && npm run dev` | 5173 端口，`/api` 已代理到 8000 |
| 重新构建 | `cd frontend && npm run build` | 产出到 `frontend/dist` |

> 端口可用环境变量 `UI_PORT` / `UI_HOST` 覆盖。

**端口占用处理（v1.7 修复）**

`allow_reuse_address` 必须按平台区分：

| 平台 | 取值 | 原因 |
| --- | --- | --- |
| Linux / macOS | `True` | `SO_REUSEADDR` 只允许绑定处于 `TIME_WAIT` 的端口，不会双监听；保留可加快重启 |
| Windows | `False` | `SO_REUSEADDR` 语义不同，**允许两个进程同时绑定同一端口** |

Windows 下若不关闭，多个实例会静默共享端口，请求随机落到不同进程，导致状态不一致
（实测曾出现 3 个实例同时监听 8000）。关闭后第二个实例会因 `WSAEADDRINUSE` 失败，
服务端给出可操作提示（直接访问 / 换端口 / 结束旧进程）。

**配置读取行为（`.env` 改动何时生效）**

`Settings.load()` 每次调用都会执行 `load_env()`，把 `.env` 的键值注入 `os.environ`，
但**只注入尚不存在的键**（`if key not in os.environ`），以免覆盖真实环境变量。

由此产生两种情形：

| 情形 | 是否需重启 |
| --- | --- |
| 某键原本**未配置**（`.env` 里被注释或缺失），现在补上 | **不需要**。下次 `Settings.load()` 即生效 |
| 某键**已配置**，现在改值 | **需要重启**。`os.environ` 已有旧值，不会覆盖 |

实测：运行中的服务在 `.env` 补上 `GITHUB_TOKEN` 后，`GET /api/system/config` 立即返回
`github_token.configured = true`，无需重启。

---

## 16. 仓库发现与两阶段解析（v1.7 新增）

### 16.1 设计目标

把「每日筛选」与「深度解析」**解耦**：

- 日常维护一个**候选池**（零 LLM 成本），并按多维度打标，供用户按条件筛选。
- 用户**先自己挑**，挑中后只看**搜索引擎的轻量摘要**（仍不调 LLM）。
- **只有用户明确表达兴趣**，才调用 LLM 做完整六模块解析。

收益：日常运行零 LLM 成本；LLM 预算只花在用户真正关心的仓库上。

### 16.2 整体功能结构

```
① 每日调度（零 LLM）
   采集 trending ──► 规则打标（5 维度）──► 候选池快照
                                            cache/candidates-YYYY-MM-DD.json
                                                     │
② 发现页（前端 /discover）                            │
   ├─ 筛选器：语言 / 可部署 / 可玩性 / 实用小工具 / star / 关键词
   └─ 候选卡片列表 ◄──────────────────────────────────┘
            │
            │ 用户勾选目标仓库
            ▼
③ 阶段一：轻量摘要（零 LLM，秒级）
   搜索引擎检索（Bing 主 / GitHub Search 兜底）
        └─► 聚合展示：标题 · 来源域名 · 摘要片段 · 链接
            │
            │ 用户点「深入解析」（明确表达兴趣）
            ▼
④ 阶段二：完整解析（调 LLM，分钟级）
   复用既有流水线 analyst ─► deploy ─► tutor（六模块 + V1–V7 门禁）
        └─► 归档 outputs/YYYY-MM-DD/，可在「解读文档」页阅读
```

**成本边界**：① 与 ③ **不调用 LLM**；只有 ④ 调用。这是本设计的核心约束。

### 16.3 每日自动更新与筛选机制

| 项 | 设计 |
| --- | --- |
| 触发 | 复用 `daily` 流程（系统计划任务或 `serve --at HH:MM`），在原有抓取之后追加打标与快照写入 |
| 步骤 | ① 抓取 trending（主方案页面解析，失败降级 Search API）→ ② 逐仓库规则打标 → ③ 写入候选池快照 → ④ 清理超期快照 |
| 快照文件 | `cache/candidates-YYYY-MM-DD.json`，含当日榜单来源与逐仓库维度标签 |
| 保留策略 | 默认保留最近 **7 天**（可配），供跨日筛选；超期自动清理 |
| 去重 | 以 `full_name` 为键，跨日合并：保留 `first_seen`（首次出现）与 `last_seen`（最近出现） |
| 成本 | **全程零 LLM 调用**，只消耗 GitHub 请求配额 |

### 16.4 仓库分类维度

五个业务维度 + 两个辅助维度，全部由**规则**判定（确定性、可复现、零成本）。

| 维度 | key | 取值 | 判定依据（规则） |
| --- | --- | --- | --- |
| 亮点 | `highlight` | 文本 | 从 topics / description / README 首段提取，映射到已知技术热点词表 |
| 可学习之处 | `learnable` | 文本 | 由语言 + 项目类型映射到可学技术点词表 |
| 是否可部署 | `deployable` | `yes` / `partial` / `no` | 命中依赖清单（requirements/package.json/go.mod/Cargo.toml）或 Dockerfile → `yes`；纯文档/资源类 → `no`；仅有部分线索 → `partial` |
| 可玩性 | `playfulness` | `high` / `medium` / `low` | topics 命中 game / 3d / visual / interactive / ai-agent 等 → `high`；工具类 → `medium`；纯库 → `low` |
| 实用小工具 | `practical_tool` | `yes` / `no` | 命中 cli / tool / utility / automation / script 且仓库体积偏小 → `yes` |
| 语言 | `language` | 文本 | GitHub 元信息 |
| 热度 | `stars` / `stars_delta` | 数值 | GitHub 元信息 + 榜单快照对比 |

> 规则词表集中在 `app/classify.py`，可扩展；判定结果附 `reasons`（命中了哪些规则），便于用户理解与人工校正。

### 16.5 解析内容要点

| 阶段 | 是否调 LLM | 产出内容 |
| --- | --- | --- |
| 阶段一 · 轻量摘要 | **否** | 搜索结果条目：标题、来源域名、摘要片段、链接、检索时间；顶部给出「共 N 条来源」与来源分布 |
| 阶段二 · 完整解析 | **是** | 既有六模块文档 M1–M6（M5 为强化后的可运行部署方案），并经过 V1–V7 门禁 |

阶段一**不做任何生成式总结**——只做检索结果的机械聚合与展示，避免用户误以为那是 AI 结论。

### 16.6 筛选与选择的交互流程

```
进入发现页
   │
   ├─ 筛选器（即时生效，无需点提交）
   │    语言 ▾   可部署 ▾   可玩性 ▾   实用小工具 ▾   最低 Star ── 关键词搜索
   │
   ├─ 候选卡片网格
   │    每张卡：仓库名 · 语言 · star · 5 维度标签 · 「查看摘要」/「直接解析」
   │
   ├─[查看摘要]──► 阶段一抽屉/详情页
   │                显示搜索引擎结果（标题/来源/摘要/链接）
   │                ├─[换一批关键词] 重新检索
   │                ├─[打开仓库] 跳转 GitHub
   │                └─[深入解析] ──► 阶段二
   │
   └─[直接解析]──────────────────► 阶段二
                                     │
                        提交任务 → 任务中心可看实时日志
                                     │
                        完成后跳「解读文档」阅读六模块
```

**分阶段原则的落地约束**：

1. 进入发现页、筛选、翻列表——**不产生任何 LLM 调用**。
2. 点「查看摘要」——只调搜索引擎，**不调 LLM**；响应时间目标 < 5 秒。
3. 只有点「深入解析」才创建 LLM 任务；按钮上明确标注「将调用 AI 解析（耗时较长）」。
4. 阶段一结果可重复触发，不做缓存也不计入 LLM 预算。

### 16.7 后端接口（新增）

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/candidates` | 候选列表，支持 `language` / `deployable` / `playfulness` / `practical_tool` / `min_stars` / `q` / `date` 筛选 |
| GET | `/api/candidates/facets` | 返回可选筛选项与各维度分布计数 |
| GET | `/api/candidates/{owner}/{repo}` | 单仓库候选详情（含维度标签与判定理由） |
| POST | `/api/candidates/{owner}/{repo}/preview` | **阶段一**：搜索引擎摘要（零 LLM） |
| POST | `/api/candidates/{owner}/{repo}/analyze` | **阶段二**：提交完整解析任务（调 LLM） |

### 16.8 搜索引擎接入

| 提供方 | 角色 | 说明 |
| --- | --- | --- |
| Bing（HTML 解析） | **主** | 实测可达，结果结构稳定（`li.b_algo` → 标题/链接/摘要） |
| GitHub Search API | **兜底** | 主提供方失败时改用仓库搜索，返回仓库级摘要 |

> 实测记录：DuckDuckGo 在本机网络下不可达（ProxyError），故选 Bing 为主提供方。
> 提供方以 `app/search.py` 的可插拔接口实现，后续可替换或增加。

### 16.9 与既有设计的关系

- 候选池与打标**不改动**既有 `RepoMeta` / `DraftDoc` / `DeployPlan` / `FinalDoc` 契约。
- 阶段二直接复用 `Orchestrator.run_repo()`，不新增解析链路。
- 候选池写入 `cache/`，与内容寻址缓存共存但互不干扰。
