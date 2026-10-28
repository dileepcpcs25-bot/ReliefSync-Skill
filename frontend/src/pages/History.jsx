import { useState } from 'react'
import { REGIONS, fmtDateTime } from '../constants'
import { useQuery } from '../hooks/useQuery'
import { Badge, Card, DataTable, EmptyState, FilterBar, PageHeader, QueryBoundary, Spinner } from '../components/ui'

export default function History() {
  const [since, setSince] = useState('')
  const [until, setUntil] = useState('')
  const [region, setRegion] = useState('')
  const [radius, setRadius] = useState(100)
  const [selected, setSelected] = useState(null)
  const box = REGIONS.find((r) => r.id === region)?.box
  const events = useQuery('/api/history/events', { since, until, limit: 300, ...(box ?? {}) })
  const resources = useQuery(selected ? `/api/history/events/${encodeURIComponent(selected.key)}/resources` : '/api/history/events',
    selected ? { radius_km: radius } : undefined)
  return <>
    <PageHeader title="Past events & nearby resources" subtitle="Select a stored past event to find currently recorded volunteers and shelters around it." />
    <p className="notice"><strong>Historical event records.</strong> Volunteer availability, assignments, and shelter capacity below are current database values. ReliefSync does not have past-state snapshots. Distances are straight-line estimates; unknown locations are excluded.</p>
    <FilterBar>
      <label className="check">From <input type="date" value={since} onChange={(e) => { setSince(e.target.value); setSelected(null) }} /></label>
      <label className="check">To <input type="date" value={until} onChange={(e) => { setUntil(e.target.value); setSelected(null) }} /></label>
      <select aria-label="Region" value={region} onChange={(e) => { setRegion(e.target.value); setSelected(null) }}>{REGIONS.map((r) => <option key={r.id} value={r.id}>{r.label}</option>)}</select>
      <label className="check">Resource radius (km) <input type="number" min="1" max="2000" value={radius} onChange={(e) => setRadius(Math.max(1, Math.min(2000, Number(e.target.value) || 1)))} /></label>
    </FilterBar>
    <div className="history-layout">
      <Card title="Stored historical events">
        <QueryBoundary query={events}>{(page) => <DataTable caption="Stored past events" rows={page.items} rowKey={(e) => e.key}
          empty={<EmptyState title="No stored events">Refresh external observations or record incidents to build this history. No sample events are generated.</EmptyState>}
          columns={[
            { header: 'Event date', render: (e) => <>{fmtDateTime(e.event_at)}<span className="sub">{e.date_basis}</span></> },
            { header: 'Event', render: (e) => <><strong>{e.title}</strong><span className="sub">{e.event_type} · {e.location || 'location not named'}</span></> },
            { header: 'Record', render: (e) => <><Badge>{e.event_source === 'local' ? e.status : 'External'}</Badge><span className="sub">{e.source}</span></> },
            { header: '', className: 'actions', render: (e) => <button type="button" className="btn btn-sm btn-primary" onClick={() => setSelected(e)}>Find nearby</button> },
          ]} />}</QueryBoundary>
        <p className="muted">{events.data ? `${events.data.total} stored event record(s).` : ''} Only records already saved in ReliefSync are listed.</p>
      </Card>
      <Card title={selected ? `Resources near ${selected.title}` : 'Select an event'}>
        {!selected ? <EmptyState title="Choose a past event">Use “Find nearby” on an event to see recorded volunteers and shelters within the selected radius.</EmptyState> : resources.loading ? <Spinner /> : <QueryBoundary query={resources}>{(data) => <>
          <p className="muted">Event time: {fmtDateTime(data.event.event_at)} · search radius: {data.radius_km} km</p>
          <h3>Volunteers <span className="sub">{data.volunteers.length} with coordinates</span></h3>
          <DataTable caption="Current volunteers near selected historical event" rows={data.volunteers} columns={[
            { header: 'Volunteer', render: (v) => <><strong>{v.name}</strong><span className="sub">{v.skills || 'No skills recorded'}</span></> },
            { header: 'Current area', accessor: 'location' },
            { header: 'Current availability', render: (v) => <>{v.availability}{v.assigned ? ' · active assignment' : ''}</> },
            { header: 'Distance', render: (v) => `${v.distance_km} km` },
          ]} empty={<EmptyState title="No located volunteers in range">No volunteer with known coordinates is within this radius.</EmptyState>} />
          <h3>Shelters <span className="sub">{data.shelters.length} with coordinates</span></h3>
          <DataTable caption="Current shelters near selected historical event" rows={data.shelters} columns={[
            { header: 'Shelter', render: (s) => <><strong>{s.name}</strong><span className="sub">{s.location}</span></> },
            { header: 'Current capacity', render: (s) => `${s.available_capacity} available / ${s.total_capacity}` },
            { header: 'Distance', render: (s) => `${s.distance_km} km` },
          ]} empty={<EmptyState title="No located shelters in range">No shelter with known coordinates is within this radius.</EmptyState>} />
          <p className="muted">Not matched due to unknown coordinates: {data.unlocated.volunteers} volunteer(s), {data.unlocated.shelters} shelter(s). {data.distance_note}</p>
          <p className="muted">{data.resource_time_note}</p>
        </>}</QueryBoundary>}
      </Card>
    </div>
    <div className="source-links">
      <strong>Regional satellite and disaster portals</strong>
      <span>NASA event metadata and USGS/GDACS observations load through the backend. India-specific ISRO/NRSC products are exposed through official portals; downloads may require an account or agency access.</span>
      <a href="https://bhuvan.nrsc.gov.in/" target="_blank" rel="noreferrer">ISRO / NRSC Bhuvan (India geospatial & disaster services)</a>
      <a href="https://mosdac.gov.in/" target="_blank" rel="noreferrer">ISRO MOSDAC (satellite weather/ocean data)</a>
      <a href="https://eonet.gsfc.nasa.gov/docs/v3" target="_blank" rel="noreferrer">NASA EONET API documentation</a>
    </div>
  </>
}





