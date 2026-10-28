import { useDeferredValue, useState } from 'react'
import { fmtDate, locationField } from '../constants'
import { useAction } from '../hooks/useAction'
import { useQuery } from '../hooks/useQuery'
import { api } from '../services/api'
import FormModal from '../components/FormModal'
import { Badge, DataTable, EmptyState, FilterBar, Modal, PageHeader, QueryBoundary } from '../components/ui'

const FIELDS = [
  { name: 'name', label: 'Full name', required: true },
  { name: 'phone', label: 'Phone', type: 'tel', required: true, placeholder: '+91 98765 43210', help: '7-30 characters: digits, spaces, + ( ) -' },
  { name: 'skills', label: 'Skills', placeholder: 'First aid, driving, logistics…' },
  { name: 'location', label: 'Location', required: true },
  locationField('location'),
  { name: 'sms_opt_in', type: 'checkbox', label: 'This volunteer agrees to receive incident SMS messages', help: 'Required before any SMS can be sent to them. Their exact position is private and shown to operators only.' },
]

export default function Volunteers() {
  const [q, setQ] = useState('')
  const [availability, setAvailability] = useState('')
  const [modal, setModal] = useState(null)
  const deferredQ = useDeferredValue(q)
  const query = useQuery('/api/volunteers', { q: deferredQ.trim(), availability, limit: 500 })
  const run = useAction(query.reload)
  const close = () => setModal(null)

  return (
    <>
      <PageHeader
        title="Volunteers"
        subtitle="Register volunteers and manage who is available for deployment."
        actions={<><a className="btn" href="#/notifications">Alert volunteers</a><button type="button" className="btn btn-primary" onClick={() => setModal({ kind: 'create' })}>+ Register volunteer</button></>}
      />
      <FilterBar>
        <input type="search" aria-label="Search volunteers" placeholder="Search name, skill, location…" value={q} onChange={(e) => setQ(e.target.value)} />
        <select aria-label="Filter by availability" value={availability} onChange={(e) => setAvailability(e.target.value)}>
          <option value="">All availability</option>
          <option>Available</option>
          <option>Assigned</option>
          <option>Unavailable</option>
        </select>
      </FilterBar>
      <section className="card">
        <QueryBoundary query={query}>
          {(page) => (
            <DataTable
              caption="Volunteers"
              rows={page.items}
              empty={<EmptyState title="No volunteers found">Register your first volunteer to begin.</EmptyState>}
              columns={[
                { header: 'Name', render: (r) => <strong>{r.name}</strong> },
                { header: 'Skills', render: (r) => r.skills || <span className="muted">—</span> },
                { header: 'Location', key: 'location' },
                { header: 'Phone', key: 'phone' },
                {
                  header: 'Availability',
                  render: (r) =>
                    r.availability === 'Assigned' ? (
                      <Badge>Assigned</Badge>
                    ) : (
                      <select className="inline-select" aria-label={`Availability for ${r.name}`} value={r.availability}
                        onChange={(e) => run(() => api.patch(`/api/volunteers/${r.id}/availability`, { availability: e.target.value }), 'Availability updated')}>
                        <option>Available</option>
                        <option>Unavailable</option>
                      </select>
                    ),
                },
                {
                  header: 'Actions',
                  render: (r) => (
                    <div className="actions">
                      <button type="button" className="btn btn-sm" onClick={() => setModal({ kind: 'view', row: r })}>Profile</button>
                      <button type="button" className="btn btn-sm" onClick={() => setModal({ kind: 'edit', row: r })}>Edit</button>
                    </div>
                  ),
                },
              ]}
            />
          )}
        </QueryBoundary>
      </section>

      {modal?.kind === 'create' && (
        <FormModal title="Register volunteer" fields={FIELDS} submitLabel="Register"
          onSubmit={(v) => run(() => api.post('/api/volunteers', v), 'Volunteer registered', { inline: true })} onClose={close} />
      )}
      {modal?.kind === 'edit' && (
        <FormModal title="Edit volunteer" fields={FIELDS} initial={modal.row}
          onSubmit={(v) => run(() => api.patch(`/api/volunteers/${modal.row.id}`, v), 'Volunteer updated', { inline: true })} onClose={close} />
      )}
      {modal?.kind === 'view' && (
        <Modal title={modal.row.name} onClose={close}>
          <dl className="detail-grid">
            <dt>Availability</dt><dd><Badge>{modal.row.availability}</Badge></dd>
            <dt>Phone</dt><dd>{modal.row.phone}</dd>
            <dt>Location</dt><dd>{modal.row.location}</dd>
            <dt>Skills</dt><dd>{modal.row.skills || <span className="muted">None listed</span>}</dd>
            <dt>Registered</dt><dd>{fmtDate(modal.row.created_at)}</dd>
          </dl>
        </Modal>
      )}
    </>
  )
}
