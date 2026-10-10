# 控制台 API 清单

- 版本：v1.8.3
- 本文件由 `python main.py api-doc` 从路由表内省生成，请勿手工编辑。
- 共 17 个接口；机器可读版本见 `GET /api/openapi.json`。
- 统一错误结构：`{"error": {"code": "...", "message": "..."}}`

## 接口一览

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/candidates` | 候选仓库列表 |
| GET | `/api/candidates/facets` | 候选筛选项与分布 |
| GET | `/api/candidates/{owner}/{repo}` | 候选仓库详情 |
| POST | `/api/candidates/{owner}/{repo}/analyze` | 阶段二：调用 AI 深入解析 |
| POST | `/api/candidates/{owner}/{repo}/preview` | 阶段一：搜索引擎摘要 |
| GET | `/api/documents` | 文档列表 / 全文检索 |
| GET | `/api/documents/export` | 批量导出 ZIP |
| GET | `/api/documents/stats` | 文档统计 |
| GET | `/api/documents/{date}/{name}` | 文档详情 |
| GET | `/api/health` | 健康检查 |
| GET | `/api/openapi.json` | 接口清单（OpenAPI 3.1） |
| GET | `/api/system/config` | 运行配置 |
| GET | `/api/system/overview` | 产出概览 |
| GET | `/api/tasks` | 任务列表 |
| POST | `/api/tasks` | 提交任务 |
| GET | `/api/tasks/{task_id}` | 任务详情 |
| POST | `/api/tasks/{task_id}/retry` | 重试任务 |

## 接口详情

### `GET /api/candidates`

候选仓库列表

多条件组合筛选候选池。全部筛选为规则判定，不调用 LLM。

| 参数 | 位置 | 说明 |
| --- | --- | --- |
| `language` | query | 编程语言 |
| `deployable` | query | 可部署性 |
| `playfulness` | query | 可玩性 |
| `practical_tool` | query | 是否实用工具 |
| `project_type` | query | 项目类型 |
| `direction` | query | 技术方向 |
| `trend` | query | 上榜态势 new/rising |
| `min_stars` | query | 最低 star |
| `min_days` | query | 最少上榜天数 |
| `q` | query | 关键词 |
| `day` | query | 仅看某日上榜 |
| `limit` | query | 返回条数，默认 120，上限 400 |

### `GET /api/candidates/facets`

候选筛选项与分布

返回各维度的取值分布、star 区间、可用日期与中文标签表，供筛选器渲染。

### `GET /api/candidates/{owner}/{repo}`

候选仓库详情

返回单仓库的元信息、目录树与规则打标结果。

- 路径参数：`owner`

- 路径参数：`repo`

### `POST /api/candidates/{owner}/{repo}/analyze`

阶段二：调用 AI 深入解析

提交完整六模块解析任务（**会调用 LLM**），返回任务记录。

- 路径参数：`owner`

- 路径参数：`repo`

### `POST /api/candidates/{owner}/{repo}/preview`

阶段一：搜索引擎摘要

只调搜索引擎做轻量检索，**不调用 LLM**；返回结果明确标注「非 AI 生成」。

- 路径参数：`owner`

- 路径参数：`repo`

请求体（JSON）：

- `query`：可选，自定义检索词

### `GET /api/documents`

文档列表 / 全文检索

不带 q 时按日期倒序返回文档列表；带 q 时执行全文检索，返回 match_count 与 snippet，total 为真实命中数。

| 参数 | 位置 | 说明 |
| --- | --- | --- |
| `q` | query | 关键词（触发全文检索） |
| `date` | query | 按日期筛选 YYYY-MM-DD |
| `limit` | query | 检索模式下的分页大小，默认 50，上限 200 |

### `GET /api/documents/export`

批量导出 ZIP

把产出文档打包为 ZIP（保留 日期/文件名.md 结构 + MANIFEST.txt）。上限 300 份 / 64 MB，超限截断并在清单注明。

| 参数 | 位置 | 说明 |
| --- | --- | --- |
| `date` | query | 只导出指定日期 YYYY-MM-DD；不传则导出全部 |

响应类型：`application/zip`

### `GET /api/documents/stats`

文档统计

返回文档总数、日期数与每日份数分布。

### `GET /api/documents/{date}/{name}`

文档详情

返回单个文档的元信息、按 ## 切分的模块结构与完整 Markdown。

- 路径参数：`date`

- 路径参数：`name`

### `GET /api/health`

健康检查

返回服务状态、版本号与前端构建产物信息。

### `GET /api/openapi.json`

接口清单（OpenAPI 3.1）

从路由表内省生成的机器可读接口文档，路径与方法保证与实现一致。

### `GET /api/system/config`

运行配置

返回并发数、重试次数、LLM/SMTP/GitHub 是否就绪、六模块规范。敏感值只报告是否配置。

### `GET /api/system/overview`

产出概览

返回文档统计与任务运行数，供仪表盘使用。

### `GET /api/tasks`

任务列表

按创建时间倒序返回最近的任务记录（含状态与日志）。

| 参数 | 位置 | 说明 |
| --- | --- | --- |
| `limit` | query | 返回条数，默认 20，上限 50 |

### `POST /api/tasks`

提交任务

提交仓库解析（kind=repo）或每日热门（kind=daily）任务。同一目标在途时会幂等返回既有任务。

请求体（JSON）：

- `kind`：repo | daily（必填）
- `url`：kind=repo 时的仓库地址
- `top`：kind=daily 时的解析数量，1–50

### `GET /api/tasks/{task_id}`

任务详情

返回单个任务的状态、报告与实时日志。

- 路径参数：`task_id`

### `POST /api/tasks/{task_id}/retry`

重试任务

以失败任务的原目标重新提交，返回新任务（retried_from 指向原任务）。

- 路径参数：`task_id`
