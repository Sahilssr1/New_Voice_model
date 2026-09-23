import { useCallback, useEffect, useRef, useState } from 'react'
import { api, getToken } from '../api/client'

// Inline AudioWorklet processor: captures mono mic audio and posts Float32 chunks.
const MIC_PROCESSOR_CODE = `
class MicProcessor extends AudioWorkletProcessor {
  process(inputs) {
    const input = inputs[0];
    if (input && input.length > 0 && input[0] && input[0].length > 0) {
      this.port.postMessage(input[0].slice(0));
    }
    return true;
  }
}
registerProcessor('mic-processor', MicProcessor);
`

const TARGET_SAMPLE_RATE = 16000 // contract: mic capture at 16000 Hz int16 LE
const SEND_CHUNK_SAMPLES = 2048 // ~128ms per frame at 16kHz

function floatTo16BitPCM(float32) {
  const out = new Int16Array(float32.length)
  for (let i = 0; i < float32.length; i++) {
    const s = Math.max(-1, Math.min(1, float32[i]))
    out[i] = s < 0 ? s * 0x8000 : s * 0x7fff
  }
  return out
}

function int16ToBase64(int16) {
  const bytes = new Uint8Array(int16.buffer, int16.byteOffset, int16.byteLength)
  let binary = ''
  const CHUNK = 0x8000
  for (let i = 0; i < bytes.length; i += CHUNK) {
    binary += String.fromCharCode.apply(null, bytes.subarray(i, i + CHUNK))
  }
  return btoa(binary)
}

function base64ToBytes(b64) {
  const binary = atob(b64)
  const bytes = new Uint8Array(binary.length)
  for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i)
  return bytes
}

// Linear resample from `fromRate` to TARGET_SAMPLE_RATE.
function resampleLinear(input, fromRate) {
  if (fromRate === TARGET_SAMPLE_RATE) return input
  const ratio = fromRate / TARGET_SAMPLE_RATE
  const outLen = Math.floor(input.length / ratio)
  const out = new Float32Array(outLen)
  for (let i = 0; i < outLen; i++) {
    const pos = i * ratio
    const idx = Math.floor(pos)
    const frac = pos - idx
    const a = input[idx] || 0
    const b = input[idx + 1] || 0
    out[i] = a + (b - a) * frac
  }
  return out
}

/**
 * Realtime voice-call hook.
 * Manages: WebSocket -> /ws/voice, mic capture via AudioWorklet (16kHz int16),
 * TTS playback queue (22050Hz PCM16LE), barge-in interrupt, latency + transcript state.
 */
export function useVoiceCall() {
  const [connected, setConnected] = useState(false)
  const [connecting, setConnecting] = useState(false)
  const [state, setState] = useState('idle') // idle | listening | thinking | speaking
  const [transcript, setTranscript] = useState([]) // [{role,text,language,turn}]
  const [latency, setLatency] = useState(null) // {stt_ms,llm_ms,tts_ms,total_ms,turn}
  const [micState, setMicState] = useState('prompt') // granted | denied | prompt
  const [muted, setMuted] = useState(false)
  const [error, setError] = useState(null)
  const [callInfo, setCallInfo] = useState(null) // {call_id, agent} from call_started
  const [stats, setStats] = useState(null) // call_ended payload

  const wsRef = useRef(null)
  const seqRef = useRef(0)
  const callActiveRef = useRef(false)
  const manualCloseRef = useRef(false)
  const mutedRef = useRef(false)
  const pingTimerRef = useRef(null)
  const disconnectTimerRef = useRef(null)
  const connectionIdRef = useRef(0)

  // mic refs
  const micStreamRef = useRef(null)
  const micCtxRef = useRef(null)
  const micNodeRef = useRef(null)
  const resampleBufRef = useRef(new Float32Array(0))
  // Generation counter for the mic lifecycle. Every startMic() captures the
  // current generation; any stopMic()/cleanup() bumps it, which makes an
  // in-flight (stale) startMic() abort at its next checkpoint instead of
  // completing and then tearing down the NEW connection's AudioContext.
  // (Without this, React StrictMode's double-mount — or any rapid
  // reconnect — lets the stale connect's stopMic() close the fresh
  // AudioContext mid-addModule, surfacing as
  // "Unable to load a worklet's module".)
  const micGenRef = useRef(0)

  // playback refs
  const playCtxRef = useRef(null)
  const nextPlayTimeRef = useRef(0)
  const activeSourcesRef = useRef(new Set())

  // ---- playback ----
  const ensurePlayCtx = useCallback(() => {
    if (!playCtxRef.current) {
      const AC = window.AudioContext || window.webkitAudioContext
      playCtxRef.current = new AC({ sampleRate: 22050 })
      nextPlayTimeRef.current = 0
    }
    if (playCtxRef.current.state === 'suspended') {
      playCtxRef.current.resume().catch(() => {})
    }
    return playCtxRef.current
  }, [])

  const enqueueAudio = useCallback(
    (base64Data, sampleRate) => {
      try {
        const ctx = ensurePlayCtx()
        const bytes = base64ToBytes(base64Data)
        if (bytes.length < 2) return
        const int16 = new Int16Array(bytes.buffer, bytes.byteOffset, Math.floor(bytes.byteLength / 2))
        const float32 = new Float32Array(int16.length)
        for (let i = 0; i < int16.length; i++) float32[i] = int16[i] / 32768
        const sr = sampleRate || 22050
        const buffer = ctx.createBuffer(1, float32.length, sr)
        buffer.copyToChannel(float32, 0)
        const src = ctx.createBufferSource()
        src.buffer = buffer
        src.connect(ctx.destination)
        const now = ctx.currentTime
        if (nextPlayTimeRef.current < now) nextPlayTimeRef.current = now + 0.02
        src.start(nextPlayTimeRef.current)
        nextPlayTimeRef.current += buffer.duration
        activeSourcesRef.current.add(src)
        src.onended = () => activeSourcesRef.current.delete(src)
        if (mutedRef.current) {
          // keep pipeline alive but silent while muted — reduce gain instead of dropping
        }
      } catch (e) {
        console.error('playback enqueue failed', e)
      }
    },
    [ensurePlayCtx]
  )

  // interrupt(): stop all TTS playback immediately (barge-in)
  const interrupt = useCallback(() => {
    for (const src of activeSourcesRef.current) {
      try {
        src.onended = null
        src.stop()
      } catch {
        // already stopped
      }
    }
    activeSourcesRef.current.clear()
    if (playCtxRef.current) nextPlayTimeRef.current = playCtxRef.current.currentTime
    setState((s) => (s === 'speaking' ? 'listening' : s))
  }, [])

  // ---- mic ----
  const stopMic = useCallback(() => {
    // Invalidate any in-flight startMic() so a stale startup aborts instead
    // of completing and clobbering the new connection's resources.
    micGenRef.current++
    try {
      micNodeRef.current?.disconnect()
    } catch {}
    micNodeRef.current = null
    if (micCtxRef.current) {
      micCtxRef.current.close().catch(() => {})
      micCtxRef.current = null
    }
    if (micStreamRef.current) {
      micStreamRef.current.getTracks().forEach((t) => t.stop())
      micStreamRef.current = null
    }
    resampleBufRef.current = new Float32Array(0)
  }, [])

  const startMic = useCallback(async () => {
    const gen = ++micGenRef.current
    const throwIfSuperseded = () => {
      if (micGenRef.current !== gen) {
        const e = new Error('Mic startup superseded by a newer connection')
        e.code = 'MIC_SUPERSEDED'
        throw e
      }
    }
    if (!navigator.mediaDevices?.getUserMedia) {
      setMicState('denied')
      throw new Error('Microphone is not supported in this browser.')
    }
    let stream
    try {
      stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
          channelCount: 1,
        },
        video: false,
      })
    } catch (e) {
      if (e && (e.name === 'NotAllowedError' || e.name === 'SecurityError')) {
        setMicState('denied')
      }
      throw e
    }
    throwIfSuperseded()
    setMicState('granted')
    micStreamRef.current = stream

    const AC = window.AudioContext || window.webkitAudioContext
    const audioCtx = new AC()
    micCtxRef.current = audioCtx

    const blob = new Blob([MIC_PROCESSOR_CODE], { type: 'application/javascript' })
    const url = URL.createObjectURL(blob)
    try {
      await audioCtx.audioWorklet.addModule(url)
    } finally {
      URL.revokeObjectURL(url)
    }
    throwIfSuperseded()

    const source = audioCtx.createMediaStreamSource(stream)
    try {
      source.channelCount = 1
    } catch {}
    const node = new AudioWorkletNode(audioCtx, 'mic-processor', {
      numberOfInputs: 1,
      numberOfOutputs: 1,
      outputChannelCount: [1],
    })
    micNodeRef.current = node

    node.port.onmessage = (evt) => {
      if (!callActiveRef.current) return
      const inputRate = audioCtx.sampleRate
      const resampled = resampleLinear(evt.data, inputRate)
      // append to accumulator
      const prev = resampleBufRef.current
      const merged = new Float32Array(prev.length + resampled.length)
      merged.set(prev, 0)
      merged.set(resampled, prev.length)
      resampleBufRef.current = merged
      // send fixed-size frames
      while (resampleBufRef.current.length >= SEND_CHUNK_SAMPLES) {
        const frame = resampleBufRef.current.slice(0, SEND_CHUNK_SAMPLES)
        resampleBufRef.current = resampleBufRef.current.slice(SEND_CHUNK_SAMPLES)
        if (mutedRef.current) continue
        const ws = wsRef.current
        if (ws && ws.readyState === WebSocket.OPEN) {
          const int16 = floatTo16BitPCM(frame)
          ws.send(
            JSON.stringify({
              type: 'audio',
              data: int16ToBase64(int16),
              seq: seqRef.current++,
            })
          )
        }
      }
    }

    source.connect(node)
    // Note: node is intentionally NOT connected to destination (no mic loopback).
    return audioCtx
  }, [])

  // ---- websocket ----
  const sendJson = useCallback((obj) => {
    const ws = wsRef.current
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify(obj))
      return true
    }
    return false
  }, [])

  const cleanup = useCallback(() => {
    callActiveRef.current = false
    if (pingTimerRef.current) {
      clearInterval(pingTimerRef.current)
      pingTimerRef.current = null
    }
    if (disconnectTimerRef.current) {
      clearTimeout(disconnectTimerRef.current)
      disconnectTimerRef.current = null
    }
    stopMic()
    if (wsRef.current) {
      const ws = wsRef.current
      wsRef.current = null
      try {
        ws.close()
      } catch {}
    }
    // stop playback but keep contexts for potential reuse
    for (const src of activeSourcesRef.current) {
      try {
        src.onended = null
        src.stop()
      } catch {}
    }
    activeSourcesRef.current.clear()
    setConnected(false)
    setConnecting(false)
    setState('idle')
  }, [stopMic])

  const disconnect = useCallback(() => {
    manualCloseRef.current = true
    sendJson({ type: 'end_call' })
    // give the server a moment to finalize before closing
    if (disconnectTimerRef.current) clearTimeout(disconnectTimerRef.current)
    disconnectTimerRef.current = setTimeout(() => cleanup(), 400)
  }, [cleanup, sendJson])

  const connect = useCallback(
    async (agentId) => {
      const connId = ++connectionIdRef.current
      cleanup()
      manualCloseRef.current = false
      setError(null)
      setTranscript([])
      setLatency(null)
      setCallInfo(null)
      setStats(null)
      setState('idle')
      setConnecting(true)

      const token = getToken()
      if (!token) {
        setConnecting(false)
        setError('Not authenticated. Please log in again.')
        return
      }

      // 1) mic permission first (graceful denial)
      try {
        await startMic()
      } catch (e) {
        // A superseded startup (or a stale connection id) is normal during
        // rapid remounts/reconnects — the newer connection owns the mic now.
        if (e?.code === 'MIC_SUPERSEDED' || connectionIdRef.current !== connId) return
        setConnecting(false)
        const denied = e && (e.name === 'NotAllowedError' || e.name === 'SecurityError')
        setError(
          denied
            ? 'Microphone access was denied. Allow microphone permission and try again.'
            : `Could not access microphone: ${e.message || e}`
        )
        return
      }

      if (connectionIdRef.current !== connId) {
        stopMic()
        return
      }

      // 2) websocket
      let ws
      try {
        ws = new WebSocket(api.wsUrl())
      } catch (e) {
        if (connectionIdRef.current !== connId) return
        setConnecting(false)
        setError(`Could not open WebSocket: ${e.message || e}`)
        stopMic()
        return
      }
      wsRef.current = ws
      seqRef.current = 0

      ws.onopen = () => {
        setConnected(true)
        setConnecting(false)
        ws.send(JSON.stringify({ type: 'start_call', agent_id: agentId, token }))
        pingTimerRef.current = setInterval(() => {
          sendJson({ type: 'ping' })
        }, 25000)
      }

      ws.onmessage = (evt) => {
        let msg
        try {
          msg = JSON.parse(evt.data)
        } catch {
          return
        }
        switch (msg.type) {
          case 'call_started':
            callActiveRef.current = true
            setCallInfo({ call_id: msg.call_id, agent: msg.agent })
            break
          case 'state':
            if (['listening', 'thinking', 'speaking'].includes(msg.state)) {
              setState(msg.state)
            }
            break
          case 'transcript':
            setTranscript((t) => [
              ...t,
              { role: msg.role, text: msg.text, language: msg.language, turn: msg.turn },
            ])
            break
          case 'audio':
            if (mutedRef.current) break
            enqueueAudio(msg.data, msg.sample_rate)
            break
          case 'audio_end':
            break
          case 'interrupted':
            interrupt()
            break
          case 'latency':
            setLatency({
              stt_ms: msg.stt_ms,
              llm_ms: msg.llm_ms,
              tts_ms: msg.tts_ms,
              total_ms: msg.total_ms,
              turn: msg.turn,
            })
            break
          case 'call_ended':
            setStats({
              call_id: msg.call_id,
              duration_sec: msg.duration_sec,
              message_count: msg.message_count,
            })
            manualCloseRef.current = true
            cleanup()
            break
          case 'error':
            setError(msg.message || `Server error: ${msg.code || 'unknown'}`)
            if (['auth_failed', 'agent_not_found'].includes(msg.code)) {
              manualCloseRef.current = true
              cleanup()
            }
            break
          case 'pong':
            break
          default:
            break
        }
      }

      ws.onerror = () => {
        // onclose will fire right after; handle state there
      }

      ws.onclose = (evt) => {
        const wasManual = manualCloseRef.current
        cleanup()
        if (!wasManual) {
          setError(
            evt.code === 1006
              ? 'Connection to the voice server was lost unexpectedly.'
              : `Voice connection closed (code ${evt.code}).`
          )
        }
      }
    },
    [cleanup, enqueueAudio, interrupt, sendJson, startMic, stopMic]
  )

  const toggleMute = useCallback(() => {
    setMuted((m) => {
      mutedRef.current = !m
      return !m
    })
  }, [])

  // initial mic permission probe (non-blocking)
  useEffect(() => {
    let cancelled = false
    try {
      if (navigator.permissions?.query) {
        navigator.permissions
          .query({ name: 'microphone' })
          .then((status) => {
            if (cancelled) return
            if (status.state === 'granted') setMicState('granted')
            else if (status.state === 'denied') setMicState('denied')
            else setMicState('prompt')
            status.onchange = () => {
              if (status.state === 'granted') setMicState('granted')
              else if (status.state === 'denied') setMicState('denied')
              else setMicState('prompt')
            }
          })
          .catch(() => {})
      }
    } catch {}
    return () => {
      cancelled = true
    }
  }, [])

  // unmount safety
  useEffect(() => {
    return () => {
      manualCloseRef.current = true
      callActiveRef.current = false
      if (pingTimerRef.current) clearInterval(pingTimerRef.current)
      stopMic()
      if (wsRef.current) {
        try {
          wsRef.current.close()
        } catch {}
        wsRef.current = null
      }
      for (const src of activeSourcesRef.current) {
        try {
          src.stop()
        } catch {}
      }
      activeSourcesRef.current.clear()
      if (playCtxRef.current) {
        playCtxRef.current.close().catch(() => {})
        playCtxRef.current = null
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  return {
    connected,
    connecting,
    state, // idle | listening | thinking | speaking
    transcript, // [{role,text,language,turn}]
    latency, // {stt_ms,llm_ms,tts_ms,total_ms,turn}
    micState, // granted | denied | prompt
    muted,
    toggleMute,
    connect,
    disconnect,
    interrupt,
    error,
    callInfo,
    stats,
  }
}
