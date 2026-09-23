import { useEffect, useState } from 'react'
import { getAiHealth, getServiceHealth } from '../api/client'

const SERVICE_LABELS = {
  stt: 'Speech-to-Text',
  tts: 'Text-to-Speech',
  llm: 'Language Model',
  vad: 'Voice Activity Detection',
}

function ServiceCard({ name, info, onTest, testing, result }) {
  // Provider health dicts report status as "up" | "down" | "degraded".
  const status = info?.status || 'unknown'
  const ok = status === 'up'
  const warn = status === 'degraded'
  const dotCls = ok ? 'dot-green' : warn ? 'dot-amber' : 'dot-red'
  const pillCls = ok ? 'pill-ok' : warn ? 'pill-in_progress' : 'pill-failed'
  const pillLabel = ok ? 'healthy' : warn ? 'degraded' : 'unhealthy'
  return (
    <div className="card service-card">
      <div className="service-head">
        <div>
          <h3>{SERVICE_LABELS[name] || name}</h3>
          <div className="muted small">{info?.model || info?.provider || info?.name || ''}</div>
        </div>
        <span className={`dot ${dotCls}`} title={String(status)} />
      </div>
      <div className="service-meta">
        <span className={`pill ${pillCls}`}>{pillLabel}</span>
        {info?.detail && <span className="muted small">{info.detail}</span>}
      </div>
      {info?.latency_ms !== undefined && (
        <div className="muted small">latency: {Math.round(info.latency_ms)} ms</div>
      )}
      <div className="mt">
        <button className="btn btn-ghost btn-sm" onClick={() => onTest(name)} disabled={testing}>
          {testing ? 'Testing…' : 'Test service'}
        </button>
      </div>
      {result && (
        <pre className={`test-result ${result.ok ? 'ok' : 'fail'}`}>
          {JSON.stringify(result.data, null, 2)}
        </pre>
      )}
    </div>
  )
}

export default function Settings() {
  const [ai, setAi] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [testing, setTesting] = useState(null)
  const [results, setResults] = useState({})

  const load = async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await getAiHealth()
      setAi(data)
    } catch (e) {
      setError(e.message || 'Failed to load AI health')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
  }, [])

  const testService = async (name) => {
    setTesting(name)
    try {
      const data = await getServiceHealth(name)
      setResults((r) => ({ ...r, [name]: { ok: true, data } }))
    } catch (e) {
      setResults((r) => ({ ...r, [name]: { ok: false, data: { error: e.message } } }))
    } finally {
      setTesting(null)
    }
  }

  const services = ai ? Object.keys(ai).filter((k) => k !== 'status') : []

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <h2>Settings</h2>
          <p className="muted">AI service status and configuration.</p>
        </div>
        <button className="btn btn-ghost" onClick={load} disabled={loading}>
          ⟳ Refresh
        </button>
      </div>

      {loading && <div className="skeleton-grid">{['a','b','c','d'].map(k=><div key={k} className="skeleton"/>)}</div>}
      {error && <div className="alert alert-error">{error}</div>}

      {!loading && !error && ai && (
        <>
          <div className="service-grid">
            {services.map((name) => (
              <ServiceCard
                key={name}
                name={name}
                info={ai[name]}
                onTest={testService}
                testing={testing === name}
                result={results[name]}
              />
            ))}
          </div>
          <div className="card mt">
            <h3>Configuration</h3>
            <div className="detail-grid">
              <div className="detail-field">
                <div className="detail-label">LLM model</div>
                <div className="detail-value"><code>{ai.llm?.model || '—'}</code></div>
              </div>
              <div className="detail-field">
                <div className="detail-label">Whisper model</div>
                <div className="detail-value"><code>{ai.stt?.model || '—'}</code></div>
              </div>
              <div className="detail-field">
                <div className="detail-label">STT provider</div>
                <div className="detail-value"><code>{ai.stt?.provider || ai.stt?.name || '—'}</code></div>
              </div>
              <div className="detail-field">
                <div className="detail-label">TTS provider</div>
                <div className="detail-value"><code>{ai.tts?.provider || ai.tts?.name || '—'}</code></div>
              </div>
              <div className="detail-field">
                <div className="detail-label">VAD provider</div>
                <div className="detail-value"><code>{ai.vad?.provider || ai.vad?.name || '—'}</code></div>
              </div>
            </div>
            <p className="muted small mt">
              Values come from <code>GET /health/ai</code>. Backend defaults: LLM{' '}
              <code>qwen2.5:1.5b</code> via Ollama, Whisper <code>base</code> on CPU, Piper TTS.
            </p>
          </div>
        </>
      )}
    </div>
  )
}
