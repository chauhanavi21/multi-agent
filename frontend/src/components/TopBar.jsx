import { useState } from 'react'
import { useAuth } from '../auth/AuthContext'

export default function TopBar({ view, onChangeView }) {
  const { user, company, logout } = useAuth()
  const [open, setOpen] = useState(false)

  return (
    <header className="topbar">
      <div className="topbar-left">
        <div className="brand">
          <span className="brand-dot"></span>
          <span>{company?.name || 'No company'}</span>
        </div>
        <div className="topbar-tabs">
          <button className={view === 'workspace' ? 'tabchip tabchip-active' : 'tabchip'}
                  onClick={() => onChangeView('workspace')}>Workspace</button>
          <button className={view === 'dashboard' ? 'tabchip tabchip-active' : 'tabchip'}
                  onClick={() => onChangeView('dashboard')}>Dashboard</button>
          <button className={view === 'memory' ? 'tabchip tabchip-active' : 'tabchip'}
                  onClick={() => onChangeView('memory')}>Memory</button>
          <button className={view === 'observability' ? 'tabchip tabchip-active' : 'tabchip'}
                  onClick={() => onChangeView('observability')}>Observability</button>
          {user?.is_admin && (
            <button className={view === 'admin' ? 'tabchip tabchip-active' : 'tabchip'}
                    onClick={() => onChangeView('admin')}>Admin</button>
          )}
        </div>
      </div>

      <div className="topbar-right">
        <button className="userchip" onClick={() => setOpen((v) => !v)}>
          <span className="user-avatar">{(user?.full_name || user?.email || '?')[0].toUpperCase()}</span>
          <span className="user-name">{user?.full_name || user?.email}</span>
          {user?.is_admin && <span className="admin-pill">admin</span>}
        </button>
        {open && (
          <div className="userdrop">
            <div className="userdrop-row dim">{user?.email}</div>
            <button onClick={logout} className="userdrop-btn">Sign out</button>
          </div>
        )}
      </div>
    </header>
  )
}
