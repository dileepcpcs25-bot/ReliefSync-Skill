import { fmt, fmtDate, fmtDateTime, plural } from '../constants'
import { useQuery } from '../hooks/useQuery'
import { Badge, Card, DataTable, EmptyState, Meter, PageHeader, QueryBoundary, StatCard } from '../components/ui'

export default function Dashboard() {
  const query = useQuery('/api/dashboard')
  return <>
    <PageHeader title="Operations overview" subtitle="Live figures aggregated from the ReliefSync database." actions={<button type="button" className="btn" onClick={query.reload} disabled={query.loading}>{query.loading ? 'Refreshing...' : 'Refresh'}</button>} />
    <QueryBoundary query={query}>{(d) => <DashboardBody d={d} />}</QueryBoundary>
  </>
}

function DashboardBody({ d }) {
  const { disasters: ds, volunteers: v, assignments: a, inventory: inv, shelters: sh, allocations: al } = d
  return <>
    <div className="grid grid-stats">
      <StatCard label="Active disasters" value={fmt(ds.active)} hint={`${fmt(ds.total)} total / ${fmt(ds.monitoring)} monitoring`} tone="red" />
      <StatCard label="Critical / High priority" value={`${fmt(ds.critical_priority)} / ${fmt(ds.high_priority)}`} hint="Open incidents by rule-based score" tone="red" />
      <StatCard label="Volunteers available" value={`${fmt(v.available)} / ${fmt(v.total)}`} hint={`${fmt(v.assigned)} deployed`} tone="green" />
      <StatCard label="Active assignments" value={fmt(a.active)} hint={`${fmt(a.total)} all-time`} />
      <StatCard label="Low-stock items" value={fmt(inv.low_stock)} hint={`${plural(inv.items, 'item')} / ${plural(inv.total_units, 'unit')}`} tone={inv.low_stock ? 'amber' : undefined} />
      <StatCard label="Shelter places free" value={fmt(sh.available_capacity)} hint={`${plural(sh.total, 'shelter')} / ${sh.occupancy_percent}% full`} tone="green" />
      <StatCard label="Active allocations" value={fmt(al.active)} hint={`${fmt(al.delivered)} delivered / ${fmt(al.total)} total`} />
      <StatCard label="MongoDB archive" value={fmt(d.mongo_archive?.observation_count ?? 0)} hint={d.mongo_archive?.connected ? `Connected / ${d.mongo_archive.database}` : "Offline; start Docker Compose to enable archive"} tone={d.mongo_archive?.connected ? "green" : "amber"} />
    </div>
    <div className="grid grid-2">
      <Card title="Priority overview" action={<a href="#/priority">View ranking</a>}>
        {d.top_priorities.length === 0 ? <EmptyState title="No open incidents">Report a disaster to see it ranked here.</EmptyState> : <ul className="list">{d.top_priorities.map((p) => <li key={p.disaster.id}><span><strong>#{p.rank} {p.disaster.disaster_type}</strong><span className="sub">{p.disaster.location} / {fmt(p.disaster.people_affected)} affected</span></span><span className="row"><Badge>{p.level}</Badge><strong>{p.score}</strong></span></li>)}</ul>}
      </Card>
      <Card title="Recent reports" action={<a href="#/disasters">All disasters</a>}>
        <DataTable caption="Most recently reported disasters" rows={d.recent_disasters} empty={<EmptyState title="No disasters reported yet" />} columns={[
          { header: 'Incident', render: (r) => <>{r.disaster_type}<span className="sub">{r.location}</span></> },
          { header: 'Status', render: (r) => <Badge>{r.status}</Badge> },
          { header: 'Reported', render: (r) => fmtDate(r.created_at) },
        ]} />
      </Card>
      <Card title="Regional activity" action={<a href="#/external">Open regional data</a>}>
        <p className="muted">Counts use stored, geolocated records. Broad regional views may overlap. Public sources have different historical coverage; this is not an exhaustive world disaster census.</p>
        {d.observation_coverage?.first_observed_at && <p className="sub">Stored observation dates: {fmtDate(d.observation_coverage.first_observed_at)} to {fmtDate(d.observation_coverage.last_observed_at)} / {fmt(d.observation_coverage.unique_observations)} unique records worldwide</p>}
        <section className="region-heatmap" aria-label="Regional heatmap of stored public disaster observations">
          {(d.regional_overview ?? []).map((r) => {
            const peak = Math.max(1, ...(d.regional_overview ?? []).map((x) => x.observations))
            const strength = Math.sqrt(r.observations / peak)
            return <a className="region-heatmap-cell" href={`#/external?region=${encodeURIComponent(r.id)}`} key={r.id} style={{ '--heat': strength }} title={`${r.label}: ${fmt(r.observations)} observations`}>
              <span>{r.label}</span><strong>{fmt(r.observations)}</strong><small>observations</small>
              <span className="region-active">{fmt(r.active_incidents)} active reported</span>
            </a>
          })}
        </section>
        <DataTable caption="Activity by broad geographic region" rows={d.regional_overview ?? []} empty={<EmptyState title="No regional records yet">Refresh free public sources or add located operational records.</EmptyState>} columns={[
          { header: 'Region', render: (r) => <a href={`#/external?region=${encodeURIComponent(r.id)}`}>{r.label}</a> },
          { header: 'Observations', key: 'observations' }, { header: 'Active incidents', key: 'active_incidents' },
          { header: 'Volunteers', key: 'volunteers' }, { header: 'Shelters', key: 'shelters' },
          { header: 'Latest source record', render: (r) => fmtDateTime(r.latest_observation) },
        ]} />
      </Card>
      <Card title="MongoDB archive status" action={<a href="#/external">Manage source observations</a>}>
        <p><Badge tone={d.mongo_archive?.connected ? "green" : "amber"}>{d.mongo_archive?.connected ? "Connected" : "Not connected"}</Badge></p>
        <p className="muted">{d.mongo_archive?.connected ? `${fmt(d.mongo_archive.observation_count)} source observations archived in ${d.mongo_archive.database}.` : "MongoDB stores a separate archive of external observations. Start Docker Desktop and run docker compose up -d mongodb from the project folder, then refresh public sources to archive records."}</p>
      </Card>
      <Card title="Worldwide external observations" action={<a href="#/external">Open all observations</a>}>
        <strong>{fmt(d.external_observations.total)} stored observations</strong>
        <p className="sub">By source: {Object.entries(d.external_observations).filter(([key]) => key !== 'total').map(([source, count]) => `${source.toUpperCase()} ${fmt(count)}`).join(' / ') || 'No source records yet'}</p>
        <DataTable caption="Recent worldwide external observations" rows={d.recent_external_events} empty={<EmptyState title="No external observations stored">Open External Observations and refresh a public source.</EmptyState>} columns={[
          { header: 'Observed', render: (e) => fmtDateTime(e.observed_at) },
          { header: 'Event', render: (e) => <><strong>{e.title}</strong><span className="sub">{e.event_type}{e.country ? ` / ${e.country}` : ''}</span></> },
          { header: 'Source', key: 'source' },
          { header: '', className: 'actions', render: (e) => e.url ? <a className="btn btn-sm" href={e.url} target="_blank" rel="noreferrer">Source</a> : null },
        ]} />
      </Card>
      <Card title="Inventory alerts" action={<a href="#/inventory">Inventory</a>}>
        {d.low_stock_items.length === 0 ? <EmptyState title="No low-stock items" /> : <ul className="list">{d.low_stock_items.map((i) => <li key={i.id}><span>{i.name}<span className="sub">{i.storage_location} / threshold {fmt(i.low_stock_threshold)}</span></span><Badge tone="amber">{fmt(i.quantity)} {i.unit}</Badge></li>)}</ul>}
        {d.inventory_by_category.length > 0 && <><h4 className="muted" style={{ margin: '14px 0 6px' }}>Stock by category</h4><ul className="list">{d.inventory_by_category.map((c) => <li key={c.category}><span>{c.category}</span><span className="muted">{plural(c.units, 'unit')} / {plural(c.items, 'item')}</span></li>)}</ul></>}
      </Card>
      <Card title="Capacity & availability">
        <p className="muted">Shelter occupancy</p><Meter value={sh.occupancy} max={sh.total_capacity} tone={sh.occupancy_percent >= 90 ? 'red' : sh.occupancy_percent >= 70 ? 'amber' : 'green'} label="Shelter occupancy" />
        <p className="sub">{fmt(sh.occupancy)} of {fmt(sh.total_capacity)} places in use</p>
        <p className="muted" style={{ marginTop: 16 }}>Volunteers deployed</p><Meter value={v.assigned} max={v.total} tone="blue" label="Volunteers deployed" />
        <p className="sub">{fmt(v.assigned)} of {fmt(v.total)} registered volunteers assigned</p>
      </Card>
    </div>
  </>
}

