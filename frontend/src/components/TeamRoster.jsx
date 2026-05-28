import { useEffect, useState } from 'react'
import { api } from '../api/client'
import AgentBadge from './AgentBadge'

export default function TeamRoster() {
  const [team, setTeam] = useState([])

  useEffect(() => {
    api.myTeam().then((d) => setTeam(d.team || []))
  }, [])

  if (!team.length) {
    return <div className="dim" style={{ padding: 16 }}>Loading team...</div>
  }

  return (
    <div className="roster">
      <div className="card-title" style={{ padding: '14px 16px 8px' }}>Your team</div>
      {team.map((agent) => (
        <div key={agent.name} className="roster-row">
          <div className="roster-head">
            <AgentBadge name={agent.name} />
            {agent.count > 1 && <span className="dim">x{agent.count}</span>}
          </div>
          <div className="roster-desc">{agent.description}</div>
        </div>
      ))}
      <div className="roster-lock dim">🔒 Org chart locked</div>
    </div>
  )
}
