const BASE = 'http://localhost:8000/api'
const TOKEN_KEY = 'sa.token'

export function getToken() { return localStorage.getItem(TOKEN_KEY) }
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
    headers: { 'Content-Type': 'application/json', ...authHeaders(), ...(opts.headers || {}) },
    ...opts,
  })
  if (res.status === 401) {
    setToken(null); window.location.reload()
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
  signup: (data) => http('/auth/signup', { method: 'POST', body: JSON.stringify(data) }),
  login: (data) => http('/auth/login', { method: 'POST', body: JSON.stringify(data) }),
  me: () => http('/auth/me'),

  myCompany: () => http('/company/me'),
  myTeam: () => http('/company/team'),

  listLeads: () => http('/leads'),
  getLead: (id) => http(`/leads/${id}`),
  setStatus: (id, status) =>
    http(`/leads/${id}/status`, { method: 'PUT', body: JSON.stringify({ status }) }),
  listDrafts: (leadId) => http(`/leads/${leadId}/drafts`),
  updateDraft: (id, subject, body) =>
    http(`/drafts/${id}`, { method: 'PUT', body: JSON.stringify({ subject, body }) }),
  sendDraft: (id) => http(`/drafts/${id}/send`, { method: 'POST' }),

  createSession: (title) =>
    http('/chat/sessions', { method: 'POST', body: JSON.stringify({ title }) }),
  listSessions: () => http('/chat/sessions'),
  sessionTasks: (id) => http(`/chat/sessions/${id}/tasks`),

  adminUsers: () => http('/admin/users'),
  adminCompanies: () => http('/admin/companies'),
  adminSetActive: (userId, isActive) =>
    http(`/admin/users/${userId}/active`, {
      method: 'PUT', body: JSON.stringify({ is_active: isActive }) }),
  adminSetCloud: (companyId, useCloud) =>
    http(`/admin/companies/${companyId}/cloud`, {
      method: 'PUT', body: JSON.stringify({ use_cloud_api: useCloud }) }),
  adminSetBudget: (companyId, budget) =>
    http(`/admin/companies/${companyId}/budget`, {
      method: 'PUT', body: JSON.stringify({ monthly_budget_usd: budget }) }),
  adminSetProvider: (companyId, provider) =>
    http(`/admin/companies/${companyId}/cloud_provider`, {
      method: 'PUT', body: JSON.stringify({ cloud_provider: provider }) }),

  // ---- Phase 6: Admin (ICP + scheduler toggle) ----
  adminSetIcpProfile: (companyId, icpProfile) =>
    http(`/admin/companies/${companyId}/icp_profile`, {
      method: 'PUT', body: JSON.stringify({ icp_profile: icpProfile }) }),
  adminSetScheduler: (companyId, enabled) =>
    http(`/admin/companies/${companyId}/scheduler`, {
      method: 'PUT', body: JSON.stringify({ enabled }) }),
  adminSetPlan: (companyId, plan) =>
    http(`/admin/companies/${companyId}/plan`, {
      method: 'PUT', body: JSON.stringify({ plan }) }),
  adminPlans: () => http('/admin/plans'),

  // ---- Phase 6: Memory ----
  memoryStats: () => http('/memory/stats'),
  memoryRecent: (limit = 100, kind = null) => {
    const q = new URLSearchParams({ limit: String(limit) })
    if (kind) q.set('kind', kind)
    return http(`/memory/recent?${q.toString()}`)
  },
  memoryRetrieve: (query, k = 10, kinds = null, tags = null, min_score = 0.45) =>
    http('/memory/retrieve', {
      method: 'POST',
      body: JSON.stringify({ query, k, kinds, tags, min_score }),
    }),
  memoryDelete: (id) => http(`/memory/${id}`, { method: 'DELETE' }),
  memorySetImportance: (id, importance) =>
    http(`/memory/${id}/importance`, {
      method: 'PUT', body: JSON.stringify({ importance }) }),

  // ---- Phase 6: Scheduler ----
  schedulerJobs: () => http('/scheduler/jobs'),
  schedulerUpsertJob: (jobName, cronExpr, enabled) =>
    http(`/scheduler/jobs/${jobName}`, {
      method: 'PUT', body: JSON.stringify({ cron_expr: cronExpr, enabled }) }),
  schedulerRunNow: (jobName) =>
    http(`/scheduler/jobs/${jobName}/run_now`, { method: 'POST' }),
  schedulerActive: () => http('/scheduler/active'),

  // ---- Phase 6: Pipeline & content ----
  dailyPlan: (date = null) =>
    http(`/daily_plan${date ? `?plan_date=${date}` : ''}`),
  reelScripts: (limit = 20) => http(`/reel_scripts?limit=${limit}`),
  smsOutbox: (limit = 50) => http(`/sms?limit=${limit}`),
  leadStageHistory: (leadId) => http(`/leads/${leadId}/stage_history`),
  qualifyLead: (leadId) =>
    http(`/agents/sales/qualify_lead/${leadId}`, { method: 'POST' }),
  transitionStage: (leadId, toStage, reason = null) =>
    http(`/agents/sales/transition_stage/${leadId}`, {
      method: 'POST', body: JSON.stringify({ to_stage: toStage, reason }) }),

  costSummary: () => http('/observability/cost/summary'),
  costTimeseries: (days = 14) => http(`/observability/cost/timeseries?days=${days}`),
  recentTraces: (limit = 100) => http(`/observability/traces/recent?limit=${limit}`),
  sessionTraces: (sessionId) => http(`/observability/traces/session/${sessionId}`),
  cacheStats: () => http('/observability/cache/stats'),
  clearCache: () => http('/observability/cache', { method: 'DELETE' }),

  async *streamAgent(path, payload) {
    const res = await fetch(`${BASE}${path}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...authHeaders() },
      body: JSON.stringify(payload),
    })
    if (res.status === 401) { setToken(null); window.location.reload(); throw new Error('Unauthorized') }
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
