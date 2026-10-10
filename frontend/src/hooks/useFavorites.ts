/**
 * 收藏切换 Hook（v1.8.3）。
 *
 * 设计取舍：**不做乐观更新**。收藏是低频操作，用户点一下等 100ms 完全可以接受；
 * 而乐观更新一旦请求失败就会出现「界面显示已收藏、实际没存」的假象——
 * 对「攒着回头再看」这个场景，这种假象的代价比等一下更高。
 * 这里改为等接口返回后再更新界面，失败时给出明确提示。
 */
import { useCallback, useState } from 'react'
import { ApiRequestError, api } from '../api/client'
import type { Candidate } from '../api/types'

export function useFavoriteToggle(onSettled?: (fullName: string, favorited: boolean) => void) {
  const [pending, setPending] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  const toggle = useCallback(
    async (candidate: Candidate): Promise<boolean | null> => {
      const [owner, repo] = candidate.full_name.split('/')
      if (!owner || !repo) return null

      setPending(candidate.full_name)
      setError(null)
      try {
        const res = candidate.favorited
          ? await api.unfavoriteCandidate(owner, repo)
          : await api.favoriteCandidate(owner, repo)
        onSettled?.(candidate.full_name, res.favorited)
        return res.favorited
      } catch (err) {
        setError(err instanceof ApiRequestError ? err.message : String(err))
        return null
      } finally {
        setPending(null)
      }
    },
    [onSettled],
  )

  return { toggle, pending, error }
}
