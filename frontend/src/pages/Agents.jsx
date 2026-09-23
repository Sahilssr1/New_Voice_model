import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { deleteAgent, listAgents } from '../api/client'
import { languageLabel } from '../utils/format'

export default function Agents() {
  const [agents, setAgents] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [deleting, setDeleting] = useState(null)

  const load = async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await listAgents()
      setAgents(Array.isArray(data) ? data : [])
    } catch (e) {
      setError(e.message || 'Failed to load agents')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
  }, [])

  const onDelete = async (agent) => {
    if (!window.confirm(`Delete agent "${agent.name}"? This cannot be undone.`)) return
    setDeleting(agent.id)
    try {
      await deleteAgent(agent.id)
      setAgents((a) => a.filter((x) => x.id !== agent.id))
    } catch (e) {
      alert(`Delete failed: ${e.message}`)
    } finally {
      setDeleting(null)
    }
  }

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <h2>Agents</h2>
          <p className="muted">Create and manage your AI voice agents.</p>
        </div>
        <Link to="/agents/new" className="btn btn-primary">
          + New Agent
        </Link>
      </div>

      {loading && <div className="skeleton-grid">{['a', 'b', 'c'].map((k) => <div key={k} className="skeleton" />)}</div>}
      {error && <div className="alert alert-error">{error}</div>}

      {!loading && !error && agents && (
        agents.length === 0 ? (
          <div className="card empty-state">
            <div className="empty-icon">◈</div>
            <h3>No agents yet</h3>
            <p className="muted">Create your first AI voice agent to start taking calls.</p>
            <Link to="/agents/new" className="btn btn-primary">
              Create agent
            </Link>
          </div>
        ) : (
          <div className="agent-grid">
            {agents.map((agent) => (
              <div key={agent.id} className="card agent-card">
                <div className="agent-card-head">
                  <div className="agent-avatar">{agent.name?.[0]?.toUpperCase() || 'A'}</div>
                  <div>
                    <Link to={`/agents/${agent.id}`} className="agent-name">
                      {agent.name}
                    </Link>
                    <div className="muted small">
                      {languageLabel(agent.language)} · {agent.voice_gender} voice · {agent.tts_provider}
                    </div>
                  </div>
                </div>
                {agent.description && <p className="agent-desc">{agent.description}</p>}
                <div className="agent-card-actions">
                  <Link to={`/calls/live/${agent.id}`} className="btn btn-primary btn-sm">
                    Test Agent
                  </Link>
                  <Link to={`/agents/${agent.id}`} className="btn btn-ghost btn-sm">
                    Details
                  </Link>
                  <button
                    className="btn btn-danger-ghost btn-sm"
                    onClick={() => onDelete(agent)}
                    disabled={deleting === agent.id}
                  >
                    {deleting === agent.id ? 'Deleting…' : 'Delete'}
                  </button>
                </div>
              </div>
            ))}
          </div>
        )
      )}
    </div>
  )
}
