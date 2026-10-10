/** 顶栏：页面标题、后端健康状态、定时任务状态、移动端菜单按钮。 */
import { IconMenu } from '../ui/icons'
import { StatusDot } from '../ui'
import { useSchedule } from '../../hooks/useSystem'
import type { HealthInfo } from '../../api/types'

interface TopbarProps {
  title: string
  health: HealthInfo | null
  healthError: string | null
  onMenuClick: () => void
}

/**
 * 定时任务状态角标（v1.8.3）。
 *
 * `serve` 是独立进程，前端此前完全不知道它在不在跑。
 * 三种状态刻意区分开：
 *   在跑 → 绿点 + 下次执行时间；
 *   已停止 / 从未启动 → 灰点 + 原因（不报红，因为「没开定时」是常见且合法的选择）；
 *   后端取不到状态 → 不显示，避免误报。
 */
function ScheduleBadge() {
  const { data, error } = useSchedule()

  if (error || !data) return null

  const running = data.running
  const neverStarted = data.reason === 'never_started'

  const label = running
    ? `定时任务运行中${data.next_run_at ? ` · 下次 ${data.next_run_at.slice(5)}` : ''}`
    : neverStarted
      ? '定时任务未启动'
      : '定时任务已停止'

  const tip = [
    data.message,
    data.last_run_at ? `上次执行：${data.last_run_at}（${data.last_result ?? '-'}）` : null,
    !running && !neverStarted ? '执行 python main.py serve 可重新开启' : null,
  ]
    .filter(Boolean)
    .join('\n')

  return (
    <span
      className={`topbar__status${running ? '' : ' topbar__status--muted'}`}
      title={tip}
    >
      {/* 顺序与健康角标一致：圆点在前、文字在后，
          这样移动端的 `span:last-child { display:none }` 会正确地只保留圆点 */}
      <StatusDot tone={running ? 'ok' : 'idle'} />
      <span>{label}</span>
    </span>
  )
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
        <ScheduleBadge />
        <span className="topbar__status" title={healthError ?? `版本 ${health?.version ?? '-'}`}>
          <StatusDot tone={tone} />
          <span>{label}</span>
        </span>
      </div>
    </header>
  )
}
