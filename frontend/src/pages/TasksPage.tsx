/** 任务中心：提交解析任务、查看运行状态与实时日志。 */
import { TaskLauncher } from '../components/tasks/TaskLauncher'
import { TaskLogPanel } from '../components/tasks/TaskLogPanel'
import { useTasks } from '../hooks/useTasks'
import { useSystemConfig } from '../hooks/useSystem'
import { Alert, Button, Card } from '../components/ui'
import { IconRefresh } from '../components/ui/icons'
import '../styles/pages.css'

export function TasksPage() {
  const { items, error, loading, submitting, submit, retry, refresh } = useTasks(20)
  const { data: config } = useSystemConfig()

  const llmMissing = config !== null && !config.llm.ready

  return (
    <div className="stack">
      <header className="page-head">
        <h2 className="page-head__title">任务中心</h2>
        <p className="page-head__desc">
          提交仓库解析或每日热门任务，实时查看执行日志。任务在后台线程运行，不阻塞界面。
        </p>
      </header>

      {llmMissing && (
        <Alert tone="warn" title="LLM 未配置">
          当前未检测到可用的 LLM 接口，任务会在内容生成环节降级交付（只完成采集与校验）。
          请在项目根目录的 <code>.env</code> 中配置 <code>LLM_BASE_URL</code> /{' '}
          <code>LLM_API_KEY</code> / <code>LLM_MODEL</code> 后重启后端服务。
        </Alert>
      )}

      <Card title="新建任务" description="仓库解析为单仓库全流程；每日热门会抓取当日榜单前 N 个">
        <TaskLauncher submitting={submitting} error={error} onSubmit={submit} />
      </Card>

      <Card
        title="任务记录"
        description="点击任意记录可展开实时日志；失败任务可直接重试"
        actions={
          <Button icon={<IconRefresh size={15} />} onClick={refresh}>
            刷新
          </Button>
        }
      >
        <TaskLogPanel items={items} loading={loading} error={error} onRetry={retry} />
      </Card>
    </div>
  )
}
