const TOKEN = 'reliefsync.sessionToken'
const KEY = 'reliefsync.operatorKey'
const NAME = 'reliefsync.operatorName'
const USERNAME = 'reliefsync.username'
const ROLE = 'reliefsync.role'
const EVENT = 'reliefsync:operator'
function read(k) { try { return sessionStorage.getItem(k) ?? '' } catch { return '' } }
export const getOperator = () => ({ token: read(TOKEN), key: read(KEY), name: read(NAME), username: read(USERNAME), role: read(ROLE) })
export function setOperator({ token = '', key = '', name = '', username = '', role = '' }) {
  try { for (const [k,v] of [[TOKEN,token],[KEY,key],[NAME,name],[USERNAME,username],[ROLE,role]]) v ? sessionStorage.setItem(k,v) : sessionStorage.removeItem(k) } catch { /* Storage can be blocked by browser policy. */ }
  window.dispatchEvent(new Event(EVENT))
}
export function subscribeOperator(callback) { window.addEventListener(EVENT, callback); return () => window.removeEventListener(EVENT, callback) }

