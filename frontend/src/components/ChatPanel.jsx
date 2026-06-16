import { useEffect, useRef, useState } from 'react'
import { api } from '../api/client'
import AgentBadge from './AgentBadge'
import TaskKanban from './TaskKanban'
import LegalBanner from './LegalBanner'
import { CHAT_BANNER } from '../legal/legalContent'

export default function ChatPanel() {
  const [sessionId, setSessionId] = useState(null)
  const [messages, setMessages] = useState([])
  const [tasks, setTasks] = useState([])
  const [draft, setDraft] = useState('')
  const [streaming, setStreaming] = useState(false)
  const [liveEvents, setLiveEvents] = useState([])
  const [sessionErr, setSessionErr] = useState(null)
  const scrollRef = useRef(null)

  useEffect(() => {
    let alive = true
    api.createSession('New conversation')
      .then((s) => { if (alive) setSessionId(s.id) })
      .catch((e) => { if (alive) setSessionErr(e.message) })
    return () => { alive = false }
  }, [])

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight
    }
  }, [messages, liveEvents])

  async function refreshTasks() {
    if (!sessionId) return
    try {
      setTasks(await api.sessionTasks(sessionId))
    } catch { /* ignore */ }
  }

  async function send() {
    if (!draft.trim() || streaming || !sessionId) return
    const userMsg = draft.trim()
    setDraft('')
    setMessages((m) => [...m, { role: 'user', content: userMsg }])
    setStreaming(true)
    setLiveEvents([])

    try {
      for await (const ev of api.streamChat(sessionId, userMsg)) {
        setLiveEvents((prev) => [...prev, ev])

        if (ev.type === 'manager_reply') {
          const meta = ev._router
          let suffix = ''
          if (meta?.was_plan_limited || meta?.was_downgraded) {
            suffix = ' (local AI — upgrade for premium)'
          } else if (meta?.model && !meta.model.includes('llama') && !meta.model.includes('phi3')) {
            suffix = ' (premium)'
          }
          setMessages((m) => [...m, {
            role: 'manager',
            content: ev.content,
            meta: suffix,
          }])
        }
        if (ev.type === 'status' || ev.type === 'plan' || ev.type === 'error') {
          refreshTasks()
        }
      }
      refreshTasks()
    } catch (e) {
      setMessages((m) => [...m, { role: 'system', content: `Error: ${e.message}` }])
    } finally {
      setStreaming(false)
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
      <LegalBanner text={CHAT_BANNER} />
      <div className="chat-header">
        <div className="card-title" style={{ margin: 0 }}>Talk to the team</div>
        <span className="dim">session #{sessionId ?? '...'}</span>
      </div>

      {sessionErr && (
        <div className="login-err" style={{ margin: '8px 12px' }}>{sessionErr}</div>
      )}

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
              {m.meta && <span className="dim" style={{ fontSize: 11, marginLeft: 6 }}>{m.meta}</span>}
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
        <button onClick={send} disabled={streaming || !draft.trim() || !sessionId} className="primary">
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
