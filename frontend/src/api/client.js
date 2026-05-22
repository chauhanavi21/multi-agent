const BASE = 'http://localhost:8000/api'

async function http(path, opts = {}) {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...opts,
  })
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`)
  return res.status === 204 ? null : res.json()
}

export const api = {
  listLeads: () => http('/leads'),
  getLead: (id) => http(`/leads/${id}`),
  setStatus: (id, status) =>
    http(`/leads/${id}/status`, { method: 'PUT', body: JSON.stringify({ status }) }),

  listDrafts: (leadId) => http(`/leads/${leadId}/drafts`),
  updateDraft: (id, subject, body) =>
    http(`/drafts/${id}`, { method: 'PUT', body: JSON.stringify({ subject, body }) }),
  sendDraft: (id) => http(`/drafts/${id}/send`, { method: 'POST' }),

  /**
   * Stream an SSE response from a POST. Yields parsed JSON events.
   */
  async *streamAgent(path, payload) {
    const res = await fetch(`${BASE}${path}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    })
    if (!res.ok) throw new Error(`${res.status} ${res.statusText}`)

    const reader = res.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''

    while (true) {
      const { value, done } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })

      // SSE events are separated by blank line; each line starts with "data: "
      const lines = buffer.split('\n')
      buffer = lines.pop() // keep partial
      for (const line of lines) {
        const trimmed = line.trim()
        if (!trimmed.startsWith('data:')) continue
        const data = trimmed.slice(5).trim()
        if (!data) continue
        try {
          yield JSON.parse(data)
        } catch {
          // ignore malformed
        }
      }
    }
  },
}
