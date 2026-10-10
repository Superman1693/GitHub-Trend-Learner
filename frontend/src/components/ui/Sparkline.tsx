/**
 * 迷你趋势曲线（sparkline）—— 纯 SVG，无第三方依赖。
 *
 * 用于发现页展示候选仓库的 star 变化趋势（v1.8.3）。
 * 只有 1 个数据点时不画线（单点无法体现趋势），改为显示「数据不足」，
 * 避免新手误以为「曲线是平的 = 没涨」。
 */
import './ui.css'

interface SparklineProps {
  /** 由旧到新的数值序列 */
  values: number[]
  /** 与 values 逐位对应的日期，用于 tooltip */
  days?: string[]
  width?: number
  height?: number
  /** 指标名，用于无障碍描述与 tooltip 前缀 */
  label?: string
}

type Tone = 'up' | 'down' | 'flat'

function toneOf(values: number[]): Tone {
  const delta = values[values.length - 1] - values[0]
  if (delta > 0) return 'up'
  if (delta < 0) return 'down'
  return 'flat'
}

function formatNum(n: number): string {
  if (Math.abs(n) >= 10000) return `${(n / 1000).toFixed(1)}k`
  return n.toLocaleString('zh-CN')
}

export function Sparkline({
  values,
  days,
  width = 104,
  height = 30,
  label = '趋势',
}: SparklineProps) {
  const points = (values ?? []).filter((v) => Number.isFinite(v))

  if (points.length < 2) {
    return (
      <span className="sparkline sparkline--empty" title={`${label}：至少需要 2 天上榜数据才能画趋势`}>
        数据不足
      </span>
    )
  }

  const pad = 3
  const min = Math.min(...points)
  const max = Math.max(...points)
  const span = max - min || 1 // 全相等时给个非零跨度，避免除零
  const stepX = (width - pad * 2) / (points.length - 1)
  const yOf = (v: number) => height - pad - ((v - min) / span) * (height - pad * 2)
  const xOf = (i: number) => pad + i * stepX

  const coords = points.map((v, i) => [xOf(i), yOf(v)] as const)
  const line = coords.map(([x, y], i) => `${i === 0 ? 'M' : 'L'}${x.toFixed(1)},${y.toFixed(1)}`).join(' ')
  const area = `${line} L${coords[coords.length - 1][0].toFixed(1)},${height} L${coords[0][0].toFixed(1)},${height} Z`

  const tone = toneOf(points)
  const delta = points[points.length - 1] - points[0]
  const first = days?.[0] ?? '最早'
  const last = days?.[days.length - 1] ?? '最新'
  const tip = `${label}：${first} ${formatNum(points[0])} → ${last} ${formatNum(points[points.length - 1])}（${delta >= 0 ? '+' : ''}${formatNum(delta)}）`

  return (
    <svg
      className={`sparkline sparkline--${tone}`}
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      role="img"
      aria-label={tip}
    >
      <title>{tip}</title>
      <path className="sparkline__area" d={area} />
      <path className="sparkline__line" d={line} fill="none" />
      <circle className="sparkline__dot" cx={coords[coords.length - 1][0]} cy={coords[coords.length - 1][1]} r={2.2} />
    </svg>
  )
}

/** 趋势徽标：把 Δ 值渲染成带箭头的文字，与曲线配套使用。 */
export function TrendDelta({ delta, days }: { delta: number; days?: number }) {
  if (!days || days < 2) return null
  const sign = delta > 0 ? '+' : ''
  const tone: Tone = delta > 0 ? 'up' : delta < 0 ? 'down' : 'flat'
  return (
    <span className={`trend-delta trend-delta--${tone}`} title="本次上榜期间 star 变化">
      {tone === 'up' ? '↑' : tone === 'down' ? '↓' : '→'} {sign}
      {formatNum(delta)}
    </span>
  )
}
