import { useEffect, useState, useCallback } from 'react'
import { api } from './api/client'
import { useAuth } from './auth/AuthContext'
import LoginScreen from './auth/LoginScreen'
import LeadList from './components/LeadList'
import AgentStream from './components/AgentStream'
import EmailEditor from './components/EmailEditor'
import ChatPanel from './components/ChatPanel'
import TopBar from './components/TopBar'
import TeamRoster from './components/TeamRoster'
import AdminPanel from './components/AdminPanel'
import ObservabilityPanel from './components/ObservabilityPanel'
import MemoryPanel from './components/MemoryPanel'
import DashboardPanel from './components/DashboardPanel'
import CostCard from './components/CostCard'
import LegalFooter from './components/LegalFooter'
import LegalBanner from './components/LegalBanner'
import { SHORT_AI_WARNING } from './legal/legalContent'

export default function App() {
  const { user, loading } = useAuth()
  const [view, setView] = useState('workspace')
  const [billingNotice, setBillingNotice] = useState(null)

  useEffect(() => {
    const params = new URLSearchParams(window.location.search)
    if (params.get('billing') === 'success') {
      setBillingNotice('Payment received. Your plan will update shortly — refresh if needed.')
      window.history.replaceState({}, '', window.location.pathname)
    } else if (params.get('billing') === 'cancel') {
      setBillingNotice('Checkout cancelled. No charge was made.')
      window.history.replaceState({}, '', window.location.pathname)
    }
  }, [])

  if (loading) return <div className="empty" style={{ height: '100vh' }}>Loading...</div>
  if (!user) return <LoginScreen />

  const effectiveView = (user.is_admin && !user.company_id && view === 'workspace') ? 'admin' : view

  let body
  if (effectiveView === 'admin') body = <AdminPanel />
  else if (effectiveView === 'observability') body = <ObservabilityPanel />
  else if (effectiveView === 'memory') body = <MemoryPanel />
  else if (effectiveView === 'dashboard') body = <DashboardPanel />
  else body = <Workspace />

  return (
    <div className="appshell">
      <TopBar view={effectiveView} onChangeView={setView} />
      {billingNotice && (
        <LegalBanner text={billingNotice} variant="info" />
      )}
      <LegalBanner text={SHORT_AI_WARNING} />
      <div className="appshell-body">
        {body}
      </div>
      <LegalFooter />
    </div>
  )
}

function Workspace() {
  const [leads, setLeads] = useState([])
  const [selectedId, setSelectedId] = useState(null)
  const [drafts, setDrafts] = useState([])
  const [events, setEvents] = useState([])
  const [busy, setBusy] = useState(false)
  const [criteria, setCriteria] = useState('Fintech startups in Series A')
  const [history, setHistory] = useState([])
  const [icpResult, setIcpResult] = useState(null)

  const refreshLeads = useCallback(async () => {
    const data = await api.listLeads(); setLeads(data); return data
  }, [])

  const refreshDrafts = useCallback(async (leadId) => {
    if (!leadId) { setDrafts([]); setHistory([]); return }
    const [d, h] = await Promise.all([
      api.listDrafts(leadId),
      api.leadStageHistory(leadId).catch(() => []),
    ])
    setDrafts(d); setHistory(h)
  }, [])

  useEffect(() => { refreshLeads() }, [refreshLeads])
  useEffect(() => {
    refreshDrafts(selectedId); setEvents([]); setIcpResult(null)
  }, [selectedId, refreshDrafts])

  const selectedLead = leads.find((l) => l.id === selectedId)

  async function draftEmail() {
    if (!selectedId || busy) return
    setBusy(true); setEvents([{ type: 'tool', content: 'Starting agent...' }])
    try {
      for await (const ev of api.streamAgent('/agents/sales/draft_email', { lead_id: selectedId })) {
        setEvents((prev) => [...prev, ev])
      }
      await refreshDrafts(selectedId)
    } catch (e) { setEvents((prev) => [...prev, { type: 'error', content: String(e) }]) }
    finally { setBusy(false) }
  }

  async function generateLeads() {
    if (!criteria.trim() || busy) return
    setBusy(true); setEvents([{ type: 'tool', content: `Generating leads for: ${criteria}` }])
    try {
      for await (const ev of api.streamAgent('/agents/sales/generate_leads', { criteria })) {
        setEvents((prev) => [...prev, ev])
      }
      await refreshLeads()
    } catch (e) { setEvents((prev) => [...prev, { type: 'error', content: String(e) }]) }
    finally { setBusy(false) }
  }

  async function qualifyLead() {
    if (!selectedId || busy) return
    setBusy(true); setIcpResult(null)
    try {
      const res = await api.qualifyLead(selectedId)
      setIcpResult(res)
      await refreshLeads()
    } catch (e) {
      setEvents((prev) => [...prev, { type: 'error', content: String(e) }])
    } finally { setBusy(false) }
  }

  async function transitionTo(stage) {
    if (!selectedId || busy) return
    const reason = prompt(`Why moving to ${stage}?`, '') || null
    setBusy(true)
    try {
      await api.transitionStage(selectedId, stage, reason)
      await refreshLeads()
      await refreshDrafts(selectedId)
    } catch (e) {
      setEvents((prev) => [...prev, { type: 'error', content: String(e) }])
    } finally { setBusy(false) }
  }

  async function handleSend(draftId) {
    await api.sendDraft(draftId); await refreshDrafts(selectedId); await refreshLeads()
  }
  async function handleUpdate(draftId, subject, body) {
    await api.updateDraft(draftId, subject, body); await refreshDrafts(selectedId)
  }

  return (
    <div className="app app-phase3">
      <aside className="sidebar">
        <TeamRoster />
        <div className="sidebar-divider" />
        <div className="sidebar-actions">
          <CostCard />
        </div>
        <div className="sidebar-divider" />
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
                <div className="main-title">
                  {selectedLead.name}
                  {selectedLead.icp_score != null && (
                    <span style={{ marginLeft: 8, fontSize: 13,
                                   color: selectedLead.icp_score >= 70 ? '#5cd47e' :
                                          selectedLead.icp_score >= 50 ? '#e0c46c' : '#d96a6a' }}>
                      ICP {selectedLead.icp_score}
                    </span>
                  )}
                </div>
                <div className="main-sub">
                  {selectedLead.title} · {selectedLead.company} · {selectedLead.industry}
                </div>
              </div>
              <div className="row" style={{ gap: 6 }}>
                <button onClick={qualifyLead} disabled={busy}>
                  {busy ? '...' : 'Qualify (ICP)'}
                </button>
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
                  Status: <span className={`status-badge status-${selectedLead.current_stage || selectedLead.status}`}>
                    {selectedLead.current_stage || selectedLead.status}
                  </span>
                  <span style={{ marginLeft: 12 }}>
                    Move to:{' '}
                    {['qualified', 'contacted', 'in_conversation', 'won', 'lost'].map((s) => (
                      <button key={s} onClick={() => transitionTo(s)}
                              disabled={busy}
                              style={{ marginLeft: 4, padding: '2px 8px', fontSize: 11 }}>
                        {s}
                      </button>
                    ))}
                  </span>
                </div>
                {history.length > 0 && (
                  <div className="dim" style={{ marginTop: 10, fontSize: 11.5 }}>
                    History: {history.map((h) =>
                      `${h.from_stage || '∅'}→${h.to_stage}`).join(' · ')}
                  </div>
                )}
              </div>

              {icpResult && (
                <div className="card">
                  <div className="card-title">
                    ICP qualification
                    <span style={{ marginLeft: 8, fontSize: 12,
                                   color: icpResult.score >= 70 ? '#5cd47e' :
                                          icpResult.score >= 50 ? '#e0c46c' : '#d96a6a' }}>
                      {icpResult.score}/100
                    </span>
                  </div>
                  <div style={{ fontSize: 13 }}>{icpResult.rationale}</div>
                  {icpResult.transitioned_to_qualified && (
                    <div style={{ marginTop: 6, fontSize: 12 }}>
                      <span className="pill-ok">Auto-transitioned to <b>qualified</b></span>
                    </div>
                  )}
                </div>
              )}

              {events.length > 0 && <AgentStream events={events} />}
              {drafts.length === 0 ? (
                <div className="dim" style={{ textAlign: 'center', padding: 24 }}>No drafts yet.</div>
              ) : (
                drafts.map((d) => (
                  <EmailEditor key={d.id} draft={d} onSend={handleSend} onUpdate={handleUpdate} />
                ))
              )}
            </div>
          </>
        )}
      </main>

      <ChatPanel />
    </div>
  )
}
