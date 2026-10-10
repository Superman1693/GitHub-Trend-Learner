/** 任务启动器：选择任务类型（仓库解析 / 每日热门）并提交。 */
import { useState, type FormEvent } from 'react'
import type { SubmitTaskPayload, TaskKind } from '../../api/types'
import { Alert, Button, Field } from '../ui'
import './tasks.css'

interface TaskLauncherProps {
  submitting: boolean
  error: string | null
  onSubmit: (payload: SubmitTaskPayload) => Promise<unknown>
}

const REPO_PATTERN = /^(https?:\/\/(www\.)?github\.com\/[\w.-]+\/[\w.-]+\/?|[\w.-]+\/[\w.-]+)$/

export function TaskLauncher({ submitting, error, onSubmit }: TaskLauncherProps) {
  const [kind, setKind] = useState<TaskKind>('repo')
  const [url, setUrl] = useState('')
  const [top, setTop] = useState('3')
  const [localError, setLocalError] = useState<string | null>(null)

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    setLocalError(null)

    if (kind === 'repo') {
      const trimmed = url.trim()
      if (!trimmed) {
        setLocalError('请填写仓库地址')
        return
      }
      if (!REPO_PATTERN.test(trimmed)) {
        setLocalError('地址格式不正确，示例：https://github.com/owner/repo 或 owner/repo')
        return
      }
      await onSubmit({ kind: 'repo', url: trimmed })
      return
    }

    const parsed = Number.parseInt(top, 10)
    if (Number.isNaN(parsed) || parsed < 1 || parsed > 20) {
      setLocalError('解析数量需为 1–20 之间的整数')
      return
    }
    await onSubmit({ kind: 'daily', top: parsed })
  }

  const message = localError ?? error

  return (
    <form onSubmit={handleSubmit}>
      <div className="segmented" role="tablist" aria-label="任务类型">
        <button
          type="button"
          role="tab"
          aria-selected={kind === 'repo'}
          className={`segmented__item${kind === 'repo' ? ' is-active' : ''}`}
          onClick={() => setKind('repo')}
        >
          解析指定仓库
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={kind === 'daily'}
          className={`segmented__item${kind === 'daily' ? ' is-active' : ''}`}
          onClick={() => setKind('daily')}
        >
          每日热门
        </button>
      </div>

      <div className="launcher__row" style={{ marginTop: 'var(--sp-4)' }}>
        {kind === 'repo' ? (
          <div className="grow">
            <Field
              label="仓库地址"
              hint="支持完整链接或 owner/repo 简写"
              htmlFor="task-url"
            >
              <input
                id="task-url"
                className="input"
                value={url}
                onChange={(e) => setUrl(e.target.value)}
                placeholder="https://github.com/owner/repo"
                autoComplete="off"
                spellCheck={false}
              />
            </Field>
          </div>
        ) : (
          <div style={{ width: 160 }}>
            <Field label="解析数量" hint="抓取当日热门榜前 N 个" htmlFor="task-top">
              <input
                id="task-top"
                className="input"
                type="number"
                min={1}
                max={20}
                value={top}
                onChange={(e) => setTop(e.target.value)}
              />
            </Field>
          </div>
        )}

        <Button type="submit" variant="primary" size="lg" loading={submitting}>
          {submitting ? '提交中…' : '开始任务'}
        </Button>
      </div>

      {message && (
        <div style={{ marginTop: 'var(--sp-3)' }}>
          <Alert tone="danger" title="无法提交">
            {message}
          </Alert>
        </div>
      )}
    </form>
  )
}
