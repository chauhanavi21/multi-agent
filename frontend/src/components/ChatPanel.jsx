import { useEffect, useRef, useState } from 'react'
import AgentBadge from './AgentBadge'
import TaskKanban from './TaskKanban'

const BASE = 'http://localhost:8000/api'

async function* streamSSE(url, body) {
  const res = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`)
  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buf = ''
  while (true) {
    const { value, done } = await reader.read()
    if (done) break
    buf += decoder.decode(value, { stream: true })
    const lines = buf.split('\n')
    buf = lines.pop()
    for (const line of lines) {
      const t = line.trim()
      if (!t.startsWith('data:')) continue
      const data = t.slice(5).trim()
      if (!data) continue
      try { yield JSON.parse(data) } catch {}
    }
  }
}

export default function ChatPanel() {
  const [sessionId, setSessionId] = useState(null)
  const [messages, setMessages] = useState([])
  const [tasks, setTasks] = useState([])
  const [draft, setDraft] = useState('')
  const [streaming, setStreaming] = useState(false)
  const [liveEvents, setLiveEvents] = useState([])
  const scrollRef = useRef(null)

  useEffect(() => {
    // start with a fresh session
    fetch(`${BASE}/chat/sessions`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title: 'New conversation' }),
    })
      .then((r) => r.json())
      .then((s) => setSessionId(s.id))
  }, [])

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight
    }
  }, [messages, liveEvents])

  async function refreshTasks() {
    if (!sessionId) return
    const r = await fetch(`${BASE}/chat/sessions/${sessionId}/tasks`)
    setTasks(await r.json())
  }

  async function send() {
    if (!draft.trim() || streaming || !sessionId) return
    const userMsg = draft.trim()
    setDraft('')
    setMessages((m) => [...m, { role: 'user', content: userMsg }])
    setStreaming(true)
    setLiveEvents([])

    try {
      for await (const ev of streamSSE(`${BASE}/chat/message`, {
        session_id: sessionId,
        message: userMsg,
      })) {
        setLiveEvents((prev) => [...prev, ev])

        if (ev.type === 'manager_reply') {
          setMessages((m) => [...m, { role: 'manager', content: ev.content }])
        }
        // refresh kanban whenever a task changes status
        if (ev.type === 'status' || ev.type === 'plan' || ev.type === 'error') {
          refreshTasks()
        }
      }
      // final refresh
      refreshTasks()
    } catch (e) {
      setMessages((m) => [...m, { role: 'system', content: `Error: ${e.message}` }])
    } finally {
      setStreaming(false)
      // keep last few events visible briefly, then clear
      setTimeout(() => setLiveEvents([]), 1500)
    }
  }

  function onKeyDown(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      send()
    }
  }

  return (
    <div className="chat">
      <div className="chat-header">
        <div className="card-title" style={{ margin: 0 }}>Talk to the team</div>
        <span className="dim">session #{sessionId ?? '...'}</span>
      </div>

      <div className="chat-body" ref={scrollRef}>
        {messages.length === 0 && !streaming && (
          <div className="dim" style={{ padding: 24, textAlign: 'center' }}>
            Try: <em>"Find 3 healthtech leads then draft an outreach for each"</em>
          </div>
        )}

        {messages.map((m, i) => (
          <div key={i} className={`chat-msg chat-msg-${m.role}`}>
            <AgentBadge name={m.role === 'user' ? 'system' : (m.agent_name || 'manager')} />
            <div className="chat-msg-body">
              {m.role === 'user' ? <strong style={{color: 'var(--text)'}}>You</strong> : null}
              {m.role === 'user' && <br />}
              {m.content}
            </div>
          </div>
        ))}

        {streaming && (
          <div className="chat-live">
            <div className="card-title" style={{ marginBottom: 8 }}>Live</div>
            {liveEvents.slice(-8).map((ev, i) => (
              <div key={i} className="chat-live-row">
                <AgentBadge name={ev.agent || 'manager'} />
                <span className="dim chat-live-type">{ev.type}</span>
                <span className="chat-live-content">{renderEv(ev.content)}</span>
              </div>
            ))}
          </div>
        )}

        {tasks.length > 0 && <TaskKanban tasks={tasks} />}
      </div>

      <div className="chat-input">
        <textarea
          value={draft}
          placeholder="Ask the manager..."
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={onKeyDown}
          disabled={streaming || !sessionId}
          rows={2}
        />
        <button onClick={send} disabled={streaming || !draft.trim()} className="primary">
          {streaming ? '...' : 'Send'}
        </button>
      </div>
    </div>
  )
}

function renderEv(c) {
  if (c == null) return ''
  if (typeof c === 'string') return c.slice(0, 100)
  if (typeof c === 'object') {
    if (c.task_key && c.status) return `${c.task_key} → ${c.status}`
    if (c.tasks) return `${c.tasks.length} task(s) planned`
    if (c.subject) return `📧 ${c.subject}`
    if (c.title) return `📄 ${c.title}`
    if (c.findings) return `${c.severity}: ${c.findings.length} finding(s)`
    if (c.summary) return c.summary.slice(0, 80) + '...'
    return JSON.stringify(c).slice(0, 80)
  }
  return String(c)
}
