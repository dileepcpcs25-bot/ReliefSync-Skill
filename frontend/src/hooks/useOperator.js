import { useSyncExternalStore } from 'react'
import { getOperator, subscribeOperator } from '../services/operator'
const snapshot = () => { const o = getOperator(); return `${o.token}\u0000${o.key}\u0000${o.name}\u0000${o.role}` }
export function useOperator() {
  const [token = '', key = '', name = '', role = ''] = useSyncExternalStore(subscribeOperator, snapshot).split('\u0000')
  return { token, key, name, role, hasKey: Boolean(token || key) }
}
