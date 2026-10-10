/** 路由与页面装配。 */
import { BrowserRouter, Route, Routes } from 'react-router-dom'
import { AppShell } from './components/layout/AppShell'
import { EmptyState } from './components/ui'
import { Link } from 'react-router-dom'
import { DashboardPage } from './pages/DashboardPage'
import { DiscoverPage } from './pages/DiscoverPage'
import { DocumentsPage } from './pages/DocumentsPage'
import { DocumentPage } from './pages/DocumentPage'
import { TasksPage } from './pages/TasksPage'
import { SettingsPage } from './pages/SettingsPage'

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
        <Routes>
          <Route path="/" element={<DashboardPage />} />
          <Route path="/discover" element={<DiscoverPage />} />
          <Route path="/documents" element={<DocumentsPage />} />
          <Route path="/documents/:date/:name" element={<DocumentPage />} />
          <Route path="/tasks" element={<TasksPage />} />
          <Route path="/settings" element={<SettingsPage />} />
          <Route path="*" element={<NotFoundPage />} />
        </Routes>
      </AppShell>
    </BrowserRouter>
  )
}
