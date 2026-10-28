import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it } from 'vitest'
import FormModal from '../components/FormModal'
import Guide from '../pages/Guide'
import Dashboard from '../pages/Dashboard'
import History from '../pages/History'
import ToastProvider from '../components/ToastProvider'
import { STATUS_RULE_TEXT, locationField } from '../constants'
import Alerts from '../pages/Alerts'
import ExternalObservations from '../pages/ExternalObservations'
import MapPage from '../pages/MapPage'
import Login from '../pages/Login'
import Notifications from '../pages/Notifications'
import SmartPriority from '../pages/SmartPriority'
import { setOperator } from '../services/operator'
import { mockApi } from './mockApi'

const wrap = (ui) => render(<ToastProvider>{ui}</ToastProvider>)
const page = (items) => ({ items, total: items.length, limit: 100, offset: 0 })

const disaster = { id: 1, disaster_type: 'Flood', location: 'Chennai', severity: 'High', people_affected: 5000, status: 'Active', priority_score: 70, priority_level: 'High', latitude: 13.08, longitude: 80.27, location_source: 'manual', location_approximate: false, description: '', origin: 'user' }
const mapData = {
  features: [
    { kind: 'disaster', id: 1, latitude: 13.08, longitude: 80.27, title: 'Flood - Chennai', status: 'Active', severity: 'High', source: 'ReliefSync', label: 'Operational record (entered in ReliefSync, not independently verified)', timestamp: '2026-10-24T06:00:00Z', approximate: false, details: { people_affected: 5000 } },
    { kind: 'external', id: 9, latitude: 38.3, longitude: 141, title: 'M 6.4 - Sendai', status: 'Unreviewed', severity: 'High', source: 'USGS', label: 'External observation (unverified by an operator)', severity_label: 'Estimate (rule-based)', timestamp: '2026-10-24T06:00:00Z', retrieved_at: '2026-10-24T06:05:00Z', approximate: false, details: {} },
  ],
  count: 2, missing_coordinates: { shelters: 1 }, volunteers_hidden: true, generated_at: '2026-10-24T06:10:00Z', status_rule: STATUS_RULE_TEXT,
}

beforeEach(() => { window.location.hash = ''; localStorage.clear(); setOperator({ key: '', name: '' }) })

describe('constants', () => {
  it('excludes resolved incidents from the priority list', () => {
    expect(STATUS_RULE_TEXT).toBe('Resolved incidents are excluded.')
  })
})

describe('Dashboard external-source data', () => {
  it('shows backend observation totals and recent global-source events', async () => {
    mockApi({ 'GET /api/dashboard': {
      disasters: { total: 0, active: 0, monitoring: 0, resolved: 0, critical_priority: 0, high_priority: 0 },
      volunteers: { total: 0, available: 0, assigned: 0 }, assignments: { active: 0, total: 0 },
      inventory: { items: 0, total_units: 0, low_stock: 0 }, inventory_by_category: [],
      shelters: { total: 0, total_capacity: 0, occupancy: 0, available_capacity: 0, occupancy_percent: 0 },
      allocations: { active: 0, delivered: 0, total: 0 }, recent_disasters: [], top_priorities: [], low_stock_items: [],
      external_observations: { total: 1, eonet: 1 }, recent_external_events: [{ id: 1, source: 'eonet', title: 'Storm in India', event_type: 'severe storms', observed_at: '2026-10-20T00:00:00Z', country: 'India', url: 'https://example.org/event' }],
      regional_overview: [{ id: 'south-asia', label: 'India & South Asia', observations: 1, active_incidents: 0, volunteers: 0, shelters: 0, latest_observation: '2026-10-20T00:00:00Z' }],
      observation_coverage: { first_observed_at: '2026-10-20T00:00:00Z', last_observed_at: '2026-10-20T00:00:00Z', unique_observations: 1 },
    } })
    wrap(<Dashboard />)
    expect(await screen.findByText('1 stored observations')).toBeInTheDocument()
    expect(screen.getByText('Storm in India')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'India & South Asia' })).toHaveAttribute('href', '#/external?region=south-asia')
    expect(screen.getByRole('link', { name: 'Open regional data' })).toHaveAttribute('href', '#/external')
  })
})
describe('Past events and resources', () => {
  it('loads a real event list and fetches current nearby resource rows after selection', async () => {
    const calls = mockApi({
      'GET /api/history/events': { items: [{ key: 'local:7', record_id: 7, event_source: 'local', source: 'ReliefSync operational record', title: 'Flood - Chennai', event_type: 'Flood', location: 'Chennai', status: 'Resolved', severity: 'High', event_at: '2026-10-20T10:00:00Z', date_basis: 'record created in ReliefSync' }], total: 1, limit: 300, offset: 0 },
      'GET /api/history/events/local%3A7/resources': { event: { key: 'local:7', title: 'Flood - Chennai', event_at: '2026-10-20T10:00:00Z' }, radius_km: 100, volunteers: [{ id: 2, name: 'Asha', skills: 'First aid', location: 'Chennai', availability: 'Available', assigned: false, distance_km: 18.2 }], shelters: [{ id: 3, name: 'Camp A', location: 'Chennai', total_capacity: 100, current_occupancy: 20, available_capacity: 80, distance_km: 4.3 }], unlocated: { volunteers: 0, shelters: 0 }, distance_note: 'Straight-line estimate.', resource_time_note: 'Current database values.' },
    })
    wrap(<History />)
    await userEvent.click(await screen.findByRole('button', { name: 'Find nearby' }))
    expect(await screen.findByText('Asha')).toBeInTheDocument()
    expect(screen.getByText('Camp A')).toBeInTheDocument()
    expect(screen.getAllByText(/current database values/i).length).toBeGreaterThan(0)
    expect(calls.some((c) => c.path.endsWith('/resources') && c.search.includes('radius_km=100'))).toBe(true)
  })
})
describe('Smart priority', () => {
  it('shows the status rule and the contributing factors', async () => {
    mockApi({ 'GET /api/intelligence/priority': { status_rule: STATUS_RULE_TEXT, items: [{ rank: 1, score: 70, level: 'High', explanation: 'because', method: 'score = ...', label: 'Estimate (rule-based)', factors: [{ name: 'Severity', input: 'High', points: 40, basis: 'Rating entered by a ReliefSync user (not independently verified)' }, { name: 'People affected', input: '5,000', points: 30, basis: 'Reported figure - an unverified estimate' }], disaster }] } })
    wrap(<SmartPriority />)
    expect(await screen.findByText(STATUS_RULE_TEXT)).toBeInTheDocument()
    expect(screen.getByText('How this score is calculated')).toBeInTheDocument()
    expect(screen.getByText('Reported figure - an unverified estimate')).toBeInTheDocument()
  })
})


describe('Operator sign in', () => {
  it('validates the username and stores a successful password session in the tab', async () => {
    const calls = mockApi({
      'GET /api/auth/config': { key_required: false, password_auth_enabled: true, registration_enabled: true, auth_type: 'multi_user_password' },
      'POST /api/auth/login/password': (_url, body) => ({ authenticated: true, token: 'test-session', username: body.username, name: 'Hemanth', role: 'operator' }),
    })
    wrap(<Login />)
    const user = userEvent.setup()
    await user.click(await screen.findByRole('button', { name: 'Sign in' }))
    expect(await screen.findByText(/Use 3-32 letters/)).toBeInTheDocument()
    await user.type(screen.getByLabelText('Username'), 'hemanth')
    await user.type(screen.getByLabelText('Password'), 'A strong test password!')
    await user.click(screen.getByRole('button', { name: 'Sign in' }))
    await waitFor(() => expect(window.location.hash).toBe('#/dashboard'))
    expect(sessionStorage.getItem('reliefsync.sessionToken')).toBe('test-session')
    expect(sessionStorage.getItem('reliefsync.username')).toBe('hemanth')
    expect(calls.find((call) => call.path === '/api/auth/login/password').body).toMatchObject({ username: 'hemanth', password: 'A strong test password!' })
  })

  it('validates account registration and creates a multi-user account', async () => {
    const calls = mockApi({
      'GET /api/auth/config': { key_required: false, password_auth_enabled: true, registration_enabled: true, auth_type: 'multi_user_password' },
      'POST /api/auth/register': (_url, body) => ({ authenticated: true, token: 'new-session', username: body.username, name: body.display_name, role: 'operator' }),
    })
    wrap(<Login />)
    const user = userEvent.setup()
    await user.click(await screen.findByRole('button', { name: 'Create an account' }))
    await user.type(screen.getByLabelText('Display name'), 'Hemanth Reddy')
    await user.type(screen.getByLabelText('Username'), 'hemanth2')
    await user.type(screen.getByLabelText('Password'), 'Safe team password! 2026')
    await user.click(screen.getByRole('button', { name: 'Create account' }))
    await waitFor(() => expect(window.location.hash).toBe('#/dashboard'))
    expect(sessionStorage.getItem('reliefsync.sessionToken')).toBe('new-session')
    expect(calls.find((call) => call.path === '/api/auth/register').body.username).toBe('hemanth2')
  })
})

describe('Map page', () => {
  it('renders markers data, legend and status notes', async () => {
    const calls = mockApi({ 'GET /api/map/features': mapData })
    wrap(<MapPage />)
    expect(await screen.findByText(/2 item\(s\) with a known position/)).toBeInTheDocument()
    expect(await screen.findByText(STATUS_RULE_TEXT)).toBeInTheDocument()
    const legend = screen.getByLabelText('Map legend')
    expect(within(legend).getByText('External observation (unverified)')).toBeInTheDocument()
    expect(within(legend).getByText(/approximate or inferred/)).toBeInTheDocument()
    expect(screen.getByText(/volunteer positions are visible to operators only/)).toBeInTheDocument()
    expect(screen.getByText(/not shown \(no coordinates yet\): 1 shelters/)).toBeInTheDocument()
    expect(calls[0].search).toContain('layers=disasters')
    expect(calls[0].search).not.toContain('include_resolved')
    await userEvent.setup().selectOptions(screen.getByLabelText('Region'), 'south-asia')
    await waitFor(() => expect(localStorage.getItem('reliefsync.map.region')).toBe(JSON.stringify('south-asia')))
  })

  it('switches between marker, incident heatmap, and table views', async () => {
    mockApi({ 'GET /api/map/features': mapData })
    wrap(<MapPage />)
    await screen.findByText(/item\(s\) with a known position/)
    const mode = screen.getByLabelText('Map view')
    await userEvent.selectOptions(mode, 'heatmap')
    expect(await screen.findByText('Reported-incident intensity')).toBeInTheDocument()
    expect(localStorage.getItem('reliefsync.map.viewMode')).toBe(JSON.stringify('heatmap'))
    await userEvent.selectOptions(mode, 'table')
    expect(await screen.findByText('Filtered map records')).toBeInTheDocument()
    expect(screen.getByText('M 6.4 - Sendai')).toBeInTheDocument()
  })

  it('layer and resolved toggles change the request', async () => {
    const calls = mockApi({ 'GET /api/map/features': mapData })
    wrap(<MapPage />)
    await screen.findByText(/item\(s\) with a known position/)
    await userEvent.click(screen.getByLabelText('Include resolved (history)'))
    await userEvent.click(screen.getByLabelText('External observations'))
    await waitFor(() => expect(calls.at(-1).search).toContain('include_resolved=true'))
    expect(calls.at(-1).search).not.toContain('external')
  })

  it('shows an honest error when the backend is down', async () => {
    mockApi({ 'GET /api/map/features': Object.assign(new Error('boom'), { status: 500 }) })
    wrap(<MapPage />)
    expect(await screen.findByText('boom')).toBeInTheDocument()
  })

  it('geocoding an ambiguous place asks the user to choose', async () => {
    mockApi({
      'GET /api/map/features': mapData,
      'GET /api/geo/geocode': { query: 'Springfield', ambiguous: true, attribution: 'Geocoding: Nominatim', candidates: [{ display_name: 'Springfield, Illinois', latitude: 39, longitude: -89, osm_ref: 'a' }, { display_name: 'Springfield, Massachusetts', latitude: 42, longitude: -72, osm_ref: 'b' }] },
    })
    wrap(<MapPage />)
    await screen.findByText(/item\(s\) with a known position/)
    await userEvent.type(screen.getByLabelText('Search for a place'), 'Springfield')
    await userEvent.click(screen.getByText('Go to place'))
    expect(await screen.findByText(/Several different places match/)).toBeInTheDocument()
    expect(screen.getByText('Springfield, Massachusetts')).toBeInTheDocument()
  })
})

describe('External observations', () => {
  const status = { sources: [
    { source: 'usgs', label: 'USGS Earthquake Hazards Program', configured: true, last_success_at: '2026-10-24T06:00:00Z', last_attempt_at: '2026-10-24T06:00:00Z', last_status: 'ok', last_message: '', stale: false, refresh_interval_seconds: 300 },
    { source: 'gdacs', label: 'GDACS global disaster alerts', configured: true, last_success_at: null, last_attempt_at: '2026-10-24T06:00:00Z', last_status: 'error', last_message: 'Could not reach www.gdacs.org: ConnectError', stale: true, refresh_interval_seconds: 600 },
    { source: 'firms', label: 'NASA FIRMS satellite fire detections', configured: false, last_success_at: null, last_attempt_at: null, last_status: null, last_message: '', stale: true, refresh_interval_seconds: 900 },
  ] }
  const ev = { id: 9, source: 'usgs', external_id: 'us1', event_type: 'earthquake', title: 'M 6.4 - Sendai', latitude: 38, longitude: 141, magnitude: 6.4, source_alert_level: 'orange', severity_estimate: 'High', country: null, observed_at: '2026-10-24T06:00:00Z', retrieved_at: '2026-10-24T06:05:00Z', url: 'https://example.org/e', review_status: 'Unreviewed', duplicate_of_id: null }

  it('labels data as unverified, shows last-updated, errors and unconfigured sources', async () => {
    mockApi({ 'GET /api/external/status': status, 'GET /api/external/events': page([ev]), 'POST /api/external/refresh': { results: [], sources: status.sources } })
    wrap(<ExternalObservations />)
    expect(await screen.findByText('M 6.4 - Sendai')).toBeInTheDocument()
    expect(screen.getByText('Last fetch failed')).toBeInTheDocument()
    expect(screen.getByText('Could not reach www.gdacs.org: ConnectError')).toBeInTheDocument()
    expect(screen.getByText('Not configured')).toBeInTheDocument()
    expect(screen.getAllByText('unverified').length).toBeGreaterThan(0)
    expect(screen.getByText(/estimate · source level: orange/)).toBeInTheDocument()
  })

  it('manual refresh shows a loading state and then each source result', async () => {
    const calls = mockApi({
      'GET /api/external/status': { sources: status.sources.map((s) => ({ ...s, stale: false })) }, 'GET /api/external/events': page([ev]),
      'POST /api/external/refresh': () => ({ results: [{ source: 'usgs', status: 'ok', new: 2, updated: 1, skipped: 0, message: '' }, { source: 'gdacs', status: 'error', message: 'GDACS returned HTTP 500' }], sources: status.sources }),
    })
    wrap(<ExternalObservations />)
    await screen.findByText('M 6.4 - Sendai')
    await userEvent.click(screen.getByText('Refresh now'))
    expect(await screen.findByText(/2 new, 1 updated/)).toBeInTheDocument()
    expect(screen.getByText(/GDACS returned HTTP 500/)).toBeInTheDocument()
    expect(calls.some((c) => c.method === 'POST' && c.body.force === true)).toBe(true)
  })

  it('promoting asks for confirmation and sends nothing if declined', async () => {
    const calls = mockApi({ 'GET /api/external/status': { sources: status.sources.map((s) => ({ ...s, stale: false })) }, 'GET /api/external/events': page([ev]) })
    window.confirm = () => false
    wrap(<ExternalObservations />)
    await screen.findByText('M 6.4 - Sendai')
    await userEvent.click(screen.getByText('Promote…'))
    expect(calls.some((c) => c.path.includes('promote'))).toBe(false)
  })
})

describe('Notifications console', () => {
  const base = {
    'GET /api/notifications/status': { mode: 'development', in_app: {}, sms: { available: false }, email: { available: false }, browser_push: { available: false }, cooldown_minutes: 30, operator_auth: 'open (development only: set OPERATOR_API_KEY)' },
    'GET /api/notifications/templates': [{ key: 'volunteer_request', label: 'Volunteer assistance request', audiences: ['volunteers'], purpose: 'Ask nearby volunteers.' }],
    'GET /api/disasters': page([disaster]),
  }
  const campaign = { id: 5, audience: 'volunteers', template_key: 'volunteer_request', template: 'Volunteer assistance request', disaster_id: 1, disaster_label: 'Flood - Chennai', disaster_status: 'Active', radius_km: 25, channels: ['in_app'], required_skills: '', instructions: '', verified_info: '', status: 'Approved', created_by: 'Priya', approved_by: 'Priya', approved_at: '2026-10-24T06:00:00Z', created_at: '2026-10-24T05:00:00Z', dispatched_at: null, mode_at_dispatch: null }
  const preview = { campaign_id: 5, status: 'Approved', mode: 'development', subject: 'Volunteers needed: Flood near Chennai', body: 'Reported incident (not independently verified)', sample_personalised_body: null, recipient_count: 2, recipients: [{ type: 'volunteer', id: 1, label: 'Volunteer #1 Asha', channel: 'in_app', address_masked: '(in-app)', distance_km: 22.1 }], excluded: { 'outside radius': 1 }, warnings: ['DEVELOPMENT MODE: SMS and email are simulated. No real person will be contacted.'], channels: { in_app: { eligible: 2, will_contact_real_people: false, cost: 'No cost (in-app record)' } }, target_area: { latitude: 13.08, longitude: 80.27, radius_km: 25 }, disaster: { id: 1, label: 'Flood - Chennai', status: 'Active', latitude: 13.08, longitude: 80.27, approximate: false } }

  it('shows the mode banner and campaign history', async () => {
    mockApi({ ...base, 'GET /api/notifications/campaigns': page([campaign]) })
    wrap(<Notifications />)
    expect(await screen.findByText('DEVELOPMENT MODE')).toBeInTheDocument()
    expect(screen.getByText(/Nobody outside this app is ever contacted/)).toBeInTheDocument()
    expect(await screen.findByText('Volunteer assistance request')).toBeInTheDocument()
    expect(screen.getAllByText('Approved').length).toBeGreaterThan(0)
  })

  it('requires an explicit confirmation tick before dispatch and sends an idempotency key', async () => {
    const calls = mockApi({ ...base, 'GET /api/notifications/campaigns': page([campaign]), 'GET /api/notifications/campaigns/5': { ...campaign, summary: {} }, 'GET /api/notifications/campaigns/5/preview': preview,
      'POST /api/notifications/campaigns/5/dispatch': { status: 'Dispatched', deliveries: { recorded_in_app: 2 } } })
    wrap(<Notifications />)
    await userEvent.click(await screen.findByText('Open'))
    expect(await screen.findByText('Exact message')).toBeInTheDocument()
    expect(screen.getByText('Reported incident (not independently verified)')).toBeInTheDocument()
    expect(screen.getByText(/record inside ReliefSync only/)).toBeInTheDocument()
    const button = screen.getByText('Dispatch now')
    expect(button).toBeDisabled()
    await userEvent.click(screen.getByLabelText(/I confirm: send the message above to 2 recipient/))
    expect(button).toBeEnabled()
    await userEvent.click(button)
    await waitFor(() => expect(calls.some((c) => c.path.endsWith('/dispatch'))).toBe(true))
    const sent = calls.find((c) => c.path.endsWith('/dispatch')).body
    expect(sent.confirm).toBe(true)
    expect(sent.idempotency_key.length).toBeGreaterThanOrEqual(8)
  })

  it('sends operator credentials as headers only when set', async () => {
    setOperator({ key: 'k-123', name: 'Priya' })
    const calls = mockApi({ ...base, 'GET /api/notifications/campaigns': page([]) })
    wrap(<Notifications />)
    await screen.findByText('DEVELOPMENT MODE')
    expect(calls[0].headers['X-Operator-Key']).toBe('k-123')
    expect(calls[0].headers['X-Operator-Name']).toBe('Priya')
  })

  it('failed deliveries are shown as failed with a retry control, never as delivered', async () => {
    mockApi({ ...base, 'GET /api/notifications/campaigns': page([{ ...campaign, status: 'Partially Failed' }]), 'GET /api/notifications/campaigns/5': { ...campaign, status: 'Partially Failed', summary: {} },
      'GET /api/notifications/campaigns/5/preview': preview,
      'GET /api/notifications/campaigns/5/deliveries': page([{ id: 1, recipient_type: 'volunteer', recipient_id: 1, channel: 'sms', address_masked: '*******10', status: 'failed', provider: 'twilio-sms', detail: 'Provider error: HTTP 500', attempts: 1 }, { id: 2, recipient_type: 'volunteer', recipient_id: 2, channel: 'sms', address_masked: '*******11', status: 'accepted_by_provider', provider: 'twilio-sms', detail: 'Handset delivery is not confirmed.', attempts: 1 }]) })
    wrap(<Notifications />)
    await userEvent.click(await screen.findByText('Open'))
    expect(await screen.findByText('Provider error: HTTP 500')).toBeInTheDocument()
    expect(screen.getByText('Accepted by provider (delivery not confirmed)')).toBeInTheDocument()
    expect(screen.getByText('Retry failed deliveries…')).toBeInTheDocument()
    expect(screen.queryByText(/^Delivered$/)).not.toBeInTheDocument()
  })
})

describe('Public alerts', () => {
  it('lists alerts with the not-official notice and requires consent and an area to subscribe', async () => {
    mockApi({ 'GET /api/notifications/public-alerts': { items: [{ id: 1, title: 'Safety information: Flood near Chennai', body: 'Please follow instructions from your official local emergency-management authority.', created_at: '2026-10-24T06:00:00Z', kind: 'alert' }], notice: 'x' } })
    wrap(<Alerts />)
    expect(await screen.findByText('Safety information: Flood near Chennai')).toBeInTheDocument()
    expect(screen.getByText(/This is not an official warning system/)).toBeInTheDocument()
    const submit = screen.getByRole('button', { name: 'Subscribe' })
    expect(submit).toBeDisabled()
    await userEvent.type(screen.getByLabelText(/Email address/), 'a@example.com')
    await userEvent.click(screen.getByRole('checkbox', { name: /I agree to receive occasional incident alerts/ }))
    expect(submit).toBeDisabled() // still no area chosen: coordinates are never guessed
  })

  it('an unsubscribe link offers a one-click unsubscribe', async () => {
    window.location.hash = '#/alerts?unsubscribe=tok-1234567890abcdef'
    const calls = mockApi({ 'GET /api/notifications/public-alerts': { items: [], notice: '' }, 'POST /api/subscriptions/unsubscribe': { status: 'unsubscribed' } })
    wrap(<Alerts />)
    await userEvent.click(await screen.findByText('Yes, unsubscribe me'))
    expect(await screen.findByText(/You have been unsubscribed/)).toBeInTheDocument()
    expect(calls.find((c) => c.method === 'POST').body.token).toBe('tok-1234567890abcdef')
  })
})

describe('Location field in forms', () => {
  const fields = [{ name: 'location', label: 'Location', required: true }, locationField('location')]
  const open = (onSubmit) => wrap(<FormModal title="t" fields={fields} onSubmit={onSubmit} onClose={() => {}} />)

  it('submits typed coordinates as numbers with source "manual", and omits them when left empty', async () => {
    const seen = []
    open(async (v) => { seen.push(v); return { ok: true } })
    await userEvent.type(screen.getByLabelText(/^Location/), 'Chennai')
    await userEvent.click(screen.getByText('Save'))
    await waitFor(() => expect(seen).toHaveLength(1))
    expect(seen[0]).toEqual({ location: 'Chennai' }) // unknown position is never invented
  })

  it('sends coordinates when given, and rejects out-of-range or half-filled values', async () => {
    const seen = []
    open(async (v) => { seen.push(v); return { ok: true } })
    await userEvent.type(screen.getByLabelText(/^Location/), 'Chennai')
    const lat = await screen.findByLabelText('Latitude')
    const lng = screen.getByLabelText('Longitude')
    await userEvent.type(lat, '95')
    await userEvent.type(lng, '80.27')
    await userEvent.click(screen.getByText('Save'))
    expect(await screen.findByText(/Latitude must be a number from -90 to 90/)).toBeInTheDocument()
    expect(seen).toHaveLength(0)
    await userEvent.clear(lat)
    await userEvent.type(lat, '13.0827')
    await userEvent.click(screen.getByText('Save'))
    await waitFor(() => expect(seen).toHaveLength(1))
    expect(seen[0]).toMatchObject({ location: 'Chennai', latitude: 13.0827, longitude: 80.27, location_source: 'manual', location_approximate: false })
    await userEvent.clear(lng)
    await userEvent.click(screen.getByText('Save'))
    expect(await screen.findByText(/Enter both latitude and longitude, or neither/)).toBeInTheDocument()
  })
})


describe('How it works', () => {
  it('explains button API calls in a table', () => {
    wrap(<Guide />)
    const table = screen.getByRole('table', { name: 'Action to API mapping' })
    expect(within(table).getByText('POST /api/external/refresh')).toBeInTheDocument()
    expect(within(table).getByText(/simulates email\/SMS/)).toBeInTheDocument()
  })
})




