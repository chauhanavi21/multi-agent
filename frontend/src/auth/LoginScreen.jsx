import { useState } from 'react'
import { useAuth } from './AuthContext'

export default function LoginScreen() {
  const { login, signup } = useAuth()
  const [mode, setMode] = useState('login')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [fullName, setFullName] = useState('')
  const [companyName, setCompanyName] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)

  async function submit(e) {
    e.preventDefault()
    setBusy(true)
    setErr(null)
    try {
      if (mode === 'login') {
        await login(email, password)
      } else {
        await signup({ email, password, full_name: fullName, company_name: companyName })
      }
    } catch (e) {
      setErr(e.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="login-screen">
      <div className="login-card">
        <div className="brand" style={{ marginBottom: 24 }}>
          <span className="brand-dot"></span>
          <span>Agent team</span>
        </div>

        <div className="login-tabs">
          <button
            className={mode === 'login' ? 'tab tab-active' : 'tab'}
            onClick={() => { setMode('login'); setErr(null) }}
            type="button"
          >Sign in</button>
          <button
            className={mode === 'signup' ? 'tab tab-active' : 'tab'}
            onClick={() => { setMode('signup'); setErr(null) }}
            type="button"
          >Sign up</button>
        </div>

        <form onSubmit={submit}>
          {mode === 'signup' && (
            <>
              <div className="field">
                <label className="field-label">Your name</label>
                <input
                  type="text" required value={fullName}
                  onChange={(e) => setFullName(e.target.value)}
                  autoComplete="name"
                />
              </div>
              <div className="field">
                <label className="field-label">Company name</label>
                <input
                  type="text" required value={companyName}
                  onChange={(e) => setCompanyName(e.target.value)}
                  placeholder="e.g. Acme Co"
                />
              </div>
            </>
          )}
          <div className="field">
            <label className="field-label">Email</label>
            <input
              type="email" required value={email}
              onChange={(e) => setEmail(e.target.value)}
              autoComplete="email"
            />
          </div>
          <div className="field">
            <label className="field-label">Password</label>
            <input
              type="password" required minLength={6} value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete={mode === 'login' ? 'current-password' : 'new-password'}
            />
          </div>
          {err && <div className="login-err">{err}</div>}
          <button type="submit" className="primary" disabled={busy}
                  style={{ width: '100%', marginTop: 6 }}>
            {busy ? 'Working...' : (mode === 'login' ? 'Sign in' : 'Create company')}
          </button>
        </form>

        <div className="login-hint">
          {mode === 'login' ? (
            <>Default admin: <code>boss@local.dev</code> / <code>bosspass</code></>
          ) : (
            <>Signing up creates your company with the fixed agent team.</>
          )}
        </div>
      </div>
    </div>
  )
}
