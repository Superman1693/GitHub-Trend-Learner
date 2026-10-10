/**
 * Markdown 渲染组件：marked 解析 + DOMPurify 消毒。
 *
 * 安全说明：内容来自本地流水线产出，但仍经 LLM 生成，
 * 因此统一做 XSS 消毒后再注入，避免产出中的恶意 HTML 影响控制台。
 */
import { useEffect, useMemo, useRef } from 'react'
import { marked } from 'marked'
import DOMPurify from 'dompurify'

marked.setOptions({ gfm: true, breaks: false })

interface MarkdownViewProps {
  markdown: string
  className?: string
  /** 是否为标题注入锚点 id（目录跳转用） */
  anchorPrefix?: string
}

export function MarkdownView({ markdown, className = '', anchorPrefix }: MarkdownViewProps) {
  const ref = useRef<HTMLDivElement>(null)

  const html = useMemo(() => {
    const raw = marked.parse(markdown, { async: false }) as string
    return DOMPurify.sanitize(raw, {
      ADD_ATTR: ['target', 'rel', 'id'],
      FORBID_TAGS: ['style', 'form', 'input', 'iframe', 'script'],
    })
  }, [markdown])

  // 标题注入锚点 + 外链新窗口打开
  useEffect(() => {
    const root = ref.current
    if (!root) return

    root.querySelectorAll('h2, h3').forEach((node, i) => {
      if (!node.id) node.id = `${anchorPrefix ?? 'sec'}-h${i}`
    })

    root.querySelectorAll('a[href^="http"]').forEach((a) => {
      a.setAttribute('target', '_blank')
      a.setAttribute('rel', 'noopener noreferrer')
    })
  }, [html, anchorPrefix])

  return (
    <div
      ref={ref}
      className={`md-body ${className}`.trim()}
      dangerouslySetInnerHTML={{ __html: html }}
    />
  )
}
