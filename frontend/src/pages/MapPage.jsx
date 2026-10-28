import { useEffect, useMemo, useState } from 'react'
import { REGIONS, STATUS_RULE_TEXT, SEVERITIES, fmt, fmtDateTime } from '../constants'
import { useAction } from '../hooks/useAction'
import { useLocalStorage } from '../hooks/useLocalStorage'
import { useHashParams } from '../hooks/useHashRoute'
import { useQuery } from '../hooks/useQuery'
import { api, qs } from '../services/api'
import Legend from '../components/map/Legend'
import MapBase from '../components/map/MapBase'
import { KINDS, LAYER_OPTIONS, USING_PUBLIC_OSM_TILES } from '../components/map/mapConfig'
import { Badge, Card, DataTable, EmptyState, ErrorState, PageHeader, Spinner } from '../components/ui'

const DEFAULT_LAYERS = ['disasters', 'external', 'shelters', 'inventory', 'allocations']
const keyOf = (f) => (f ? `${f.kind}-${f.id}` : null)

function Row({ label, children }) {
  return <><dt>{label}</dt><dd>{children}</dd></>
}

function WeatherBlock({ lat, lng }) {
  const [state, setState] = useState({ loading: false, data: null, error: '' })
  const load = async () => {
    setState({ loading: true, data: null, error: '' })
    try { setState({ loading: false, data: await api.get(`/api/external/weather${qs({ lat, lng })}`), error: '' }) } catch (e) { setState({ loading: false, data: null, error: e.message }) }
  }
  const w = state.data
  return (
    <div className="subpanel">
      <button type="button" className="btn" onClick={load} disabled={state.loading}>{state.loading ? 'Loading weather…' : 'Show local weather'}</button>
      {state.error && <p className="field-error" role="alert">{state.error}</p>}
      {w && (
        <dl className="detail-grid compact">
          <Row label="Now">{w.summary ?? '-'}, {w.temperature_c ?? '-'} °C, wind {w.wind_speed_kmh ?? '-'} km/h (gusts {w.wind_gusts_kmh ?? '-'})</Row>
          <Row label="Rain today">{w.today_precipitation_sum_mm ?? '-'} mm forecast</Row>
          <Row label="Source"><span className="tag-external">External observation / model forecast (unverified)</span> Open-Meteo · retrieved {fmtDateTime(w.retrieved_at)}{w.cached ? ' (cached)' : ''}</Row>
        </dl>
      )}
    </div>
  )
}

function NearbyPanel({ disaster, onRoute, onRadius }) {
  const [radius, setRadius] = useState(50)
  const [shelters, setShelters] = useState(null)
  const [volunteers, setVolunteers] = useState(null)
  const [busy, setBusy] = useState('')
  const [error, setError] = useState('')
  const run = useAction()

  const changeRadius = (value) => { setRadius(value); onRadius?.(Number(value) || 50) }

  async function loadShelters() {
    setBusy('shelters'); setError('')
    try { setShelters(await api.get(`/api/disasters/${disaster.id}/nearby-shelters${qs({ radius_km: radius, with_routes: true })}`)) } catch (e) { setError(e.message); setShelters(null) }
    setBusy('')
  }
  async function loadVolunteers() {
    setBusy('volunteers'); setError('')
    try { setVolunteers(await api.get(`/api/disasters/${disaster.id}/nearby-volunteers${qs({ radius_km: radius })}`)) } catch (e) { setError(e.message); setVolunteers(null) }
    setBusy('')
  }
  async function approve(c) {
    if (!window.confirm(`Assign ${c.name} (${c.suggested_role}) to this incident? Availability will be re-checked now.`)) return
    const r = await run(() => api.post(`/api/disasters/${disaster.id}/nearby-volunteers/approve-assignment`, { volunteer_id: c.volunteer_id, role: c.suggested_role, radius_km: Number(radius), confirm: true }), 'Volunteer assigned')
    if (r.ok) loadVolunteers()
  }

  return (
    <div className="subpanel">
      <div className="row">
        <label className="inline-label">Search radius (km)
          <input type="number" min="1" max="500" value={radius} onChange={(e) => changeRadius(e.target.value)} className="narrow" />
        </label>
        <button type="button" className="btn" onClick={loadShelters} disabled={Boolean(busy)}>{busy === 'shelters' ? 'Searching…' : 'Nearby shelters'}</button>
        <button type="button" className="btn" onClick={loadVolunteers} disabled={Boolean(busy)}>{busy === 'volunteers' ? 'Searching…' : 'Nearby volunteers'}</button>
      </div>
      {error && <p className="field-error" role="alert">{error}</p>}
      {shelters && (
        <div>
          <h4>Shelters with free capacity</h4>
          {shelters.items.length === 0 && <p className="muted">None within {shelters.radius_km} km. {Object.entries(shelters.excluded).map(([k, v]) => `${v} ${k}`).join(', ')}</p>}
          <ul className="list">
            {shelters.items.map((s) => (
              <li key={s.shelter_id}>
                <div>
                  <strong>{s.name}</strong> <span className="sub">{s.location}{s.approximate_location ? ' · approximate position' : ''}</span>
                  <span className="sub">{s.available_capacity} free of {s.total_capacity} ({s.current_occupancy} occupied) · updated {fmtDateTime(s.last_updated)}</span>
                  <span className="sub">≈ {s.straight_line_km} km straight line (not travel distance)
                    {s.route ? ` · by road ≈ ${s.route.distance_km} km, ≈ ${s.route.duration_min} min (routing estimate, OSRM)` : s.route_error ? ` · route unavailable: ${s.route_error}` : ''}</span>
                  <a href={s.directions_url} target="_blank" rel="noreferrer">Directions on openstreetmap.org</a>
                </div>
                {s.route?.geometry?.length > 1 && <button type="button" className="btn btn-sm" onClick={() => onRoute(s.route.geometry)}>Show route</button>}
              </li>
            ))}
          </ul>
          <small className="muted">{shelters.note}</small>
        </div>
      )}
      {volunteers && (
        <div>
          <h4>Suggested volunteers</h4>
          <p className="muted">{volunteers.ranking}. {volunteers.distance_note}</p>
          {volunteers.candidates.length === 0 && <p className="muted">No eligible volunteers. {Object.entries(volunteers.excluded).map(([k, v]) => `${v} ${k}`).join(', ')}</p>}
          <ul className="list">
            {volunteers.candidates.map((c) => (
              <li key={c.volunteer_id}>
                <div><strong>{c.name}</strong> <Badge tone="blue">score {c.score}</Badge><span className="sub">{c.reason}</span><span className="sub">Suggested role: {c.suggested_role}</span></div>
                <button type="button" className="btn btn-sm btn-primary" onClick={() => approve(c)}>Review &amp; assign</button>
              </li>
            ))}
          </ul>
          <small className="muted">Contact details are never shown here. Assigning needs your confirmation and re-checks availability.</small>
        </div>
      )}
    </div>
  )
}

function DetailPanel({ feature, onClose, onRoute, onRadius, reload }) {
  const [priority, setPriority] = useState(null)
  const run = useAction(reload)
  const isDisaster = feature.kind === 'disaster'

  useEffect(() => {
    if (!isDisaster) return undefined
    const c = new AbortController()
    api.get(`/api/intelligence/priority/${feature.id}`, c.signal).then(setPriority, () => setPriority(null))
    return () => c.abort()
  }, [feature.id, isDisaster])

  const d = feature.details ?? {}
  return (
    <aside className="map-detail card" aria-label="Selected item details">
      <header className="card-header"><h3>{feature.title}</h3><button type="button" className="btn btn-sm" onClick={onClose} aria-label="Close details">✕</button></header>
      <p className="basis">{feature.kind === 'external' ? <span className="tag-external">{feature.label}</span> : <span className="tag-record">{feature.label}</span>}</p>
      <dl className="detail-grid compact">
        <Row label="Type">{KINDS[feature.kind]?.label}</Row>
        <Row label="Status">{feature.status ? <Badge>{feature.status}</Badge> : '-'}{feature.severity && <> <Badge>{feature.severity}</Badge>{feature.kind === 'external' && <small className="muted"> (estimate)</small>}</>}</Row>
        <Row label="Source">{feature.source}</Row>
        <Row label="Time">{fmtDateTime(feature.timestamp)}</Row>
        {feature.retrieved_at && <Row label="Retrieved">{fmtDateTime(feature.retrieved_at)}</Row>}
        <Row label="Position">{feature.latitude.toFixed(4)}, {feature.longitude.toFixed(4)}{feature.approximate ? ' (approximate / inferred)' : ''}</Row>
        {Object.entries(d).filter(([k, v]) => v !== null && v !== '' && k !== 'description' && k !== 'priority_level' && k !== 'priority_score').map(([k, v]) => <Row key={k} label={k.replaceAll('_', ' ')}>{typeof v === 'number' ? fmt(v) : String(v)}</Row>)}
      </dl>
      {d.description && <p className="muted">{d.description}</p>}
      {feature.url && <p><a href={feature.url} target="_blank" rel="noreferrer">Open the source page</a></p>}
      {isDisaster && priority && (
        <div className="subpanel">
          <strong>Priority {priority.entry.score} ({priority.entry.level})</strong> <span className="tag-estimate">{priority.entry.label}</span>
          <p className="muted">{priority.entry.explanation}</p>
          <ul className="plain">{priority.entry.factors.map((f) => <li key={f.name}>{f.name}: {f.input} → {f.points}</li>)}</ul>
          <p className="status-rule"><strong>{priority.status_rule}</strong></p>
        </div>
      )}
      {isDisaster && <NearbyPanel disaster={feature} onRoute={onRoute} onRadius={onRadius} />}
      {(isDisaster || feature.kind === 'external') && <WeatherBlock lat={feature.latitude} lng={feature.longitude} />}
      {isDisaster && <p><a className="btn" href={`#/notifications?disaster=${feature.id}`}>Plan a notification campaign…</a></p>}
      {feature.kind === 'external' && (
        <div className="row">
          <button type="button" className="btn" onClick={() => run(() => api.post(`/api/external/events/${feature.id}/review`, { status: 'Reviewed' }), 'Marked reviewed')}>Mark reviewed</button>
          <button type="button" className="btn" onClick={() => run(() => api.post(`/api/external/events/${feature.id}/review`, { status: 'Dismissed' }), 'Dismissed')}>Dismiss</button>
          <button type="button" className="btn btn-primary" onClick={() => window.confirm('Create a NEW Monitoring incident from this unverified observation?') && run(() => api.post(`/api/external/events/${feature.id}/promote`, {}), 'Incident created (Monitoring)')}>Promote to incident…</button>
        </div>
      )}
      {feature.kind === 'shelter' && <p className="muted">Capacity is the last value recorded by an operator.</p>}
    </aside>
  )
}

export default function MapPage() {
  const params = useHashParams()
  const [layers, setLayers] = useLocalStorage('reliefsync.map.layers', DEFAULT_LAYERS)
  const [severity, setSeverity] = useLocalStorage('reliefsync.map.severity', '')
  const [source, setSource] = useLocalStorage('reliefsync.map.source', '')
  const [eventType, setEventType] = useLocalStorage('reliefsync.map.eventType', '')
  const [since, setSince] = useLocalStorage('reliefsync.map.since', '')
  const [until, setUntil] = useLocalStorage('reliefsync.map.until', '')
  const [incidentStatus, setIncidentStatus] = useLocalStorage('reliefsync.map.status', '')
  const [region, setRegion] = useLocalStorage('reliefsync.map.region', '')
  const [includeResolved, setIncludeResolved] = useLocalStorage('reliefsync.map.includeResolved', false)
  const [viewMode, setViewMode] = useLocalStorage('reliefsync.map.viewMode', 'heatmap')
  const [heatSeverityWeight, setHeatSeverityWeight] = useLocalStorage('reliefsync.map.heatSeverityWeight', 65)
  const [selected, setSelected] = useState(null)
  const [closedLink, setClosedLink] = useState('')
  const [route, setRoute] = useState(null)
  const [radiusKm, setRadiusKm] = useState(50)
  const [manualFocus, setManualFocus] = useState(null)
  const [fitTick, setFitTick] = useState(0)
  const [search, setSearch] = useState('')
  const [found, setFound] = useState(null)
  const [searchError, setSearchError] = useState('')
  const [searching, setSearching] = useState(false)
  const [refreshing, setRefreshing] = useState(false)
  const [refreshNote, setRefreshNote] = useState('')

  const box = REGIONS.find((r) => r.id === region)?.box
  const query = useQuery('/api/map/features', { layers: layers.join(','), severity, source, event_type: eventType, since, until, status: incidentStatus, include_resolved: includeResolved, ...(box ?? {}) })
  const features = useMemo(() => query.data?.features ?? [], [query.data])
  const filterKey = [layers.join(','), severity, source, eventType, since, until, incidentStatus, region, includeResolved].join('|')
  const fitSignal = `${filterKey}#${fitTick}` // changes only when filters change or "Fit all" is pressed, so a data refresh keeps the user's view

  // "#/map?disaster=3" (from other pages) selects that incident once the data has loaded.
  const linked = useMemo(() => (params.disaster ? features.find((x) => x.kind === 'disaster' && String(x.id) === params.disaster) ?? null : null), [params.disaster, features])
  const active = selected ?? (linked && closedLink !== params.disaster ? linked : null)
  const circle = active?.kind === 'disaster' ? { latitude: active.latitude, longitude: active.longitude, radius_km: radiusKm } : null
  const [linkId, linkLat, linkLng] = [linked?.id, linked?.latitude, linked?.longitude]
  const linkFocus = useMemo(() => (linkId === undefined ? null : { latitude: linkLat, longitude: linkLng, zoom: 10 }), [linkId, linkLat, linkLng])
  const focus = manualFocus ?? linkFocus

  const select = (f) => { setSelected(f); setRoute(null); setRadiusKm(50) }
  const closeDetail = () => { setSelected(null); setClosedLink(params.disaster ?? ''); setRoute(null) }
  const toggleLayer = (id) => setLayers((l) => (l.includes(id) ? l.filter((x) => x !== id) : [...l, id]))

  async function doSearch(e) {
    e.preventDefault()
    if (search.trim().length < 3) { setSearchError('Type at least 3 characters.'); return }
    setSearching(true); setSearchError(''); setFound(null)
    try { setFound(await api.get(`/api/geo/geocode${qs({ q: search })}`)) } catch (err) { setSearchError(err.message) }
    setSearching(false)
  }
  async function refreshExternal() {
    setRefreshing(true); setRefreshNote('')
    try {
      const r = await api.post('/api/external/refresh', { force: true })
      setRefreshNote(r.results.map((x) => `${x.source.toUpperCase()}: ${x.status}${x.message ? ` (${x.message})` : ''}`).join(' · '))
      query.reload()
    } catch (err) { setRefreshNote(err.message) }
    setRefreshing(false)
  }

  const eventTypes = ['earthquake', 'flood', 'tropical cyclone', 'wildfire', 'volcano', 'drought', 'severe storms', 'landslides', 'sea and lake ice', 'dust and haze']
  const missing = query.data?.missing_coordinates ?? {}
  const selectedKey = keyOf(active)

  return (
    <>
      <PageHeader
        title="Map"
        subtitle="Incidents, external observations, shelters, stores and destinations with known positions."
        actions={<>
          <button type="button" className="btn" onClick={query.reload} disabled={query.loading}>{query.loading ? 'Refreshing…' : 'Refresh map'}</button>
          <button type="button" className="btn btn-primary" onClick={refreshExternal} disabled={refreshing}>{refreshing ? 'Fetching…' : 'Fetch latest external data'}</button>
        </>}
      />
      <p className="status-rule"><strong>{STATUS_RULE_TEXT}</strong> The map shows active incidents only unless you tick “Include resolved”.</p>
      {refreshNote && <p className="muted" role="status">{refreshNote}</p>}

      <section className="card map-controls">
        <form className="row" onSubmit={doSearch} role="search">
          <input type="search" aria-label="Search for a place" placeholder="Search a place or address…" value={search} onChange={(e) => setSearch(e.target.value)} />
          <button type="submit" className="btn" disabled={searching}>{searching ? 'Searching…' : 'Go to place'}</button>
          <button type="button" className="btn" onClick={() => setFitTick((n) => n + 1)}>Fit all</button>
          <button type="button" className="btn" disabled={!navigator.geolocation} onClick={() => navigator.geolocation.getCurrentPosition((p) => setManualFocus({ latitude: p.coords.latitude, longitude: p.coords.longitude, zoom: 11 }), () => setSearchError('Could not read your location (permission denied?). Nothing was stored.'))}>Centre on me</button>
        </form>
        {searchError && <p className="field-error" role="alert">{searchError}</p>}
        {found && (
          <div className="picker-results">
            {found.candidates.length === 0 && <p className="muted">No place found.</p>}
            {found.ambiguous && <p className="form-error">Several different places match - pick the one you mean.</p>}
            {found.candidates.map((c) => <button type="button" className="btn btn-block" key={c.osm_ref + c.display_name} onClick={() => { setManualFocus({ latitude: c.latitude, longitude: c.longitude, zoom: 11 }); setFound(null) }}>{c.display_name}</button>)}
            <small className="muted">{found.attribution}</small>
          </div>
        )}
        <fieldset className="layer-toggles"><legend>Layers</legend>
          {LAYER_OPTIONS.map((l) => <label className="check" key={l.id}><input type="checkbox" checked={layers.includes(l.id)} onChange={() => toggleLayer(l.id)} />{l.label}</label>)}
        </fieldset>
        <div className="filters">
          <select aria-label="Severity" value={severity} onChange={(e) => setSeverity(e.target.value)}><option value="">Any severity</option>{SEVERITIES.map((s) => <option key={s}>{s}</option>)}</select>
          <select aria-label="External source" value={source} onChange={(e) => setSource(e.target.value)}><option value="">All external sources</option><option value="usgs">USGS</option><option value="gdacs">GDACS</option><option value="firms">NASA FIRMS</option><option value="eonet">NASA EONET</option></select>
          <select aria-label="External event type" value={eventType} onChange={(e) => setEventType(e.target.value)}><option value="">All event types</option>{eventTypes.map((t) => <option key={t}>{t}</option>)}</select>
          <select aria-label="Region" value={region} onChange={(e) => setRegion(e.target.value)}>{REGIONS.map((r) => <option key={r.id} value={r.id}>{r.label}</option>)}</select>
          <label className="check">From <input type="date" value={since} onChange={(e) => setSince(e.target.value)} /></label>
          <label className="check">To <input type="date" value={until} onChange={(e) => setUntil(e.target.value)} /></label>
          <select aria-label="Incident status" value={incidentStatus} onChange={(e) => setIncidentStatus(e.target.value)}><option value="">Any open status</option><option>Active</option><option>Monitoring</option><option>Resolved</option></select>
          <label className="check"><input type="checkbox" checked={includeResolved} onChange={(e) => setIncludeResolved(e.target.checked)} />Include resolved (history)</label>
          <label className="check">View <select aria-label="Map view" value={viewMode} onChange={(e) => setViewMode(e.target.value)}><option value="markers">Markers</option><option value="heatmap">Incident heatmap</option><option value="table">Table</option></select></label>
          {viewMode === 'heatmap' && <label className="check">Intensity weight: severity {heatSeverityWeight}% / population {100 - heatSeverityWeight}% <input aria-label="Heatmap severity weight" type="range" min="0" max="100" step="5" value={heatSeverityWeight} onChange={(e) => setHeatSeverityWeight(Number(e.target.value))} /></label>}
        </div>
        <p className="muted">Severity on external observations is an <strong>estimate</strong> derived from the source’s own magnitude/alert level.</p>
      </section>

      <div className={`map-layout ${active ? 'with-detail' : ''}`}>
        <section className="card map-card">
          {query.error && !query.data ? <ErrorState error={query.error} onRetry={query.reload} /> : !query.data ? <Spinner label="Loading map data…" /> : (
            <MapBase features={viewMode === 'table' ? [] : features} heatPoints={viewMode === 'heatmap' ? features.filter((f) => f.kind === 'disaster') : []} heatSeverityWeight={heatSeverityWeight} selectedKey={selectedKey} onSelect={select} circle={circle} route={route} focus={focus} fitSignal={fitSignal} height={560} />
          )}
          {viewMode === 'heatmap' && <div className="heat-legend"><strong>Reported-incident intensity</strong><span>Red = higher combined rule weight: {heatSeverityWeight}% recorded severity + {100 - heatSeverityWeight}% log-scaled reported affected population. Imported observations remain separate markers. This is a visualization, not a future-risk probability.</span></div>}
          {viewMode === 'heatmap' && features.filter((f) => f.kind === 'disaster').length === 0 && <p className="muted">No eligible reported incidents with coordinates match the current filters.</p>}
          <Legend />
          <p className="muted map-foot">
            {query.data ? `${query.data.count} item(s) with a known position · generated ${fmtDateTime(query.data.generated_at)}` : ''}
            {Object.keys(missing).length > 0 && ` · not shown (no coordinates yet): ${Object.entries(missing).map(([k, v]) => `${v} ${k}`).join(', ')}`}
            {query.data?.volunteers_hidden && ' · volunteer positions are visible to operators only'}
          </p>
          {USING_PUBLIC_OSM_TILES && <p className="muted map-foot">Map tiles: the public OpenStreetMap server (light use only). Configure <code>VITE_MAP_TILE_URL</code> for production.</p>}
        </section>
        {active && <DetailPanel key={keyOf(active)} feature={active} onClose={closeDetail} onRoute={setRoute} onRadius={setRadiusKm} reload={() => { query.reload(); closeDetail() }} />}
      </div>
      {viewMode === 'table' && <Card title="Filtered map records"><DataTable caption="Map records" rows={features} rowKey={(f) => `${f.kind}-${f.id}`} empty={<EmptyState title="No eligible incidents">No records with known coordinates match these filters.</EmptyState>} columns={[
        { header: 'Event', render: (f) => <><strong>{f.title}</strong><span className="sub">{f.kind} · {f.details?.event_type ?? f.status}</span></> },
        { header: 'Severity', render: (f) => f.severity ?? '-' },
        { header: 'Reported affected', render: (f) => f.kind === 'disaster' ? fmt(f.details?.people_affected) : 'Not reported' },
        { header: 'Source / observed', render: (f) => <>{f.source}<span className="sub">{fmtDateTime(f.timestamp)}</span></> },
        { header: '', className: 'actions', render: (f) => <button type="button" className="btn btn-sm" onClick={() => select(f)}>Details</button> },
      ]} /></Card>}
    </>
  )
}

