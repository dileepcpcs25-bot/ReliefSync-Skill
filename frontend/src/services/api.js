import { getOperator } from './operator'

const BASE_URL = (import.meta.env.VITE_API_BASE_URL ?? '').replace(/\/$/, '')

export class ApiError extends Error {
  constructor(message, status) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

/** Turns FastAPI's `detail` (string or validation-error array) into one readable sentence. */
function formatDetail(detail) {
  if (!detail) return null
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) {
    return detail
      .map((e) => `${(e.loc ?? []).filter((p) => p !== 'body').join('.')}: ${e.msg}`.replace(/^: /, ''))
      .join('; ')
  }
  return null
}

/** Builds "?a=1&b=2", skipping empty values. */
export function qs(params = {}) {
  const sp = new URLSearchParams()
  for (const [k, v] of Object.entries(params)) {
    if (v !== '' && v !== undefined && v !== null && v !== false) sp.set(k, String(v))
  }
  const s = sp.toString()
  return s ? `?${s}` : ''
}

async function request(path, { method = 'GET', body, signal } = {}) {
  let res
  try {
    const op = getOperator()
    const headers = {}
    if (body !== undefined) headers['Content-Type'] = 'application/json'
    if (op.token) headers.Authorization = `Bearer ${op.token}`
    if (op.key) headers['X-Operator-Key'] = op.key
    if (op.name) headers['X-Operator-Name'] = op.name
    res = await fetch(`${BASE_URL}${path}`, {
      method,
      signal,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
    })
  } catch (err) {
    if (err.name === 'AbortError') throw err
    throw new ApiError(`Cannot reach the ReliefSync API${BASE_URL ? ` at ${BASE_URL}` : ''}. Is the backend running?`, 0)
  }
  if (res.status === 204) return null
  const data = await res.json().catch(() => null)
  if (!res.ok) throw new ApiError(formatDetail(data?.detail) ?? `Request failed (${res.status})`, res.status)
  return data
}

export const api = {
  get: (path, signal) => request(path, { signal }),
  post: (path, body) => request(path, { method: 'POST', body }),
  patch: (path, body) => request(path, { method: 'PATCH', body }),
  del: (path) => request(path, { method: 'DELETE' }),
}
