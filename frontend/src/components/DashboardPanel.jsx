import { useEffect, useState } from 'react'
import { api } from '../api/client'

const JOB_DESCRIPTIONS = {
  ceo_daily:      'CEO writes today\'s priorities (reviews yesterday)',
  cmo_daily:      'CMO scrapes top competitor reels + scripts 3 new ones',
  insights_daily: 'Insights agent mines patterns from converting leads',
  outreach_daily: 'Outreach agent contacts every lead due for follow-up',
}

export default function DashboardPanel() {
  const [plan, setPlan] = useState(null)
  const [jobs, setJobs] = useState([])
  const [scripts, setScripts] = useState([])
  const [sms, setSms] = useState([])
  const [err, setErr] = useState(null)
  const [busyJob, setBusyJob] = useState(null)
  const [editing, setEditing] = useState({})  // {job_name: {cron, enabled}}

  async function load() {
    setErr(null)
    try {
      const [p, j, s, m] = await Promise.all([
        api.dailyPlan().catch(() => null),
        api.schedulerJobs(),
        api.reelScripts(10),
        api.smsOutbox(20),
      ])
      setPlan(p); setJobs(j); setScripts(s); setSms(m)
    } catch (e) { setErr(e.message) }
  }

  useEffect(() => { load() }, [])

  async function runNow(job) {
    setBusyJob(job.job_name); setErr(null)
    try { await api.schedulerRunNow(job.job_name); await load() }
    catch (e) { setErr(e.message) }
    finally { setBusyJob(null) }
  }

  function startEdit(job) {
    setEditing({ ...editing, [job.job_name]: { cron: job.cron_expr, enabled: job.enabled } })
  }

  function changeEdit(job_name, patch) {
    setEditing({ ...editing, [job_name]: { ...editing[job_name], ...patch } })
  }

  async function saveEdit(job_name) {
    const e = editing[job_name]
    if (!e) return
    setBusyJob(job_name); setErr(null)
    try {
      await api.schedulerUpsertJob(job_name, e.cron, e.enabled)
      const next = { ...editing }; delete next[job_name]; setEditing(next)
      await load()
    } catch (er) { setErr(er.message) }
    finally { setBusyJob(null) }
  }

  return (
    <div className="obs">
      <div className="obs-header">
        <h2 style={{ margin: 0, fontSize: 18 }}>Dashboard</h2>
        <button onClick={load}>Refresh</button>
      </div>
      {err && <div className="login-err" style={{ marginBottom: 12 }}>{err}</div>}

      {/* ===== TODAY'S PLAN ===== */}
      <div className="card" style={{ marginBottom: 14 }}>
        <div className="card-title">CEO daily plan</div>
        {!plan ? (
          <div className="dim" style={{ padding: 12 }}>
            No plan yet for today. Run the <code>ceo_daily</code> job below
            (or wait for its scheduled time).
          </div>
        ) : (
          <div style={{ padding: 4 }}>
            <div className="dim" style={{ fontSize: 12 }}>
              {plan.plan_date} · written {plan.created_at?.slice(11, 16) || '—'}
            </div>
            <div style={{ marginTop: 6, fontSize: 13 }}>{plan.summary}</div>
            {plan.priorities?.length > 0 && (
              <ol style={{ marginTop: 10, paddingLeft: 20 }}>
                {plan.priorities.map((p, i) => (
                  <li key={i} style={{ marginBottom: 4 }}>{p}</li>
                ))}
              </ol>
            )}
            {plan.metrics_yesterday && (
              <div className="dim" style={{ marginTop: 10, fontSize: 11.5 }}>
                Yesterday: {plan.metrics_yesterday.leads_added} new leads ·{' '}
                {plan.metrics_yesterday.stage_changes} stage changes ·{' '}
                ${(plan.metrics_yesterday.cost_usd || 0).toFixed(4)} spent
              </div>
            )}
          </div>
        )}
      </div>

      {/* ===== SCHEDULER ===== */}
      <div className="card" style={{ marginBottom: 14 }}>
        <div className="card-title">Scheduled jobs</div>
        <div className="dim" style={{ fontSize: 11.5, marginBottom: 8 }}>
          Cron syntax: <code>m h dom mon dow</code>. Times are UTC.
        </div>
        <table className="admin-table" style={{ fontSize: 12.5 }}>
          <thead><tr>
            <th>Job</th><th>Cron</th><th>Enabled</th><th>Last run</th><th>Status</th><th></th>
          </tr></thead>
          <tbody>
            {jobs.map((j) => {
              const e = editing[j.job_name]
              return (
                <tr key={j.job_name}>
                  <td>
                    <div><b>{j.job_name}</b></div>
                    <div className="dim" style={{ fontSize: 10.5 }}>
                      {JOB_DESCRIPTIONS[j.job_name] || ''}
                    </div>
                  </td>
                  <td>
                    {e ? (
                      <input value={e.cron} onChange={(ev) => changeEdit(j.job_name, { cron: ev.target.value })}
                              style={{ width: 100, padding: '3px 6px', fontSize: 11.5 }} />
                    ) : <code>{j.cron_expr}</code>}
                  </td>
                  <td>
                    {e ? (
                      <input type="checkbox" checked={e.enabled}
                              onChange={(ev) => changeEdit(j.job_name, { enabled: ev.target.checked })} />
                    ) : (
                      <span className={j.enabled ? 'pill-ok' : 'pill-off'}>
                        {j.enabled ? 'on' : 'off'}
                      </span>
                    )}
                  </td>
                  <td className="dim" style={{ fontSize: 11 }}>
                    {j.last_run_at?.slice(0, 16).replace('T', ' ') || '—'}
                  </td>
                  <td>
                    {j.last_status === 'ok' && <span className="pill-ok">ok</span>}
                    {j.last_status === 'error' && (
                      <span className="pill-off" title={j.last_error || ''}>error</span>
                    )}
                    {!j.last_status && <span className="dim">—</span>}
                  </td>
                  <td>
                    {e ? (
                      <>
                        <button onClick={() => saveEdit(j.job_name)}
                                disabled={busyJob === j.job_name}
                                className="primary" style={{ padding: '2px 8px', fontSize: 11 }}>Save</button>
                        <button onClick={() => {
                          const next = { ...editing }; delete next[j.job_name]; setEditing(next)
                        }} disabled={busyJob === j.job_name}
                                style={{ marginLeft: 4, padding: '2px 8px', fontSize: 11 }}>Cancel</button>
                      </>
                    ) : (
                      <>
                        <button onClick={() => startEdit(j)} style={{ padding: '2px 8px', fontSize: 11 }}>Edit</button>
                        <button onClick={() => runNow(j)}
                                disabled={busyJob === j.job_name}
                                className="primary"
                                style={{ marginLeft: 4, padding: '2px 8px', fontSize: 11 }}>
                          {busyJob === j.job_name ? '...' : 'Run now'}
                        </button>
                      </>
                    )}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>

      {/* ===== REEL SCRIPTS ===== */}
      <div className="card" style={{ marginBottom: 14 }}>
        <div className="card-title">Recent reel scripts</div>
        {scripts.length === 0 ? (
          <div className="dim" style={{ padding: 12 }}>
            No scripts yet. Run the <code>cmo_daily</code> job to generate.
          </div>
        ) : (
          <div className="trace-tree" style={{ maxHeight: 'none' }}>
            {scripts.map((s) => (
              <div key={s.id} className="trace-node" style={{ marginLeft: 0 }}>
                <div className="trace-row">
                  <span className="trace-status" style={{ background: 'rgba(91,140,255,0.15)', color: '#a8c2ff' }}>
                    {s.title}
                  </span>
                  <span className="dim" style={{ fontSize: 10.5, marginLeft: 'auto' }}>
                    {s.created_at?.slice(0, 16).replace('T', ' ')}
                  </span>
                </div>
                <div style={{ marginLeft: 8, marginTop: 4, fontSize: 12.5 }}>
                  <div><b>Hook:</b> {s.hook}</div>
                  <div style={{ marginTop: 4 }}><b>Body:</b> {s.body}</div>
                  {s.cta && <div style={{ marginTop: 4 }}><b>CTA:</b> {s.cta}</div>}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* ===== SMS OUTBOX ===== */}
      <div className="card">
        <div className="card-title">SMS outbox</div>
        {sms.length === 0 ? (
          <div className="dim" style={{ padding: 12 }}>
            No SMS sent yet. The outreach agent will queue messages when leads are due
            for SMS follow-up.
          </div>
        ) : (
          <table className="admin-table" style={{ fontSize: 12 }}>
            <thead><tr>
              <th>When</th><th>Lead</th><th>To</th><th>Status</th><th>Body</th>
            </tr></thead>
            <tbody>
              {sms.map((m) => (
                <tr key={m.id}>
                  <td className="dim">{m.created_at?.slice(0, 16).replace('T', ' ')}</td>
                  <td className="dim">{m.lead_id ? `#${m.lead_id}` : '—'}</td>
                  <td className="dim">{m.to_number}</td>
                  <td>
                    {m.status === 'sent' && <span className="pill-ok">sent</span>}
                    {m.status === 'mock' && <span className="pill-warn">mock</span>}
                    {m.status === 'failed' && <span className="pill-off" title={m.error || ''}>failed</span>}
                    {m.status === 'queued' && <span className="dim">queued</span>}
                  </td>
                  <td style={{ maxWidth: 360, whiteSpace: 'normal' }}>{m.body}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}
