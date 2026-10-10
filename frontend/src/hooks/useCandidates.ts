/** 候选仓库发现 Hook（design.md §16）。筛选与预览阶段**不产生 LLM 调用**。 */
import { useCallback, useState } from 'react'
import { ApiRequestError, api } from '../api/client'
import type {
  CandidateFacets,
  CandidateFilters,
  CandidateListResponse,
  PreviewResponse,
} from '../api/types'
import { useAsync, type AsyncState } from './useAsync'

export function useCandidates(filters: CandidateFilters): AsyncState<CandidateListResponse> {
  const key = JSON.stringify(filters)
  const loader = useCallback(() => api.listCandidates(filters), [key])
  return useAsync(loader, [key], { keepPreviousData: true })
}

export function useCandidateFacets(): AsyncState<CandidateFacets> {
  const loader = useCallback(() => api.candidateFacets(), [])
  return useAsync(loader, [])
}

/** 阶段一：搜索引擎摘要。可重复触发，不计入 LLM 预算。 */
export function useCandidatePreview() {
  const [data, setData] = useState<PreviewResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const run = useCallback(async (owner: string, repo: string, query?: string) => {
    setLoading(true)
    setError(null)
    try {
      const res = await api.previewCandidate(owner, repo, query)
      setData(res)
      return res
    } catch (err) {
      const message = err instanceof ApiRequestError ? err.message : String(err)
      setError(message)
      return null
    } finally {
      setLoading(false)
    }
  }, [])

  const reset = useCallback(() => {
    setData(null)
    setError(null)
  }, [])

  return { data, loading, error, run, reset }
}

/** 阶段二：提交 LLM 解析任务。 */
export function useAnalyzeCandidate() {
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [submittedFor, setSubmittedFor] = useState<string | null>(null)

  const run = useCallback(async (owner: string, repo: string) => {
    setSubmitting(true)
    setError(null)
    try {
      const task = await api.analyzeCandidate(owner, repo)
      setSubmittedFor(`${owner}/${repo}`)
      return task
    } catch (err) {
      setError(err instanceof ApiRequestError ? err.message : String(err))
      return null
    } finally {
      setSubmitting(false)
    }
  }, [])

  return { submitting, error, submittedFor, run }
}
