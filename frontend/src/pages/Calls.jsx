import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { deleteCall, listCalls } from '../api/client'

function formatDuration(totalSec) {
  if (totalSec === null || totalSec === undefined) return '—'
  const s = Math.round(totalSec)
  const m = Math.floor(s / 60)
  const sec = s % 60
  return m > 0 ? `${m}m ${sec}s` : `${sec}s`
}

function formatTime(iso) {
  if (!iso) return '—'
  try {
    return new Date(iso).toLocaleString()
  } catch {
    return iso
  }
}

export default function Calls() {
  const [calls, setCalls] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [deleting, setDeleting] = useState(null)

  const load = async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await listCalls()
      setCalls(Array.isArray(data) ? data : [])
    } catch (e) {
      setError(e.message || 'Failed to load calls')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
  }, [])

  const onDelete = async (call) => {
    if (!window.confirm('Delete this call and its transcript?')) return
    setDeleting(call.id)
    try {
      await deleteCall(call.id)
      setCalls((c) => c.filter((x) => x.id !== call.id))
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
          <h2>Calls</h2>
          <p className="muted">Conversation history across all agents.</p>
        </div>
      </div>

      {loading && <div className="skeleton-grid">{['a','b','c'].map(k=><div key={k} className="skeleton"/>)}</div>}
      {error && <div className="alert alert-error">{error}</div>}

      {!loading && !error && calls && (
        calls.length === 0 ? (
          <div className="card empty-state">
            <div className="empty-icon">◉</div>
            <h3>No calls yet</h3>
            <p className="muted">Start a live call from any agent to see it here.</p>
            <Link to="/agents" className="btn btn-primary">Go to agents</Link>
          </div>
        ) : (
          <div className="card table-card">
            <table className="table">
              <thead>
                <tr>
                  <th>Agent</th>
                  <th>Status</th>
                  <th>Duration</th>
                  <th>Language</th>
                  <th>Messages</th>
                  <th>Started</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {calls.map((c) => (
                  <tr key={c.id}>
                    <td>
                      <Link to={`/calls/${c.id}`}>{c.agent_name || c.agent_id?.slice(0, 8) || '—'}</Link>
                    </td>
                    <td><span className={`pill pill-${c.status}`}>{c.status}</span></td>
                    <td>{formatDuration(c.duration_sec)}</td>
                    <td>{c.language ? <span className="chip chip-sm">{c.language}</span> : '—'}</td>
                    <td>{c.message_count ?? '—'}</td>
                    <td className="muted">{formatTime(c.started_at)}</td>
                    <td>
                      <button
                        className="btn btn-danger-ghost btn-sm"
                        onClick={() => onDelete(c)}
                        disabled={deleting === c.id}
                      >
                        {deleting === c.id ? '…' : 'Delete'}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )
      )}
    </div>
  )
}
