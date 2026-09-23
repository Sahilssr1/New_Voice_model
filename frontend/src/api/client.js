// REST API client for the voiceagent backend.
// Base URL per CONTRACT.md: http://localhost:8000
// JWT stored in localStorage under `va_token`.

const BASE_URL = 'http://localhost:8000'

const TOKEN_KEY = 'va_token'

export function getToken() {
  return localStorage.getItem(TOKEN_KEY)
}

export function setToken(token) {
  if (token) localStorage.setItem(TOKEN_KEY, token)
  else localStorage.removeItem(TOKEN_KEY)
}

export function getUser() {
  try {
    return JSON.parse(localStorage.getItem('va_user') || 'null')
  } catch {
    return null
  }
}

export function setUser(user) {
  if (user) localStorage.setItem('va_user', JSON.stringify(user))
  else localStorage.removeItem('va_user')
}

class ApiError extends Error {
  constructor(status, body) {
    const detail =
      body && typeof body === 'object'
        ? body.detail || body.message || JSON.stringify(body)
        : body || `HTTP ${status}`
    super(typeof detail === 'string' ? detail : JSON.stringify(detail))
    this.name = 'ApiError'
    this.status = status
    this.body = body
  }
}

async function request(method, path, body) {
  const headers = {}
  const token = getToken()
  if (token) headers['Authorization'] = `Bearer ${token}`
  const opts = { method, headers }
  if (body !== undefined) {
    headers['Content-Type'] = 'application/json'
    opts.body = JSON.stringify(body)
  }
  let res
  try {
    res = await fetch(`${BASE_URL}${path}`, opts)
  } catch (e) {
    throw new Error(`Network error: could not reach ${BASE_URL} (${e.message})`)
  }
  const contentType = res.headers.get('content-type') || ''
  let data = null
  if (contentType.includes('application/json')) {
    data = await res.json().catch(() => null)
  } else {
    const text = await res.text().catch(() => '')
    data = text ? { message: text } : null
  }
  if (!res.ok) {
    throw new ApiError(res.status, data)
  }
  return data
}

export const api = {
  get: (path) => request('GET', path),
  post: (path, body) => request('POST', path, body),
  patch: (path, body) => request('PATCH', path, body),
  del: (path) => request('DELETE', path),
  wsUrl: () => 'ws://localhost:8000/ws/voice',
  // Multipart upload (FormData); lets the browser set the content type.
  async upload(path, formData) {
    const headers = {}
    const token = getToken()
    if (token) headers['Authorization'] = `Bearer ${token}`
    const res = await fetch(`${BASE_URL}${path}`, {
      method: 'POST',
      headers,
      body: formData,
    })
    const data = await res.json().catch(() => null)
    if (!res.ok) throw new ApiError(res.status, data)
    return data
  },
}

export function listKbDocuments(agentId) {
  return api.get(`/api/agents/${agentId}/kb/documents`)
}
export function uploadKbDocument(agentId, file) {
  const fd = new FormData()
  fd.append('file', file)
  return api.upload(`/api/agents/${agentId}/kb/documents`, fd)
}
export function deleteKbDocument(agentId, docId) {
  return api.del(`/api/agents/${agentId}/kb/documents/${docId}`)
}
export function searchKb(agentId, query, top_k = 3) {
  return api.post(`/api/agents/${agentId}/kb/search`, { query, top_k })
}

// ---------- Auth ----------
export function register({ email, password, name }) {
  return api.post('/api/auth/register', { email, password, name })
}

export function login({ email, password }) {
  return api.post('/api/auth/login', { email, password })
}

export function me() {
  return api.get('/api/auth/me')
}

// ---------- Agents ----------
export function listAgents() {
  return api.get('/api/agents')
}

export function createAgent(payload) {
  return api.post('/api/agents', payload)
}

export function getAgent(id) {
  return api.get(`/api/agents/${id}`)
}

export function updateAgent(id, payload) {
  return api.patch(`/api/agents/${id}`, payload)
}

export function deleteAgent(id) {
  return api.del(`/api/agents/${id}`)
}

// ---------- Voices ----------
export function getVoices(params = {}) {
  const q = new URLSearchParams()
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== null && v !== '') q.append(k, v)
  }
  const qs = q.toString()
  return api.get(`/api/voices${qs ? `?${qs}` : ''}`)
}

// ---------- Calls ----------
export function listCalls(agent_id) {
  const qs = agent_id ? `?agent_id=${encodeURIComponent(agent_id)}` : ''
  return api.get(`/api/calls${qs}`)
}

export function getCall(id) {
  return api.get(`/api/calls/${id}`)
}

export function deleteCall(id) {
  return api.del(`/api/calls/${id}`)
}

// ---------- Tools ----------
export function listTools() {
  return api.get('/api/tools')
}

export function attachTool(agentId, tool_id) {
  return api.post(`/api/agents/${agentId}/tools`, { tool_id })
}

export function detachTool(agentId, tool_id) {
  return api.del(`/api/agents/${agentId}/tools/${tool_id}`)
}

// ---------- Dashboard / Health ----------
export function getDashboard() {
  return api.get('/api/dashboard')
}

export function getHealth() {
  return api.get('/health')
}

export function getAiHealth() {
  return api.get('/health/ai')
}

export function getServiceHealth(service) {
  return api.get(`/health/${service}`)
}
