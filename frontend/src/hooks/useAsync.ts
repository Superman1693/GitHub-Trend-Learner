/** 通用异步数据 Hook：统一 loading / error / reload 语义。 */
import { useCallback, useEffect, useRef, useState } from 'react'
import { ApiRequestError } from '../api/client'

export interface AsyncState<T> {
  data: T | null
  error: string | null
  loading: boolean
  reload: () => void
}

export function useAsync<T>(
  loader: () => Promise<T>,
  deps: readonly unknown[] = [],
  options: { keepPreviousData?: boolean } = {},
): AsyncState<T> {
  const [data, setData] = useState<T | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [tick, setTick] = useState(0)

  const loaderRef = useRef(loader)
  loaderRef.current = loader
  const keepRef = useRef(options.keepPreviousData)
  keepRef.current = options.keepPreviousData

  const reload = useCallback(() => setTick((n) => n + 1), [])

  useEffect(() => {
    let alive = true
    setLoading(true)
    if (!keepRef.current) setError(null)

    loaderRef
      .current()
      .then((result) => {
        if (!alive) return
        setData(result)
        setError(null)
      })
      .catch((err: unknown) => {
        if (!alive) return
        setError(
          err instanceof ApiRequestError ? err.message : `加载失败：${String(err)}`,
        )
      })
      .finally(() => {
        if (alive) setLoading(false)
      })

    return () => {
      alive = false
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, tick])

  return { data, error, loading, reload }
}
