import { useEffect, useMemo, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { createAgent, getVoices } from '../api/client'

const LANGUAGES = [
  { value: 'auto', label: 'Auto (detect per turn)' },
  { value: 'en', label: 'English' },
  { value: 'hi', label: 'Hindi' },
  { value: 'hinglish', label: 'Hinglish' },
  { value: 'es', label: 'Spanish' },
  { value: 'fr', label: 'French' },
  { value: 'de', label: 'German' },
  { value: 'pt', label: 'Portuguese' },
  { value: 'it', label: 'Italian' },
  { value: 'ja', label: 'Japanese' },
  { value: 'zh', label: 'Chinese' },
]

export default function AgentForm() {
  const navigate = useNavigate()
  const [form, setForm] = useState({
    name: '',
    description: '',
    system_prompt: 'You are a helpful, friendly AI voice assistant. Speak naturally and concisely, as in a phone call. Keep responses short and conversational.',
    language: 'auto',
    voice_gender: 'female',
    voice_id: '',
    tts_provider: 'piper',
    llm_model: '',
    temperature: 0.7,
    greeting: 'Hello! How can I help you today?',
    max_duration_sec: 600,
    silence_timeout_sec: 12,
  })
  const [voices, setVoices] = useState([])
  const [voicesLoading, setVoicesLoading] = useState(false)
  const [voicesError, setVoicesError] = useState(null)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState(null)

  const set = (key) => (e) => {
    const v = e.target.type === 'number' ? Number(e.target.value) : e.target.value
    setForm((f) => ({ ...f, [key]: v }))
  }

  // Load voices filtered by gender + language (auto -> no language filter)
  useEffect(() => {
    let cancelled = false
    async function loadVoices() {
      setVoicesLoading(true)
      setVoicesError(null)
      try {
        const params = {
          provider: form.tts_provider,
          gender: form.voice_gender,
        }
        if (form.language !== 'auto') params.language = form.language
        const data = await getVoices(params)
        if (cancelled) return
        const list = Array.isArray(data) ? data : []
        setVoices(list)
        setForm((f) => ({
          ...f,
          voice_id: list.some((v) => v.voice_id === f.voice_id) ? f.voice_id : list[0]?.voice_id || '',
        }))
      } catch (e) {
        if (!cancelled) {
          setVoicesError(e.message || 'Could not load voices')
          setVoices([])
        }
      } finally {
        if (!cancelled) setVoicesLoading(false)
      }
    }
    loadVoices()
    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [form.tts_provider, form.voice_gender, form.language])

  const voiceById = useMemo(() => {
    const map = {}
    for (const v of voices) map[v.voice_id] = v
    return map
  }, [voices])

  const submit = async (e) => {
    e.preventDefault()
    setSaving(true)
    setError(null)
    try {
      const payload = {
        name: form.name.trim(),
        description: form.description.trim() || undefined,
        system_prompt: form.system_prompt,
        language: form.language,
        voice_gender: form.voice_gender,
        voice_id: form.voice_id,
        tts_provider: form.tts_provider,
        llm_model: form.llm_model.trim() || undefined,
        temperature: Number(form.temperature),
        greeting: form.greeting,
        max_duration_sec: Number(form.max_duration_sec),
        silence_timeout_sec: Number(form.silence_timeout_sec),
      }
      const agent = await createAgent(payload)
      navigate(`/agents/${agent.id}`)
    } catch (err) {
      setError(err.message || 'Failed to create agent')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <h2>New Agent</h2>
          <p className="muted">Configure personality, voice, and call behavior.</p>
        </div>
        <Link to="/agents" className="btn btn-ghost">
          ← Back
        </Link>
      </div>

      <form onSubmit={submit} className="form card form-card">
        <div className="form-grid">
          <label className="field">
            <span>Agent name *</span>
            <input type="text" value={form.name} onChange={set('name')} required placeholder="e.g. Support Agent" maxLength={120} />
          </label>
          <label className="field">
            <span>Language</span>
            <select value={form.language} onChange={set('language')}>
              {LANGUAGES.map((l) => (
                <option key={l.value} value={l.value}>
                  {l.label}
                </option>
              ))}
            </select>
          </label>
        </div>

        <label className="field">
          <span>Description</span>
          <input type="text" value={form.description} onChange={set('description')} placeholder="What is this agent for?" maxLength={500} />
        </label>

        <label className="field">
          <span>System prompt *</span>
          <textarea
            value={form.system_prompt}
            onChange={set('system_prompt')}
            required
            rows={6}
            placeholder="You are a professional customer support representative..."
          />
        </label>

        <div className="form-grid">
          <label className="field">
            <span>Voice gender</span>
            <select value={form.voice_gender} onChange={set('voice_gender')}>
              <option value="female">Female</option>
              <option value="male">Male</option>
            </select>
          </label>
          <label className="field">
            <span>TTS provider</span>
            <select value={form.tts_provider} onChange={set('tts_provider')}>
              <option value="piper">Piper</option>
            </select>
          </label>
        </div>

        <label className="field">
          <span>Voice *</span>
          <select value={form.voice_id} onChange={set('voice_id')} required disabled={voicesLoading || voices.length === 0}>
            {voicesLoading && <option>Loading voices…</option>}
            {!voicesLoading && voices.length === 0 && <option value="">No voices available</option>}
            {voices.map((v) => (
              <option key={v.voice_id} value={v.voice_id}>
                {v.name} ({v.language}, {v.gender})
              </option>
            ))}
          </select>
          {form.voice_id && voiceById[form.voice_id] && (
            <small className="muted">
              Selected: {voiceById[form.voice_id].name} · {voiceById[form.voice_id].sample_rate} Hz ·{' '}
              {voiceById[form.voice_id].provider}
            </small>
          )}
          {voicesError && <small className="field-error">{voicesError}</small>}
        </label>

        <div className="form-grid">
          <label className="field">
            <span>LLM model</span>
            <input
              type="text"
              value={form.llm_model}
              onChange={set('llm_model')}
              placeholder="Default (e.g. qwen2.5:1.5b)"
            />
          </label>
          <label className="field">
            <span>
              Temperature <strong>{Number(form.temperature).toFixed(2)}</strong>
            </span>
            <input type="range" min={0} max={2} step={0.05} value={form.temperature} onChange={set('temperature')} />
          </label>
        </div>

        <label className="field">
          <span>Greeting</span>
          <input type="text" value={form.greeting} onChange={set('greeting')} placeholder="First thing the agent says" maxLength={500} />
        </label>

        <div className="form-grid">
          <label className="field">
            <span>Max conversation duration (sec)</span>
            <input type="number" min={30} max={7200} value={form.max_duration_sec} onChange={set('max_duration_sec')} />
          </label>
          <label className="field">
            <span>Silence timeout (sec)</span>
            <input type="number" min={3} max={120} value={form.silence_timeout_sec} onChange={set('silence_timeout_sec')} />
          </label>
        </div>

        {error && <div className="alert alert-error">{error}</div>}

        <div className="form-actions">
          <Link to="/agents" className="btn btn-ghost">
            Cancel
          </Link>
          <button type="submit" className="btn btn-primary" disabled={saving || !form.voice_id}>
            {saving ? 'Creating…' : 'Create agent'}
          </button>
        </div>
      </form>
    </div>
  )
}
