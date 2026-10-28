import { useState } from 'react'
import { fmtDate } from '../constants'
import { useAction } from '../hooks/useAction'
import { useQuery } from '../hooks/useQuery'
import { api } from '../services/api'
import FormModal from '../components/FormModal'
import { Badge, ConfirmDialog, DataTable, EmptyState, FilterBar, PageHeader, QueryBoundary } from '../components/ui'

export default function Assignments() {
  const [status, setStatus] = useState('')
  const [modal, setModal] = useState(null)
  const list = useQuery('/api/assignments', { status, limit: 500 })
  const volunteers = useQuery('/api/volunteers', { availability: 'Available', limit: 500 })
  const disasters = useQuery('/api/disasters', { limit: 500 })
  const run = useAction(() => {
    list.reload()
    volunteers.reload()
  })
  const close = () => setModal(null)

  const volunteerOptions = (volunteers.data?.items ?? []).map((v) => ({ value: v.id, label: `${v.name} - ${v.location}` }))
  const disasterOptions = (disasters.data?.items ?? [])
    .filter((d) => d.status !== 'Resolved')
    .map((d) => ({ value: d.id, label: `${d.disaster_type} - ${d.location} (${d.severity})` }))
  const canAssign = volunteerOptions.length > 0 && disasterOptions.length > 0

  const fields = [
    { name: 'volunteer_id', label: 'Volunteer (available only)', type: 'select-number', options: volunteerOptions, required: true },
    { name: 'disaster_id', label: 'Disaster', type: 'select-number', options: disasterOptions, required: true },
    { name: 'role', label: 'Role', required: true, placeholder: 'Medic, driver, shelter lead…' },
  ]

  const finish = (row, next) => {
    close()
    run(() => api.patch(`/api/assignments/${row.id}/status`, { status: next }), `Assignment ${next.toLowerCase()}`)
  }

  return (
    <>
      <PageHeader
        title="Assignments"
        subtitle="Deploy available volunteers to disasters. Completing or cancelling frees the volunteer."
        actions={<button type="button" className="btn btn-primary" disabled={!canAssign} onClick={() => setModal({ kind: 'create' })}>+ Assign volunteer</button>}
      />
      {!canAssign && !volunteers.loading && !disasters.loading && (
        <p className="muted">Assigning needs at least one available volunteer and one unresolved disaster.</p>
      )}
      <FilterBar>
        <select aria-label="Filter by status" value={status} onChange={(e) => setStatus(e.target.value)}>
          <option value="">All statuses</option>
          <option>Active</option>
          <option>Completed</option>
          <option>Cancelled</option>
        </select>
      </FilterBar>
      <section className="card">
        <QueryBoundary query={list}>
          {(page) => (
            <DataTable
              caption="Volunteer assignments"
              rows={page.items}
              empty={<EmptyState title="No assignments" >Assign an available volunteer to a disaster.</EmptyState>}
              columns={[
                { header: 'Volunteer', render: (r) => <strong>{r.volunteer_name}</strong> },
                { header: 'Disaster', key: 'disaster_label' },
                { header: 'Role', key: 'role' },
                { header: 'Status', render: (r) => <Badge>{r.status}</Badge> },
                { header: 'Assigned', render: (r) => fmtDate(r.created_at) },
                {
                  header: 'Actions',
                  render: (r) =>
                    r.status === 'Active' ? (
                      <div className="actions">
                        <button type="button" className="btn btn-sm" onClick={() => finish(r, 'Completed')}>Complete</button>
                        <button type="button" className="btn btn-sm btn-danger" onClick={() => setModal({ kind: 'cancel', row: r })}>Cancel</button>
                      </div>
                    ) : null,
                },
              ]}
            />
          )}
        </QueryBoundary>
      </section>

      {modal?.kind === 'create' && (
        <FormModal title="Assign volunteer" fields={fields} submitLabel="Assign"
          onSubmit={(v) => run(() => api.post('/api/assignments', v), 'Volunteer assigned', { inline: true })} onClose={close} />
      )}
      {modal?.kind === 'cancel' && (
        <ConfirmDialog danger title="Cancel assignment?" confirmLabel="Cancel assignment"
          message={`${modal.row.volunteer_name} will be released and become available again.`}
          onConfirm={() => finish(modal.row, 'Cancelled')} onCancel={close} />
      )}
    </>
  )
}
