import { useSyncExternalStore } from 'react'

const subscribe = (callback) => {
  window.addEventListener('hashchange', callback)
  return () => window.removeEventListener('hashchange', callback)
}
const getHash = () => window.location.hash.replace(/^#\/?/, '')
const getSnapshot = () => getHash().split('?')[0] || 'dashboard'

/** Minimal hash router: "#/inventory" -> "inventory"; "#/map?disaster=3" -> "map". Works on any static host. */
export function useHashRoute() {
  return useSyncExternalStore(subscribe, getSnapshot)
}

/** Query parameters of the current hash route, e.g. "#/map?disaster=3" -> { disaster: '3' }. */
export function useHashParams() {
  const hash = useSyncExternalStore(subscribe, getHash)
  return Object.fromEntries(new URLSearchParams(hash.split('?')[1] ?? ''))
}
