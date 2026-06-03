import { useEffect, useState } from 'react'
import { api } from '../api/client'

export default function CostCard() {
  const [data, setData] = useState(null)
  const [err, setErr] = useState(null)

  useEffect(() => {
    let alive = true
    async function load() {
      try {
        const d = await api.costSummary()
        if (alive) setData(d)
      } catch (e) { if (alive) setErr(e.message) }
    }
    load()
    const t = setInterval(load, 15000)
    return () => { alive = false; clearInterval(t) }
  }, [])

  if (err) return <div className="card"><div className="card-title">Cost</div><div className="dim">{err}</div></div>
  if (!data) return <div className="card"><div className="card-title">Cost</div><div className="dim">Loading...</div></div>

  const { budget, cache } = data
  const pct = Math.min(100, budget.pct_used)
  const barColor = pct >= 100 ? 'var(--danger)' : pct >= 80 ? 'var(--warn)' : 'var(--accent)'

  return (
    <div className="card">
      <div className="card-title">Cost this month</div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: 6 }}>
        <span style={{ fontSize: 18, fontWeight: 600 }}>
          ${budget.spent_usd.toFixed(4)}
        </span>
        <span className="dim">of ${budget.budget_usd.toFixed(2)}</span>
      </div>
      <div className="progress">
        <div className="progress-fill" style={{ width: `${pct}%`, background: barColor }} />
      </div>
      <div className="dim" style={{ marginTop: 6, fontSize: 11.5 }}>
        {budget.pct_used.toFixed(1)}% used
        {budget.must_downgrade && <span style={{ color: 'var(--warn)', marginLeft: 8 }}>· downgrading cloud→local</span>}
        {!budget.can_use_cloud && budget.pct_used < 100 && <span style={{ color: 'var(--text-dim)', marginLeft: 8 }}>· cloud disabled</span>}
      </div>

      <div className="cost-divider" />

      <div className="row" style={{ justifyContent: 'space-between' }}>
        <div>
          <div className="dim" style={{ fontSize: 10.5, textTransform: 'uppercase', letterSpacing: '0.05em' }}>Cache hit rate</div>
          <div style={{ fontSize: 16, fontWeight: 500 }}>{cache.hit_rate_pct.toFixed(1)}%</div>
        </div>
        <div style={{ textAlign: 'right' }}>
          <div className="dim" style={{ fontSize: 10.5, textTransform: 'uppercase', letterSpacing: '0.05em' }}>Calls (30d)</div>
          <div style={{ fontSize: 16, fontWeight: 500 }}>{cache.total_calls_30d}</div>
        </div>
      </div>
    </div>
  )
}
