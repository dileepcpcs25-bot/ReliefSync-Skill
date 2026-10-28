import { useDeferredValue, useState } from 'react'
import { DISASTER_STATUSES, SEVERITIES, STATUS_RULE_TEXT, fmt, fmtDate, locationField } from '../constants'
import { useAction } from '../hooks/useAction'
import { useQuery } from '../hooks/useQuery'
import { api } from '../services/api'
import FormModal from '../components/FormModal'
import { Badge, ConfirmDialog, DataTable, EmptyState, FilterBar, Modal, PageHeader, QueryBoundary } from '../components/ui'

const FIELDS = [
  { name: 'disaster_type', label: 'Disaster type', required: true, placeholder: 'Flood, Cyclone, Earthquake…' },
  { name: 'location', label: 'Location', required: true },
  { name: 'severity', label: 'Severity', type: 'select', options: SEVERITIES, required: true },
  { name: 'people_affected', label: 'People affected', type: 'number', min: 0, required: true },
  { name: 'description', label: 'Description', type: 'textarea' },
  locationField('location'),
]

function DisasterIntel({ id }) {
  const q = useQuery(`/api/intelligence/priority/${id}`)
  if (!q.data) return q.error ? <p className="muted">Priority detail unavailable: {q.error.message}</p> : null
  const { entry, ranked } = q.data
  return (
    <div className="subpanel">
      <strong>{ranked ? `Priority score ${entry.score} (${entry.level}), rank #${entry.rank}` : 'Resolved: excluded from priority rankings'}</strong>{' '}
      <span className="tag-estimate">{entry.label}</span>
      <p className="muted">{entry.explanation}</p>
      <table>
        <thead><tr><th>Factor</th><th>Input</th><th className="num">Points</th><th>Basis</th></tr></thead>
        <tbody>{entry.factors.map((f) => <tr key={f.name}><td>{f.name}</td><td>{f.input}</td><td className="num">{f.points}</td><td>{f.basis}</td></tr>)}</tbody>
      </table>
      <p className="status-rule"><strong>{q.data.status_rule ?? STATUS_RULE_TEXT}</strong></p>
    </div>
  )
}

export default function Disasters() {
  const [q, setQ] = useState('')
  const [severity, setSeverity] = useState('')
  const [status, setStatus] = useState('')
  const [modal, setModal] = useState(null) // { kind: 'create' | 'edit' | 'view' | 'delete', row? }
  const deferredQ = useDeferredValue(q)
  const query = useQuery('/api/disasters', { q: deferredQ.trim(), severity, status, limit: 200 })
  const run = useAction(query.reload)
  const close = () => setModal(null)

  const changeStatus = (row, next) => run(() => api.patch(`/api/disasters/${row.id}/status`, { status: next }), `Marked ${next}`)
  const confirmDelete = () => {
    const { row } = modal
    close()
    run(() => api.del(`/api/disasters/${row.id}`), 'Disaster deleted')
  }

  return (
    <>
      <PageHeader
        title="Disasters"
        subtitle="Report incidents, track their status and review priority."
        actions={<button type="button" className="btn btn-primary" onClick={() => setModal({ kind: 'create' })}>+ Report disaster</button>}
      />
      <FilterBar>
        <input type="search" aria-label="Search disasters" placeholder="Search type, location, description…" value={q} onChange={(e) => setQ(e.target.value)} />
        <select aria-label="Filter by severity" value={severity} onChange={(e) => setSeverity(e.target.value)}>
          <option value="">All severities</option>
          {SEVERITIES.map((s) => <option key={s}>{s}</option>)}
        </select>
        <select aria-label="Filter by status" value={status} onChange={(e) => setStatus(e.target.value)}>
          <option value="">All statuses</option>
          {DISASTER_STATUSES.map((s) => <option key={s}>{s}</option>)}
        </select>
      </FilterBar>

      <section className="card">
        <QueryBoundary query={query}>
          {(page) => (
            <DataTable
              caption="Disasters"
              rows={page.items}
              empty={<EmptyState title="No disasters match" >Adjust the filters or report a new disaster.</EmptyState>}
              columns={[
                { header: 'Incident', render: (r) => <><strong>{r.disaster_type}</strong><span className="sub">{r.location}</span></> },
                { header: 'Severity', render: (r) => <Badge>{r.severity}</Badge> },
                { header: 'Priority', render: (r) => <><Badge>{r.priority_level}</Badge> <span className="sub">score {r.priority_score}</span></> },
                { header: 'Affected', className: 'num', render: (r) => fmt(r.people_affected) },
                {
                  header: 'Status',
                  render: (r) => (
                    <select className="inline-select" aria-label={`Status for ${r.disaster_type} in ${r.location}`} value={r.status} onChange={(e) => changeStatus(r, e.target.value)}>
                      {DISASTER_STATUSES.map((s) => <option key={s}>{s}</option>)}
                    </select>
                  ),
                },
                { header: 'Reported', render: (r) => fmtDate(r.created_at) },
                {
                  header: 'Actions',
                  className: 'actions-col',
                  render: (r) => (
                    <div className="actions">
                      <button type="button" className="btn btn-sm" onClick={() => setModal({ kind: 'view', row: r })}>Details</button>
                      <button type="button" className="btn btn-sm" onClick={() => setModal({ kind: 'edit', row: r })}>Edit</button>
                      <button type="button" className="btn btn-sm btn-danger" onClick={() => setModal({ kind: 'delete', row: r })}>Delete</button>
                    </div>
                  ),
                },
              ]}
            />
          )}
        </QueryBoundary>
      </section>

      {modal?.kind === 'create' && (
        <FormModal title="Report a disaster" fields={FIELDS} initial={{ severity: 'High', people_affected: 0 }} submitLabel="Report"
          onSubmit={(v) => run(() => api.post('/api/disasters', v), 'Disaster reported', { inline: true })} onClose={close} />
      )}
      {modal?.kind === 'edit' && (
        <FormModal title="Edit disaster" fields={FIELDS} initial={modal.row}
          onSubmit={(v) => run(() => api.patch(`/api/disasters/${modal.row.id}`, v), 'Disaster updated', { inline: true })} onClose={close} />
      )}
      {modal?.kind === 'delete' && (
        <ConfirmDialog danger title="Delete disaster?" confirmLabel="Delete"
          message={`Permanently delete "${modal.row.disaster_type} - ${modal.row.location}"? Disasters with assignment or allocation history cannot be deleted; resolve them instead.`}
          onConfirm={confirmDelete} onCancel={close} />
      )}
      {modal?.kind === 'view' && (
        <Modal title={`${modal.row.disaster_type} - ${modal.row.location}`} onClose={close} wide>
          <dl className="detail-grid">
            <dt>Severity</dt><dd><Badge>{modal.row.severity}</Badge></dd>
            <dt>Status</dt><dd><Badge>{modal.row.status}</Badge></dd>
            <dt>People affected</dt><dd>{fmt(modal.row.people_affected)}</dd>
            <dt>Priority</dt><dd><Badge>{modal.row.priority_level}</Badge> score {modal.row.priority_score}</dd>
            <dt>Description</dt><dd>{modal.row.description || <span className="muted">No description</span>}</dd>
            <dt>Position</dt><dd>{modal.row.latitude != null ? <>{modal.row.latitude.toFixed(4)}, {modal.row.longitude.toFixed(4)} <span className="muted">({modal.row.location_source}{modal.row.location_approximate ? ', approximate' : ''})</span> · <a href={`#/map?disaster=${modal.row.id}`}>View on map</a></> : <span className="muted">Unknown - edit the incident to set it on the map</span>}</dd>
            <dt>Origin</dt><dd>{modal.row.origin === 'external_promoted' ? 'Promoted by an operator from an unverified external observation' : 'Entered in ReliefSync'}</dd>
            <dt>Reported</dt><dd>{fmtDate(modal.row.created_at)}</dd>
            <dt>Last updated</dt><dd>{fmtDate(modal.row.updated_at)}</dd>
          </dl>
          <DisasterIntel id={modal.row.id} />
        </Modal>
      )}
    </>
  )
}
