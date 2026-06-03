import AgentBadge from './AgentBadge'

export default function TraceTree({ spans, compact = false }) {
  if (!spans?.length) {
    return <div className="dim" style={{ padding: 16, textAlign: 'center' }}>No traces yet</div>
  }

  // Build tree by parent_span_id
  const byId = new Map(spans.map((s) => [s.id, { ...s, children: [] }]))
  const roots = []
  for (const span of byId.values()) {
    if (span.parent_span_id && byId.has(span.parent_span_id)) {
      byId.get(span.parent_span_id).children.push(span)
    } else {
      roots.push(span)
    }
  }

  return (
    <div className="trace-tree">
      {roots.map((s) => <SpanNode key={s.id} span={s} depth={0} compact={compact} />)}
    </div>
  )
}

function SpanNode({ span, depth, compact }) {
  const isCloud = span.model && (span.model.includes('claude'))
  const isCache = span.was_cache_hit
  const status = span.status

  return (
    <div className="trace-node" style={{ marginLeft: depth * 16 }}>
      <div className="trace-row">
        <AgentBadge name={span.agent_name || 'manager'} />
        <span className="trace-kind">{span.kind}</span>
        <span className={`trace-model ${isCloud ? 'cloud' : 'local'}`}>
          {span.model || '—'}
        </span>
        {isCache && <span className="trace-tag-cache">cache</span>}
        {!isCache && (
          <span className="trace-tokens">{span.input_tokens + span.output_tokens} tok</span>
        )}
        <span className="trace-cost">${span.cost_usd.toFixed(6)}</span>
        <span className="trace-latency">{span.latency_ms}ms</span>
        <span className={`trace-status status-${status}`}>{status}</span>
      </div>
      {!compact && span.input_preview && (
        <div className="trace-preview">{span.input_preview}</div>
      )}
      {span.error && <div className="trace-error">{span.error}</div>}
      {span.children?.length > 0 && (
        <div>{span.children.map((c) => <SpanNode key={c.id} span={c} depth={depth + 1} compact={compact} />)}</div>
      )}
    </div>
  )
}
