/**
 * 应用外壳：负责整体布局与响应式行为。
 *
 * - 桌面（≥768px）：左侧固定侧栏 + 顶栏 + 内容区
 * - 移动端（<768px）：顶栏汉堡按钮 + 抽屉导航 + 底部导航
 */
import { useEffect, useState, type ReactNode } from 'react'
import { NavLink, useLocation } from 'react-router-dom'
import { NAV_ITEMS } from '../../config/navigation'
import { useHealth, useOverview } from '../../hooks/useSystem'
import { useIsMobile } from '../../hooks/useMediaQuery'
import { Sidebar } from './Sidebar'
import { Topbar } from './Topbar'
import './layout.css'

const TITLES: Record<string, string> = {
  '/': '概览',
  '/discover': '发现仓库',
  '/documents': '解读文档',
  '/tasks': '任务中心',
  '/settings': '系统设置',
}

function resolveTitle(pathname: string): string {
  if (TITLES[pathname]) return TITLES[pathname]
  if (pathname.startsWith('/documents/')) return '文档详情'
  return '控制台'
}

export function AppShell({ children }: { children: ReactNode }) {
  const location = useLocation()
  const isMobile = useIsMobile()
  const [drawerOpen, setDrawerOpen] = useState(false)

  const { data: health, error: healthError } = useHealth()
  const { data: overview } = useOverview()

  // 路由变化时自动关闭抽屉
  useEffect(() => {
    setDrawerOpen(false)
  }, [location.pathname])

  // 抽屉打开时锁定滚动
  useEffect(() => {
    if (!drawerOpen) return
    const prev = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => {
      document.body.style.overflow = prev
    }
  }, [drawerOpen])

  const closeDrawer = () => setDrawerOpen(false)

  return (
    <div className="shell">
      {!isMobile && (
        <aside className="sidebar">
          <Sidebar documentCount={overview?.documents.total_documents} />
        </aside>
      )}

      <div className="main">
        <Topbar
          title={resolveTitle(location.pathname)}
          health={health}
          healthError={healthError}
          onMenuClick={() => setDrawerOpen(true)}
        />

        <main className="content">{children}</main>

        <nav className="bottom-nav" aria-label="底部导航">
          <ul className="bottom-nav__list">
            {NAV_ITEMS.filter((i) => i.mobile).map((item) => {
              const Icon = item.icon
              return (
                <li key={item.to}>
                  <NavLink
                    to={item.to}
                    end={item.end}
                    className={({ isActive }) =>
                      `bottom-nav__item${isActive ? ' is-active' : ''}`
                    }
                  >
                    <Icon size={18} />
                    <span>{item.label}</span>
                  </NavLink>
                </li>
              )
            })}
          </ul>
        </nav>
      </div>

      {isMobile && drawerOpen && (
        <>
          <button className="drawer-backdrop" onClick={closeDrawer} aria-label="关闭导航" />
          <div className="drawer" role="dialog" aria-modal="true" aria-label="导航菜单">
            <Sidebar onNavigate={closeDrawer} documentCount={overview?.documents.total_documents} />
          </div>
        </>
      )}
    </div>
  )
}
