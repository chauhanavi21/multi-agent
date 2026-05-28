import { createContext, useContext, useEffect, useState, useCallback } from 'react'
import { api, getToken, setToken } from '../api/client'

const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null)
  const [company, setCompany] = useState(null)
  const [loading, setLoading] = useState(true)

  const refresh = useCallback(async () => {
    if (!getToken()) {
      setUser(null)
      setCompany(null)
      setLoading(false)
      return
    }
    try {
      const data = await api.me()
      setUser(data.user)
      setCompany(data.company)
    } catch {
      setToken(null)
      setUser(null)
      setCompany(null)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { refresh() }, [refresh])

  async function login(email, password) {
    const r = await api.login({ email, password })
    setToken(r.access_token)
    setUser(r.user)
    setCompany(r.company)
  }

  async function signup(payload) {
    const r = await api.signup(payload)
    setToken(r.access_token)
    setUser(r.user)
    setCompany(r.company)
  }

  function logout() {
    setToken(null)
    setUser(null)
    setCompany(null)
  }

  return (
    <AuthContext.Provider value={{ user, company, loading, login, signup, logout, refresh }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be inside AuthProvider')
  return ctx
}
