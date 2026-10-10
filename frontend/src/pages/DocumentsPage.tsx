/** 文档列表页：搜索 + 日期筛选 + 分组列表。 */
import { useMemo, useState } from 'react'
import { useDocuments } from '../hooks/useDocuments'
import { useOverview } from '../hooks/useSystem'
import { DocumentList } from '../components/documents/DocumentList'
import { Button } from '../components/ui'
import { IconRefresh, IconSearch } from '../components/ui/icons'
import '../styles/pages.css'

export function DocumentsPage() {
  const [keyword, setKeyword] = useState('')
  const [date, setDate] = useState('')

  const { data: items, loading, error, reload } = useDocuments({ date: date || undefined })
  const { data: overview } = useOverview()

  const filtered = useMemo(() => {
    if (!items) return []
    const kw = keyword.trim().toLowerCase()
    if (!kw) return items
    return items.filter(
      (d) => d.name.toLowerCase().includes(kw) || d.title.toLowerCase().includes(kw),
    )
  }, [items, keyword])

  return (
    <div className="stack">
      <header className="page-head">
        <h2 className="page-head__title">解读文档</h2>
        <p className="page-head__desc">
          每份文档按六模块结构组织。点击进入阅读器，可查看目录、复制全文或下载 Markdown。
        </p>
      </header>

      <div className="toolbar">
        <div className="toolbar__search">
          <span className="toolbar__search-icon">
            <IconSearch size={15} />
          </span>
          <input
            className="input"
            value={keyword}
            onChange={(e) => setKeyword(e.target.value)}
            placeholder="搜索仓库名或标题…"
            aria-label="搜索文档"
          />
        </div>

        <select
          className="select"
          style={{ width: 168 }}
          value={date}
          onChange={(e) => setDate(e.target.value)}
          aria-label="按日期筛选"
        >
          <option value="">全部日期</option>
          {(overview?.documents.dates ?? []).map((d) => (
            <option key={d.date} value={d.date}>
              {d.date}（{d.count}）
            </option>
          ))}
        </select>

        <Button icon={<IconRefresh size={15} />} onClick={reload}>
          刷新
        </Button>
      </div>

      <DocumentList
        items={filtered}
        loading={loading}
        error={error}
        emptyHint={
          keyword || date
            ? '当前筛选条件下没有匹配的文档，试试清空搜索或切换日期。'
            : undefined
        }
      />
    </div>
  )
}
