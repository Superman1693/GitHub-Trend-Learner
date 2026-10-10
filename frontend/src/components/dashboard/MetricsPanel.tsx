/**
 * 运行指标面板（v1.8.3）。
 *
 * 数据来自 `GET /api/system/metrics`，由后端从 logs/*.jsonl 聚合。
 *
 * 展示上的两个刻意选择：
 * 1. `success_rate === null` 显示「未知」而非 0% —— 该 Agent 不记录 done 事件，
 *    成功率本就无从计算（见 app/metrics.py 的说明）；
 * 2. 缓存命中率在无查询时显示「—」而非 0%，避免误导成「缓存完全没生效」。
 */
import { Card, Badge } from '../ui'
import { useMetrics } from '../../hooks/useSystem'
import { formatCount } from '../../utils/format'

function pct(rate: number | null | undefined): string {
  return rate === null || rate === undefined ? '未知' : `${Math.round(rate * 100)}%`
}

function ms(value: number): string {
  if (value >= 1000) return `${(value / 1000).toFixed(1)}s`
  return `${value}ms`
}

export function MetricsPanel({ days = 7 }: { days?: number }) {
  const { data, loading, error } = useMetrics(days)

  if (loading) {
    return (
      <Card title="运行指标">
        <p className="text-subtle" style={{ fontSize: 'var(--fs-sm)' }}>正在聚合日志…</p>
      </Card>
    )
  }
  if (error) {
    return (
      <Card title="运行指标">
        <p className="text-subtle" style={{ fontSize: 'var(--fs-sm)' }}>
          无法读取运行指标：{error}
        </p>
      </Card>
    )
  }
  if (!data) return null

  const { tasks, cache, tokens, agents, gate, recent_errors: errors } = data
  const hasData = data.range.events > 0

  return (
    <Card
      title="运行指标"
      description={`最近 ${data.range.days} 天 · ${data.range.files} 个日志文件 · ${formatCount(data.range.events)} 条事件`}
    >
      {!hasData ? (
        <p className="text-subtle" style={{ fontSize: 'var(--fs-sm)' }}>
          这段时间没有运行记录。跑一次任务中心的任务后即可看到指标。
        </p>
      ) : (
        <>
          <div className="grid grid--stats" style={{ marginBottom: 'var(--sp-4)' }}>
            <div className="stat">
              <div className="stat__label">任务成功率</div>
              <div className="stat__value">
                {pct(tasks.success_rate)}
              </div>
              <div className="stat__hint">
                启动 {tasks.started} · 失败 {tasks.failed}
                {tasks.retry ? ` · 重试 ${tasks.retry}` : ''}
              </div>
            </div>

            <div className="stat">
              <div className="stat__label">缓存命中率</div>
              <div className="stat__value">
                {cache.hit_rate === null ? '—' : pct(cache.hit_rate)}
              </div>
              <div className="stat__hint">
                命中 {cache.hit} · 新生成 {cache.stored}
              </div>
            </div>

            <div className="stat">
              <div className="stat__label">Token 消耗</div>
              <div className="stat__value">
                {formatCount(tokens.total)}
              </div>
              <div className="stat__hint">平均每任务 {formatCount(tokens.avg_per_task)}</div>
            </div>

            <div className="stat">
              <div className="stat__label">质量门禁</div>
              <div className="stat__value">
                {gate.pass ?? 0}
                <span className="stat__unit">pass</span>
              </div>
              <div className="stat__hint">
                {gate.degraded ? `降级 ${gate.degraded} 篇` : '无降级交付'}
              </div>
            </div>
          </div>

          <div className="metrics-table">
            <div className="metrics-table__head">
              <span>Agent</span>
              <span>调用</span>
              <span>成功率</span>
              <span>平均耗时</span>
              <span>P95</span>
            </div>
            {Object.entries(agents).map(([name, a]) => (
              <div className="metrics-table__row" key={name}>
                <span className="metrics-table__name">{name}</span>
                <span>{a.calls}</span>
                <span className={a.success_rate === null ? 'text-subtle' : ''}>
                  {a.success_rate === null && a.failed > 0
                    ? `失败 ${a.failed}`
                    : pct(a.success_rate)}
                </span>
                <span>{a.duration_samples ? ms(a.avg_ms) : '—'}</span>
                <span>{a.duration_samples ? ms(a.p95_ms) : '—'}</span>
              </div>
            ))}
          </div>

          {errors.length > 0 && (
            <details className="metrics-errors">
              <summary>最近 {errors.length} 条错误</summary>
              <ul>
                {errors.map((e, i) => (
                  <li key={`${e.ts}-${i}`}>
                    <Badge tone="danger">{e.agent}</Badge>
                    <span className="metrics-errors__msg">{e.error}</span>
                  </li>
                ))}
              </ul>
            </details>
          )}
        </>
      )}
    </Card>
  )
}
