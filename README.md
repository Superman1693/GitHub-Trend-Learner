# GitHub-Trend-Learner

面向零基础编程新手的 GitHub 开源项目 **AI 解读 · 教学 · 部署** 助手。

系统每日抓取 GitHub 热门仓库并通过**邮件**推送解读，也支持用户粘贴任意仓库链接，由多 Agent 协同产出统一的**六模块新手友好文档**。

> **交付形态（v1.4）**：**可运行的 Python 3.10+ 应用**。编排、采集、缓存、静态校验、质量门禁与邮件投递由代码实现；5 个 Agent 提示词作为 LLM 系统提示词（OpenAI 兼容接口，`.env` 配置）；GitHub 数据直连 REST API（只读语义）。
> **系统边界**：帮助用户**看懂仓库内容**，不代替用户执行部署命令，**不提供报错修复服务**（v1.5 起）。

---

## 文档地图

| 文件 | 作用 | 权威范围 |
| --- | --- | --- |
| `企业级 GitHub 热门仓库 AI 学习助手 产品提示词（完整版）.docx` | 产品需求基线（源文档） | 产品定位与原始诉求 |
| `requirements.md` | 功能需求、非功能需求、决策记录 | **需求权威来源** |
| `design.md` | 架构、交接约定、数据源、并发缓存、邮件设计、实现设计、可视化界面 | **技术实现权威来源** |
| `global.md` | 全局强制规则（语言、结构、安全、分工、门禁） | **结构与命名唯一权威来源** |
| `tasks.md` | 任务拆解、优先级、依赖与验收标准 | **任务权威来源** |
| `agent/OrchestratorAgent.md` | 主编排调度 Agent | 调度与容错 |
| `agent/TrendCollectorAgent.md` | 趋势采集 Agent | 数据采集 |
| `agent/RepoAnalystAgent.md` | 仓库解析 Agent | M1–M4、M6 正文 + M5 骨架 |
| `agent/DeployAgent.md` | 部署方案编排 Agent | M5 完整方案 |
| `agent/TutorAgent.md` | 新手教学转译 Agent | 语言转译与终审门禁 |
| `templates/six-module-template.md` | 六模块输出模板 | 输出结构落地 |
| `templates/email-template.md` | 每日邮件模板 | 邮件投递落地 |

## 建议阅读顺序

1. `requirements.md` —— 先看要做什么、已确认什么
2. `global.md` —— 再看必须遵守的规则（尤其 §2.1 六模块命名）
3. `design.md` —— 然后看怎么做
4. `agent/*.md` —— 再看每个 Agent 的具体提示词
5. `tasks.md` —— 最后排期与验收

## 核心概念：六模块

所有输出固定为六个模块，名称与顺序以 `global.md` §2.1 为准：

1. 项目基础大白话介绍
2. 零基础通俗原理讲解
3. 新手入门使用教程
4. 源码核心逻辑通俗分析
5. 本地一键部署完整方案 ★
6. 新手学习提升指南

> **原则：结构固定，内容定制。** 六个模块不可增删改名，但模块内部内容按项目类型（工具 / AI 模型 / 框架 / 脚本 / 模板）定制，不套用同一套模板话术。
>
> **★ M5 是本项目的质量重心**：部署方案必须做到「**照着一步步做就能真正跑起来**」——环境准备逐项附安装教程、每个关键步骤给出执行位置与「预期看到什么」、补齐所有前置操作（包括怎么打开终端）、不留未说明的占位符。

## 执行链路

```
定时触发 / 用户输入
        ↓
 OrchestratorAgent  识别 · 路由 · 调度 · 聚合
        ↓
 TrendCollectorAgent → RepoAnalystAgent → DeployAgent → TutorAgent
   （采集原始数据）     （M1–M4、M6 + M5 骨架）（补全 M5 可运行方案）（转译+终审）
        ↓
 六模块最终文档 → 邮件投递 + 本地归档
```

仓库与仓库之间并行（上限 3）；单仓库内部串行（存在强数据依赖）。

## 关键设计决策

| 项 | 结论 |
| --- | --- |
| 输出结构 | 结构固定（六模块）+ 内容定制（按项目类型） |
| 系统形态 | 可运行 Python 3.10+ 应用（代码编排 + LLM 生成内容），无数据库 |
| 数据来源 | GitHub REST API v3 直连（只读语义）+ trending 页面解析（失败降级 Search API） |
| 沙箱 | **不采用**。命令校验改为静态校验 + 风险标注 |
| 缓存 | 内容寻址（`full_name + head_sha`），仓库无新提交则复用 |
| 并发 | 3 个仓库 |
| 性能 | 单仓库端到端 ≤10 分钟 |
| 成本 | 不设 Token 预算上限 |
| 投递 | 邮件（失败重试 ≤3 次后本地归档兜底） |
| 报错大全 | **已移除**（v1.5，模块 7 → 6） |

## 项目结构

```
GitHub-Trend-Learner/
├── README.md                        本文件
├── CHANGELOG.md                     版本变更记录
├── global.md                        全局强制规则
├── requirements.md                  需求与决策记录
├── design.md                        设计说明（§14 实现设计 / §15 可视化界面 / §16 发现与两阶段解析）
├── tasks.md                         任务拆解
├── agent/                           5 个 Agent 提示词（LLM 系统提示词）
├── templates/                       六模块模板 + 邮件模板
├── app/                             流水线代码（编排/采集/缓存/校验/投递/搜索/打标/候选池）
├── main.py                          CLI 入口
├── server/                          控制台后端 API（分层，零新增依赖）
├── frontend/                        可视化前端工程（Vite + React + TS）
├── start_ui.py                      一键启动控制台
├── tests/                           单元测试（116 项）
├── requirements.txt                 Python 依赖
├── .env.example                     配置样例（复制为 .env 填写）
├── cache/                           内容寻址缓存 + 候选池快照（运行时生成）
├── logs/                            运行日志（运行时生成）
└── outputs/YYYY-MM-DD/              每日归档（运行时生成）
```

## 可视化控制台

浏览器界面，用于浏览产出、发起任务、查看运行状态。

```bash
python start_ui.py            # 一键：装依赖 → 构建 → 起服务 → 开浏览器
```

访问 **http://127.0.0.1:8000** 。也可分开跑：

```bash
python -m server                    # 仅起后端（默认 8000，可用 --port 覆盖）
cd frontend && npm run dev          # 前端开发模式（5173，/api 已代理到 8000）
cd frontend && npm run build        # 重新构建前端产物
```

**界面功能**

| 页面 | 内容 |
| --- | --- |
| 概览 | 产出统计、日期分布、运行配置、快捷入口 |
| **发现仓库** | **候选池筛选（语言 / 可部署 / 可玩性 / 工具类 / star / 关键词）+ 两阶段解析** |
| 解读文档 | 搜索 / 按日期筛选 / 分组列表 |
| 文档详情 | 模块目录（滚动联动）、全文渲染、复制与下载 |
| 任务中心 | 发起仓库解析或每日热门、实时日志轮询 |
| 系统设置 | 配置只读展示、服务健康、模块规范说明 |

**响应式**：≥1024px 固定侧栏 + 右侧目录；768–1023px 单列；<768px 抽屉导航 + 底部导航。

## 发现仓库：两阶段解析

核心原则：**先让用户自己挑，只对真正感兴趣的项目花 AI 预算。**

```
① 每日自动（零 LLM）
   trending 抓取 → 5 维度规则打标 → 候选池快照
                                        │
② 发现页筛选（零 LLM）                   │
   语言 / 可部署 / 可玩性 / 工具类 / star / 关键词 ◄┘
        │
        │ 用户挑选
        ▼
③ 阶段一：搜索引擎摘要（零 LLM，秒级）
   Bing 检索 → 展示标题/来源/摘要（明确标注「非 AI 生成」）
        │
        │ 用户点「深入解析」
        ▼
④ 阶段二：完整解析（调 LLM，分钟级）
   复用六模块流水线 → 归档 → 在「解读文档」阅读
```

**分类维度**（规则判定，零成本，附判定理由）：

| 维度 | 取值 |
| --- | --- |
| 技术方向 | 多值（AI / 大模型、前端 / Web、DevOps / 云原生…），可多选筛选 |
| 项目类型 | AI 模型 / 应用、框架 / 库、工具 / 脚本、模板 / 脚手架、资料 / 清单 |
| 是否可部署 | 可部署 / 部分 / 无需部署 / 未知 |
| 可玩性 | 高 / 中 / 低 |
| 是否实用小工具 | 是 / 否 |
| 上榜态势 | 今日新上榜 / 持续在榜（跨日快照合并判定） |

> 候选池规模由 `CANDIDATE_POOL_SIZE`（默认 60）控制，与每日「自动解析」数量 `TRENDING_TOP_N`（默认 10）解耦——
> 池子可以很大，但只有被用户点选或进入 Top N 的仓库才会调用 LLM。
>
> 仓库描述由**免费翻译引擎**译为中文（有道 → MyMemory 降级），带内容寻址缓存，**不消耗 LLM token**；
> 卡片上可一键切换「中文 / 原文」。
>
> 搜索提供方：Bing 为主，GitHub Search 兜底（实测 DuckDuckGo 在本机网络下不可达）。

## 快速开始（CLI）

```bash
pip install -r requirements.txt
copy .env.example .env                       # 填入 LLM_API_KEY 等（可选：GITHUB_TOKEN、SMTP）
python main.py doctor                        # 检查配置
python main.py repo https://github.com/owner/repo   # 解析任意仓库
python main.py collect --pool 60             # 仅刷新候选池（抓取+打标+翻译，零 LLM）
python main.py translate                     # 为候选池补齐中文描述（免费引擎，带缓存）
python main.py daily                         # 抓取今日热门并归档/发邮件
```

## 文档状态

- 文档版本：v1.8.1
- 已就绪：`global.md`、`requirements.md`、`design.md`、`tasks.md`、`agent/*.md`（5 份）、`templates/*.md`（2 份）；流水线代码 `app/`、CLI `main.py`、后端 `server/`、前端 `frontend/`、测试 `tests/`（**171 项全部通过**）
- 决策事项：Q1–Q9 见 `requirements.md` §9 与 `tasks.md` 决策记录
- 数据读取：GitHub REST API 直连（`github.com/trending` 多入口聚合主方案 + Search API 降级）
- 描述翻译：免费翻译引擎 + 内容寻址缓存（不消耗 LLM）
- 代码与文档已对齐六模块口径；仓库发现与两阶段解析见 `design.md` §16
- 代码审查结论与整改记录见 `CODE_REVIEW.md`（v1.8.1 已修复全部 P0 与主要 P1）
