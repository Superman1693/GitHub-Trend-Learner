/** 导航配置：侧栏与底部导航共用同一份来源。 */
import type { ComponentType } from 'react'
import {
  IconDashboard,
  IconDocument,
  IconSettings,
  IconSpark,
  IconTask,
} from '../components/ui/icons'

export interface NavItem {
  to: string
  label: string
  icon: ComponentType<{ size?: number }>
  /** 精确匹配（用于根路径） */
  end?: boolean
  /** 移动端底部导航是否展示 */
  mobile?: boolean
}

export const NAV_ITEMS: NavItem[] = [
  { to: '/', label: '概览', icon: IconDashboard, end: true, mobile: true },
  { to: '/discover', label: '发现仓库', icon: IconSpark, mobile: true },
  { to: '/documents', label: '解读文档', icon: IconDocument, mobile: true },
  { to: '/tasks', label: '任务', icon: IconTask, mobile: true },
  { to: '/settings', label: '系统设置', icon: IconSettings },
]

export const APP_NAME = 'GitHub-Trend-Learner'
export const APP_SUBTITLE = '热门仓库解读控制台'
