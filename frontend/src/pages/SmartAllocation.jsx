import { useState } from 'react'
import { fmt } from '../constants'
import { useAction } from '../hooks/useAction'
import { useQuery } from '../hooks/useQuery'
import { api } from '../services/api'
import FormModal from '../components/FormModal'
import { Badge, Card, EmptyState, PageHeader, QueryBoundary } from '../components/ui'

export default function SmartAllocation() {
  const query = useQuery('/api/intelligence/recommendations')
  const run = useAction(query.reload)
  const [selected, setSelected] = useState(null)

  const fields = selected && [
    { name: 'quantity', label: `Quantity (${selected.unit})`, type: 'number', min: 1, max: selected.available_quantity, required: true, help: `Suggested ${fmt(selected.suggested_quantity)}; ${fmt(selected.available_quantity)} in stock.` },
    { name: 'destination', label: 'Destination', required: true },
    { name: 'position', type: 'location', label: 'Destination on the map (optional)', searchFrom: 'destination', names: { lat: 'destination_latitude', lng: 'destination_longitude', source: 'destination_location_source', approx: null } },
  ]

  return (
    <>
      <PageHeader
        title="Smart allocation"
        subtitle="Suggested distributions based on priority, population affected and current stock. Nothing is deducted until you confirm."
        actions={<button type="button" className="btn" onClick={query.reload} disabled={query.loading}>Refresh suggestions</button>}
      />
      <QueryBoundary query={query}>
        {(res) => (
          <>
            {res.items.length === 0 ? (
              <Card><EmptyState title="No recommendations">Either there are no open disasters with people affected, no stock in a supported category, or all estimated needs are already allocated.</EmptyState></Card>
            ) : (
              <div className="grid grid-2">
                {res.items.map((r) => (
                  <Card key={`${r.disaster_id}-${r.item_id}`}>
                    <div className="rec-card">
                      <div className="row" style={{ justifyContent: 'space-between' }}>
                        <strong>{r.disaster_label}</strong>
                        <Badge>{r.priority_level}</Badge>
                      </div>
                      <p><strong>{fmt(r.suggested_quantity)} {r.unit}</strong> of {r.item_name} <Badge tone="gray">{r.category}</Badge></p>
                      <p className="muted">{r.reasoning}</p>
                      <p className="sub">Destination: {r.destination}</p>
                      <div><button type="button" className="btn btn-primary" onClick={() => setSelected(r)}>Review &amp; confirm</button></div>
                    </div>
                  </Card>
                ))}
              </div>
            )}
          </>
        )}
      </QueryBoundary>

      {selected && (
        <FormModal
          title={`Confirm allocation: ${selected.item_name}`}
          fields={fields}
          initial={{ quantity: selected.suggested_quantity, destination: selected.destination }}
          submitLabel="Confirm allocation"
          onSubmit={(v) =>
            run(
              () => api.post('/api/allocations', { disaster_id: selected.disaster_id, item_id: selected.item_id, quantity: v.quantity, destination: v.destination, destination_latitude: v.destination_latitude, destination_longitude: v.destination_longitude, destination_location_source: v.destination_location_source, notes: 'Created from a Smart Allocation recommendation' }),
              'Allocation confirmed and stock deducted',
              { inline: true },
            )
          }
          onClose={() => setSelected(null)}
        />
      )}
    </>
  )
}
