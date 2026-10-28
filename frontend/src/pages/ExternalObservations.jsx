import { useEffect, useRef, useState } from 'react'
import { EXTERNAL_SOURCES, REGIONS, SEVERITIES, fmtDateTime } from '../constants'
import { useAction } from '../hooks/useAction'
import { useOperator } from '../hooks/useOperator'
import { useQuery } from '../hooks/useQuery'
import { api } from '../services/api'
import { Badge, Card, DataTable, EmptyState, FilterBar, PageHeader, QueryBoundary } from '../components/ui'

const TYPES = ['earthquake', 'flood', 'tropical cyclone', 'wildfire', 'volcano', 'drought', 'severe storms', 'landslides', 'sea and lake ice', 'dust and haze']
const SOURCE_NAME = Object.fromEntries(EXTERNAL_SOURCES.map((s) => [s.id, s.label]))

function SourceCard({ s }) {
  const tone = !s.configured ? 'gray' : s.last_status === 'error' ? 'red' : s.stale ? 'amber' : 'green'
  const word = !s.configured ? 'Not configured' : s.last_status === 'error' ? 'Last fetch failed' : s.last_success_at ? (s.stale ? 'Stale' : 'Up to date') : 'Never fetched'
  return (
    <div className="source-card">
      <div className="row space"><strong>{s.label}</strong><Badge tone={tone}>{word}</Badge></div>
      <dl className="detail-grid compact">
        <dt>Last updated</dt><dd>{s.last_success_at ? fmtDateTime(s.last_success_at) : 'never'}</dd>
        <dt>Last attempt</dt><dd>{s.last_attempt_at ? `${fmtDateTime(s.last_attempt_at)} (${s.last_status})` : '-'}</dd>
        <dt>Refresh interval</dt><dd>{Math.round(s.refresh_interval_seconds / 60)} min</dd>
      </dl>
      {s.last_message && <p className={s.last_status === 'error' ? 'field-error' : 'muted'}>{s.last_message}</p>}
    </div>
  )
}

export default function ExternalObservations() {
  const op = useOperator()
  const [source, setSource] = useState('')
  const [type, setType] = useState('')
  const [severity, setSeverity] = useState('')
  const [since, setSince] = useState('')
  const [region, setRegion] = useState(() => new URLSearchParams(window.location.hash.split('?')[1] ?? '').get('region') ?? '')
  const [review, setReview] = useState('')
  const [dups, setDups] = useState(false)
  const [refreshing, setRefreshing] = useState(false)
  const [outcome, setOutcome] = useState(null)
  const autoTried = useRef(false)
  const box = REGIONS.find((r) => r.id === region)?.box
  const status = useQuery('/api/external/status')
  const events = useQuery('/api/external/events', { source, event_type: type, severity, since, review_status: review, include_duplicates: dups, limit: 300, ...(box ?? {}) })
  const reloadAll = () => { status.reload(); events.reload() }
  const run = useAction(reloadAll)

  async function refresh(force) {
    setRefreshing(true); setOutcome(null)
    try {
      const r = await api.post('/api/external/refresh', { force })
      setOutcome({ results: r.results })
      reloadAll()
    } catch (e) { setOutcome({ error: e.message }) }
    setRefreshing(false)
  }

  // On first visit, fetch automatically when any configured source has never succeeded or is stale (the backend caches,
  // so this does not hammer the providers). Failures are shown, never hidden.
  const needsFetch = status.data?.sources.some((s) => s.configured && s.stale)
  useEffect(() => {
    if (needsFetch && !autoTried.current) { autoTried.current = true; refresh(false) }
  }, [needsFetch]) // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <>
      <PageHeader
        title="External observations"
        subtitle="Automated data from third parties. Not verified by an operator and not operational incidents."
        actions={<button type="button" className="btn btn-primary" onClick={() => refresh(true)} disabled={refreshing}>{refreshing ? 'Fetching from sources…' : 'Refresh now'}</button>}
      />
      <p className="disclaimer" role="note"><strong>External Observations</strong> - shown exactly as the source reports them. Severity bands here are <strong>estimates</strong> derived from each source’s own magnitude or alert level. An observation only becomes an incident when an authorised operator promotes it.</p>

      {refreshing && <p role="status" className="muted"><span className="spinner inline" aria-hidden="true" /> Contacting USGS, GDACS, NASA EONET and (if configured) NASA FIRMS…</p>}
      {outcome?.error && <p className="form-error" role="alert">{outcome.error}{!op.hasKey && ' If the backend requires an operator key, use “Operator access” at the top.'}</p>}
      {outcome?.results && (
        <ul className="plain" role="status">
          {outcome.results.map((r) => (
            <li key={r.source}><Badge tone={r.status === 'ok' ? 'green' : r.status === 'cached' ? 'blue' : r.status === 'not_configured' ? 'gray' : 'red'}>{r.status}</Badge> {SOURCE_NAME[r.source]}: {r.status === 'ok' ? `${r.new} new, ${r.updated} updated${r.skipped ? `, ${r.skipped} skipped (invalid)` : ''}` : r.message}{r.status === 'ok' && r.message ? ` - ${r.message}` : ''}</li>
          ))}
        </ul>
      )}

      <QueryBoundary query={status}>
        {(st) => <div className="grid-3">{st.sources.map((s) => <SourceCard key={s.source} s={s} />)}</div>}
      </QueryBoundary>

      <FilterBar>
        <select aria-label="Source" value={source} onChange={(e) => setSource(e.target.value)}><option value="">All sources</option>{EXTERNAL_SOURCES.map((s) => <option key={s.id} value={s.id}>{s.label}</option>)}</select>
        <select aria-label="Event type" value={type} onChange={(e) => setType(e.target.value)}><option value="">All event types</option>{TYPES.map((t) => <option key={t}>{t}</option>)}</select>
        <select aria-label="Estimated severity" value={severity} onChange={(e) => setSeverity(e.target.value)}><option value="">Any estimated severity</option>{SEVERITIES.map((s) => <option key={s}>{s}</option>)}</select>
        <select aria-label="Region" value={region} onChange={(e) => setRegion(e.target.value)}>{REGIONS.map((r) => <option key={r.id} value={r.id}>{r.label}</option>)}</select>
        <select aria-label="Review state" value={review} onChange={(e) => setReview(e.target.value)}><option value="">Not dismissed</option><option>Unreviewed</option><option>Reviewed</option><option>Promoted</option><option>Dismissed</option></select>
        <label className="check">Since <input type="date" value={since} onChange={(e) => setSince(e.target.value)} /></label>
        <label className="check"><input type="checkbox" checked={dups} onChange={(e) => setDups(e.target.checked)} />Show cross-source duplicates</label>
      </FilterBar>

      <Card>
        <QueryBoundary query={events}>
          {(page) => (
            <DataTable
              caption="External observations"
              rows={page.items}
              empty={<EmptyState title="No observations">Nothing stored matches. Press “Refresh now” to fetch from the sources - nothing is invented when a source is unavailable.</EmptyState>}
              columns={[
                { header: 'Observed', render: (e) => <>{fmtDateTime(e.observed_at)}<span className="sub">retrieved {fmtDateTime(e.retrieved_at)}</span></> },
                { header: 'Event', render: (e) => <><strong>{e.title}</strong><span className="sub">{e.event_type}{e.country ? ` · ${e.country}` : ''}{e.magnitude != null ? ` · value ${e.magnitude}` : ''}{e.duplicate_of_id ? ' · duplicate of another source' : ''}</span></> },
                { header: 'Estimated severity', render: (e) => <><Badge>{e.severity_estimate}</Badge><span className="sub">estimate{e.source_alert_level ? ` · source level: ${e.source_alert_level}` : ''}</span></> },
                { header: 'Source', render: (e) => <>{SOURCE_NAME[e.source] ?? e.source}{e.url && <a className="sub" href={e.url} target="_blank" rel="noreferrer">source page</a>}<span className="sub tag-external">unverified</span></> },
                { header: 'Review', render: (e) => <Badge>{e.review_status}</Badge> },
                { header: '', className: 'actions', render: (e) => (
                  <>
                    <a className="btn btn-sm" href="#/map">Map</a>
                    {e.review_status !== 'Promoted' && (
                      <>
                        <button type="button" className="btn btn-sm" onClick={() => run(() => api.post(`/api/external/events/${e.id}/review`, { status: 'Reviewed' }), 'Marked reviewed')}>Reviewed</button>
                        <button type="button" className="btn btn-sm" onClick={() => run(() => api.post(`/api/external/events/${e.id}/review`, { status: 'Dismissed' }), 'Dismissed')}>Dismiss</button>
                        <button type="button" className="btn btn-sm btn-primary" onClick={() => window.confirm('Create a NEW incident (status Monitoring) from this unverified observation? It will not be updated automatically afterwards.') && run(() => api.post(`/api/external/events/${e.id}/promote`, {}), 'Incident created (Monitoring)')}>Promote…</button>
                      </>
                    )}
                  </>
                ) },
              ]}
            />
          )}
        </QueryBoundary>
      </Card>
      <p className="muted">Sources: USGS Earthquake Hazards Program · GDACS · NASA EONET (no key) · NASA FIRMS (free MAP_KEY required) · Open-Meteo.</p><div className="source-links"><strong>ISRO / NRSC regional portals</strong><span>Bhuvan provides India-focused geospatial and disaster-management services. MOSDAC offers satellite weather/ocean products; account registration is needed to download data. NDEM services are for authorized emergency-management users, so this app does not scrape or claim access to restricted feeds.</span><a href="https://bhuvan.nrsc.gov.in/" target="_blank" rel="noreferrer">Open ISRO / NRSC Bhuvan</a><a href="https://mosdac.gov.in/" target="_blank" rel="noreferrer">Open MOSDAC</a><a href="https://www.mosdac.gov.in/downloadapi-manual" target="_blank" rel="noreferrer">MOSDAC API access manual</a></div>
    </>
  )
}


