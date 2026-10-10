/**
 * HTTP 客户端：统一请求、错误归一化、超时控制。
 *
 * 所有错误都归一为 ApiError 形态，调用方只需 catch 一次。
 */
import type {
  ApiError,
  Candidate,
  CandidateFacets,
  CandidateFilters,
  CandidateListResponse,
  DocumentDetail,
  DocumentMeta,
  HealthInfo,
  PreviewResponse,
  SubmitTaskPayload,
  SystemConfig,
  SystemOverview,
  TaskRecord,
} from './types'

const BASE = '/api'
const DEFAULT_TIMEOUT = 15000

export class ApiRequestError extends Error {
  readonly status: number
  readonly code: string

  constructor(status: number, error: ApiError) {
    super(error.message)
    this.name = 'ApiRequestError'
    this.status = status
    this.code = error.code
  }
}

async function request<T>(
  path: string,
  init: RequestInit = {},
  timeout = DEFAULT_TIMEOUT,
): Promise<T> {
  const controller = new AbortController()
  const timer = window.setTimeout(() => controller.abort(), timeout)

  try {
    const res = await fetch(`${BASE}${path}`, {
      ...init,
      signal: controller.signal,
      headers: {
        Accept: 'application/json',
        ...(init.body ? { 'Content-Type': 'application/json' } : {}),
        ...init.headers,
      },
    })

    const text = await res.text()
    let payload: unknown = null
    if (text) {
      try {
        payload = JSON.parse(text)
      } catch {
        throw new ApiRequestError(res.status, {
          code: 'INVALID_RESPONSE',
          message: `服务端返回了非 JSON 内容（HTTP ${res.status}）`,
        })
      }
    }

    if (!res.ok) {
      const err = (payload as { error?: ApiError } | null)?.error
      throw new ApiRequestError(res.status, {
        code: err?.code ?? `HTTP_${res.status}`,
        message: err?.message ?? `请求失败（HTTP ${res.status}）`,
      })
    }

    return payload as T
  } catch (err) {
    if (err instanceof ApiRequestError) throw err
    if (err instanceof DOMException && err.name === 'AbortError') {
      throw new ApiRequestError(0, { code: 'TIMEOUT', message: '请求超时，请检查后端服务是否在运行' })
    }
    throw new ApiRequestError(0, {
      code: 'NETWORK_ERROR',
      message: '无法连接到后端服务，请确认已启动 python -m server',
    })
  } finally {
    window.clearTimeout(timer)
  }
}

export const api = {
  health: () => request<HealthInfo>('/health'),

  config: () => request<SystemConfig>('/system/config'),

  overview: () => request<SystemOverview>('/system/overview'),

  listDocuments: (params: { date?: string; q?: string } = {}) => {
    const qs = new URLSearchParams()
    if (params.date) qs.set('date', params.date)
    if (params.q) qs.set('q', params.q)
    const suffix = qs.toString() ? `?${qs}` : ''
    return request<{ total: number; items: DocumentMeta[] }>(`/documents${suffix}`)
  },

  getDocument: (date: string, name: string) =>
    request<DocumentDetail>(
      `/documents/${encodeURIComponent(date)}/${encodeURIComponent(name)}`,
    ),

  listTasks: (limit = 20) =>
    request<{ total: number; items: TaskRecord[] }>(`/tasks?limit=${limit}`),

  getTask: (taskId: string) => request<TaskRecord>(`/tasks/${encodeURIComponent(taskId)}`),

  /** 以失败任务的目标重新提交（v1.8） */
  retryTask: (taskId: string) =>
    request<TaskRecord>(
      `/tasks/${encodeURIComponent(taskId)}/retry`,
      { method: 'POST', body: JSON.stringify({}) },
      20000,
    ),

  submitTask: (payload: SubmitTaskPayload) =>
    request<TaskRecord>('/tasks', { method: 'POST', body: JSON.stringify(payload) }, 20000),

  /* ---- 候选仓库发现（design.md §16） ---- */

  listCandidates: (filters: CandidateFilters = {}) => {
    const qs = new URLSearchParams()
    Object.entries(filters).forEach(([key, value]) => {
      if (value !== undefined && value !== null && value !== '') qs.set(key, String(value))
    })
    const suffix = qs.toString() ? `?${qs}` : ''
    return request<CandidateListResponse>(`/candidates${suffix}`)
  },

  candidateFacets: () => request<CandidateFacets>('/candidates/facets'),

  candidateDetail: (owner: string, repo: string) =>
    request<Candidate>(`/candidates/${encodeURIComponent(owner)}/${encodeURIComponent(repo)}`),

  /** 阶段一：搜索引擎摘要（后端保证不调用 LLM） */
  previewCandidate: (owner: string, repo: string, query?: string) =>
    request<PreviewResponse>(
      `/candidates/${encodeURIComponent(owner)}/${encodeURIComponent(repo)}/preview`,
      { method: 'POST', body: JSON.stringify(query ? { query } : {}) },
      30000,
    ),

  /** 阶段二：提交完整 LLM 解析任务 */
  analyzeCandidate: (owner: string, repo: string) =>
    request<TaskRecord>(
      `/candidates/${encodeURIComponent(owner)}/${encodeURIComponent(repo)}/analyze`,
      { method: 'POST', body: JSON.stringify({}) },
      20000,
    ),
}
