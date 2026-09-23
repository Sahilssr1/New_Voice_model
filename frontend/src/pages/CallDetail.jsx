import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { getCall } from '../api/client'
import { formatDateTime, formatDuration, formatLatency, languageLabel } from '../utils/format'

function LatencyBadge({ latency_ms }) {
  if (latency_ms === null || latency_ms === undefined) return null
  const ms = Math.round(latency_ms)
  const tone = ms < 1500 ? 'green' : ms < 3000 ? 'amber' : 'red'
  return <span className={`badge badge-${tone}`}>{formatLatency(ms)}</span>
}

export default function CallDetail() {
  const { id } = useParams()
  const [call, setCall] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    let cancelled = false
    async function load() {
      setLoading(true)
      setError(null)
      try {
        const data = await getCall(id)
        if (!cancelled) setCall(data)
      } catch (e) {
        if (!cancelled) setError(e.message || 'Failed to load call')
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    load()
    return () => {
      cancelled = true
    }
  }, [id])

  if (loading) return <div className="page"><div className="skeleton-grid">{['a','b'].map(k=><div key={k} className="skeleton"/>)}</div></div>
  if (error) return <div className="page"><div className="alert alert-error">{error}</div><Link to="/calls" className="btn btn-ghost">← Calls</Link></div>
  if (!call) return null

  const messages = call.messages || []
  const events = call.events || []

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <h2>Call detail</h2>
          <p className="muted">
            {call.agent?.name || 'Unknown agent'} ·{' '}
            <span className={`pill pill-${call.status}`}>{call.status}</span> ·{' '}
            {formatDuration(call.duration_sec)} · {formatDateTime(call.started_at)}
            {call.language && (
              <>
                {' '}· <span className="chip chip-sm">{languageLabel(call.language)}</span>
              </>
            )}
            <span className="muted"> · {messages.length} message{messages.length === 1 ? '' : 's'}</span>
          </p>
        </div>
        <Link to="/calls" className="btn btn-ghost">← Calls</Link>
      </div>

      <div className="two-col">
        <div className="card">
          <h3>Transcript</h3>
          {messages.length ? (
            <div className="transcript transcript-static">
              {messages.map((m, i) => (
                <div key={m.id || i} className={`bubble bubble-${m.role}`}>
                  <div className="bubble-head">
                    <span className="bubble-role">{m.role === 'assistant' ? 'AI' : m.role}</span>
                    {m.language && <span className="badge badge-gray">{languageLabel(m.language)}</span>}
                    {m.intent && <span className="badge badge-blue">{m.intent}</span>}
                    <LatencyBadge latency_ms={m.latency_ms} />
                    <span className="muted small ml-auto">{formatDateTime(m.created_at)}</span>
                  </div>
                  <div className="bubble-text">{m.text}</div>
                  {m.entities && Object.keys(m.entities).length > 0 && (
                    <div className="bubble-entities">
                      {Object.entries(m.entities).map(([k, v]) => (
                        <span key={k} className="badge badge-gray">
                          {k}: {String(v)}
                        </span>
                      ))}
                    </div>
                  )}
                </div>
              ))}
            </div>
          ) : (
            <p className="muted empty">No messages recorded for this call.</p>
          )}
          {call.facts && Object.keys(call.facts).length > 0 && (
            <div className="summary-box">
              <h4>Remembered facts</h4>
              <div className="chip-row">
                {Object.entries(call.facts).map(([k, v]) => (
                  <span key={k} className="chip">
                    {k}: {String(v)}
                  </span>
                ))}
              </div>
            </div>
          )}
          {call.summary && (
            <div className="summary-box">
              <h4>Summary</h4>
              <p>{call.summary}</p>
            </div>
          )}
        </div>

        <div className="card">
          <h3>Events timeline</h3>
          {events.length ? (
            <ul className="timeline">
              {events.map((ev, i) => (
                <li key={i} className={`timeline-item timeline-${ev.event_type === 'error' ? 'error' : 'info'}`}>
                  <div className="timeline-dot" />
                  <div className="timeline-body">
                    <div className="timeline-type"><code>{ev.event_type}</code></div>
                    <div className="muted small">{formatDateTime(ev.created_at)}</div>
                    {ev.payload && (
                      <pre className="timeline-payload">
                        {typeof ev.payload === 'string' ? ev.payload : JSON.stringify(ev.payload, null, 2)}
                      </pre>
                    )}
                  </div>
                </li>
              ))}
            </ul>
          ) : (
            <p className="muted empty">No events recorded.</p>
          )}
        </div>
      </div>
    </div>
  )
}
