/** 系统领域 Hook：健康状态、运行配置、概览。 */
import { useCallback } from 'react'
import { api } from '../api/client'
import type { HealthInfo, SystemConfig, SystemOverview } from '../api/types'
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
