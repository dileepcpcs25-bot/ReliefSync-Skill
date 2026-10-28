import { useState } from 'react'
import { ROUTES } from '../constants'
import { useOperator } from '../hooks/useOperator'
import { useQuery } from '../hooks/useQuery'
import { setOperator } from '../services/operator'
import { Icon } from './ui'

function ApiStatus() {
  const { data, error, loading } = useQuery('/health')
  if (loading && !data) return <span className="api-status">Checking API…</span>
  return data ? (
    <span className="api-status api-online">● API online</span>
  ) : (
    <span className="api-status api-offline" title={error?.message}>● API offline</span>
  )
}

function OperatorAccess() {
  const op = useOperator()
  if (op.name) return (
    <div className="row">
      <span className="muted">{op.name} · {op.role || 'team'}</span>
      <button type="button" className="btn" onClick={() => { setOperator({ token: '', key: '', name: '', username: '', role: '' }); window.location.hash = '#/login' }}>Sign out</button>
    </div>
  )
  return <a className="btn" href="#/login">Team sign in</a>
}

export default function Layout({ route, children }) {
  const [menuOpen, setMenuOpen] = useState(false)
  const current = ROUTES.find((r) => r.id === route)

  return (
    <div className="shell">
      <a className="skip-link" href="#main">Skip to content</a>
      <aside className={`sidebar ${menuOpen ? 'open' : ''}`}>
        <div className="brand">
          <span className="brand-mark" aria-hidden="true">+</span>
          <div>
            <strong>ReliefSync</strong>
            <small>Disaster Relief Intelligence</small>
          </div>
        </div>
        <nav aria-label="Primary">
          {ROUTES.map((r) => (
            <a key={r.id} href={`#/${r.id}`} aria-current={r.id === route ? 'page' : undefined} onClick={() => setMenuOpen(false)}>
              <Icon name={r.icon} />
              {r.label}
            </a>
          ))}
        </nav>
        <p className="sidebar-note">Demonstration decision-support system. Not a certified emergency-response tool.</p>
      </aside>

      <div className="content">
        <header className="topbar">
          <button type="button" className="icon-btn menu-btn" aria-label="Toggle navigation" aria-expanded={menuOpen} onClick={() => setMenuOpen((o) => !o)}>
            <Icon name="menu" size={22} />
          </button>
          <h1>{current?.label ?? 'Not found'}</h1>
          <OperatorAccess />
          <ApiStatus />
        </header>
        <main id="main" tabIndex={-1}>{children}</main>
      </div>
    </div>
  )
}
