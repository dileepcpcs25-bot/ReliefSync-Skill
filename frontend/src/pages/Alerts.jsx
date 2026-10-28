import { lazy, Suspense, useState } from 'react'
import { fmtDateTime } from '../constants'
import { useHashParams } from '../hooks/useHashRoute'
import { useQuery } from '../hooks/useQuery'
import { api } from '../services/api'
import { Badge, Card, EmptyState, PageHeader, QueryBoundary, Spinner } from '../components/ui'

const LocationPicker = lazy(() => import('../components/LocationPicker'))

const CONSENT = 'I agree to receive occasional incident alerts for the area I selected at the contact I gave. I understand alerts are informational, may be incomplete, and are not an official warning system. I can unsubscribe at any time using the link in every message.'

function TokenAction({ token, kind }) {
  const [state, setState] = useState({ busy: false, done: '', error: '' })
  const path = kind === 'unsubscribe' ? '/api/subscriptions/unsubscribe' : '/api/subscriptions/confirm'
  async function go() {
    setState({ busy: true, done: '', error: '' })
    try { await api.post(path, { token }); setState({ busy: false, done: kind === 'unsubscribe' ? 'You have been unsubscribed. No more alerts will be sent to that contact.' : 'Subscription confirmed. You will receive alerts for your area.', error: '' }) } catch (e) { setState({ busy: false, done: '', error: e.message }) }
  }
  return (
    <Card title={kind === 'unsubscribe' ? 'Unsubscribe from alerts' : 'Confirm your subscription'}>
      {state.done ? <p role="status">{state.done}</p> : <button type="button" className="btn btn-primary" onClick={go} disabled={state.busy}>{state.busy ? 'Working…' : kind === 'unsubscribe' ? 'Yes, unsubscribe me' : 'Confirm subscription'}</button>}
      {state.error && <p className="form-error" role="alert">{state.error}</p>}
    </Card>
  )
}

function SubscribeForm() {
  const [channel, setChannel] = useState('email')
  const [contact, setContact] = useState('')
  const [label, setLabel] = useState('')
  const [pos, setPos] = useState({ latitude: '', longitude: '', source: '', approximate: false })
  const [radius, setRadius] = useState(25)
  const [consent, setConsent] = useState(false)
  const [token, setToken] = useState('')
  const [state, setState] = useState({ busy: false, result: null, error: '' })
  const has = pos.latitude !== '' && pos.longitude !== ''

  async function submit(e) {
    e.preventDefault()
    setState({ busy: true, result: null, error: '' })
    try {
      const result = await api.post('/api/subscriptions', { channel, contact, area_label: label, latitude: Number(pos.latitude), longitude: Number(pos.longitude), radius_km: Number(radius), consent })
      setState({ busy: false, result, error: '' })
    } catch (err) { setState({ busy: false, result: null, error: err.message }) }
  }
  async function confirm() {
    try { await api.post('/api/subscriptions/confirm', { token }); setState({ busy: false, result: { message: 'Subscription confirmed.' }, error: '' }); setToken('') } catch (err) { setState((s) => ({ ...s, error: err.message })) }
  }

  return (
    <Card title="Get alerts for my area (optional)">
      <p className="muted">Alerts are sent only to people who ask for them. We store the contact you give, a <strong>coarse</strong> area (rounded to about 11 km) and your consent - never your exact location.</p>
      <form onSubmit={submit}>
        <div className="row">
          <div className="field"><label htmlFor="al-ch">Send alerts by</label><select id="al-ch" value={channel} onChange={(e) => setChannel(e.target.value)}><option value="email">Email</option><option value="sms">SMS</option></select></div>
          <div className="field grow"><label htmlFor="al-c">{channel === 'sms' ? 'Mobile number (with country code)' : 'Email address'}</label><input id="al-c" required type={channel === 'sms' ? 'tel' : 'email'} value={contact} onChange={(e) => setContact(e.target.value)} placeholder={channel === 'sms' ? '+919876543210' : 'you@example.com'} /></div>
        </div>
        <div className="field"><label htmlFor="al-l">Name of your area (optional)</label><input id="al-l" value={label} onChange={(e) => setLabel(e.target.value)} placeholder="e.g. T. Nagar, Chennai" /></div>
        <div className="field"><span className="label-like">Choose your area on the map</span>
          <Suspense fallback={<Spinner label="Loading map…" />}><LocationPicker value={pos} onChange={(p) => setPos((v) => ({ latitude: p.latitude ?? v.latitude, longitude: p.longitude ?? v.longitude, source: p.source ?? v.source, approximate: p.approximate ?? v.approximate }))} searchText={label} /></Suspense>
          <small className="muted">Pick roughly where you live or care about. You will be asked about incidents within the radius below.</small>
        </div>
        <div className="field"><label htmlFor="al-r">Radius: {radius} km</label><input id="al-r" type="range" min="1" max="200" value={radius} onChange={(e) => setRadius(e.target.value)} /></div>
        <label className="check consent"><input type="checkbox" checked={consent} onChange={(e) => setConsent(e.target.checked)} /><span>{CONSENT}</span></label>
        <button className="btn btn-primary" disabled={state.busy || !consent || !has || !contact}>{state.busy ? 'Sending…' : 'Subscribe'}</button>
        {!has && <small className="muted"> Choose an area first.</small>}
      </form>
      {state.error && <p className="form-error" role="alert">{state.error}</p>}
      {state.result && (
        <div role="status" className="subpanel">
          <p>{state.result.message}</p>
          {state.result.dev_note && <p className="muted"><strong>Development mode:</strong> {state.result.dev_note} Code: <code>{state.result.dev_confirm_token}</code></p>}
        </div>
      )}
      <details><summary>I have a confirmation code</summary>
        <div className="row"><input aria-label="Confirmation code" value={token} onChange={(e) => setToken(e.target.value)} placeholder="Paste the code from the message" /><button type="button" className="btn" onClick={confirm} disabled={token.length < 16}>Confirm</button></div>
      </details>
    </Card>
  )
}

export default function Alerts() {
  const params = useHashParams()
  const feed = useQuery('/api/notifications/public-alerts')
  return (
    <>
      <PageHeader title="Public alerts" subtitle="Informational alerts published by ReliefSync operators." actions={<button type="button" className="btn" onClick={feed.reload}>Refresh</button>} />
      <p className="disclaimer" role="note"><strong>This is not an official warning system.</strong> In an emergency follow your local emergency-management authority.</p>
      {params.unsubscribe && <TokenAction token={params.unsubscribe} kind="unsubscribe" />}
      {params.confirm && <TokenAction token={params.confirm} kind="confirm" />}
      <Card title="Current alerts">
        <QueryBoundary query={feed}>
          {(res) => res.items.length === 0 ? <EmptyState title="No active alerts">Alerts for resolved incidents are not shown as active.</EmptyState> : (
            <ul className="list alerts">
              {res.items.map((a) => (
                <li key={a.id}>
                  <div><strong>{a.title}</strong> <Badge tone={a.kind === 'all_clear' ? 'green' : 'amber'}>{a.kind === 'all_clear' ? 'All clear' : 'Alert'}</Badge>
                    <pre className="msg-inline">{a.body}</pre><small className="muted">{fmtDateTime(a.created_at)} · entered by ReliefSync operators</small></div>
                </li>
              ))}
            </ul>
          )}
        </QueryBoundary>
      </Card>
      <SubscribeForm />
    </>
  )
}
