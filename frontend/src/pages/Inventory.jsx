import { useDeferredValue, useState } from 'react'
import { CATEGORIES, fmt, locationField } from '../constants'
import { useAction } from '../hooks/useAction'
import { useQuery } from '../hooks/useQuery'
import { api } from '../services/api'
import FormModal from '../components/FormModal'
import { Badge, ConfirmDialog, DataTable, EmptyState, FilterBar, PageHeader, QueryBoundary } from '../components/ui'

const DETAIL_FIELDS = [
  { name: 'name', label: 'Item name', required: true },
  { name: 'category', label: 'Category', type: 'select', options: CATEGORIES, required: true },
  { name: 'unit', label: 'Unit', required: true, placeholder: 'kg, litres, boxes…' },
  { name: 'storage_location', label: 'Storage location', required: true },
  { name: 'low_stock_threshold', label: 'Low-stock threshold', type: 'number', min: 0, required: true, help: 'Flagged when quantity is at or below this level.' },
  locationField('storage_location'),
]
const CREATE_FIELDS = [...DETAIL_FIELDS.slice(0, 3), { name: 'quantity', label: 'Opening quantity', type: 'number', min: 0, required: true }, ...DETAIL_FIELDS.slice(3)]
const ADJUST_FIELDS = [
  { name: 'delta', label: 'Change in quantity', type: 'number', required: true, help: 'Positive to add stock, negative to remove. Stock can never go below zero.' },
  { name: 'reason', label: 'Reason', placeholder: 'Donation received, damaged goods…' },
]

export default function Inventory() {
  const [q, setQ] = useState('')
  const [category, setCategory] = useState('')
  const [location, setLocation] = useState('')
  const [lowOnly, setLowOnly] = useState(false)
  const [modal, setModal] = useState(null)
  const deferredQ = useDeferredValue(q)
  const deferredLocation = useDeferredValue(location)
  const query = useQuery('/api/inventory', { q: deferredQ.trim(), category, storage_location: deferredLocation.trim(), low_stock: lowOnly, limit: 500 })
  const run = useAction(query.reload)
  const close = () => setModal(null)

  return (
    <>
      <PageHeader
        title="Inventory"
        subtitle="Track relief supplies. Quantities change only through adjustments and confirmed allocations."
        actions={<button type="button" className="btn btn-primary" onClick={() => setModal({ kind: 'create' })}>+ Add item</button>}
      />
      <FilterBar>
        <input type="search" aria-label="Search items" placeholder="Search items…" value={q} onChange={(e) => setQ(e.target.value)} />
        <select aria-label="Filter by category" value={category} onChange={(e) => setCategory(e.target.value)}>
          <option value="">All categories</option>
          {CATEGORIES.map((c) => <option key={c}>{c}</option>)}
        </select>
        <input type="text" aria-label="Filter by storage location" placeholder="Storage location…" value={location} onChange={(e) => setLocation(e.target.value)} />
        <label className="check"><input type="checkbox" checked={lowOnly} onChange={(e) => setLowOnly(e.target.checked)} /> Low stock only</label>
      </FilterBar>
      <section className="card">
        <QueryBoundary query={query}>
          {(page) => (
            <DataTable
              caption="Inventory items"
              rows={page.items}
              empty={<EmptyState title="No inventory items">Add supplies or relax the filters.</EmptyState>}
              columns={[
                { header: 'Item', render: (r) => <strong>{r.name}</strong> },
                { header: 'Category', render: (r) => <Badge tone="gray">{r.category}</Badge> },
                { header: 'Quantity', className: 'num', render: (r) => <>{fmt(r.quantity)} {r.unit} {r.is_low_stock && <Badge tone="amber">Low stock</Badge>}</> },
                { header: 'Threshold', className: 'num', render: (r) => fmt(r.low_stock_threshold) },
                { header: 'Storage', key: 'storage_location' },
                {
                  header: 'Actions',
                  render: (r) => (
                    <div className="actions">
                      <button type="button" className="btn btn-sm" onClick={() => setModal({ kind: 'adjust', row: r })}>Adjust</button>
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
        <FormModal title="Add inventory item" fields={CREATE_FIELDS} initial={{ low_stock_threshold: 0, quantity: 0 }} submitLabel="Add"
          onSubmit={(v) => run(() => api.post('/api/inventory', v), 'Item added', { inline: true })} onClose={close} />
      )}
      {modal?.kind === 'edit' && (
        <FormModal title="Edit item details" fields={DETAIL_FIELDS} initial={modal.row}
          onSubmit={(v) => run(() => api.patch(`/api/inventory/${modal.row.id}`, v), 'Item updated', { inline: true })} onClose={close} />
      )}
      {modal?.kind === 'adjust' && (
        <FormModal title={`Adjust stock: ${modal.row.name}`} fields={ADJUST_FIELDS} submitLabel="Apply"
          onSubmit={(v) => run(() => api.patch(`/api/inventory/${modal.row.id}/adjust`, v), 'Stock adjusted', { inline: true })} onClose={close} />
      )}
      {modal?.kind === 'delete' && (
        <ConfirmDialog danger title="Delete item?" confirmLabel="Delete"
          message={`Delete "${modal.row.name}"? Items with allocation history cannot be deleted.`}
          onConfirm={() => { const { row } = modal; close(); run(() => api.del(`/api/inventory/${row.id}`), 'Item deleted') }} onCancel={close} />
      )}
    </>
  )
}
