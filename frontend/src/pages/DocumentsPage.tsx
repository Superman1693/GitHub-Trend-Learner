/** 文档列表页：全文检索（后端）+ 日期筛选 + 分组列表。 */
import { useState } from 'react'
import { useDocuments } from '../hooks/useDocuments'
import { useDebounced } from '../hooks/useDebounced'
import { useOverview } from '../hooks/useSystem'
import { DocumentList } from '../components/documents/DocumentList'
import { Button } from '../components/ui'
import { IconRefresh, IconSearch } from '../components/ui/icons'
import '../styles/pages.css'

export function DocumentsPage() {
  const [keyword, setKeyword] = useState('')
  const [date, setDate] = useState('')

  // 防抖后再请求：全文检索会扫描正文，避免逐字触发（v1.8）
  const debouncedKeyword = useDebounced(keyword.trim(), 300)

  const { data: items, loading, error, reload } = useDocuments({
    date: date || undefined,
    q: debouncedKeyword || undefined,
  })
  const { data: overview } = useOverview()

  return (
    <div className="stack">
      <header className="page-head">
        <h2 className="page-head__title">解读文档</h2>
        <p className="page-head__desc">
          每份文档按六模块结构组织。搜索会同时检索<strong>正文内容</strong>与标题，
          命中处会给出上下文片段。点击进入阅读器，可查看目录、复制全文或下载 Markdown。
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
            placeholder="全文搜索：仓库名、标题或正文关键词…"
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
        items={items ?? []}
        loading={loading}
        error={error}
        emptyHint={
          keyword || date
            ? '当前筛选条件下没有匹配的文档，试试换关键词或清空搜索。'
            : undefined
        }
      />
    </div>
  )
}
