const COLORS = {
  manager: { bg: 'rgba(251, 191, 36, 0.18)', fg: '#ffd069' },
  sales: { bg: 'rgba(74, 222, 128, 0.18)', fg: '#88f0a6' },
  dev_backend: { bg: 'rgba(91, 140, 255, 0.18)', fg: '#a8c2ff' },
  dev_frontend: { bg: 'rgba(124, 92, 255, 0.18)', fg: '#c2b3ff' },
  dev_qa: { bg: 'rgba(232, 89, 60, 0.18)', fg: '#ffa088' },
  social_analyst: { bg: 'rgba(236, 72, 153, 0.18)', fg: '#ffaed4' },
  system: { bg: 'rgba(150, 150, 150, 0.18)', fg: '#c0c0c0' },
}

const LABELS = {
  manager: 'manager',
  sales: 'sales',
  dev_backend: 'dev · backend',
  dev_frontend: 'dev · frontend',
  dev_qa: 'dev · QA',
  social_analyst: 'analyst',
  system: 'system',
}

export default function AgentBadge({ name }) {
  const c = COLORS[name] || COLORS.system
  return (
    <span
      style={{
        background: c.bg,
        color: c.fg,
        fontSize: 10,
        fontWeight: 600,
        textTransform: 'uppercase',
        letterSpacing: '0.06em',
        padding: '2px 7px',
        borderRadius: 4,
        whiteSpace: 'nowrap',
      }}
    >
      {LABELS[name] || name}
    </span>
  )
}
