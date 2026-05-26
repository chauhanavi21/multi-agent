import AgentBadge from './AgentBadge'

const STATUS_COLORS = {
  pending: { bg: 'rgba(150, 150, 150, 0.12)', fg: '#9aa3b2', label: 'Pending' },
  running: { bg: 'rgba(251, 191, 36, 0.15)', fg: '#ffd069', label: 'Running' },
  ok: { bg: 'rgba(74, 222, 128, 0.15)', fg: '#88f0a6', label: 'Done' },
  error: { bg: 'rgba(248, 113, 113, 0.15)', fg: '#fa9999', label: 'Error' },
  skipped: { bg: 'rgba(150, 150, 150, 0.12)', fg: '#6b7280', label: 'Skipped' },
}

export default function TaskKanban({ tasks }) {
  if (!tasks?.length) return null

  return (
    <div className="kanban">
      <div className="card-title">Tasks ({tasks.length})</div>
      <div className="kanban-list">
        {tasks.map((t) => {
          const s = STATUS_COLORS[t.status] || STATUS_COLORS.pending
          const out = t.output
          return (
            <div key={t.task_key || t.id} className="kanban-row">
              <div className="kanban-row-head">
                <span className="kanban-key">{t.task_key}</span>
                <AgentBadge name={t.agent_name} />
                <span className="kanban-action">{t.action}</span>
                <span
                  className="kanban-status"
                  style={{ background: s.bg, color: s.fg }}
                >
                  {s.label}
                </span>
              </div>
              {t.depends_on && t.depends_on.length > 0 && (
                <div className="kanban-deps">
                  ↳ depends on {t.depends_on.join(', ')}
                </div>
              )}
              {t.error && (
                <div className="kanban-error">{t.error}</div>
              )}
              {out && t.status === 'ok' && (
                <div className="kanban-output">{summarizeOutput(out)}</div>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}

function summarizeOutput(o) {
  if (!o) return ''
  if (o.subject && o.body) return `✉ ${o.subject}`
  if (o.created) return `+ ${o.created.length} new leads`
  if (o.title && o.body) return `📄 ${o.title}`
  if (o.findings) return `${o.severity}: ${o.findings.length} finding(s)`
  if (o.summary) return o.summary.slice(0, 120) + (o.summary.length > 120 ? '...' : '')
  if (o.test_cases) return `${o.test_cases.length} test cases`
  if (o.hashtags_by_platform) {
    const total = Object.values(o.hashtags_by_platform).reduce((n, arr) => n + arr.length, 0)
    return `${total} hashtags across platforms`
  }
  if (o.leads) return `${o.leads.length} leads matched`
  return JSON.stringify(o).slice(0, 100) + '...'
}
