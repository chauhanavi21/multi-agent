export default function AgentStream({ events }) {
  return (
    <div className="card">
      <div className="card-title">Agent activity</div>
      <div className="stream">
        {events.map((ev, i) => (
          <div className="stream-event" key={i}>
            <span className={`stream-tag tag-${ev.type}`}>{ev.type}</span>
            <span className="stream-content">{renderContent(ev.content)}</span>
          </div>
        ))}
      </div>
    </div>
  )
}

function renderContent(content) {
  if (content == null) return ''
  if (typeof content === 'string') return content
  if (typeof content === 'object') {
    // Nicer formatting for draft_ready and leads_created payloads
    if (content.subject && content.body) {
      return `📧 ${content.subject}\n\n${content.body}`
    }
    if (Array.isArray(content)) {
      return content.map((c) =>
        c.name ? `• ${c.name} — ${c.title} @ ${c.company}` : JSON.stringify(c)
      ).join('\n')
    }
    return JSON.stringify(content, null, 2)
  }
  return String(content)
}
