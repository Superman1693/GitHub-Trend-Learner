/** 候选仓库卡片：展示多维度标签、中文描述与两个阶段入口。 */
import { useState } from 'react'
import type { Candidate, DimensionLabels } from '../../api/types'
import { Badge, Button, Sparkline, TrendDelta } from '../ui'
import {
  IconExternal,
  IconFlame,
  IconSearch,
  IconSpark,
  IconStar,
  IconStarFilled,
} from '../ui/icons'
import { formatCount } from '../../utils/format'
import './discovery.css'

interface CandidateCardProps {
  candidate: Candidate
  labels?: DimensionLabels
  onPreview: (c: Candidate) => void
  onAnalyze: (c: Candidate) => void
  onToggleFavorite: (c: Candidate) => void
  analyzing?: boolean
  favoritePending?: boolean
}

function tagClass(key: string, value: string): string {
  if (key === 'deployable' && value === 'yes') return 'tag-deploy-yes'
  if (key === 'playfulness' && value === 'high') return 'tag-play-high'
  if (key === 'practical_tool' && value === 'yes') return 'tag-tool-yes'
  return ''
}

export function CandidateCard({
  candidate,
  labels,
  onPreview,
  onAnalyze,
  onToggleFavorite,
  analyzing = false,
  favoritePending = false,
}: CandidateCardProps) {
  const d = candidate.dimensions
  const [owner, repo] = candidate.full_name.split('/')
  const [showOriginal, setShowOriginal] = useState(false)

  const zh = (candidate.description_zh || '').trim()
  const en = (candidate.description || '').trim()
  const hasZh = zh.length > 0 && zh !== en
  const desc = showOriginal || !hasZh ? en : zh
  const projectLabel = labels?.project_type?.[d.project_type] ?? d.project_type
  const fav = Boolean(candidate.favorited)

  return (
    <article className={`cand-card${fav ? ' cand-card--favorited' : ''}`}>
      <header className="cand-card__head">
        <h3 className="cand-card__name">
          <span className="owner">{owner}/</span>
          {repo}
        </h3>
        <div className="cand-card__head-right">
          {candidate.trend === 'new' && (
            <span className="cand-card__trend">
              <IconFlame size={12} />
              新上榜
            </span>
          )}
          <button
            type="button"
            className={`cand-card__fav${fav ? ' is-on' : ''}`}
            onClick={() => onToggleFavorite(candidate)}
            disabled={favoritePending}
            aria-pressed={fav}
            aria-label={fav ? `取消收藏 ${candidate.full_name}` : `收藏 ${candidate.full_name}`}
            title={fav ? '取消收藏' : '收藏，稍后再看'}
          >
            {favoritePending ? (
              <span className="spinner" aria-hidden="true" />
            ) : fav ? (
              <IconStarFilled size={15} />
            ) : (
              <IconStar size={15} />
            )}
          </button>
        </div>
      </header>

      <div className="cand-card__metrics">
        {candidate.language && <span className="cand-card__metric">{candidate.language}</span>}
        <span className="cand-card__metric">★ {formatCount(candidate.stars)}</span>
        {candidate.stars_today ? (
          <span className="cand-card__metric cand-card__metric--up">
            今日 +{formatCount(candidate.stars_today)}
          </span>
        ) : null}
        {candidate.days_count && candidate.days_count > 1 ? (
          <Badge tone="accent">上榜 {candidate.days_count} 天</Badge>
        ) : null}
        {candidate.last_seen ? (
          <span className="cand-card__metric cand-card__metric--subtle" title="最近一次出现在热门榜单的日期">
            最近上榜 {candidate.last_seen}
          </span>
        ) : null}
      </div>

      {/* star 趋势曲线（v1.8.3）：≥2 天数据才画，单点无趋势可言 */}
      {(candidate.star_history?.length ?? 0) >= 2 && (
        <div className="cand-card__spark">
          <Sparkline
            values={candidate.star_history as number[]}
            days={candidate.history_days}
            label={`${candidate.full_name} 的 star`}
          />
          <TrendDelta
            delta={candidate.star_delta ?? 0}
            days={(candidate.star_history as number[]).length}
          />
          <span className="cand-card__metric--subtle">
            {candidate.history_days?.[0]} → {candidate.history_days?.[candidate.history_days.length - 1]}
          </span>
        </div>
      )}

      <div className="cand-card__desc-wrap">
        <p className="cand-card__desc clamp-2">
          {desc || '（该仓库未填写描述）'}
        </p>
        {hasZh && (
          <button
            type="button"
            className="cand-card__lang-toggle"
            onClick={() => setShowOriginal((v) => !v)}
            title="在中文翻译与英文原文之间切换"
          >
            {showOriginal ? '中文' : '原文'}
          </button>
        )}
      </div>

      <div className="cand-card__tags">
        <span className="badge tag-project">{projectLabel}</span>
        <span className={`badge ${tagClass('deployable', d.deployable)}`}>
          {labels?.deployable?.[d.deployable] ?? d.deployable}
        </span>
        <span className={`badge ${tagClass('playfulness', d.playfulness)}`}>
          可玩性 {labels?.playfulness?.[d.playfulness] ?? d.playfulness}
        </span>
        <span className={`badge ${tagClass('practical_tool', d.practical_tool)}`}>
          {d.practical_tool === 'yes' ? '实用小工具' : '非工具类'}
        </span>
        {(d.directions ?? []).slice(0, 2).map((dir) => (
          <Badge key={dir}>{dir}</Badge>
        ))}
      </div>

      <div className="cand-card__fact">
        <span className="cand-card__fact-key">可学习</span>
        <span className="clamp-2">{d.learnable}</span>
      </div>

      <div className="cand-card__actions">
        <Button icon={<IconSearch size={14} />} onClick={() => onPreview(candidate)}>
          查看摘要
        </Button>
        <Button
          variant="primary"
          icon={<IconSpark size={14} />}
          loading={analyzing}
          onClick={() => onAnalyze(candidate)}
          title="将调用 AI 解析（耗时较长）"
        >
          深入解析
        </Button>
        <a
          className="btn btn--ghost"
          href={candidate.html_url}
          target="_blank"
          rel="noopener noreferrer"
          aria-label="打开仓库"
          style={{ flex: 'none' }}
        >
          <IconExternal size={14} />
        </a>
      </div>
    </article>
  )
}
