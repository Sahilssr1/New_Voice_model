// Shared display formatting for the whole app.
// One date format, one duration format, one latency format — used by every page.

const DATE_TIME_OPTS = {
  month: 'short',
  day: 'numeric',
  year: 'numeric',
  hour: 'numeric',
  minute: '2-digit',
}

const DATE_OPTS = { month: 'short', day: 'numeric', year: 'numeric' }

function toDate(iso) {
  if (!iso) return null
  const d = iso instanceof Date ? iso : new Date(iso)
  return Number.isNaN(d.getTime()) ? null : d
}

/** "Sep 23, 2026, 4:01 PM" — '—' when missing/invalid. */
export function formatDateTime(iso) {
  const d = toDate(iso)
  if (!d) return '—'
  try {
    return d.toLocaleString(undefined, DATE_TIME_OPTS)
  } catch {
    return String(iso)
  }
}

/** "Sep 23, 2026" — '—' when missing/invalid. */
export function formatDate(iso) {
  const d = toDate(iso)
  if (!d) return '—'
  try {
    return d.toLocaleDateString(undefined, DATE_OPTS)
  } catch {
    return String(iso)
  }
}

/** 45 -> "45s", 195 -> "3m 15s", 3900 -> "1h 5m". Null/undefined/NaN -> '—'. */
export function formatDuration(totalSec) {
  if (totalSec === null || totalSec === undefined || Number.isNaN(Number(totalSec))) return '—'
  const s = Math.max(0, Math.round(Number(totalSec)))
  const h = Math.floor(s / 3600)
  const m = Math.floor((s % 3600) / 60)
  const sec = s % 60
  if (h > 0) return `${h}h ${m}m`
  if (m > 0) return `${m}m ${sec}s`
  return `${sec}s`
}

/** 1234.5 -> "1235 ms". Null/undefined -> '—'. */
export function formatLatency(ms) {
  if (ms === null || ms === undefined || Number.isNaN(Number(ms))) return '—'
  return `${Math.round(Number(ms))} ms`
}

/** Short language chip label, e.g. "en" -> "English". Unknown codes pass through. */
const LANGUAGE_LABELS = {
  auto: 'Auto',
  en: 'English',
  hi: 'Hindi',
  hinglish: 'Hinglish',
  es: 'Spanish',
  fr: 'French',
  de: 'German',
  pt: 'Portuguese',
  it: 'Italian',
  ja: 'Japanese',
  zh: 'Chinese',
}

export function languageLabel(code) {
  if (!code) return '—'
  return LANGUAGE_LABELS[code] || code
}
