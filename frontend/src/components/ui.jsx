import { useEffect, useRef } from 'react'
import { TONES } from '../constants'

const ICONS = {
  dashboard: 'M3 3h7v7H3zM14 3h7v7h-7zM3 14h7v7H3zM14 14h7v7h-7z',
  alert: 'M12 3 2 20h20zM12 10v5M12 17.5v.5',
  bars: 'M5 21V11M12 21V4M19 21v-7',
  users: 'M9 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8zM2 21c0-4 3-6 7-6s7 2 7 6M17 3.5a4 4 0 0 1 0 7M22 21c0-3-1.5-5-4-5.7',
  clipboard: 'M8 4h8v3H8zM6 5H5v16h14V5h-1M9 12h6M9 16h4',
  box: 'M3 7l9-4 9 4v10l-9 4-9-4zM3 7l9 4 9-4M12 11v10',
  home: 'M3 11 12 3l9 8M5 10v11h14V10M10 21v-6h4v6',
  spark: 'M12 3l2.2 5.8L20 11l-5.8 2.2L12 19l-2.2-5.8L4 11l5.8-2.2zM19 3v4M21 5h-4',
  truck: 'M2 6h12v10H2zM14 9h4l4 4v3h-8M6 19.5a1.5 1.5 0 1 0 0-3 1.5 1.5 0 0 0 0 3zM17 19.5a1.5 1.5 0 1 0 0-3 1.5 1.5 0 0 0 0 3z',
  login: 'M15 3h4a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-4M10 17l5-5-5-5M15 12H3',
  clock: 'M12 8v4l3 2M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0',
  guide: 'M12 18h.01M9.1 9a3 3 0 0 1 5.8 1c0 2-3 2-3 5M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20z',
  menu: 'M4 6h16M4 12h16M4 18h16',
  map: 'M9 4 3 6v14l6-2 6 2 6-2V4l-6 2zM9 4v14M15 6v14',
  globe: 'M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18zM3 12h18M12 3c3 3 3 15 0 18M12 3c-3 3-3 15 0 18',
  bell: 'M6 9a6 6 0 0 1 12 0c0 6 2 7 2 7H4s2-1 2-7zM10 20a2 2 0 0 0 4 0',
  radio: 'M12 12.5a1.5 1.5 0 1 0 0-3 1.5 1.5 0 0 0 0 3zM8 8a5.6 5.6 0 0 0 0 8M16 8a5.6 5.6 0 0 1 0 8M5 5a10 10 0 0 0 0 14M19 5a10 10 0 0 1 0 14',
}

export function Icon({ name, size = 18 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d={ICONS[name]} />
    </svg>
  )
}

export function Badge({ children, tone }) {
  return <span className={`badge badge-${tone ?? TONES[children] ?? 'gray'}`}>{children}</span>
}

export function Spinner({ label = 'Loading…' }) {
  return (
    <div className="state" role="status">
      <span className="spinner" aria-hidden="true" />
      <span>{label}</span>
    </div>
  )
}

export function EmptyState({ title, children }) {
  return (
    <div className="state">
      <strong>{title}</strong>
      {children && <p>{children}</p>}
    </div>
  )
}

export function ErrorState({ error, onRetry }) {
  return (
    <div className="state state-error" role="alert">
      <strong>{error?.status === 0 ? 'Backend unavailable' : 'Something went wrong'}</strong>
      <p>{error?.message}</p>
      {onRetry && <button type="button" className="btn" onClick={onRetry}>Try again</button>}
    </div>
  )
}

/** Renders loading / error / content for a useQuery result. `children` receives the data. */
export function QueryBoundary({ query, children }) {
  if (query.data) return children(query.data)
  if (query.error) return <ErrorState error={query.error} onRetry={query.reload} />
  return <Spinner />
}

export function PageHeader({ title, subtitle, actions }) {
  return (
    <div className="page-header">
      <div>
        <h2>{title}</h2>
        {subtitle && <p className="muted">{subtitle}</p>}
      </div>
      <div className="row">{actions}</div>
    </div>
  )
}

export function StatCard({ label, value, hint, tone }) {
  return (
    <div className={`stat ${tone ? `stat-${tone}` : ''}`}>
      <span className="stat-label">{label}</span>
      <span className="stat-value">{value}</span>
      {hint && <span className="stat-hint">{hint}</span>}
    </div>
  )
}

export function Meter({ value, max, tone = 'blue', label }) {
  const pct = max > 0 ? Math.min(100, Math.round((100 * value) / max)) : 0
  return (
    <div className="meter" role="meter" aria-label={label} aria-valuemin={0} aria-valuemax={max} aria-valuenow={value}>
      <div className={`meter-fill meter-${tone}`} style={{ width: `${pct}%` }} />
    </div>
  )
}

export function Card({ title, action, children }) {
  return (
    <section className="card">
      {(title || action) && (
        <header className="card-header">
          <h3>{title}</h3>
          {action}
        </header>
      )}
      {children}
    </section>
  )
}

export function DataTable({ caption, columns, rows, rowKey = (r) => r.id, empty }) {
  if (!rows.length) return empty
  return (
    <div className="table-wrap">
      <table>
        <caption className="sr-only">{caption}</caption>
        <thead>
          <tr>{columns.map((c) => <th key={c.header} scope="col" className={c.className}>{c.header}</th>)}</tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={rowKey(row)}>
              {columns.map((c) => <td key={c.header} className={c.className}>{c.render ? c.render(row) : row[c.key]}</td>)}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

/** Accessible modal built on the native <dialog> element (focus trap + Esc handled by the browser). */
export function Modal({ title, onClose, children, wide = false }) {
  const ref = useRef(null)
  useEffect(() => {
    const el = ref.current
    if (el && !el.open) el.showModal()
  }, [])
  return (
    <dialog
      ref={ref}
      className={`modal ${wide ? 'modal-wide' : ''}`}
      aria-labelledby="modal-title"
      onClose={onClose}
      onClick={(e) => e.target === ref.current && onClose()}
    >
      <div className="modal-body">
        <header className="modal-header">
          <h3 id="modal-title">{title}</h3>
          <button type="button" className="icon-btn" aria-label="Close dialog" onClick={onClose}>×</button>
        </header>
        {children}
      </div>
    </dialog>
  )
}

export function ConfirmDialog({ title, message, confirmLabel = 'Confirm', danger = false, onConfirm, onCancel }) {
  return (
    <Modal title={title} onClose={onCancel}>
      <p>{message}</p>
      <div className="modal-actions">
        <button type="button" className="btn" onClick={onCancel}>Keep as is</button>
        <button type="button" className={`btn ${danger ? 'btn-danger' : 'btn-primary'}`} onClick={onConfirm}>{confirmLabel}</button>
      </div>
    </Modal>
  )
}

export function FilterBar({ children }) {
  return <div className="filters" role="search">{children}</div>
}

export function Disclaimer({ children }) {
  return <p className="disclaimer" role="note">{children}</p>
}
