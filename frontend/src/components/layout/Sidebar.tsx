/** 侧栏导航：桌面常驻；移动端作为抽屉内容复用。 */
import { NavLink } from 'react-router-dom'
import { APP_NAME, APP_SUBTITLE, NAV_ITEMS } from '../../config/navigation'

interface SidebarProps {
  /** 抽屉模式下点击导航后回调（用于关闭抽屉） */
  onNavigate?: () => void
  /** 文档总数，展示在导航项右侧 */
  documentCount?: number
}

export function Sidebar({ onNavigate, documentCount }: SidebarProps) {
  return (
    <>
      <div className="sidebar__brand">
        <span className="sidebar__mark" aria-hidden="true">
          GT
        </span>
        <div>
          <div className="sidebar__name">{APP_NAME}</div>
          <div className="sidebar__tag">{APP_SUBTITLE}</div>
        </div>
      </div>

      <nav className="sidebar__nav" aria-label="主导航">
        <span className="sidebar__group">工作台</span>
        {NAV_ITEMS.map((item) => {
          const Icon = item.icon
          return (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.end}
              onClick={onNavigate}
              className={({ isActive }) => `nav-item${isActive ? ' is-active' : ''}`}
            >
              <Icon size={16} />
              <span>{item.label}</span>
              {item.to === '/documents' && documentCount !== undefined && (
                <span className="nav-item__count">{documentCount}</span>
              )}
            </NavLink>
          )
        })}
      </nav>

      <div className="sidebar__foot">
        产出目录 <code>outputs/</code>
        <br />
        六模块解读 · 邮件投递
      </div>
    </>
  )
}
