/**
 * 阶段一：搜索引擎摘要抽屉（design.md §16.6）。
 *
 * 严格遵守分阶段原则：
 *   - 本组件只展示搜索引擎返回的原始结果，**不产生任何 LLM 调用**；
 *   - 顶部明确标注「非 AI 生成」；
 *   - 「深入解析」是进入阶段二的唯一入口，且提示会调用 AI。
 */
import { useEffect, useState } from 'react'
import type { Candidate, DimensionLabels } from '../../api/types'
import { useCandidatePreview } from '../../hooks/useCandidates'
import { Alert, Button, Spinner } from '../ui'
import { IconClose, IconExternal, IconRefresh, IconSpark } from '../ui/icons'
import './discovery.css'

interface PreviewPanelProps {
  candidate: Candidate | null
  labels?: DimensionLabels
  onClose: () => void
  onAnalyze: (c: Candidate) => void
  analyzing?: boolean
}

function DimensionGrid({ candidate, labels }: { candidate: Candidate; labels?: DimensionLabels }) {
  const d = candidate.dimensions
  const cells = [
    { label: '项目类型', value: labels?.project_type?.[d.project_type] ?? d.project_type },
    { label: '技术方向', value: (d.directions ?? []).join('、') || d.highlight },
    { label: '可学习之处', value: d.learnable, reason: d.reasons?.learnable?.[0] },
    { label: '是否可部署', value: labels?.deployable?.[d.deployable] ?? d.deployable, reason: d.reasons?.deployable?.[0] },
    { label: '可玩性', value: labels?.playfulness?.[d.playfulness] ?? d.playfulness, reason: d.reasons?.playfulness?.[0] },
    { label: '实用小工具', value: labels?.practical_tool?.[d.practical_tool] ?? d.practical_tool, reason: d.reasons?.practical_tool?.[0] },
  ]
  return (
    <div className="dim-grid">
      {cells.map((c) => (
        <div className="dim-cell" key={c.label}>
          <div className="dim-cell__label">{c.label}</div>
          <div className="dim-cell__value">{c.value}</div>
          {c.reason && <div className="dim-cell__reason">{c.reason}</div>}
        </div>
      ))}
    </div>
  )
}

export function PreviewPanel({ candidate, labels, onClose, onAnalyze, analyzing }: PreviewPanelProps) {
  const { data, loading, error, run, reset } = useCandidatePreview()
  const [customQuery, setCustomQuery] = useState('')

  const [owner, repo] = (candidate?.full_name ?? '/').split('/')

  // 打开面板时自动跑一次阶段一检索
  useEffect(() => {
    if (!candidate) return
    setCustomQuery('')
    void run(owner, repo)
    return () => reset()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [candidate?.full_name])

  if (!candidate) return null

  return (
    <>
      <button className="overlay" onClick={onClose} aria-label="关闭" />
      <aside className="panel" role="dialog" aria-modal="true" aria-label="仓库摘要">
        <header className="panel__head">
          <div style={{ minWidth: 0 }}>
            <div className="row" style={{ marginBottom: 6, gap: 'var(--sp-2)' }}>
              <span className="stage-badge stage-badge--search">阶段一 · 搜索引擎</span>
              {data && <span className="text-subtle">{data.took_ms} ms</span>}
            </div>
            <h2 className="panel__title truncate">{candidate.full_name}</h2>
            <p className="text-subtle clamp-2" style={{ marginTop: 4 }}>
              {candidate.description_zh || candidate.description || '（该仓库未填写描述）'}
            </p>
          </div>
          <button className="icon-btn" onClick={onClose} aria-label="关闭" style={{ display: 'flex' }}>
            <IconClose size={16} />
          </button>
        </header>

        <div className="panel__body">
          <div className="stack">
            <section>
              <div className="eyebrow" style={{ marginBottom: 'var(--sp-3)' }}>
                维度速览（规则判定，非 AI 生成）
              </div>
              <DimensionGrid candidate={candidate} labels={labels} />
            </section>

            <hr className="divider" />

            <section>
              <div className="row-between" style={{ marginBottom: 'var(--sp-3)' }}>
                <span className="eyebrow">搜索结果</span>
                {data && (
                  <span className="text-subtle">
                    来源 {data.provider} · {data.results.length} 条
                  </span>
                )}
              </div>

              {data?.disclaimer && (
                <div style={{ marginBottom: 'var(--sp-3)' }}>
                  <Alert tone="info">{data.disclaimer}</Alert>
                </div>
              )}

              {data?.degraded && data.note && (
                <div style={{ marginBottom: 'var(--sp-3)' }}>
                  <Alert tone="warn">{data.note}</Alert>
                </div>
              )}

              {loading && (
                <div className="loading-block">
                  <Spinner large />
                  <span>正在检索外部资料…</span>
                </div>
              )}

              {!loading && error && <Alert tone="danger" title="检索失败">{error}</Alert>}

              {!loading && !error && data && data.results.length === 0 && (
                <Alert tone="warn" title="没有找到相关结果">
                  可以换个关键词再试，或直接点下方「打开仓库」自己看看。
                </Alert>
              )}

              {!loading && data && data.results.length > 0 && (
                <div className="result-list">
                  {data.results.map((r, i) => (
                    <article className="result-item" key={`${r.url}-${i}`}>
                      <h4 className="result-item__title">
                        <a href={r.url} target="_blank" rel="noopener noreferrer">
                          {r.title || r.url}
                        </a>
                      </h4>
                      <div className="result-item__meta">
                        <span>{r.domain}</span>
                      </div>
                      {r.snippet && <p className="result-item__snippet">{r.snippet}</p>}
                    </article>
                  ))}
                </div>
              )}

              <div className="row" style={{ marginTop: 'var(--sp-4)' }}>
                <input
                  className="input grow"
                  value={customQuery}
                  onChange={(e) => setCustomQuery(e.target.value)}
                  placeholder="换个关键词再搜一次…"
                  aria-label="自定义检索词"
                />
                <Button
                  icon={<IconRefresh size={14} />}
                  disabled={!customQuery.trim() || loading}
                  onClick={() => void run(owner, repo, customQuery.trim())}
                >
                  重新检索
                </Button>
              </div>
            </section>
          </div>
        </div>

        <footer className="panel__foot">
          <a
            className="btn"
            href={candidate.html_url}
            target="_blank"
            rel="noopener noreferrer"
            style={{ flex: 1 }}
          >
            <IconExternal size={14} />
            打开仓库
          </a>
          <Button
            variant="primary"
            icon={<IconSpark size={14} />}
            loading={analyzing}
            onClick={() => onAnalyze(candidate)}
            style={{ flex: 1.4 }}
          >
            深入解析（调用 AI）
          </Button>
        </footer>
      </aside>
    </>
  )
}
