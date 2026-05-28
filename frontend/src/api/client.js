const BASE = 'http://localhost:8000/api'
const TOKEN_KEY = 'sa.token'

export function getToken() {
  return localStorage.getItem(TOKEN_KEY)
}

export function setToken(token) {
  if (token) localStorage.setItem(TOKEN_KEY, token)
  else localStorage.removeItem(TOKEN_KEY)
}

function authHeaders() {
  const t = getToken()
  return t ? { Authorization: `Bearer ${t}` } : {}
}

async function http(path, opts = {}) {
  const res = await fetch(`${BASE}${path}`, {
    headers: {
      'Content-Type': 'application/json',
      ...authHeaders(),
      ...(opts.headers || {}),
    },
    ...opts,
  })
  if (res.status === 401) {
    setToken(null)
    window.location.reload()
    throw new Error('Unauthorized')
  }
  if (!res.ok) {
    let detail
    try { detail = (await res.json()).detail } catch {}
    throw new Error(detail || `${res.status} ${res.statusText}`)
  }
  return res.status === 204 ? null : res.json()
}

export const api = {
  // Auth
  signup: (data) => http('/auth/signup', { method: 'POST', body: JSON.stringify(data) }),
  login: (data) => http('/auth/login', { method: 'POST', body: JSON.stringify(data) }),
  me: () => http('/auth/me'),

  // Company
  myCompany: () => http('/company/me'),
  myTeam: () => http('/company/team'),

  // Leads (Phase 1, now scoped)
  listLeads: () => http('/leads'),
  getLead: (id) => http(`/leads/${id}`),
  setStatus: (id, status) =>
    http(`/leads/${id}/status`, { method: 'PUT', body: JSON.stringify({ status }) }),
  listDrafts: (leadId) => http(`/leads/${leadId}/drafts`),
  updateDraft: (id, subject, body) =>
    http(`/drafts/${id}`, { method: 'PUT', body: JSON.stringify({ subject, body }) }),
  sendDraft: (id) => http(`/drafts/${id}/send`, { method: 'POST' }),

  // Chat (Phase 2, now scoped)
  createSession: (title) =>
    http('/chat/sessions', { method: 'POST', body: JSON.stringify({ title }) }),
  listSessions: () => http('/chat/sessions'),
  sessionTasks: (id) => http(`/chat/sessions/${id}/tasks`),

  // Admin
  adminUsers: () => http('/admin/users'),
  adminCompanies: () => http('/admin/companies'),
  adminSetActive: (userId, isActive) =>
    http(`/admin/users/${userId}/active`, {
      method: 'PUT', body: JSON.stringify({ is_active: isActive }),
    }),

  /**
   * Stream an SSE response from a POST.
   */
  async *streamAgent(path, payload) {
    const res = await fetch(`${BASE}${path}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...authHeaders() },
      body: JSON.stringify(payload),
    })
    if (res.status === 401) {
      setToken(null)
      window.location.reload()
      throw new Error('Unauthorized')
    }
    if (!res.ok) throw new Error(`${res.status} ${res.statusText}`)
    const reader = res.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''
    while (true) {
      const { value, done } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop()
      for (const line of lines) {
        const trimmed = line.trim()
        if (!trimmed.startsWith('data:')) continue
        const data = trimmed.slice(5).trim()
        if (!data) continue
        try { yield JSON.parse(data) } catch {}
      }
    }
  },
}
