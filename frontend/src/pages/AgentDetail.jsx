import { useCallback, useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { attachTool, deleteAgent, detachTool, getAgent, listTools } from '../api/client'
import { formatDateTime, languageLabel } from '../utils/format'
import KnowledgeBase from '../components/KnowledgeBase'

function Field({ label, value }) {
  return (
    <div className="detail-field">
      <div className="detail-label">{label}</div>
      <div className="detail-value">{value ?? <span className="muted">—</span>}</div>
    </div>
  )
}

export default function AgentDetail() {
  const { id } = useParams()
  const navigate = useNavigate()
  const [agent, setAgent] = useState(null)
  const [tools, setTools] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [toolBusy, setToolBusy] = useState(null)
  const [deleting, setDeleting] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [a, t] = await Promise.all([getAgent(id), listTools().catch(() => [])])
      setAgent(a)
      setTools(Array.isArray(t) ? t : [])
    } catch (e) {
      setError(e.message || 'Failed to load agent')
    } finally {
      setLoading(false)
    }
  }, [id])

  useEffect(() => {
    load()
  }, [load])

  const attachedIds = new Set((agent?.tools || []).map((t) => t.id ?? t.tool_id ?? t))
  const availableTools = tools.filter((t) => !attachedIds.has(t.id))

  const onAttach = async (toolId) => {
    setToolBusy(toolId)
    try {
      await attachTool(id, toolId)
      await load()
    } catch (e) {
      alert(`Attach failed: ${e.message}`)
    } finally {
      setToolBusy(null)
    }
  }

  const onDetach = async (toolId) => {
    setToolBusy(toolId)
    try {
      await detachTool(id, toolId)
      await load()
    } catch (e) {
      alert(`Detach failed: ${e.message}`)
    } finally {
      setToolBusy(null)
    }
  }

  const onDelete = async () => {
    if (!window.confirm(`Delete agent "${agent.name}"? This cannot be undone.`)) return
    setDeleting(true)
    try {
      await deleteAgent(id)
      navigate('/agents')
    } catch (e) {
      alert(`Delete failed: ${e.message}`)
      setDeleting(false)
    }
  }

  if (loading) return <div className="page"><div className="skeleton-grid">{['a','b'].map(k=><div key={k} className="skeleton"/>)}</div></div>
  if (error) return <div className="page"><div className="alert alert-error">{error}</div><Link to="/agents" className="btn btn-ghost">← Agents</Link></div>
  if (!agent) return null

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <h2>{agent.name}</h2>
          <p className="muted">{agent.description || 'No description'}</p>
        </div>
        <div className="btn-row">
          <Link to={`/calls/live/${agent.id}`} className="btn btn-primary btn-lg">
            ▶ Test Agent
          </Link>
          <Link to="/agents" className="btn btn-ghost">
            ← Back
          </Link>
        </div>
      </div>

      <div className="two-col">
        <div className="card">
          <h3>Configuration</h3>
          <div className="detail-grid">
            <Field label="Language" value={<span className="chip">{languageLabel(agent.language)}</span>} />
            <Field label="Voice gender" value={agent.voice_gender} />
            <Field label="Voice ID" value={<code>{agent.voice_id}</code>} />
            <Field label="TTS provider" value={agent.tts_provider} />
            <Field label="LLM model" value={<code>{agent.llm_model || 'default'}</code>} />
            <Field label="Temperature" value={agent.temperature} />
            <Field label="Max duration" value={`${agent.max_duration_sec}s`} />
            <Field label="Silence timeout" value={`${agent.silence_timeout_sec}s`} />
          </div>
          <div className="detail-field">
            <div className="detail-label">Greeting</div>
            <div className="detail-value quote">{agent.greeting || <span className="muted">—</span>}</div>
          </div>
          <div className="detail-field">
            <div className="detail-label">System prompt</div>
            <pre className="prompt-box">{agent.system_prompt}</pre>
          </div>
          <div className="muted small">
            Created {formatDateTime(agent.created_at)}
            {agent.updated_at ? ` · Updated ${formatDateTime(agent.updated_at)}` : ''}
          </div>
          <div className="mt">
            <button className="btn btn-danger-ghost btn-sm" onClick={onDelete} disabled={deleting}>
              {deleting ? 'Deleting…' : 'Delete agent'}
            </button>
          </div>
        </div>

        <div className="card">
          <h3>Attached tools</h3>
          {agent.tools?.length ? (
            <ul className="tool-list">
              {agent.tools.map((t) => {
                const tid = t.id ?? t.tool_id
                return (
                  <li key={tid} className="tool-item">
                    <div>
                      <div className="tool-name">{t.name || tid}</div>
                      {t.description && <div className="muted small">{t.description}</div>}
                    </div>
                    <button
                      className="btn btn-ghost btn-sm"
                      onClick={() => onDetach(tid)}
                      disabled={toolBusy === tid}
                    >
                      {toolBusy === tid ? '…' : 'Detach'}
                    </button>
                  </li>
                )
              })}
            </ul>
          ) : (
            <p className="muted empty">No tools attached.</p>
          )}

          <h3 className="mt">Available tools</h3>
          {availableTools.length ? (
            <ul className="tool-list">
              {availableTools.map((t) => (
                <li key={t.id} className="tool-item">
                  <div>
                    <div className="tool-name">
                      {t.name}
                      {t.is_builtin && <span className="chip chip-sm ml">builtin</span>}
                    </div>
                    {t.description && <div className="muted small">{t.description}</div>}
                  </div>
                  <button
                    className="btn btn-primary btn-sm"
                    onClick={() => onAttach(t.id)}
                    disabled={toolBusy === t.id}
                  >
                    {toolBusy === t.id ? '…' : 'Attach'}
                  </button>
                </li>
              ))}
            </ul>
          ) : (
            <p className="muted empty">No more tools available.</p>
          )}
        </div>
      </div>

      <KnowledgeBase agentId={id} />
    </div>
  )
}
