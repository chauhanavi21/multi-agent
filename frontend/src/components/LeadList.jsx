export default function LeadList({ leads, selectedId, onSelect }) {
  if (!leads.length) {
    return <div className="dim" style={{ padding: 16, textAlign: 'center' }}>No leads yet</div>
  }
  return (
    <div className="lead-list">
      {leads.map((lead) => (
        <div
          key={lead.id}
          className={`lead-card ${lead.id === selectedId ? 'active' : ''}`}
          onClick={() => onSelect(lead.id)}
        >
          <div className="lead-name">{lead.name}</div>
          <div className="lead-title">{lead.title}</div>
          <div className="lead-company">{lead.company}</div>
          <span className={`status-badge status-${lead.status}`}>{lead.status}</span>
        </div>
      ))}
    </div>
  )
}
