/** 文档领域 Hook：列表与详情。 */
import { useCallback } from 'react'
import { api } from '../api/client'
import type { DocumentDetail, DocumentMeta, DocumentStats } from '../api/types'
import { useAsync, type AsyncState } from './useAsync'

export interface DocumentFilters {
  date?: string
  q?: string
}

export function useDocuments(filters: DocumentFilters = {}): AsyncState<DocumentMeta[]> {
  const { date, q } = filters
  const loader = useCallback(async () => {
    const res = await api.listDocuments({ date, q })
    return res.items
  }, [date, q])
  return useAsync(loader, [date, q], { keepPreviousData: true })
}

export function useDocumentStats(): AsyncState<DocumentStats> {
  const loader = useCallback(() => api.overview().then((o) => o.documents), [])
  return useAsync(loader, [])
}

export function useDocument(
  date: string | undefined,
  name: string | undefined,
): AsyncState<DocumentDetail> {
  const loader = useCallback(async () => {
    if (!date || !name) throw new Error('缺少文档标识')
    return api.getDocument(date, name)
  }, [date, name])
  return useAsync(loader, [date, name])
}
