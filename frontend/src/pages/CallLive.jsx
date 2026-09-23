import { useEffect, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { getAgent } from '../api/client'
import { useVoiceCall } from '../hooks/useVoiceCall'
import VoiceOrb from '../components/VoiceOrb'

const STATE_LABELS = {
  idle: 'Idle',
  listening: 'Listening',
  thinking: 'Thinking',
  speaking: 'Speaking',
}

function LatencyBar({ latency }) {
  if (!latency) return <span className="muted small">latency: —</span>
  const { stt_ms, llm_ms, tts_ms, total_ms } = latency
  return (
    <span className="latency-bar small">
      latency · STT <strong>{Math.round(stt_ms ?? 0)}ms</strong> · LLM{' '}
      <strong>{Math.round(llm_ms ?? 0)}ms</strong> · TTS <strong>{Math.round(tts_ms ?? 0)}ms</strong> ·{' '}
      total <strong>{Math.round(total_ms ?? 0)}ms</strong>
    </span>
  )
}

export default function CallLive() {
  const { agentId } = useParams()
  const navigate = useNavigate()
  const [agent, setAgent] = useState(null)
  const [agentError, setAgentError] = useState(null)
  const {
    connected,
    connecting,
    state,
    transcript,
    latency,
    micState,
    muted,
    toggleMute,
    connect,
    disconnect,
    error,
  } = useVoiceCall()
  const transcriptRef = useRef(null)

  // load agent meta
  useEffect(() => {
    let cancelled = false
    getAgent(agentId)
      .then((a) => {
        if (!cancelled) setAgent(a)
      })
      .catch((e) => {
        if (!cancelled) setAgentError(e.message || 'Agent not found')
      })
    return () => {
      cancelled = true
    }
  }, [agentId])

  // connect on mount, disconnect on unmount
  useEffect(() => {
    connect(agentId)
    return () => {
      disconnect()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [agentId])

  // auto-scroll transcript
  useEffect(() => {
    const el = transcriptRef.current
    if (el) el.scrollTop = el.scrollHeight
  }, [transcript])

  const endCall = () => {
    disconnect()
    setTimeout(() => navigate('/calls'), 600)
  }

  const connDot = connected ? 'dot-green' : connecting ? 'dot-amber' : 'dot-red'
  const connLabel = connected ? 'Connected' : connecting ? 'Connecting…' : 'Disconnected'
  const micLabel =
    micState === 'granted' ? 'Mic: allowed' : micState === 'denied' ? 'Mic: denied' : 'Mic: permission needed'

  return (
    <div className="call-live">
      <div className="call-live-top">
        <button className="btn btn-ghost btn-sm" onClick={endCall}>
          ← End & leave
        </button>
        <div className="indicators">
          <span className={`indicator ${micState === 'denied' ? 'bad' : ''}`}>
            <span className={`dot ${micState === 'granted' ? 'dot-green' : micState === 'denied' ? 'dot-red' : 'dot-amber'}`} />
            {micLabel}
          </span>
          <span className="indicator">
            <span className={`dot ${connDot}`} />
            {connLabel}
          </span>
          <LatencyBar latency={latency} />
        </div>
      </div>

      {agentError && <div className="alert alert-error">{agentError}</div>}
      {error && <div className="alert alert-error call-error">{error}</div>}
      {micState === 'denied' && (
        <div className="alert alert-warn">
          Microphone access is denied. Please allow microphone permission in your browser's site
          settings, then reload this page.
        </div>
      )}

      <div className="call-center">
        <VoiceOrb state={connected ? state : 'idle'} size={200} />
        <h2 className="call-agent-name">{agent?.name || 'Loading agent…'}</h2>
        <div className={`state-label state-${state}`}>
          {connecting ? 'Connecting…' : connected ? STATE_LABELS[state] : 'Disconnected'}
        </div>
        {muted && <div className="muted small">You are muted — the agent cannot hear you.</div>}
      </div>

      <div className="call-transcript-wrap">
        <h4>Live transcript</h4>
        <div className="transcript transcript-live" ref={transcriptRef}>
          {transcript.length === 0 && (
            <p className="muted empty small">
              {connected ? 'Say something — your words will appear here.' : 'Waiting for connection…'}
            </p>
          )}
          {transcript.map((t, i) => (
            <div key={i} className={`bubble bubble-${t.role}`}>
              <div className="bubble-head">
                <span className="bubble-role">{t.role === 'assistant' ? 'AI' : 'You'}</span>
                {t.language && <span className="badge badge-gray">{t.language}</span>}
              </div>
              <div className="bubble-text">{t.text}</div>
            </div>
          ))}
        </div>
      </div>

      <div className="call-controls">
        <button
          className={`btn btn-circle ${muted ? 'btn-warn' : 'btn-ghost'}`}
          onClick={toggleMute}
          disabled={!connected}
          title={muted ? 'Unmute' : 'Mute'}
        >
          {muted ? '🔇' : '🎙'}
          <span className="btn-circle-label">{muted ? 'Unmute' : 'Mute'}</span>
        </button>
        <button className="btn btn-danger btn-circle" onClick={endCall} title="End call">
          ✕<span className="btn-circle-label">End</span>
        </button>
      </div>
    </div>
  )
}
