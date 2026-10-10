/** 任务列表：状态徽标、耗时、可展开的实时日志，失败任务可一键重试。 */
import { useState } from 'react'
import type { TaskRecord, TaskStatus } from '../../api/types'
import { Badge, Button, EmptyState, LoadingBlock, StatusDot } from '../ui'
import { IconChevronRight, IconRefresh } from '../ui/icons'
import './tasks.css'

const STATUS_META: Record<
  TaskStatus,
  { label: string; tone: 'neutral' | 'accent' | 'success' | 'danger'; dot: 'idle' | 'running' | 'ok' | 'err' }
> = {
  pending: { label: '排队中', tone: 'neutral', dot: 'idle' },
  running: { label: '运行中', tone: 'accent', dot: 'running' },
  succeeded: { label: '已完成', tone: 'success', dot: 'ok' },
  failed: { label: '失败', tone: 'danger', dot: 'err' },
}

function duration(task: TaskRecord): string {
  if (!task.started_at) return '-'
  const start = new Date(task.started_at.replace(' ', 'T')).getTime()
  const end = task.finished_at
    ? new Date(task.finished_at.replace(' ', 'T')).getTime()
    : Date.now()
  if (Number.isNaN(start) || Number.isNaN(end)) return '-'
  const seconds = Math.max(0, Math.round((end - start) / 1000))
  if (seconds < 60) return `${seconds} 秒`
  return `${Math.floor(seconds / 60)} 分 ${seconds % 60} 秒`
}

interface TaskLogPanelProps {
  items: TaskRecord[]
  loading: boolean
  error: string | null
  onRetry?: (taskId: string) => Promise<TaskRecord | null>
}

export function TaskLogPanel({ items, loading, error, onRetry }: TaskLogPanelProps) {
  const [expanded, setExpanded] = useState<string | null>(null)
  const [retrying, setRetrying] = useState<string | null>(null)

  if (loading) return <LoadingBlock text="正在读取任务列表…" />
  if (error) return <EmptyState title="无法加载任务列表" description={error} />
  if (items.length === 0) {
    return (
      <EmptyState
        title="暂无任务记录"
        description="提交一个任务后，这里会显示运行状态与实时日志。任务记录会持久化到 cache/tasks.json，服务重启后仍可回溯。"
      />
    )
  }

  const handleRetry = async (taskId: string) => {
    if (!onRetry) return
    setRetrying(taskId)
    try {
      await onRetry(taskId)
    } finally {
      setRetrying(null)
    }
  }

  return (
    <div className="task-list">
      {items.map((task) => {
        const meta = STATUS_META[task.status]
        const open = expanded === task.task_id
        return (
          <div className="task-item" key={task.task_id}>
            <button
              type="button"
              className="task-item__head"
              onClick={() => setExpanded(open ? null : task.task_id)}
              aria-expanded={open}
            >
              <StatusDot tone={meta.dot} />
              <div className="grow">
                <div className="task-item__title truncate">
                  {task.kind === 'repo' ? '仓库解析' : '每日热门'} · {task.target}
                </div>
                <div className="task-item__sub">
                  创建于 {task.created_at} · 耗时 {duration(task)}
                </div>
              </div>
              <Badge tone={meta.tone}>{meta.label}</Badge>
              <span
                style={{
                  display: 'inline-flex',
                  transform: open ? 'rotate(90deg)' : 'none',
                  transition: 'transform 200ms',
                  color: 'var(--c-text-subtle)',
                }}
              >
                <IconChevronRight size={16} />
              </span>
            </button>

            {open && (
              <div className="task-item__body">
                <div className="kv">
                  <span className="kv__k">任务 ID</span>
                  <span className="kv__v mono">{task.task_id}</span>
                  <span className="kv__k">开始时间</span>
                  <span className="kv__v">{task.started_at ?? '-'}</span>
                  <span className="kv__k">结束时间</span>
                  <span className="kv__v">{task.finished_at ?? '-'}</span>
                  {task.error && (
                    <>
                      <span className="kv__k">错误</span>
                      <span className="kv__v" style={{ color: 'var(--c-danger)' }}>
                        {task.error}
                      </span>
                    </>
                  )}
                  {task.report && 'ok' in task.report && (
                    <>
                      <span className="kv__k">结果</span>
                      <span className="kv__v">
                        {task.report.ok ? '成功' : '失败（已降级交付）'}
                      </span>
                    </>
                  )}
                  {task.retried_from && (
                    <>
                      <span className="kv__k">重试自</span>
                      <span className="kv__v mono">{task.retried_from}</span>
                    </>
                  )}
                </div>

                {onRetry && task.status !== 'running' && task.status !== 'pending' && (
                  <div className="row" style={{ marginBottom: 'var(--sp-3)' }}>
                    <Button
                      variant={task.status === 'failed' ? 'primary' : 'default'}
                      icon={<IconRefresh size={14} />}
                      loading={retrying === task.task_id}
                      onClick={() => void handleRetry(task.task_id)}
                      title="以相同目标重新提交一个任务"
                    >
                      {task.status === 'failed' ? '重试此任务' : '重新运行'}
                    </Button>
                  </div>
                )}

                <pre className="task-log">{task.log.join('\n')}</pre>
              </div>
            )}
          </div>
        )
      })}
    </div>
  )
}
