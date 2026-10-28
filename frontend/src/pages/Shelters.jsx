import { useDeferredValue, useState } from 'react'
import { fmt, locationField } from '../constants'
import { useAction } from '../hooks/useAction'
import { useQuery } from '../hooks/useQuery'
import { api } from '../services/api'
import FormModal from '../components/FormModal'
import { Badge, ConfirmDialog, DataTable, EmptyState, FilterBar, Meter, PageHeader, QueryBoundary } from '../components/ui'

const DETAIL_FIELDS = [
  { name: 'name', label: 'Shelter name', required: true },
  { name: 'location', label: 'Location', required: true },
  { name: 'total_capacity', label: 'Total capacity', type: 'number', min: 1, required: true },
  { name: 'contact', label: 'Contact information', placeholder: 'Name / phone / email' },
  locationField('location'),
]
const CREATE_FIELDS = [...DETAIL_FIELDS.slice(0, 3), { name: 'current_occupancy', label: 'Current occupancy', type: 'number', min: 0, required: true }, ...DETAIL_FIELDS.slice(3)]
const OCCUPANCY_FIELDS = [{ name: 'current_occupancy', label: 'Current occupancy', type: 'number', min: 0, required: true }]

const toneFor = (pct) => (pct >= 90 ? 'red' : pct >= 70 ? 'amber' : 'green')

export default function Shelters() {
  const [q, setQ] = useState('')
  const [modal, setModal] = useState(null)
  const deferredQ = useDeferredValue(q)
  const query = useQuery('/api/shelters', { q: deferredQ.trim(), limit: 500 })
  const run = useAction(query.reload)
  const close = () => setModal(null)

  return (
    <>
      <PageHeader
        title="Shelters"
        subtitle="Monitor capacity and occupancy. Occupancy can never exceed capacity."
        actions={<button type="button" className="btn btn-primary" onClick={() => setModal({ kind: 'create' })}>+ Register shelter</button>}
      />
      <FilterBar>
        <input type="search" aria-label="Search shelters" placeholder="Search name or location…" value={q} onChange={(e) => setQ(e.target.value)} />
      </FilterBar>
      <section className="card">
        <QueryBoundary query={query}>
          {(page) => (
            <DataTable
              caption="Shelters"
              rows={page.items}
              empty={<EmptyState title="No shelters registered">Register a shelter to track capacity.</EmptyState>}
              columns={[
                { header: 'Shelter', render: (r) => <><strong>{r.name}</strong><span className="sub">{r.location}</span></> },
                {
                  header: 'Occupancy',
                  render: (r) => (
                    <div style={{ minWidth: 150 }}>
                      <Meter value={r.current_occupancy} max={r.total_capacity} tone={toneFor(r.occupancy_percent)} label={`${r.name} occupancy`} />
                      <span className="sub">{fmt(r.current_occupancy)} / {fmt(r.total_capacity)} ({r.occupancy_percent}%)</span>
                    </div>
                  ),
                },
                { header: 'Places free', className: 'num', render: (r) => <Badge tone={r.available_capacity === 0 ? 'red' : 'green'}>{fmt(r.available_capacity)}</Badge> },
                { header: 'Contact', render: (r) => r.contact || <span className="muted">—</span> },
                {
                  header: 'Actions',
                  render: (r) => (
                    <div className="actions">
                      <button type="button" className="btn btn-sm" onClick={() => setModal({ kind: 'occupancy', row: r })}>Occupancy</button>
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
        <FormModal title="Register shelter" fields={CREATE_FIELDS} initial={{ current_occupancy: 0 }} submitLabel="Register"
          onSubmit={(v) => run(() => api.post('/api/shelters', v), 'Shelter registered', { inline: true })} onClose={close} />
      )}
      {modal?.kind === 'edit' && (
        <FormModal title="Edit shelter" fields={DETAIL_FIELDS} initial={modal.row}
          onSubmit={(v) => run(() => api.patch(`/api/shelters/${modal.row.id}`, v), 'Shelter updated', { inline: true })} onClose={close} />
      )}
      {modal?.kind === 'occupancy' && (
        <FormModal title={`Occupancy: ${modal.row.name}`} fields={OCCUPANCY_FIELDS} initial={modal.row}
          onSubmit={(v) => run(() => api.patch(`/api/shelters/${modal.row.id}/occupancy`, v), 'Occupancy updated', { inline: true })} onClose={close} />
      )}
      {modal?.kind === 'delete' && (
        <ConfirmDialog danger title="Delete shelter?" confirmLabel="Delete" message={`Delete "${modal.row.name}"?`}
          onConfirm={() => { const { row } = modal; close(); run(() => api.del(`/api/shelters/${row.id}`), 'Shelter deleted') }} onCancel={close} />
      )}
    </>
  )
}
