import { useEffect, useState } from 'react'
import { api } from '../api/client'

const KINDS = ['lesson', 'pattern', 'fact', 'preference', 'competitor', 'win', 'loss']

export default function MemoryPanel() {
  const [stats, setStats] = useState(null)
  const [rows, setRows] = useState([])
  const [filterKind, setFilterKind] = useState('')
  const [query, setQuery] = useState('')
  const [searched, setSearched] = useState(false)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)

  async function load() {
    setErr(null)
    try {
      const [s, r] = await Promise.all([
        api.memoryStats(),
        api.memoryRecent(100, filterKind || null),
      ])
      setStats(s)
      setRows(r)
      setSearched(false)
    } catch (e) { setErr(e.message) }
  }

  useEffect(() => { load() }, [filterKind])

  async function search() {
    if (!query.trim()) { load(); return }
    setBusy(true); setErr(null)
    try {
      const r = await api.memoryRetrieve(query, 20, filterKind ? [filterKind] : null)
      setRows(r)
      setSearched(true)
    } catch (e) { setErr(e.message) }
    finally { setBusy(false) }
  }

  async function remove(id) {
    if (!confirm('Delete this memory?')) return
    try {
      await api.memoryDelete(id)
      setRows(rows.filter((r) => r.id !== id))
    } catch (e) { setErr(e.message) }
  }

  return (
    <div className="obs">
      <div className="obs-header">
        <h2 style={{ margin: 0, fontSize: 18 }}>Shared memory</h2>
        {stats && (
          <div className="dim" style={{ fontSize: 12 }}>
            backend: <span className={`trace-model ${stats.backend === 'pgvector' ? 'cloud' : 'local'}`}>{stats.backend}</span>
            {' · '}
            total: <b style={{ color: 'var(--text)' }}>{stats.total}</b>
          </div>
        )}
      </div>

      {err && <div className="login-err" style={{ margin: '8px 0' }}>{err}</div>}

      {stats && (
        <div className="card" style={{ marginBottom: 14 }}>
          <div className="card-title">By kind</div>
          <div className="row" style={{ gap: 12, flexWrap: 'wrap', marginTop: 6 }}>
            {KINDS.map((k) => (
              <div key={k} style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                <span className={`trace-tag-cache`} style={{ background: 'rgba(91,140,255,0.15)', color: '#a8c2ff' }}>{k}</span>
                <span className="dim">{stats.by_kind?.[k] || 0}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="card" style={{ marginBottom: 14 }}>
        <div className="row" style={{ gap: 8, alignItems: 'stretch' }}>
          <select value={filterKind} onChange={(e) => setFilterKind(e.target.value)}
                  style={{ padding: '6px 10px' }}>
            <option value="">All kinds</option>
            {KINDS.map((k) => <option key={k} value={k}>{k}</option>)}
          </select>
          <input value={query} onChange={(e) => setQuery(e.target.value)}
                 onKeyDown={(e) => e.key === 'Enter' && search()}
                 placeholder="Semantic search (e.g., 'fintech outreach what worked')"
                 style={{ flex: 1, padding: '6px 10px' }} />
          <button onClick={search} disabled={busy} className="primary">
            {busy ? '...' : 'Search'}
          </button>
          <button onClick={load} disabled={busy}>Reset</button>
        </div>
      </div>

      <div className="card">
        <div className="card-title">
          {searched ? `Search results (${rows.length})` : `Recent memories (${rows.length})`}
        </div>
        {rows.length === 0 ? (
          <div className="dim" style={{ padding: 20, textAlign: 'center' }}>
            No memories {searched ? 'matched' : 'yet'}. Agents write here automatically after tasks.
          </div>
        ) : (
          <div className="trace-tree" style={{ maxHeight: 'none' }}>
            {rows.map((m) => (
              <div key={m.id} className="trace-node" style={{ marginLeft: 0 }}>
                <div className="trace-row">
                  <span className={`trace-tag-cache`} style={{ background: 'rgba(91,140,255,0.15)', color: '#a8c2ff' }}>{m.kind}</span>
                  {(m.tags || []).slice(0, 4).map((t) => (
                    <span key={t} className="trace-tokens">#{t}</span>
                  ))}
                  {m.score != null && <span className="trace-cost">sim={m.score.toFixed(2)}</span>}
                  <span className="dim" style={{ fontSize: 10.5 }}>imp={m.importance?.toFixed(2)}</span>
                  <span className="trace-status" style={{ marginLeft: 'auto', fontWeight: 400, background: 'rgba(255,255,255,0.06)', color: 'var(--text-dim)' }}>
                    {m.source_agent || '?'}
                  </span>
                  <button onClick={() => remove(m.id)}
                          style={{ marginLeft: 4, padding: '2px 8px', fontSize: 11 }}
                          className="danger">×</button>
                </div>
                <div style={{ marginTop: 4, marginLeft: 8, fontSize: 13 }}>
                  {m.content}
                </div>
                <div className="dim" style={{ marginTop: 4, marginLeft: 8, fontSize: 10.5 }}>
                  {m.created_at?.slice(0, 16).replace('T', ' ')}
                  {m.access_count > 0 && <span> · accessed {m.access_count}x</span>}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
