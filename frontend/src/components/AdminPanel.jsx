import { useEffect, useState } from 'react'
import { api } from '../api/client'

export default function AdminPanel() {
  const [users, setUsers] = useState([])
  const [companies, setCompanies] = useState([])
  const [tab, setTab] = useState('users')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)

  async function load() {
    setErr(null)
    try {
      const [u, c] = await Promise.all([api.adminUsers(), api.adminCompanies()])
      setUsers(u); setCompanies(c)
    } catch (e) { setErr(e.message) }
  }

  useEffect(() => { load() }, [])

  async function toggleActive(u) {
    setBusy(true)
    try { await api.adminSetActive(u.id, !u.is_active); await load() }
    catch (e) { setErr(e.message) } finally { setBusy(false) }
  }

  async function toggleCloud(c) {
    setBusy(true)
    try { await api.adminSetCloud(c.id, !c.use_cloud_api); await load() }
    catch (e) { setErr(e.message) } finally { setBusy(false) }
  }

  async function updateBudget(c, newBudget) {
    setBusy(true)
    try { await api.adminSetBudget(c.id, newBudget); await load() }
    catch (e) { setErr(e.message) } finally { setBusy(false) }
  }

  async function updateProvider(c, newProvider) {
    setBusy(true)
    try { await api.adminSetProvider(c.id, newProvider); await load() }
    catch (e) { setErr(e.message) } finally { setBusy(false) }
  }

  return (
    <div className="admin">
      <div className="admin-header">
        <h2 style={{ margin: 0, fontSize: 18 }}>Admin panel</h2>
        <div className="topbar-tabs">
          <button className={tab === 'users' ? 'tabchip tabchip-active' : 'tabchip'}
                  onClick={() => setTab('users')}>Users ({users.length})</button>
          <button className={tab === 'companies' ? 'tabchip tabchip-active' : 'tabchip'}
                  onClick={() => setTab('companies')}>Companies ({companies.length})</button>
        </div>
      </div>

      {err && <div className="login-err" style={{ margin: 20 }}>{err}</div>}

      <div className="admin-body">
        {tab === 'users' ? (
          <table className="admin-table">
            <thead><tr>
              <th>ID</th><th>Email</th><th>Name</th><th>Role</th>
              <th>Company</th><th>Created</th><th>Last login</th><th>Active</th><th></th>
            </tr></thead>
            <tbody>
              {users.map((u) => (
                <tr key={u.id}>
                  <td className="dim">{u.id}</td>
                  <td>{u.email}</td>
                  <td>{u.full_name || '—'}</td>
                  <td>{u.is_admin ? <span className="admin-pill">admin</span> : 'user'}</td>
                  <td className="dim">{u.company_id || '—'}</td>
                  <td className="dim">{u.created_at?.slice(0, 10)}</td>
                  <td className="dim">{u.last_login_at?.slice(0, 10) || '—'}</td>
                  <td><span className={u.is_active ? 'pill-ok' : 'pill-off'}>
                    {u.is_active ? 'active' : 'inactive'}
                  </span></td>
                  <td>
                    {!u.is_admin && (
                      <button onClick={() => toggleActive(u)} disabled={busy}
                              className={u.is_active ? 'danger' : ''}>
                        {u.is_active ? 'Deactivate' : 'Activate'}
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <table className="admin-table">
            <thead><tr>
              <th>ID</th><th>Name</th><th>Owner</th><th>Cloud API</th><th>Provider</th>
              <th>Budget</th><th>Override</th><th>Created</th>
            </tr></thead>
            <tbody>
              {companies.map((c) => (
                <tr key={c.id}>
                  <td className="dim">{c.id}</td>
                  <td>{c.name}</td>
                  <td className="dim">user #{c.owner_user_id}</td>
                  <td>
                    <button onClick={() => toggleCloud(c)} disabled={busy}
                            className={c.use_cloud_api ? 'primary' : ''}>
                      {c.use_cloud_api ? 'On' : 'Off'}
                    </button>
                  </td>
                  <td>
                    <select
                      value={c.cloud_provider || 'anthropic'}
                      disabled={busy || !c.use_cloud_api}
                      onChange={(e) => updateProvider(c, e.target.value)}
                      style={{ padding: '4px 8px', fontSize: 12, minWidth: 110 }}
                    >
                      <option value="anthropic">Anthropic</option>
                      <option value="bedrock">Bedrock</option>
                    </select>
                  </td>
                  <td><BudgetCell company={c} onSave={(v) => updateBudget(c, v)} busy={busy} /></td>
                  <td className="dim">
                    {c.org_chart_override
                      ? <span className="pill-warn">overridden</span>
                      : <span className="dim">default</span>}
                  </td>
                  <td className="dim">{c.created_at?.slice(0, 10)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}

function BudgetCell({ company, onSave, busy }) {
  const [editing, setEditing] = useState(false)
  const [val, setVal] = useState(company.monthly_budget_usd)

  if (!editing) {
    return (
      <span className="budget-cell">
        ${company.monthly_budget_usd.toFixed(2)}/mo
        <button onClick={() => setEditing(true)} disabled={busy} style={{ marginLeft: 6, padding: '2px 8px', fontSize: 11 }}>Edit</button>
      </span>
    )
  }
  return (
    <span className="budget-cell">
      $<input type="number" step="0.01" min="0" value={val}
              onChange={(e) => setVal(parseFloat(e.target.value) || 0)}
              style={{ width: 70, padding: '3px 6px', fontSize: 12 }} />
      <button onClick={async () => { await onSave(val); setEditing(false) }}
              disabled={busy} className="primary"
              style={{ marginLeft: 4, padding: '2px 8px', fontSize: 11 }}>Save</button>
      <button onClick={() => { setEditing(false); setVal(company.monthly_budget_usd) }}
              disabled={busy} style={{ marginLeft: 4, padding: '2px 8px', fontSize: 11 }}>Cancel</button>
    </span>
  )
}
