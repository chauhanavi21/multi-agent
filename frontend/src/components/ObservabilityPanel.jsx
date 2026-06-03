import { useEffect, useState } from 'react'
import { api } from '../api/client'
import TraceTree from './TraceTree'

export default function ObservabilityPanel() {
  const [summary, setSummary] = useState(null)
  const [traces, setTraces] = useState([])
  const [timeseries, setTimeseries] = useState([])
  const [cacheStats, setCacheStats] = useState(null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)

  async function load() {
    setErr(null)
    try {
      const [s, t, ts, cs] = await Promise.all([
        api.costSummary(), api.recentTraces(100),
        api.costTimeseries(14), api.cacheStats(),
      ])
      setSummary(s); setTraces(t); setTimeseries(ts); setCacheStats(cs)
    } catch (e) { setErr(e.message) }
  }

  useEffect(() => { load(); const t = setInterval(load, 15000); return () => clearInterval(t) }, [])

  async function clearCache() {
    if (!confirm('Clear all cached responses for your company?')) return
    setBusy(true)
    try { await api.clearCache(); await load() }
    catch (e) { setErr(e.message) }
    finally { setBusy(false) }
  }

  const maxCost = Math.max(0.0001, ...timeseries.map((d) => d.cost_usd))

  return (
    <div className="obs">
      <div className="obs-header">
        <h2 style={{ margin: 0, fontSize: 18 }}>Observability</h2>
        <button onClick={clearCache} disabled={busy} className="danger">
          {busy ? 'Clearing...' : 'Clear cache'}
        </button>
      </div>

      {err && <div className="login-err" style={{ margin: '8px 0' }}>{err}</div>}

      <div className="obs-grid">
        {/* Budget */}
        {summary && (
          <div className="card">
            <div className="card-title">Budget this month</div>
            <div style={{ fontSize: 24, fontWeight: 600 }}>
              ${summary.budget.spent_usd.toFixed(4)}
              <span className="dim" style={{ fontSize: 13, fontWeight: 400, marginLeft: 6 }}>
                / ${summary.budget.budget_usd.toFixed(2)}
              </span>
            </div>
            <div className="progress" style={{ marginTop: 8 }}>
              <div className="progress-fill" style={{
                width: `${Math.min(100, summary.budget.pct_used)}%`,
                background: summary.budget.pct_used >= 100 ? 'var(--danger)'
                          : summary.budget.pct_used >= 80 ? 'var(--warn)'
                          : 'var(--accent)',
              }} />
            </div>
            <div className="dim" style={{ marginTop: 10, fontSize: 12 }}>
              Cloud API: {summary.budget.can_use_cloud
                ? <span style={{ color: 'var(--success)' }}>enabled</span>
                : <span style={{ color: 'var(--text-dim)' }}>disabled / over budget</span>}
              {summary.budget.must_downgrade && (
                <span style={{ color: 'var(--warn)', marginLeft: 8 }}>· downgrading</span>
              )}
            </div>
          </div>
        )}

        {/* Cache */}
        {summary && cacheStats && (
          <div className="card">
            <div className="card-title">Semantic cache</div>
            <div style={{ fontSize: 24, fontWeight: 600 }}>{summary.cache.hit_rate_pct.toFixed(1)}%</div>
            <div className="dim" style={{ marginTop: 4 }}>hit rate · 30d</div>
            <div className="row" style={{ marginTop: 10, justifyContent: 'space-between' }}>
              <span className="dim">{summary.cache.cache_hits_30d} / {summary.cache.total_calls_30d} calls</span>
              <span className="dim">{cacheStats.entries} entries</span>
            </div>
            {!cacheStats.available && (
              <div style={{ marginTop: 8, color: 'var(--warn)', fontSize: 11 }}>
                Redis unavailable — cache disabled
              </div>
            )}
          </div>
        )}

        {/* Sparkline */}
        <div className="card">
          <div className="card-title">Daily cost · last 14d</div>
          <div className="spark">
            {timeseries.length === 0 ? (
              <div className="dim" style={{ padding: 20, textAlign: 'center' }}>No data yet</div>
            ) : (
              timeseries.map((d) => (
                <div key={d.day} className="spark-bar" title={`${d.day}: $${d.cost_usd.toFixed(4)} (${d.calls} calls)`}>
                  <div className="spark-bar-fill" style={{
                    height: `${(d.cost_usd / maxCost) * 100}%`
                  }} />
                  <div className="spark-bar-label">{d.day?.slice(5)}</div>
                </div>
              ))
            )}
          </div>
        </div>
      </div>

      {/* By model */}
      {summary && summary.by_model?.length > 0 && (
        <div className="card" style={{ marginTop: 16 }}>
          <div className="card-title">By model · 30d</div>
          <table className="admin-table">
            <thead>
              <tr><th>Model</th><th>Calls</th><th>Input tok</th><th>Output tok</th><th>Cost</th></tr>
            </thead>
            <tbody>
              {summary.by_model.map((m) => (
                <tr key={m.model}>
                  <td>
                    <span className={`trace-model ${m.model.includes('claude') ? 'cloud' : 'local'}`}>
                      {m.model}
                    </span>
                  </td>
                  <td>{m.calls}</td>
                  <td className="dim">{m.input_tokens.toLocaleString()}</td>
                  <td className="dim">{m.output_tokens.toLocaleString()}</td>
                  <td>${m.cost_usd.toFixed(6)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Recent traces */}
      <div className="card" style={{ marginTop: 16 }}>
        <div className="card-title">Recent traces ({traces.length})</div>
        <TraceTree spans={traces} />
      </div>
    </div>
  )
}
