/** 与后端 API 契约对应的类型定义（见 server/routes/*.py）。 */

export interface ApiError {
  code: string
  message: string
}

export interface DocumentMeta {
  doc_id: string
  date: string
  name: string
  title: string
  size: number
  modified: string
  module_count: number
  /** 全文检索命中时才返回（v1.8） */
  snippet?: string
  match_count?: number
  matched_in?: string
}

export interface DocumentModule {
  key: string
  title: string
  raw_title: string
  content: string
}

export interface DocumentDetail {
  doc_id: string
  date: string
  name: string
  title: string
  meta: Record<string, string>
  modules: DocumentModule[]
  markdown: string
  size: number
  modified: string
}

export interface DateBucket {
  date: string
  count: number
}

export interface DocumentStats {
  total_documents: number
  total_dates: number
  latest_date: string | null
  dates: DateBucket[]
}

export type TaskKind = 'repo' | 'daily'
export type TaskStatus = 'pending' | 'running' | 'succeeded' | 'failed'

export interface TaskRecord {
  task_id: string
  kind: TaskKind
  target: string
  status: TaskStatus
  created_at: string
  started_at: string | null
  finished_at: string | null
  report: Record<string, unknown> | null
  error: string | null
  retried_from?: string | null
  log: string[]
}

export interface SystemConfig {
  github_token: { configured: boolean }
  llm: { ready: boolean; model: string | null }
  smtp: { ready: boolean }
  concurrency: number
  max_retries: number
  max_gate_returns: number
  /** 六模块规范由后端单一来源透出（v1.8）；旧后端可能不返回 */
  modules?: { key: string; name: string }[]
  version?: string
}

export interface SystemOverview {
  documents: DocumentStats
  tasks: { running: number; total: number }
}

export interface HealthInfo {
  status: string
  service: string
  version: string
  time: string
  frontend: { built: boolean; dist_path: string; index_mtime: number | null }
}

export interface SubmitTaskPayload {
  kind: TaskKind
  url?: string
  top?: number | null
}

/* ---------------- 候选仓库发现（design.md §16） ---------------- */

export type Deployable = 'yes' | 'partial' | 'no' | 'unknown'
export type Playfulness = 'high' | 'medium' | 'low' | 'unknown'
export type YesNo = 'yes' | 'no' | 'unknown'

export interface Dimensions {
  highlight: string
  directions?: string[]
  learnable: string
  deployable: Deployable
  playfulness: Playfulness
  practical_tool: YesNo
  project_type: string
  reasons: Record<string, string[]>
}

export interface Candidate {
  full_name: string
  html_url: string
  description: string
  description_zh?: string
  language: string | null
  stars: number
  forks?: number
  stars_today?: number | null
  topics: string[]
  dimensions: Dimensions
  first_seen: string
  last_seen: string
  days: string[]
  days_count?: number
  trend?: 'new' | 'rising' | 'unknown'
  /** star 趋势序列（由旧到新），与 history_days 逐位对应（v1.8.3） */
  star_history?: number[]
  history_days?: string[]
  /** 序列首尾差值；不足 2 个点时为 0 */
  star_delta?: number
  /** 是否已收藏（v1.8.3） */
  favorited?: boolean
}

export interface ScheduleStatus {
  running: boolean
  /** 判定依据：running / stale / never_started / unknown_heartbeat */
  reason: 'running' | 'stale' | 'never_started' | 'unknown_heartbeat'
  message: string
  at: string | null
  next_run_at: string | null
  last_run_at: string | null
  last_result: string | null
  heartbeat: string | null
  stale_seconds: number | null
  started_at?: string
  pid?: number
}

export interface FavoriteResult {
  full_name: string
  favorited: boolean
  /** 本次调用是否真的改变了状态（重复收藏为 false） */
  changed: boolean
  total: number
}

export interface FavoriteItem {
  full_name: string
  html_url: string
  stars: number | null
  language: string | null
  description: string | null
  description_zh: string | null
  added_at: string
  note: string
  /** 是否仍在当前候选池中；false 表示已下榜但仍可解析 */
  in_pool: boolean
}

export interface FavoriteListResponse {
  total: number
  items: FavoriteItem[]
}

export interface DimensionLabels {
  deployable: Record<string, string>
  playfulness: Record<string, string>
  practical_tool: Record<string, string>
  project_type?: Record<string, string>
  trend?: Record<string, string>
}

export interface CandidateListResponse {
  total: number
  pool_total: number
  items: Candidate[]
  labels: DimensionLabels
}

export interface CandidateFacets {
  total: number
  languages: Record<string, number>
  deployable: Record<string, number>
  playfulness: Record<string, number>
  practical_tool: Record<string, number>
  project_type: Record<string, number>
  directions: Record<string, number>
  trend: Record<string, number>
  stars: { max: number; min: number }
  days: string[]
  labels: DimensionLabels
}

export interface SearchHit {
  title: string
  url: string
  snippet: string
  domain: string
}

/** 阶段一：搜索引擎摘要（不含 LLM 输出） */
export interface PreviewResponse {
  query: string
  provider: string
  results: SearchHit[]
  took_ms: number
  degraded: boolean
  note: string
  disclaimer: string
  full_name: string
  html_url: string
  stage: 'preview'
  llm_used: false
}

export interface CandidateFilters {
  language?: string
  deployable?: string
  playfulness?: string
  practical_tool?: string
  project_type?: string
  direction?: string
  trend?: string
  favorited?: boolean
  min_stars?: number
  min_days?: number
  q?: string
  day?: string
}


export interface AgentMetrics {
  calls: number
  done: number
  failed: number
  /** null 表示该 Agent 不记录 done 事件，成功率无从计算（≠ 0%） */
  success_rate: number | null
  avg_ms: number
  p95_ms: number
  duration_samples: number
}

export interface Metrics {
  range: { days: number; files: number; events: number }
  tasks: { started: number; failed: number; retry: number; success_rate: number | null }
  agents: Record<string, AgentMetrics>
  cache: { hit: number; stored: number; lookups: number; hit_rate: number | null }
  gate: Record<string, number>
  tokens: { total: number; avg_per_task: number }
  slowest: Array<{ agent: string; duration_ms: number; status: string; task_id: string | null; ts: string | null }>
  recent_errors: Array<{ ts: string | null; agent: string; task_id: string | null; error: string }>
}
