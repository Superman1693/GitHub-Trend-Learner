/**
 * 发现页（design.md §16.2）。
 *
 * 三阶段职责清晰：
 *   浏览 / 筛选        —— 零 LLM
 *   查看摘要（阶段一）  —— 只调搜索引擎
 *   深入解析（阶段二）  —— 仅在用户点击后才调 LLM
 */
import { useCallback, useMemo, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import type { Candidate, CandidateFilters } from '../api/types'
import { useCandidates, useCandidateFacets, useAnalyzeCandidate } from '../hooks/useCandidates'
import { useFavoriteToggle } from '../hooks/useFavorites'
import { CandidateFilters as Filters } from '../components/discovery/CandidateFilters'
import { CandidateCard } from '../components/discovery/CandidateCard'
import { PreviewPanel } from '../components/discovery/PreviewPanel'
import { Alert, Button, EmptyState, LoadingBlock, Spinner } from '../components/ui'
import { IconSpark, IconStar, IconStarFilled } from '../components/ui/icons'
import '../styles/pages.css'
import '../components/discovery/discovery.css'

const EMPTY_FILTERS: CandidateFilters = {}

export function DiscoverPage() {
  const navigate = useNavigate()
  const [filters, setFilters] = useState<CandidateFilters>(EMPTY_FILTERS)
  const [preview, setPreview] = useState<Candidate | null>(null)
  // 收藏状态覆盖表：接口返回后只改本地这一条，不整列表重拉（见 useFavorites 的说明）
  const [favOverride, setFavOverride] = useState<Record<string, boolean>>({})

  const { data, loading, error, reload } = useCandidates(filters)
  const { data: facets } = useCandidateFacets()
  const { submitting, error: analyzeError, run: analyze } = useAnalyzeCandidate()

  const onFavSettled = useCallback((name: string, favorited: boolean) => {
    setFavOverride((prev) => ({ ...prev, [name]: favorited }))
  }, [])
  const { toggle: toggleFavorite, pending: favPending, error: favError } =
    useFavoriteToggle(onFavSettled)

  const items = useMemo(() => {
    const raw = data?.items ?? []
    return raw.map((c) =>
      favOverride[c.full_name] === undefined
        ? c
        : { ...c, favorited: favOverride[c.full_name] },
    )
  }, [data, favOverride])

  const onlyFav = filters.favorited === true
  const favCount = useMemo(() => items.filter((c) => c.favorited).length, [items])

  const handleAnalyze = async (c: Candidate) => {
    const task = await analyze(...(c.full_name.split('/') as [string, string]))
    if (task) {
      setPreview(null)
      navigate('/tasks')
    }
  }

  const poolEmpty = !loading && (data?.pool_total ?? 0) === 0

  return (
    <div className="stack">
      <header className="page-head">
        <h2 className="page-head__title">发现热门仓库</h2>
        <p className="page-head__desc">
          系统每天自动抓取多个榜单、去重后按<strong>技术方向、项目类型、可部署性、可玩性、实用工具、上榜态势</strong>等维度打标，
          并把仓库简介译为中文（<strong>规则打标与翻译均不消耗 AI</strong>）。
          你可以先按口味筛选、再看搜索引擎的轻量摘要；
          <strong>只有当你点「深入解析」时，才会调用 AI 生成完整的六模块文档</strong>。
        </p>
        <div className="row" style={{ marginTop: 'var(--sp-3)' }}>
          <Button
            icon={onlyFav ? <IconStarFilled size={14} /> : <IconStar size={14} />}
            onClick={() => setFilters((f) => ({ ...f, favorited: f.favorited ? undefined : true }))}
            title={onlyFav ? '显示全部候选' : '只看已收藏的仓库'}
          >
            {onlyFav ? '只看收藏中' : '只看收藏'}
          </Button>
          {favCount > 0 && <span className="text-subtle">本页已收藏 {favCount} 个</span>}
        </div>
      </header>

      {favError && (
        <Alert tone="danger" title="收藏操作失败">
          {favError}
        </Alert>
      )}

      {analyzeError && (
        <Alert tone="danger" title="无法提交解析任务">
          {analyzeError}
        </Alert>
      )}

      {poolEmpty ? (
        <div className="cand-empty">
          <EmptyState
            title="候选池还是空的"
            description="候选池由每日任务生成。先跑一次每日任务，系统会抓取榜单并按维度打标，之后这里就能筛选与挑选了。"
            action={
              <div className="row" style={{ justifyContent: 'center' }}>
                <Link className="btn btn--primary" to="/tasks">
                  <IconSpark size={14} />
                  去任务中心跑一次
                </Link>
                <Button onClick={reload}>刷新</Button>
              </div>
            }
          />
        </div>
      ) : (
        <>
          <Filters
            filters={filters}
            facets={facets ?? null}
            total={data?.total ?? 0}
            poolTotal={data?.pool_total ?? 0}
            loading={loading}
            onChange={setFilters}
            onReset={() => setFilters(EMPTY_FILTERS)}
          />

          {loading && items.length === 0 ? (
            <LoadingBlock text="正在读取候选池…" />
          ) : error ? (
            <EmptyState title="无法加载候选列表" description={error} action={<Button onClick={reload}>重试</Button>} />
          ) : items.length === 0 ? (
            <div className="cand-empty">
              <EmptyState
                title="没有符合当前条件的仓库"
                description="试试放宽筛选条件，或清空筛选看看全部候选。"
                action={<Button onClick={() => setFilters(EMPTY_FILTERS)}>清空筛选</Button>}
              />
            </div>
          ) : (
            <div className="cand-grid">
              {items.map((c) => (
                <CandidateCard
                  key={c.full_name}
                  candidate={c}
                  labels={data?.labels}
                  onPreview={setPreview}
                  onAnalyze={handleAnalyze}
                  onToggleFavorite={toggleFavorite}
                  analyzing={submitting}
                  favoritePending={favPending === c.full_name}
                />
              ))}
            </div>
          )}
        </>
      )}

      {preview && (
        <PreviewPanel
          candidate={preview}
          labels={data?.labels}
          onClose={() => setPreview(null)}
          onAnalyze={handleAnalyze}
          analyzing={submitting}
        />
      )}

      {submitting && (
        <div
          className="row"
          style={{
            position: 'fixed',
            bottom: 24,
            left: '50%',
            transform: 'translateX(-50%)',
            background: 'var(--c-surface)',
            border: '1px solid var(--c-border)',
            borderRadius: 'var(--r-full)',
            padding: '8px 18px',
            boxShadow: 'var(--shadow-lg)',
            zIndex: 'var(--z-toast)',
          }}
        >
          <Spinner />
          <span style={{ fontSize: 'var(--fs-sm)' }}>正在提交解析任务…</span>
        </div>
      )}
    </div>
  )
}
