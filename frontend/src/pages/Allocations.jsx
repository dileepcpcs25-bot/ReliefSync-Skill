import { useState } from 'react'
import { ALLOCATION_STATUSES, fmt, fmtDate } from '../constants'
import { useAction } from '../hooks/useAction'
import { useQuery } from '../hooks/useQuery'
import { api } from '../services/api'
import FormModal from '../components/FormModal'
import { Badge, ConfirmDialog, DataTable, EmptyState, FilterBar, PageHeader, QueryBoundary } from '../components/ui'

const EDIT_FIELDS = [
  { name: 'destination', label: 'Destination', required: true },
  { name: 'notes', label: 'Notes', type: 'textarea' },
]
const NEXT = { Confirmed: ['In Transit', 'Delivered'], 'In Transit': ['Delivered'] }

export default function Allocations() {
  const [status, setStatus] = useState('')
  const [modal, setModal] = useState(null)
  const query = useQuery('/api/allocations', { status, limit: 500 })
  const run = useAction(query.reload)
  const close = () => setModal(null)

  const setStatusTo = (row, next) => run(() => api.patch(`/api/allocations/${row.id}/status`, { status: next }), `Allocation marked ${next}`)

  return (
    <>
      <PageHeader title="Allocations" subtitle="Confirmed distributions. Cancelling an open allocation returns its stock exactly once." />
      <FilterBar>
        <select aria-label="Filter by status" value={status} onChange={(e) => setStatus(e.target.value)}>
          <option value="">All statuses</option>
          {ALLOCATION_STATUSES.map((s) => <option key={s}>{s}</option>)}
        </select>
      </FilterBar>
      <section className="card">
        <QueryBoundary query={query}>
          {(page) => (
            <DataTable
              caption="Resource allocations"
              rows={page.items}
              empty={<EmptyState title="No allocations yet">Confirm a recommendation on the Smart Allocation page.</EmptyState>}
              columns={[
                { header: 'Disaster', key: 'disaster_label' },
                { header: 'Item', key: 'item_name' },
                { header: 'Quantity', className: 'num', render: (r) => `${fmt(r.quantity)} ${r.item_unit}` },
                { header: 'Destination', render: (r) => <>{r.destination}{r.notes && <span className="sub">{r.notes}</span>}</> },
                { header: 'Status', render: (r) => <Badge>{r.status}</Badge> },
                { header: 'Created', render: (r) => fmtDate(r.created_at) },
                {
                  header: 'Actions',
                  render: (r) => (
                    <div className="actions">
                      {(NEXT[r.status] ?? []).map((n) => (
                        <button key={n} type="button" className="btn btn-sm" onClick={() => setStatusTo(r, n)}>Mark {n}</button>
                      ))}
                      {NEXT[r.status] && (
                        <>
                          <button type="button" className="btn btn-sm" onClick={() => setModal({ kind: 'edit', row: r })}>Edit</button>
                          <button type="button" className="btn btn-sm btn-danger" onClick={() => setModal({ kind: 'cancel', row: r })}>Cancel</button>
                        </>
                      )}
                    </div>
                  ),
                },
              ]}
            />
          )}
        </QueryBoundary>
      </section>

      {modal?.kind === 'edit' && (
        <FormModal title="Edit allocation" fields={EDIT_FIELDS} initial={modal.row}
          onSubmit={(v) => run(() => api.patch(`/api/allocations/${modal.row.id}`, v), 'Allocation updated', { inline: true })} onClose={close} />
      )}
      {modal?.kind === 'cancel' && (
        <ConfirmDialog danger title="Cancel allocation?" confirmLabel="Cancel allocation"
          message={`${fmt(modal.row.quantity)} ${modal.row.item_unit} of ${modal.row.item_name} will be returned to stock. This cannot be undone.`}
          onConfirm={() => { const { row } = modal; close(); setStatusTo(row, 'Cancelled') }} onCancel={close} />
      )}
    </>
  )
}
