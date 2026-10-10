/** 文档阅读器：头部信息 + 模块目录 + 正文渲染，含滚动联动高亮。 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import type { DocumentDetail } from '../../api/types'
import { Badge, Button } from '../ui'
import { MarkdownView } from './MarkdownView'
import { ModuleToc, ModuleTocMobile } from './ModuleToc'
import { formatBytes, prettifyName } from '../../utils/format'
import './documents.css'

interface DocumentViewerProps {
  doc: DocumentDetail
}

export function DocumentViewer({ doc }: DocumentViewerProps) {
  const [activeKey, setActiveKey] = useState<string | null>(doc.modules[0]?.key ?? null)
  const [copied, setCopied] = useState(false)
  const containerRef = useRef<HTMLDivElement>(null)

  const sectionIds = useMemo(
    () => new Map(doc.modules.map((m) => [m.key, `module-${m.key}`])),
    [doc.modules],
  )

  // 滚动联动：取当前视口内最靠上的章节为高亮项
  useEffect(() => {
    const root = containerRef.current
    if (!root || doc.modules.length === 0) return

    const elements = doc.modules
      .map((m) => root.querySelector<HTMLElement>(`#${CSS.escape(sectionIds.get(m.key)!)}`))
      .filter((el): el is HTMLElement => el !== null)

    if (elements.length === 0) return

    const observer = new IntersectionObserver(
      (entries) => {
        const visible = entries
          .filter((e) => e.isIntersecting)
          .sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top)
        const first = visible[0]?.target as HTMLElement | undefined
        if (first?.id) setActiveKey(first.id.replace(/^module-/, ''))
      },
      { rootMargin: '-132px 0px -62% 0px', threshold: 0 },
    )

    elements.forEach((el) => observer.observe(el))
    return () => observer.disconnect()
  }, [doc.modules, sectionIds])

  const scrollTo = useCallback(
    (key: string) => {
      const id = sectionIds.get(key)
      if (!id) return
      const el = containerRef.current?.querySelector<HTMLElement>(`#${CSS.escape(id)}`)
      if (!el) return
      const top = el.getBoundingClientRect().top + window.scrollY - 120
      window.scrollTo({ top, behavior: 'smooth' })
      setActiveKey(key)
    },
    [sectionIds],
  )

  const copyAll = useCallback(async () => {
    try {
      await navigator.clipboard.writeText(doc.markdown)
      setCopied(true)
      window.setTimeout(() => setCopied(false), 1600)
    } catch {
      setCopied(false)
    }
  }, [doc.markdown])

  const download = useCallback(() => {
    const blob = new Blob([doc.markdown], { type: 'text/markdown;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = doc.name
    a.click()
    URL.revokeObjectURL(url)
  }, [doc.markdown, doc.name])

  return (
    <div className="reader" ref={containerRef}>
      <div className="reader__main">
        <div className="reader__head">
          <h1 className="reader__title">{doc.title}</h1>

          <div className="reader__meta">
            {doc.meta['仓库地址'] && (
              <span className="reader__meta-item">
                <a href={doc.meta['仓库地址']} target="_blank" rel="noopener noreferrer">
                  {doc.meta['仓库地址']}
                </a>
              </span>
            )}
            {doc.meta['数据获取时间'] && (
              <span className="reader__meta-item">获取于 {doc.meta['数据获取时间']}</span>
            )}
            {doc.meta['数据来源'] && (
              <span className="reader__meta-item">来源：{doc.meta['数据来源']}</span>
            )}
          </div>

          <div className="row" style={{ flexWrap: 'wrap' }}>
            <Badge tone="accent">{doc.modules.length} 个模块</Badge>
            <Badge>{formatBytes(doc.size)}</Badge>
            <Badge>{prettifyName(doc.name)}</Badge>
            <span className="grow" />
            <Button onClick={copyAll}>{copied ? '已复制' : '复制全文'}</Button>
            <Button onClick={download}>下载 .md</Button>
          </div>
        </div>

        {/* 移动端折叠目录：位于正文列内部 */}
        <ModuleTocMobile modules={doc.modules} activeKey={activeKey} onSelect={scrollTo} />

        <article className="reader__paper">
          {doc.modules.map((m) => (
            <section key={m.key} id={sectionIds.get(m.key)}>
              <MarkdownView markdown={`## ${m.raw_title}\n\n${m.content}`} anchorPrefix={m.key} />
            </section>
          ))}
        </article>
      </div>

      {/* 桌面常驻目录：必须是 .reader 网格的第二列（.reader__main 的兄弟节点）。
          放进 .reader__main 会让 sticky 在单列里吸顶并遮挡正文。 */}
      <ModuleToc modules={doc.modules} activeKey={activeKey} onSelect={scrollTo} />
    </div>
  )
}
