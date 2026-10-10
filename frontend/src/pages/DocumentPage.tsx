/** 文档详情页：加载单份文档并交给阅读器渲染。 */
import { Link, useParams } from 'react-router-dom'
import { useDocument } from '../hooks/useDocuments'
import { DocumentViewer } from '../components/documents/DocumentViewer'
import { Button, EmptyState, LoadingBlock } from '../components/ui'
import { IconArrowLeft } from '../components/ui/icons'
import '../styles/pages.css'

export function DocumentPage() {
  const { date, name } = useParams<{ date: string; name: string }>()
  const { data: doc, loading, error, reload } = useDocument(date, name)

  /** 常驻返回栏：sticky 吸附在顶栏下方，滚动到任意位置都能一键返回列表。 */
  const backbar = (title?: string) => (
    <div className="reader-backbar">
      <Link className="btn btn--sm reader-backbar__btn" to="/documents">
        <IconArrowLeft size={14} />
        返回列表
      </Link>
      {title ? <span className="reader-backbar__title truncate">{title}</span> : null}
    </div>
  )

  if (loading) {
    return (
      <>
        {backbar()}
        <LoadingBlock text="正在加载文档…" />
      </>
    )
  }

  if (error || !doc) {
    return (
      <>
        {backbar()}
        <EmptyState
          title="文档无法打开"
          description={error ?? '文档不存在或已被移除'}
          action={
            <div className="row">
              <Button onClick={reload}>重试</Button>
              <Link className="btn" to="/documents">
                返回列表
              </Link>
            </div>
          }
        />
      </>
    )
  }

  return (
    <>
      {backbar(doc.title)}
      <DocumentViewer doc={doc} />
    </>
  )
}
