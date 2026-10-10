/** 路由与页面装配。
 *
 * v1.8.2：页面改为**路由级懒加载**（CODE_REVIEW.md B8）。
 * 此前所有页面打进单个 281 KB chunk，首屏必须下载全部代码；
 * 现在按路由分包，首屏只需「概览 + 外壳」，其余页面访问到时才加载。
 */
import { Suspense, lazy } from 'react'
import { BrowserRouter, Link, Route, Routes } from 'react-router-dom'
import { AppShell } from './components/layout/AppShell'
import { EmptyState, LoadingBlock } from './components/ui'
import { DashboardPage } from './pages/DashboardPage'

// 概览页保持同步加载：它是首屏，懒加载反而多一次往返
const DiscoverPage = lazy(() =>
  import('./pages/DiscoverPage').then((m) => ({ default: m.DiscoverPage })),
)
const DocumentsPage = lazy(() =>
  import('./pages/DocumentsPage').then((m) => ({ default: m.DocumentsPage })),
)
const DocumentPage = lazy(() =>
  import('./pages/DocumentPage').then((m) => ({ default: m.DocumentPage })),
)
const TasksPage = lazy(() =>
  import('./pages/TasksPage').then((m) => ({ default: m.TasksPage })),
)
const SettingsPage = lazy(() =>
  import('./pages/SettingsPage').then((m) => ({ default: m.SettingsPage })),
)

function NotFoundPage() {
  return (
    <EmptyState
      title="页面不存在"
      description="你访问的地址没有对应的页面。可能是链接已失效，或路径拼写有误。"
      action={
        <Link className="btn" to="/">
          返回概览
        </Link>
      }
    />
  )
}

export default function App() {
  return (
    <BrowserRouter>
      <AppShell>
        <Suspense fallback={<LoadingBlock text="正在加载页面…" />}>
          <Routes>
            <Route path="/" element={<DashboardPage />} />
            <Route path="/discover" element={<DiscoverPage />} />
            <Route path="/documents" element={<DocumentsPage />} />
            <Route path="/documents/:date/:name" element={<DocumentPage />} />
            <Route path="/tasks" element={<TasksPage />} />
            <Route path="/settings" element={<SettingsPage />} />
            <Route path="*" element={<NotFoundPage />} />
          </Routes>
        </Suspense>
      </AppShell>
    </BrowserRouter>
  )
}
