/** 任务领域 Hook：提交任务、列表轮询、单任务实时日志。 */
import { useCallback, useEffect, useRef, useState } from 'react'
import { ApiRequestError, api } from '../api/client'
import type { SubmitTaskPayload, TaskRecord } from '../api/types'

const POLL_INTERVAL = 1500

/** 轮询任务列表；有任务在运行时自动保持轮询。 */
export function useTasks(limit = 20) {
  const [items, setItems] = useState<TaskRecord[]>([])
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [submitting, setSubmitting] = useState(false)
  const timer = useRef<number | null>(null)

  const refresh = useCallback(async () => {
    try {
      const res = await api.listTasks(limit)
      setItems(res.items)
      setError(null)
    } catch (err) {
      setError(err instanceof ApiRequestError ? err.message : String(err))
    } finally {
      setLoading(false)
    }
  }, [limit])

  useEffect(() => {
    void refresh()
  }, [refresh])

  useEffect(() => {
    const hasActive = items.some((t) => t.status === 'running' || t.status === 'pending')
    if (!hasActive) {
      if (timer.current) window.clearInterval(timer.current)
      timer.current = null
      return
    }
    timer.current = window.setInterval(() => void refresh(), POLL_INTERVAL)
    return () => {
      if (timer.current) window.clearInterval(timer.current)
      timer.current = null
    }
  }, [items, refresh])

  const submit = useCallback(
    async (payload: SubmitTaskPayload) => {
      setSubmitting(true)
      setError(null)
      try {
        const task = await api.submitTask(payload)
        setItems((prev) => [task, ...prev])
        return task
      } catch (err) {
        const message = err instanceof ApiRequestError ? err.message : String(err)
        setError(message)
        throw err
      } finally {
        setSubmitting(false)
      }
    },
    [],
  )

  /** 以失败任务的目标重新提交（v1.8）：失败后无需手动重填地址。 */
  const retry = useCallback(async (taskId: string) => {
    setError(null)
    try {
      const task = await api.retryTask(taskId)
      setItems((prev) => [task, ...prev.filter((t) => t.task_id !== task.task_id)])
      return task
    } catch (err) {
      setError(err instanceof ApiRequestError ? err.message : String(err))
      return null
    }
  }, [])

  return { items, error, loading, submitting, submit, retry, refresh }
}

/** 单任务轮询（任务运行中每 1.5s 拉一次日志）。 */
export function useTaskDetail(taskId: string | undefined) {
  const [task, setTask] = useState<TaskRecord | null>(null)
  const [error, setError] = useState<string | null>(null)
  const timer = useRef<number | null>(null)

  useEffect(() => {
    if (!taskId) return
    let alive = true

    const poll = async () => {
      try {
        const next = await api.getTask(taskId)
        if (!alive) return
        setTask(next)
        setError(null)
        if (next.status === 'running' || next.status === 'pending') {
          timer.current = window.setTimeout(poll, POLL_INTERVAL)
        }
      } catch (err) {
        if (!alive) return
        setError(err instanceof ApiRequestError ? err.message : String(err))
      }
    }

    void poll()
    return () => {
      alive = false
      if (timer.current) window.clearTimeout(timer.current)
      timer.current = null
    }
  }, [taskId])

  return { task, error }
}
