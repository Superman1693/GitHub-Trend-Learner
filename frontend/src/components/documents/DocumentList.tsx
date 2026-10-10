/** 文档列表：按日期分组展示，含模块数与体积徽标。 */
import { useMemo } from 'react'
import { Link } from 'react-router-dom'
import type { DocumentMeta } from '../../api/types'
import { Badge, EmptyState, LoadingBlock } from '../ui'
import { IconChevronRight } from '../ui/icons'
import { formatBytes } from '../../utils/format'
import './documents.css'

interface DocumentListProps {
  items: DocumentMeta[]
  loading: boolean
  error: string | null
  emptyHint?: string
}

export function DocumentList({ items, loading, error, emptyHint }: DocumentListProps) {
  const grouped = useMemo(() => {
    const map = new Map<string, DocumentMeta[]>()
    for (const item of items) {
      const bucket = map.get(item.date)
      if (bucket) bucket.push(item)
      else map.set(item.date, [item])
    }
    return [...map.entries()].sort((a, b) => (a[0] < b[0] ? 1 : -1))
  }, [items])

  if (loading) return <LoadingBlock text="正在读取产出文档…" />

  if (error) {
    return (
      <EmptyState
        title="无法加载文档列表"
        description={error}
      />
    )
  }

  if (items.length === 0) {
    return (
      <EmptyState
        title="暂无产出文档"
        description={emptyHint ?? '在「任务中心」提交一次仓库解析或每日任务，产出会归档到 outputs/ 目录并显示在这里。'}
      />
    )
  }

  return (
    <div>
      {grouped.map(([date, docs]) => (
        <section className="date-group" key={date}>
          <div className="date-group__head">
            <h2 className="date-group__title">{date}</h2>
            <span className="text-subtle">{docs.length} 份</span>
          </div>

          <div className="doc-list">
            {docs.map((doc) => (
              <Link
                className="doc-card"
                key={doc.doc_id}
                to={`/documents/${encodeURIComponent(doc.date)}/${encodeURIComponent(doc.name)}`}
              >
                <div className="doc-card__body">
                  <div className="doc-card__title truncate">{doc.title}</div>
                  <div className="doc-card__meta">
                    <Badge tone="accent">{doc.module_count} 个模块</Badge>
                    <Badge>{formatBytes(doc.size)}</Badge>
                    {doc.match_count ? (
                      <Badge tone="success">命中 {doc.match_count} 处</Badge>
                    ) : null}
                    <span className="text-subtle truncate">{doc.name}</span>
                  </div>
                  {doc.snippet && <p className="doc-card__snippet clamp-2">{doc.snippet}</p>}
                </div>
                <IconChevronRight size={16} />
              </Link>
            ))}
          </div>
        </section>
      ))}
    </div>
  )
}
