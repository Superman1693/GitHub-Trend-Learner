/** 顶栏：页面标题、后端健康状态、移动端菜单按钮。 */
import { IconMenu } from '../ui/icons'
import { StatusDot } from '../ui'
import type { HealthInfo } from '../../api/types'

interface TopbarProps {
  title: string
  health: HealthInfo | null
  healthError: string | null
  onMenuClick: () => void
}

export function Topbar({ title, health, healthError, onMenuClick }: TopbarProps) {
  const tone = healthError ? 'err' : health ? 'ok' : 'idle'
  const label = healthError ? '后端未连接' : health ? '后端正常' : '连接中…'

  return (
    <header className="topbar">
      <button className="icon-btn" onClick={onMenuClick} aria-label="打开导航菜单">
        <IconMenu size={18} />
      </button>

      <h1 className="topbar__title">{title}</h1>

      <div className="topbar__right">
        <span className="topbar__status" title={healthError ?? `版本 ${health?.version ?? '-'}`}>
          <StatusDot tone={tone} />
          <span>{label}</span>
        </span>
      </div>
    </header>
  )
}
