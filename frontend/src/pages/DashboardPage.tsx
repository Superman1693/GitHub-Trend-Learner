/** 概览页：产出统计、日期分布、系统状态与快捷入口。 */
import { Link } from 'react-router-dom'
import { useOverview, useSystemConfig } from '../hooks/useSystem'
import { Badge, Card, EmptyState, LoadingBlock, StatusDot } from '../components/ui'
import { IconDocument, IconSettings, IconTask } from '../components/ui/icons'
import { MetricsPanel } from '../components/dashboard/MetricsPanel'
import '../styles/pages.css'

export function DashboardPage() {
  const { data: overview, loading, error } = useOverview()
  const { data: config } = useSystemConfig()

  if (loading) return <LoadingBlock text="正在汇总运行状态…" />
  if (error) return <EmptyState title="无法读取运行概览" description={error} />

  const stats = overview?.documents
  const maxCount = Math.max(1, ...(stats?.dates.map((d) => d.count) ?? [1]))

  return (
    <div className="stack">
      <header className="page-head">
        <h2 className="page-head__title">运行概览</h2>
        <p className="page-head__desc">
          汇总产出文档、任务与运行配置。数据来自后端 <code>/api/system/overview</code>，
          每次进入页面实时拉取。
        </p>
      </header>

      <div className="grid grid--stats">
        <div className="stat">
          <div className="stat__label">产出文档</div>
          <div className="stat__value">
            {stats?.total_documents ?? 0}
            <span className="stat__unit">份</span>
          </div>
          <div className="stat__hint">归档在 outputs/ 目录</div>
        </div>

        <div className="stat">
          <div className="stat__label">覆盖日期</div>
          <div className="stat__value">
            {stats?.total_dates ?? 0}
            <span className="stat__unit">天</span>
          </div>
          <div className="stat__hint">最近：{stats?.latest_date ?? '暂无'}</div>
        </div>

        <div className="stat">
          <div className="stat__label">任务记录</div>
          <div className="stat__value">
            {overview?.tasks.total ?? 0}
            <span className="stat__unit">条</span>
          </div>
          <div className="stat__hint">
            运行中 {overview?.tasks.running ?? 0} 条（内存态，重启清空）
          </div>
        </div>

        <div className="stat">
          <div className="stat__label">内容生成</div>
          <div className="stat__value" style={{ fontSize: 'var(--fs-lg)' }}>
            {config?.llm.ready ? config.llm.model : '未配置'}
          </div>
          <div className="stat__hint">
            {config?.llm.ready ? 'LLM 就绪，可生成解读' : '配置 LLM_API_KEY 后可生成内容'}
          </div>
        </div>
      </div>

      <div className="grid grid--split">
        <Card title="按日期产出分布" description="最近若干天的归档数量">
          {stats && stats.dates.length > 0 ? (
            <div className="bar-list">
              {stats.dates.slice(0, 8).map((d) => (
                <div className="bar-item" key={d.date}>
                  <span className="text-subtle">{d.date}</span>
                  <span className="bar-item__track">
                    <span
                      className="bar-item__fill"
                      style={{ width: `${(d.count / maxCount) * 100}%` }}
                    />
                  </span>
                  <span className="bar-item__value">{d.count}</span>
                </div>
              ))}
            </div>
          ) : (
            <EmptyState title="暂无产出" description="提交一次任务后即可看到分布。" />
          )}
        </Card>

        <Card title="运行配置" description="敏感值只显示是否配置，不回显内容">
          <div className="kv-list">
            <span className="kv-list__k">GitHub Token</span>
            <span className="kv-list__v">
              <StatusDot tone={config?.github_token.configured ? 'ok' : 'warn'} />
              {config?.github_token.configured ? '已配置' : '未配置（限流 60 次/小时）'}
            </span>

            <span className="kv-list__k">LLM 接口</span>
            <span className="kv-list__v">
              <StatusDot tone={config?.llm.ready ? 'ok' : 'err'} />
              {config?.llm.ready ? `就绪（${config.llm.model}）` : '未配置'}
            </span>

            <span className="kv-list__k">SMTP 邮件</span>
            <span className="kv-list__v">
              <StatusDot tone={config?.smtp.ready ? 'ok' : 'warn'} />
              {config?.smtp.ready ? '已配置' : '未配置（仅归档不发信）'}
            </span>

            <span className="kv-list__k">并发 / 重试 / 退回</span>
            <span className="kv-list__v mono">
              {config ? `${config.concurrency} / ${config.max_retries} / ${config.max_gate_returns}` : '-'}
            </span>
          </div>
        </Card>
      </div>

      <Card title="快捷入口">
        <div className="quick-links">
          <Link className="quick-link" to="/documents">
            <span className="quick-link__icon">
              <IconDocument size={17} />
            </span>
            <div>
              <div className="quick-link__title">浏览解读文档</div>
              <div className="quick-link__desc">按日期查看六模块产出</div>
            </div>
          </Link>

          <Link className="quick-link" to="/tasks">
            <span className="quick-link__icon">
              <IconTask size={17} />
            </span>
            <div>
              <div className="quick-link__title">发起解析任务</div>
              <div className="quick-link__desc">粘贴仓库链接或跑每日热门</div>
            </div>
          </Link>

          <Link className="quick-link" to="/settings">
            <span className="quick-link__icon">
              <IconSettings size={17} />
            </span>
            <div>
              <div className="quick-link__title">查看系统设置</div>
              <div className="quick-link__desc">配置项与模块规范说明</div>
            </div>
          </Link>
        </div>
      </Card>

      <MetricsPanel days={7} />

      <Card title="模块口径提示">
        <p className="text-muted" style={{ fontSize: 'var(--fs-sm)' }}>
          文档规范为 <strong>六模块</strong>（v1.5 起删除报错大全，原 M7 前移为 M6）。
          代码侧已同步为六模块产出，阅读器同时兼容历史七模块文档 —— 模块数量以文档实际内容为准。
        </p>
        <div className="row" style={{ marginTop: 'var(--sp-3)', flexWrap: 'wrap' }}>
          <Badge tone="accent">结构固定 · 内容定制</Badge>
          <Badge>M5 部署方案为质量重心</Badge>
        </div>
      </Card>
    </div>
  )
}
