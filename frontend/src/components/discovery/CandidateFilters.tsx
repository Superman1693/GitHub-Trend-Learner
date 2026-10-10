/** 候选筛选器：多条件组合，即时生效（Req11.2）。筛选过程不调用 LLM。 */
import type { CandidateFacets, CandidateFilters } from '../../api/types'
import { Button } from '../ui'
import { IconFilter, IconSearch } from '../ui/icons'
import './discovery.css'

interface CandidateFiltersProps {
  filters: CandidateFilters
  facets: CandidateFacets | null
  total: number
  poolTotal: number
  loading: boolean
  onChange: (next: CandidateFilters) => void
  onReset: () => void
}

interface Option {
  value: string
  label: string
  count?: number
}

function ChipGroup({
  label,
  options,
  active,
  onPick,
}: {
  label: string
  options: Option[]
  active?: string
  onPick: (value: string) => void
}) {
  if (options.length === 0) return null
  return (
    <div className="filters__row">
      <span className="filters__label">{label}</span>
      <div className="filters__group">
        {options.map((opt) => (
          <button
            key={opt.value || '__all__'}
            type="button"
            className={`chip${(active ?? '') === opt.value ? ' is-active' : ''}`}
            onClick={() => onPick(opt.value)}
          >
            {opt.label}
            {opt.count !== undefined && <span className="chip__count">{opt.count}</span>}
          </button>
        ))}
      </div>
    </div>
  )
}

export function CandidateFilters({
  filters,
  facets,
  total,
  poolTotal,
  loading,
  onChange,
  onReset,
}: CandidateFiltersProps) {
  const patch = (part: CandidateFilters) => onChange({ ...filters, ...part })

  const languages: Option[] = Object.entries(facets?.languages ?? {})
    .slice(0, 10)
    .map(([name, count]) => ({ value: name, label: name, count }))

  const toOptions = (
    dist: Record<string, number> | undefined,
    labelMap: Record<string, string> | undefined,
  ): Option[] =>
    Object.entries(dist ?? {}).map(([v, c]) => ({
      value: v,
      label: labelMap?.[v] ?? v,
      count: c,
    }))

  const projectTypes = toOptions(facets?.project_type, facets?.labels.project_type)

  // 技术方向按命中数排序，取前 12 个，避免筛选栏过长
  const directions: Option[] = Object.entries(facets?.directions ?? {})
    .slice(0, 12)
    .map(([name, count]) => ({ value: name, label: name, count }))

  const trends = toOptions(facets?.trend, facets?.labels.trend)

  const deployable = toOptions(facets?.deployable, facets?.labels.deployable)
  const playfulness = toOptions(facets?.playfulness, facets?.labels.playfulness)

  const practical: Option[] = Object.entries(facets?.practical_tool ?? {}).map(([v, c]) => ({
    value: v,
    label: v === 'yes' ? '实用小工具' : v === 'no' ? '非工具类' : '未知',
    count: c,
  }))

  const hasFilter = Object.values(filters).some((v) => v !== undefined && v !== '')

  return (
    <section className="filters" aria-label="候选筛选">
      <div className="filters__row filters__row--head">
        <div className="filters__search">
          <span className="filters__search-icon">
            <IconSearch size={15} />
          </span>
          <input
            className="input"
            value={filters.q ?? ''}
            onChange={(e) => patch({ q: e.target.value })}
            placeholder="搜索仓库名、描述或话题…"
            aria-label="搜索候选仓库"
          />
        </div>

        <select
          className="select filters__select"
          value={filters.min_stars ?? ''}
          onChange={(e) =>
            patch({ min_stars: e.target.value ? Number(e.target.value) : undefined })
          }
          aria-label="最低 Star"
        >
          <option value="">Star 不限</option>
          <option value="1000">≥ 1k</option>
          <option value="10000">≥ 10k</option>
          <option value="50000">≥ 50k</option>
        </select>

        <select
          className="select filters__select"
          value={filters.min_days ?? ''}
          onChange={(e) =>
            patch({ min_days: e.target.value ? Number(e.target.value) : undefined })
          }
          aria-label="最少上榜天数"
        >
          <option value="">上榜天数不限</option>
          <option value="2">连续在榜 ≥ 2 天</option>
          <option value="3">连续在榜 ≥ 3 天</option>
        </select>

        {hasFilter && (
          <Button icon={<IconFilter size={14} />} onClick={onReset}>
            清空筛选
          </Button>
        )}

        <span className="filters__count">
          {loading ? '筛选中…' : `命中 ${total} / 池内 ${poolTotal}`}
        </span>
      </div>

      <ChipGroup
        label="技术方向"
        options={directions}
        active={filters.direction}
        onPick={(v) => patch({ direction: v || undefined })}
      />
      <ChipGroup
        label="项目类型"
        options={projectTypes}
        active={filters.project_type}
        onPick={(v) => patch({ project_type: v || undefined })}
      />
      <ChipGroup
        label="上榜态势"
        options={trends}
        active={filters.trend}
        onPick={(v) => patch({ trend: v || undefined })}
      />
      <ChipGroup
        label="语言"
        options={languages}
        active={filters.language}
        onPick={(v) => patch({ language: v || undefined })}
      />
      <ChipGroup
        label="可部署"
        options={deployable}
        active={filters.deployable}
        onPick={(v) => patch({ deployable: v || undefined })}
      />
      <ChipGroup
        label="可玩性"
        options={playfulness}
        active={filters.playfulness}
        onPick={(v) => patch({ playfulness: v || undefined })}
      />
      <ChipGroup
        label="工具类"
        options={practical}
        active={filters.practical_tool}
        onPick={(v) => patch({ practical_tool: v || undefined })}
      />
    </section>
  )
}
