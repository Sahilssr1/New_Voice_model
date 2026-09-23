import { useCallback, useEffect, useRef, useState } from 'react'
import {
  deleteKbDocument,
  listKbDocuments,
  searchKb,
  uploadKbDocument,
} from '../api/client'
import { formatDateTime } from '../utils/format'

export default function KnowledgeBase({ agentId }) {
  const [docs, setDocs] = useState([])
  const [loading, setLoading] = useState(true)
  const [uploading, setUploading] = useState(false)
  const [error, setError] = useState(null)
  const [query, setQuery] = useState('')
  const [hits, setHits] = useState(null)
  const [searching, setSearching] = useState(false)
  const fileRef = useRef(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const d = await listKbDocuments(agentId)
      setDocs(Array.isArray(d) ? d : [])
    } catch (e) {
      setError(e.message || 'Failed to load documents')
    } finally {
      setLoading(false)
    }
  }, [agentId])

  useEffect(() => {
    load()
  }, [load])

  const onUpload = async (e) => {
    const file = e.target.files?.[0]
    if (!file) return
    setUploading(true)
    setError(null)
    try {
      await uploadKbDocument(agentId, file)
      await load()
    } catch (err) {
      setError(err.message || 'Upload failed')
    } finally {
      setUploading(false)
      if (fileRef.current) fileRef.current.value = ''
    }
  }

  const onDelete = async (doc) => {
    if (!window.confirm(`Delete "${doc.filename}" from the knowledge base?`)) return
    try {
      await deleteKbDocument(agentId, doc.id)
      await load()
    } catch (e) {
      setError(e.message || 'Delete failed')
    }
  }

  const onSearch = async (e) => {
    e.preventDefault()
    if (!query.trim()) return
    setSearching(true)
    setHits(null)
    try {
      const h = await searchKb(agentId, query.trim(), 3)
      setHits(Array.isArray(h) ? h : [])
    } catch (err) {
      setError(err.message || 'Search failed')
    } finally {
      setSearching(false)
    }
  }

  return (
    <div className="card mt">
      <h3>Knowledge base</h3>
      <p className="muted small">
        Upload documents (TXT, Markdown, PDF). During calls the agent automatically
        pulls in the most relevant excerpts to answer from your content.
      </p>
      {error && <div className="alert alert-error">{error}</div>}

      <div className="btn-row">
        <label className="btn btn-primary btn-sm" style={{ cursor: 'pointer' }}>
          {uploading ? 'Uploading…' : '＋ Upload document'}
          <input
            ref={fileRef}
            type="file"
            accept=".txt,.md,.markdown,.pdf"
            onChange={onUpload}
            disabled={uploading}
            style={{ display: 'none' }}
          />
        </label>
      </div>

      {loading ? (
        <div className="skeleton-grid mt">{['a'].map((k) => <div key={k} className="skeleton" />)}</div>
      ) : docs.length ? (
        <ul className="tool-list mt">
          {docs.map((d) => (
            <li key={d.id} className="tool-item">
              <div>
                <div className="tool-name">{d.filename}</div>
                <div className="muted small">
                  {d.chunk_count} chunks · {(d.char_count / 1000).toFixed(1)}k chars · uploaded{' '}
                  {formatDateTime(d.created_at)}
                </div>
              </div>
              <button className="btn btn-ghost btn-sm" onClick={() => onDelete(d)}>
                Delete
              </button>
            </li>
          ))}
        </ul>
      ) : (
        <p className="muted empty">No documents yet. Upload your first one above.</p>
      )}

      <h3 className="mt">Test retrieval</h3>
      <form onSubmit={onSearch} className="btn-row">
        <input
          className="input"
          placeholder="Ask something your documents should answer…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          style={{ flex: 1 }}
        />
        <button className="btn btn-ghost btn-sm" type="submit" disabled={searching}>
          {searching ? '…' : 'Search'}
        </button>
      </form>
      {hits && (
        hits.length ? (
          <ul className="tool-list mt">
            {hits.map((h, i) => (
              <li key={i} className="tool-item" style={{ alignItems: 'flex-start' }}>
                <div>
                  <div className="tool-name">
                    {h.filename}{' '}
                    <span className="chip chip-sm ml" title="Relevance score (0–1)">
                      {Number(h.score).toFixed(3)}
                    </span>
                  </div>
                  <div className="muted small quote">{h.text}</div>
                </div>
              </li>
            ))}
          </ul>
        ) : (
          <p className="muted empty">No relevant excerpts found.</p>
        )
      )}
    </div>
  )
}
