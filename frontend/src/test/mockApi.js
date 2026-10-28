import { vi } from 'vitest'

/** Replaces fetch with a router: routes = { 'GET /api/x': data | (url, body) => data }. Unmatched calls fail the test. */
export function mockApi(routes) {
  const calls = []
  const fetchMock = vi.fn(async (url, init = {}) => {
    const u = new URL(url, 'http://localhost')
    const method = init.method ?? 'GET'
    const body = init.body ? JSON.parse(init.body) : undefined
    calls.push({ method, path: u.pathname, search: u.search, body, headers: init.headers })
    const key = Object.keys(routes).find((k) => k === `${method} ${u.pathname}`)
    if (!key) throw new Error(`Unmocked request: ${method} ${u.pathname}${u.search}`)
    const r = routes[key]
    const out = typeof r === 'function' ? r(u, body) : r
    if (out instanceof Error) return new Response(JSON.stringify({ detail: out.message }), { status: out.status ?? 400, headers: { 'content-type': 'application/json' } })
    return new Response(JSON.stringify(out), { status: 200, headers: { 'content-type': 'application/json' } })
  })
  vi.stubGlobal('fetch', fetchMock)
  return calls
}
