/** 系统领域 Hook：健康状态、运行配置、概览。 */
import { useCallback, useEffect } from 'react'
import { api } from '../api/client'
import type {
  Metrics,
  ScheduleStatus, HealthInfo, SystemConfig, SystemOverview } from '../api/types'
import { useAsync, type AsyncState } from './useAsync'

export function useHealth(): AsyncState<HealthInfo> {
  const loader = useCallback(() => api.health(), [])
  return useAsync(loader, [])
}

export function useSystemConfig(): AsyncState<SystemConfig> {
  const loader = useCallback(() => api.config(), [])
  return useAsync(loader, [])
}

export function useOverview(): AsyncState<SystemOverview> {
  const loader = useCallback(() => api.overview(), [])
  return useAsync(loader, [])
}

/** 定时任务状态。心跳每 30s 更新一次，故 60s 轮询足够，不必更频繁。 */
export function useSchedule(pollMs = 60000): AsyncState<ScheduleStatus> {
  const loader = useCallback(() => api.schedule(), [])
  const state = useAsync(loader, [])
  const { reload } = state

  useEffect(() => {
    const timer = window.setInterval(reload, pollMs)
    return () => window.clearInterval(timer)
  }, [reload, pollMs])

  return state
}

/** 运行指标。日志是追加写的，变化不快，进页面拉一次即可。 */
export function useMetrics(days = 7): AsyncState<Metrics> {
  const loader = useCallback(() => api.metrics(days), [days])
  return useAsync(loader, [days])
}
