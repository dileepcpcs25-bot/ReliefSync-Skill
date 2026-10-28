import { useCallback, useEffect, useState } from 'react'
import { api, qs } from '../services/api'

/**
 * Fetches `path` (+ query params) and refetches when they change or `reload()` is called.
 * Loading is derived (not set inside the effect), in-flight requests are aborted, and
 * stale data stays visible while a refetch is running.
 */
export function useQuery(path, params) {
  const url = path + qs(params)
  const [tick, setTick] = useState(0)
  const [result, setResult] = useState({ url: null, tick: -1, data: null, error: null })

  useEffect(() => {
    const controller = new AbortController()
    api.get(url, controller.signal).then(
      (data) => setResult({ url, tick, data, error: null }),
      (error) => {
        if (error.name !== 'AbortError') setResult((prev) => ({ url, tick, data: prev.data, error }))
      },
    )
    return () => controller.abort()
  }, [url, tick])

  const reload = useCallback(() => setTick((t) => t + 1), [])
  const loading = result.url !== url || result.tick !== tick
  return { data: result.data, error: loading ? null : result.error, loading, reload }
}
