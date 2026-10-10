/**
 * 模块目录（本文目录）。
 *
 * 拆成两个组件，由调用方放进正确的布局位置：
 *   ModuleToc        —— 桌面右侧常驻目录，必须是 `.reader` 网格的第二列（直接子元素）
 *   ModuleTocMobile  —— 移动端折叠面板，放在正文列内部
 *
 * 历史缺陷：两者曾被包在同一个组件里、整体塞进 `.reader__main`，
 * 导致桌面的 `position: sticky` 在单列容器里吸顶，目录浮在正文之上遮挡内容。
 * 布局位置与吸顶行为强相关，故此处显式分离。
 */
import { useState } from 'react'
import type { DocumentModule } from '../../api/types'
import { cnIndex } from '../../utils/format'
import { IconChevronRight } from '../ui/icons'
import './documents.css'

interface ModuleTocProps {
  modules: DocumentModule[]
  activeKey: string | null
  onSelect: (key: string) => void
}

function TocList({ modules, activeKey, onSelect }: ModuleTocProps) {
  return (
    <ul className="toc__list">
      {modules.map((m, i) => (
        <li key={m.key}>
          <button
            type="button"
            className={`toc__link${activeKey === m.key ? ' is-active' : ''}`}
            onClick={() => onSelect(m.key)}
          >
            <span className="toc__index">{cnIndex(i)}</span>
            <span className="toc__label truncate">{m.title}</span>
          </button>
        </li>
      ))}
    </ul>
  )
}

/** 桌面右侧常驻目录（≥1024px 显示）。 */
export function ModuleToc(props: ModuleTocProps) {
  if (props.modules.length === 0) return null
  return (
    <aside className="reader__toc" aria-label="本文目录">
      <div className="toc">
        <div className="toc__title">本文目录</div>
        <TocList {...props} />
      </div>
    </aside>
  )
}

/** 移动端折叠目录（<1024px 显示），放在正文列内部。 */
export function ModuleTocMobile(props: ModuleTocProps) {
  const [open, setOpen] = useState(false)

  if (props.modules.length === 0) return null

  return (
    <div className="toc-mobile">
      <button
        type="button"
        className="toc-mobile__toggle"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
      >
        <span>本文目录（{props.modules.length} 节）</span>
        <span
          className="toc-mobile__chevron"
          style={{ transform: open ? 'rotate(90deg)' : 'none' }}
        >
          <IconChevronRight size={16} />
        </span>
      </button>
      {open && (
        <div className="toc-mobile__panel">
          <TocList
            {...props}
            onSelect={(key) => {
              props.onSelect(key)
              setOpen(false)
            }}
          />
        </div>
      )}
    </div>
  )
}
