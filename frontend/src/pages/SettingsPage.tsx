/** 系统设置页：运行配置、服务健康、模块规范与使用说明。 */
import { useHealth, useSystemConfig } from '../hooks/useSystem'
import { Badge, Card, LoadingBlock, StatusDot } from '../components/ui'
import { formatTime } from '../utils/format'
import '../styles/pages.css'

// 兜底清单：正常情况下由后端 /api/system/config 的 modules 字段下发（v1.8 收敛为单一来源），
// 仅在旧后端或接口降级时使用。
const FALLBACK_MODULES = [
  { key: 'intro', name: '项目基础大白话介绍' },
  { key: 'principle', name: '零基础通俗原理讲解' },
  { key: 'tutorial', name: '新手入门使用教程' },
  { key: 'source-code', name: '源码核心逻辑通俗分析' },
  { key: 'deploy', name: '本地一键部署完整方案' },
  { key: 'growth', name: '新手学习提升指南' },
]

export function SettingsPage() {
  const { data: config, loading, error } = useSystemConfig()
  const { data: health, error: healthError } = useHealth()
  const modules = config?.modules?.length ? config.modules : FALLBACK_MODULES

  if (loading) return <LoadingBlock text="正在读取系统配置…" />

  return (
    <div className="stack">
      <header className="page-head">
        <h2 className="page-head__title">系统设置</h2>
        <p className="page-head__desc">
          只读展示当前运行配置。敏感值仅报告是否配置，不会回显内容。修改配置请编辑项目根目录的{' '}
          <code>.env</code> 并重启后端服务。
        </p>
      </header>

      {error && <Card title="配置读取异常">{error}</Card>}

      <div className="grid grid--split">
        <Card title="运行配置">
          <div className="kv-list">
            <span className="kv-list__k">GitHub Token</span>
            <span className="kv-list__v">
              <StatusDot tone={config?.github_token.configured ? 'ok' : 'warn'} />
              {config?.github_token.configured
                ? '已配置'
                : '未配置（受未认证限流 60 次/小时）'}
            </span>

            <span className="kv-list__k">LLM 接口</span>
            <span className="kv-list__v">
              <StatusDot tone={config?.llm.ready ? 'ok' : 'err'} />
              {config?.llm.ready ? `就绪 · ${config.llm.model}` : '未配置'}
            </span>

            <span className="kv-list__k">SMTP 邮件</span>
            <span className="kv-list__v">
              <StatusDot tone={config?.smtp.ready ? 'ok' : 'warn'} />
              {config?.smtp.ready ? '已配置' : '未配置（每日任务仅归档）'}
            </span>

            <span className="kv-list__k">并发上限</span>
            <span className="kv-list__v mono">{config?.concurrency ?? '-'} 个仓库</span>

            <span className="kv-list__k">重试上限</span>
            <span className="kv-list__v mono">{config?.max_retries ?? '-'} 次</span>

            <span className="kv-list__k">门禁退回上限</span>
            <span className="kv-list__v mono">{config?.max_gate_returns ?? '-'} 次</span>
          </div>
        </Card>

        <Card title="服务健康">
          {healthError ? (
            <div className="kv-list">
              <span className="kv-list__k">状态</span>
              <span className="kv-list__v">
                <StatusDot tone="err" />
                {healthError}
              </span>
            </div>
          ) : (
            <div className="kv-list">
              <span className="kv-list__k">服务状态</span>
              <span className="kv-list__v">
                <StatusDot tone="ok" />
                正常
              </span>

              <span className="kv-list__k">服务版本</span>
              <span className="kv-list__v mono">{health?.version ?? '-'}</span>

              <span className="kv-list__k">服务时间</span>
              <span className="kv-list__v mono">{formatTime(health?.time)}</span>

              <span className="kv-list__k">前端产物</span>
              <span className="kv-list__v">
                <StatusDot tone={health?.frontend.built ? 'ok' : 'warn'} />
                {health?.frontend.built ? '已构建' : '未构建（当前为引导页）'}
              </span>

              <span className="kv-list__k">产物路径</span>
              <span className="kv-list__v mono">{health?.frontend.dist_path ?? '-'}</span>
            </div>
          )}
        </Card>
      </div>

      <Card
        title="输出模块规范"
        description="结构固定、内容定制：模块不可增删改名，内部内容按项目类型调整"
      >
        <ol style={{ margin: 0, paddingLeft: 'var(--sp-6)', lineHeight: 1.9 }}>
          {modules.map((m) => (
            <li key={m.key}>
              <span>{m.name}</span>{' '}
              <span className="mono text-subtle">{m.key}</span>
              {m.key === 'deploy' && (
                <>
                  {' '}
                  <Badge tone="accent">质量重心</Badge>
                </>
              )}
            </li>
          ))}
        </ol>
        <p className="text-muted" style={{ marginTop: 'var(--sp-4)', fontSize: 'var(--fs-sm)' }}>
          M5「本地一键部署完整方案」要求做到「照着一步步做就能真正跑起来」：环境准备逐项附安装教程、
          每个关键步骤给出执行位置与预期结果、补齐前置操作、不留未说明的占位符。
        </p>
      </Card>

      <Card title="启动与访问">
        <div className="kv-list">
          <span className="kv-list__k">启动后端</span>
          <span className="kv-list__v mono">python -m server</span>

          <span className="kv-list__k">一键启动</span>
          <span className="kv-list__v mono">python start_ui.py</span>

          <span className="kv-list__k">前端开发</span>
          <span className="kv-list__v mono">cd frontend &amp;&amp; npm run dev</span>

          <span className="kv-list__k">重新构建</span>
          <span className="kv-list__v mono">cd frontend &amp;&amp; npm run build</span>

          <span className="kv-list__k">默认端口</span>
          <span className="kv-list__v mono">8000（可用 UI_PORT 覆盖）</span>
        </div>
      </Card>
    </div>
  )
}
