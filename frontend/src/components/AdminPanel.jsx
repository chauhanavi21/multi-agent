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
      setUsers(u)
      setCompanies(c)
    } catch (e) { setErr(e.message) }
  }

  useEffect(() => { load() }, [])

  async function toggleActive(u) {
    setBusy(true)
    try {
      await api.adminSetActive(u.id, !u.is_active)
      await load()
    } catch (e) { setErr(e.message) }
    finally { setBusy(false) }
  }

  return (
    <div className="admin">
      <div className="admin-header">
        <h2 style={{ margin: 0, fontSize: 18 }}>Admin panel</h2>
        <div className="topbar-tabs">
          <button
            className={tab === 'users' ? 'tabchip tabchip-active' : 'tabchip'}
            onClick={() => setTab('users')}
          >Users ({users.length})</button>
          <button
            className={tab === 'companies' ? 'tabchip tabchip-active' : 'tabchip'}
            onClick={() => setTab('companies')}
          >Companies ({companies.length})</button>
        </div>
      </div>

      {err && <div className="login-err" style={{ margin: 20 }}>{err}</div>}

      <div className="admin-body">
        {tab === 'users' ? (
          <table className="admin-table">
            <thead>
              <tr>
                <th>ID</th><th>Email</th><th>Name</th><th>Role</th>
                <th>Company</th><th>Created</th><th>Last login</th><th>Active</th><th></th>
              </tr>
            </thead>
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
                  <td>
                    <span className={u.is_active ? 'pill-ok' : 'pill-off'}>
                      {u.is_active ? 'active' : 'inactive'}
                    </span>
                  </td>
                  <td>
                    {!u.is_admin && (
                      <button
                        onClick={() => toggleActive(u)} disabled={busy}
                        className={u.is_active ? 'danger' : ''}
                      >
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
            <thead>
              <tr>
                <th>ID</th><th>Name</th><th>Owner</th><th>Override</th><th>Created</th>
              </tr>
            </thead>
            <tbody>
              {companies.map((c) => (
                <tr key={c.id}>
                  <td className="dim">{c.id}</td>
                  <td>{c.name}</td>
                  <td className="dim">user #{c.owner_user_id}</td>
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
