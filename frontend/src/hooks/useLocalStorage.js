import { useEffect, useState } from 'react'

/** Persist non-sensitive UI preferences in localStorage. Never use this for operator keys. */
export function useLocalStorage(key, initialValue) {
  const [value, setValue] = useState(() => {
    try {
      const raw = window.localStorage.getItem(key)
      return raw === null ? initialValue : JSON.parse(raw)
    } catch { return initialValue }
  })
  useEffect(() => {
    try { window.localStorage.setItem(key, JSON.stringify(value)) } catch { /* Storage can be disabled. */ }
  }, [key, value])
  return [value, setValue]
}
