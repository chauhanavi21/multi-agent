import { useState, useEffect } from 'react'
import { EMAIL_SEND_WARNING } from '../legal/legalContent'

export default function EmailEditor({ draft, onSend, onUpdate }) {
  const [subject, setSubject] = useState(draft.subject)
  const [body, setBody] = useState(draft.body)
  const [dirty, setDirty] = useState(false)
  const [saving, setSaving] = useState(false)
  const [sending, setSending] = useState(false)

  useEffect(() => {
    setSubject(draft.subject)
    setBody(draft.body)
    setDirty(false)
  }, [draft.id, draft.subject, draft.body])

  const isSent = draft.status === 'sent'

  async function save() {
    setSaving(true)
    try {
      await onUpdate(draft.id, subject, body)
      setDirty(false)
    } finally {
      setSaving(false)
    }
  }

  async function send() {
    if (!window.confirm(`${EMAIL_SEND_WARNING}\n\nSend this email now?`)) return
    if (dirty) await save()
    setSending(true)
    try {
      await onSend(draft.id)
    } finally {
      setSending(false)
    }
  }

  return (
    <div className="card">
      <div className="row" style={{ marginBottom: 14 }}>
        <div className="card-title" style={{ margin: 0 }}>
          Draft #{draft.id}
          {isSent && <span style={{ marginLeft: 10, color: 'var(--success)' }}>· sent</span>}
        </div>
        <div className="spacer" />
        <div className="dim">{new Date(draft.created_at).toLocaleString()}</div>
      </div>

      <div className="field">
        <label className="field-label">Subject</label>
        <input
          type="text"
          value={subject}
          disabled={isSent}
          onChange={(e) => { setSubject(e.target.value); setDirty(true) }}
        />
      </div>

      <div className="field">
        <label className="field-label">Body</label>
        <p className="dim" style={{ fontSize: 11, margin: '0 0 6px' }}>
          AI-generated — edit and verify before sending. You accept full responsibility for this message.
        </p>
        <textarea
          value={body}
          disabled={isSent}
          onChange={(e) => { setBody(e.target.value); setDirty(true) }}
        />
      </div>

      {!isSent && (
        <div className="row end gap-sm">
          {dirty && (
            <button onClick={save} disabled={saving}>
              {saving ? 'Saving...' : 'Save changes'}
            </button>
          )}
          <button onClick={send} disabled={sending} className="primary">
            {sending ? 'Sending...' : 'Send'}
          </button>
        </div>
      )}
    </div>
  )
}
