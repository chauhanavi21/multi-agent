import { useEffect, useState, useCallback } from 'react'
import { api } from './api/client'
import LeadList from './components/LeadList'
import AgentStream from './components/AgentStream'
import EmailEditor from './components/EmailEditor'
import ChatPanel from './components/ChatPanel'

export default function App() {
  const [leads, setLeads] = useState([])
  const [selectedId, setSelectedId] = useState(null)
  const [drafts, setDrafts] = useState([])
  const [events, setEvents] = useState([])
  const [busy, setBusy] = useState(false)
  const [criteria, setCriteria] = useState('Fintech startups in Series A')

  const refreshLeads = useCallback(async () => {
    const data = await api.listLeads()
    setLeads(data)
    return data
  }, [])

  const refreshDrafts = useCallback(async (leadId) => {
    if (!leadId) {
      setDrafts([])
      return
    }
    const d = await api.listDrafts(leadId)
    setDrafts(d)
  }, [])

  useEffect(() => { refreshLeads() }, [refreshLeads])
  useEffect(() => {
    refreshDrafts(selectedId)
    setEvents([])
  }, [selectedId, refreshDrafts])

  const selectedLead = leads.find((l) => l.id === selectedId)

  async function draftEmail() {
    if (!selectedId || busy) return
    setBusy(true)
    setEvents([{ type: 'tool', content: 'Starting agent...' }])
    try {
      for await (const ev of api.streamAgent('/agents/sales/draft_email', { lead_id: selectedId })) {
        setEvents((prev) => [...prev, ev])
      }
      await refreshDrafts(selectedId)
    } catch (e) {
      setEvents((prev) => [...prev, { type: 'error', content: String(e) }])
    } finally {
      setBusy(false)
    }
  }

  async function generateLeads() {
    if (!criteria.trim() || busy) return
    setBusy(true)
    setEvents([{ type: 'tool', content: `Generating leads for: ${criteria}` }])
    try {
      for await (const ev of api.streamAgent('/agents/sales/generate_leads', { criteria })) {
        setEvents((prev) => [...prev, ev])
      }
      await refreshLeads()
    } catch (e) {
      setEvents((prev) => [...prev, { type: 'error', content: String(e) }])
    } finally {
      setBusy(false)
    }
  }

  async function handleSend(draftId) {
    await api.sendDraft(draftId)
    await refreshDrafts(selectedId)
    await refreshLeads()
  }

  async function handleUpdate(draftId, subject, body) {
    await api.updateDraft(draftId, subject, body)
    await refreshDrafts(selectedId)
  }

  return (
    <div className="app app-phase2">
      {/* sidebar */}
      <aside className="sidebar">
        <div className="sidebar-header">
          <div className="brand">
            <span className="brand-dot"></span>
            <span>Agent team</span>
          </div>
          <div className="brand-sub">Phase 2 · multi-agent · ollama</div>
        </div>

        <div className="sidebar-actions">
          <input
            type="text"
            placeholder="Criteria for new leads..."
            value={criteria}
            onChange={(e) => setCriteria(e.target.value)}
            disabled={busy}
          />
          <button onClick={generateLeads} disabled={busy || !criteria.trim()}>
            {busy ? 'Working...' : 'Find more leads'}
          </button>
        </div>

        <LeadList leads={leads} selectedId={selectedId} onSelect={setSelectedId} />
      </aside>

      {/* center — lead detail (Phase 1) */}
      <main className="main">
        {!selectedLead ? (
          <div className="empty">
            <div style={{ fontSize: 32 }}>📬</div>
            <div>Pick a lead, or use the chat on the right.</div>
          </div>
        ) : (
          <>
            <div className="main-header">
              <div>
                <div className="main-title">{selectedLead.name}</div>
                <div className="main-sub">
                  {selectedLead.title} · {selectedLead.company} · {selectedLead.industry}
                </div>
              </div>
              <div className="row gap-sm">
                <button onClick={draftEmail} disabled={busy} className="primary">
                  {busy ? 'Drafting...' : 'Draft email'}
                </button>
              </div>
            </div>

            <div className="main-body">
              <div className="card">
                <div className="card-title">Lead notes</div>
                <div className="muted">{selectedLead.notes || '—'}</div>
                <div className="dim" style={{ marginTop: 8 }}>
                  Status: <span className={`status-badge status-${selectedLead.status}`}>
                    {selectedLead.status}
                  </span>
                </div>
              </div>

              {events.length > 0 && <AgentStream events={events} />}

              {drafts.length === 0 ? (
                <div className="dim" style={{ textAlign: 'center', padding: 24 }}>
                  No drafts yet.
                </div>
              ) : (
                drafts.map((d) => (
                  <EmailEditor
                    key={d.id}
                    draft={d}
                    onSend={handleSend}
                    onUpdate={handleUpdate}
                  />
                ))
              )}
            </div>
          </>
        )}
      </main>

      {/* right — chat with manager (Phase 2) */}
      <ChatPanel />
    </div>
  )
}
