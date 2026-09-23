import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { getDashboard, getHealth } from '../api/client'
import StatCard from '../components/StatCard'

function StatusDot({ ok }) {
  return <span className={`dot${ok ? ' dot-green' : ' dot-red'}`} />
}

function formatDuration(totalSec) {
  if (!totalSec && totalSec !== 0) return '—'
  const s = Math.round(totalSec)
  const h = Math.floor(s / 3600)
  const m = Math.floor((s % 3600) / 60)
  const sec = s % 60
  if (h > 0) return `${h}h ${m}m`
  if (m > 0) return `${m}m ${sec}s`
  return `${sec}s`
}

function formatTime(iso) {
  if (!iso) return '—'
  try {
    return new Date(iso).toLocaleString()
  } catch {
    return iso
  }
}

export default function Dashboard() {
  const [data, setData] = useState(null)
  const [health, setHealth] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    let cancelled = false
    async function load() {
      setLoading(true)
      setError(null)
      try {
        const [dash, h] = await Promise.all([
          getDashboard(),
          getHealth().catch(() => null),
        ])
        if (!cancelled) {
          setData(dash)
          setHealth(h)
        }
      } catch (e) {
        if (!cancelled) setError(e.message || 'Failed to load dashboard')
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    load()
    return () => {
      cancelled = true
    }
  }, [])

  const services = health?.services || {}
  const serviceNames = Object.keys(services)

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <h2>Dashboard</h2>
          <p className="muted">Overview of your voice agents and calls.</p>
        </div>
        <Link to="/agents/new" className="btn btn-primary">
          + New Agent
        </Link>
      </div>

      {loading && <div className="skeleton-grid">{['a', 'b', 'c', 'd', 'e'].map((k) => <div key={k} className="skeleton" />)}</div>}
      {error && (
        <div className="alert alert-error">
          {error}
          <button className="btn btn-ghost btn-sm" onClick={() => window.location.reload()}>
            Retry
          </button>
        </div>
      )}

      {data && !loading && (
        <>
          <div className="stat-grid">
            <StatCard label="Total Agents" value={data.total_agents ?? 0} icon="◈" />
            <StatCard label="Total Calls" value={data.total_calls ?? 0} icon="◉" />
            <StatCard label="Total Duration" value={formatDuration(data.total_duration_sec)} icon="◷" />
            <StatCard label="Successful" value={data.successful_calls ?? 0} icon="✓" tone="green" />
            <StatCard label="Failed" value={data.failed_calls ?? 0} icon="✕" tone="red" />
          </div>

          <div className="two-col">
            <div className="card">
              <h3>Recent calls</h3>
              {data.recent_calls?.length ? (
                <table className="table">
                  <thead>
                    <tr>
                      <th>Agent</th>
                      <th>Status</th>
                      <th>Duration</th>
                      <th>Started</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.recent_calls.map((c) => (
                      <tr key={c.id}>
                        <td>
                          <Link to={`/calls/${c.id}`}>{c.agent_name || c.agent_id?.slice(0, 8)}</Link>
                        </td>
                        <td>
                          <span className={`pill pill-${c.status}`}>{c.status}</span>
                        </td>
                        <td>{formatDuration(c.duration_sec)}</td>
                        <td className="muted">{formatTime(c.started_at)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              ) : (
                <p className="muted empty">No calls yet. Create an agent and start a live call.</p>
              )}
            </div>

            <div className="card">
              <h3>Languages</h3>
              {data.languages && Object.keys(data.languages).length ? (
                <div className="chip-row">
                  {Object.entries(data.languages).map(([lang, count]) => (
                    <span key={lang} className="chip">
                      {lang} · {count}
                    </span>
                  ))}
                </div>
              ) : (
                <p className="muted empty">No language data yet.</p>
              )}
              <h3 className="mt">Service status</h3>
              {serviceNames.length ? (
                <ul className="status-list">
                  {serviceNames.map((name) => (
                    <li key={name}>
                      <StatusDot ok={!!services[name]} />
                      <span className="status-name">{name}</span>
                      <span className="muted status-detail">
                        {typeof services[name] === 'object' ? services[name].status || '' : ''}
                      </span>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="muted empty">Health data unavailable.</p>
              )}
            </div>
          </div>
        </>
      )}
    </div>
  )
}
