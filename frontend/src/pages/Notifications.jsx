import { useMemo, useState } from 'react'
import { DELIVERY_LABELS, TONES, fmtDateTime } from '../constants'
import { useAction } from '../hooks/useAction'
import { useHashParams } from '../hooks/useHashRoute'
import { useOperator } from '../hooks/useOperator'
import { useQuery } from '../hooks/useQuery'
import { api } from '../services/api'
import MapBase from '../components/map/MapBase'
import { Badge, Card, DataTable, EmptyState, ErrorState, Modal, PageHeader, QueryBoundary, Spinner } from '../components/ui'

const CHANNELS = { volunteers: ['in_app', 'sms'], shelters: ['in_app'], residents: ['in_app', 'sms', 'email'] }
const CHANNEL_LABEL = { in_app: 'In-app record', sms: 'SMS', email: 'Email' }
const AUDIENCE_LABEL = { volunteers: 'Nearby volunteers', shelters: 'Nearby shelter coordinators', residents: 'Residents (opted-in subscribers + public feed)' }

function ModeStrip() {
  const q = useQuery('/api/notifications/status')
  if (q.error) return <ErrorState error={q.error} onRetry={q.reload} />
  if (!q.data) return <Spinner />
  const s = q.data
  const live = s.mode === 'live'
  return (
    <div className={`mode-strip ${live ? 'mode-live' : 'mode-dev'}`} role="status">
      <strong>{live ? 'LIVE MODE' : 'DEVELOPMENT MODE'}</strong>
      <span>{live ? 'Approved campaigns contact real people through configured providers.' : 'SMS and email are simulated. Nobody outside this app is ever contacted.'}</span>
      <span className="chips">
        <Badge tone="blue">In-app: records only</Badge>
        <Badge tone={s.sms.available ? 'green' : 'gray'}>SMS: {s.sms.available ? 'live provider ready' : live ? 'not configured' : 'simulated'}</Badge>
        <Badge tone={s.email.available ? 'green' : 'gray'}>Email: {s.email.available ? 'live provider ready' : live ? 'not configured' : 'simulated'}</Badge>
        <Badge tone="gray">Browser push: not implemented</Badge>
      </span>
      <small>Operator access: {s.operator_auth}. Cooldown {s.cooldown_minutes} min per recipient and incident.</small>
    </div>
  )
}

function Builder({ initialDisaster, onClose, onCreated }) {
  const templates = useQuery('/api/notifications/templates')
  const disasters = useQuery('/api/disasters', { limit: 200 })
  const [audience, setAudience] = useState('volunteers')
  const [template, setTemplate] = useState('volunteer_request')
  const [disasterId, setDisasterId] = useState(initialDisaster ?? '')
  const [radius, setRadius] = useState(25)
  const [channels, setChannels] = useState(['in_app'])
  const [skills, setSkills] = useState('')
  const [instructions, setInstructions] = useState('')
  const [verified, setVerified] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const allowed = CHANNELS[audience]
  const options = (templates.data ?? []).filter((t) => t.audiences.includes(audience))
  const disaster = disasters.data?.items.find((d) => String(d.id) === String(disasterId))

  const pickAudience = (a) => {
    setAudience(a)
    setChannels((c) => c.filter((x) => CHANNELS[a].includes(x)).length ? c.filter((x) => CHANNELS[a].includes(x)) : ['in_app'])
    setTemplate({ volunteers: 'volunteer_request', shelters: 'shelter_preparedness', residents: 'public_safety_info' }[a])
  }
  const toggle = (c) => setChannels((l) => (l.includes(c) ? l.filter((x) => x !== c) : [...l, c]))

  async function submit(e) {
    e.preventDefault()
    setBusy(true); setError('')
    try {
      const c = await api.post('/api/notifications/campaigns', { audience, template_key: template, disaster_id: Number(disasterId), radius_km: Number(radius), channels, required_skills: skills, instructions, verified_info: verified })
      onCreated(c)
    } catch (err) { setError(err.message) }
    setBusy(false)
  }

  return (
    <Modal title="New notification campaign (draft)" onClose={onClose} wide>
      <p className="muted">Nothing is sent from this form. You will preview the exact message and recipients, then approve, then confirm dispatch.</p>
      <form onSubmit={submit}>
        <div className="field"><label htmlFor="nb-d">Incident</label>
          <select id="nb-d" required value={disasterId} onChange={(e) => setDisasterId(e.target.value)}>
            <option value="">Select an incident…</option>
            {(disasters.data?.items ?? []).map((d) => <option key={d.id} value={d.id} disabled={d.latitude == null}>#{d.id} {d.disaster_type} - {d.location} [{d.status}]{d.latitude == null ? ' (no position - set it on the map first)' : ''}</option>)}
          </select>
          {disaster?.status === 'Resolved' && <small className="muted">Resolved incidents are excluded from active campaigns; only an all-clear notice can be sent.</small>}
        </div>
        <div className="field"><label htmlFor="nb-a">Audience</label>
          <select id="nb-a" value={audience} onChange={(e) => pickAudience(e.target.value)}>{Object.entries(AUDIENCE_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select>
        </div>
        <div className="field"><label htmlFor="nb-t">Message template</label>
          <select id="nb-t" value={template} onChange={(e) => setTemplate(e.target.value)}>{options.map((t) => <option key={t.key} value={t.key}>{t.label}</option>)}</select>
          <small className="muted">{options.find((t) => t.key === template)?.purpose}</small>
        </div>
        <div className="field"><label htmlFor="nb-r">Radius: {radius} km</label>
          <input id="nb-r" type="range" min="1" max="500" value={radius} onChange={(e) => setRadius(e.target.value)} />
        </div>
        <fieldset className="layer-toggles"><legend>Channels</legend>
          {allowed.map((c) => <label key={c} className="check"><input type="checkbox" checked={channels.includes(c)} onChange={() => toggle(c)} />{CHANNEL_LABEL[c]}</label>)}
        </fieldset>
        {audience === 'volunteers' && <div className="field"><label htmlFor="nb-s">Required skills (optional, comma separated)</label><input id="nb-s" value={skills} onChange={(e) => setSkills(e.target.value)} placeholder="boat, first aid" /><small className="muted">If set, only volunteers with at least one matching skill are included.</small></div>}
        <div className="field"><label htmlFor="nb-i">Instructions for responders (optional)</label><textarea id="nb-i" rows={2} value={instructions} onChange={(e) => setInstructions(e.target.value)} placeholder="e.g. Report to the community hall gate. Leave empty to use the neutral wording." /></div>
        {audience === 'residents' && <div className="field"><label htmlFor="nb-v">Verified public information (optional)</label><textarea id="nb-v" rows={3} value={verified} onChange={(e) => setVerified(e.target.value)} placeholder="Only text you have confirmed with the responsible authority. If empty, recipients are told to follow their official local emergency-management sources." /></div>}
        {error && <p className="form-error" role="alert">{error}</p>}
        <div className="modal-actions"><button type="button" className="btn" onClick={onClose}>Cancel</button><button className="btn btn-primary" disabled={busy || !disasterId || !channels.length}>{busy ? 'Creating…' : 'Create draft & preview'}</button></div>
      </form>
    </Modal>
  )
}

function Deliveries({ id, reloadKey }) {
  const q = useQuery(`/api/notifications/campaigns/${id}/deliveries`, { limit: 200, k: reloadKey })
  return (
    <QueryBoundary query={q}>
      {(page) => (
        <>
          <DataTable caption="Deliveries" rows={page.items} empty={<EmptyState title="No deliveries yet" />} columns={[
            { header: 'Recipient', render: (d) => `${d.recipient_type} #${d.recipient_id || '-'}` },
            { header: 'Channel', render: (d) => CHANNEL_LABEL[d.channel] },
            { header: 'Address', render: (d) => d.address_masked || '-' },
            { header: 'Status', render: (d) => <Badge tone={TONES[d.status]}>{DELIVERY_LABELS[d.status] ?? d.status}</Badge> },
            { header: 'Details', render: (d) => <small>{d.detail}{d.provider_message_id ? ` (id ${d.provider_message_id})` : ''}</small> },
            { header: 'Attempts', className: 'num', render: (d) => d.attempts },
          ]} />
          <small className="muted">“Accepted by provider” means the SMS/email service took the message. ReliefSync does not receive delivery receipts, so it never reports a message as delivered.</small>
        </>
      )}
    </QueryBoundary>
  )
}

function CampaignDetail({ id, onClose, onChanged }) {
  const campaign = useQuery(`/api/notifications/campaigns/${id}`)
  const c = campaign.data
  const isOpen = c && ['Draft', 'Approved'].includes(c.status)
  const preview = useQuery(`/api/notifications/campaigns/${id}/preview`, { s: c?.status ?? '' })
  const [tick, setTick] = useState(0)
  const [key] = useState(() => (crypto.randomUUID ? crypto.randomUUID() : `k-${Date.now()}-${Math.random().toString(16).slice(2)}`))
  const [confirmed, setConfirmed] = useState(false)
  const [edit, setEdit] = useState(null)
  const refresh = () => { campaign.reload(); preview.reload(); setTick((t) => t + 1); onChanged() }
  const run = useAction(refresh)
  const p = isOpen ? preview.data : null

  const features = useMemo(() => (p ? [{ kind: 'disaster', id: p.disaster.id, latitude: p.disaster.latitude, longitude: p.disaster.longitude, title: p.disaster.label, approximate: p.disaster.approximate }] : []), [p])

  async function saveEdit() {
    const r = await run(() => api.patch(`/api/notifications/campaigns/${id}`, { radius_km: Number(edit.radius_km), channels: edit.channels, required_skills: edit.required_skills, instructions: edit.instructions, verified_info: edit.verified_info }), 'Draft updated', { inline: true })
    if (r.ok) setEdit(null); else window.alert(r.error)
  }

  return (
    <Modal title={c ? `Campaign #${c.id}: ${c.template}` : 'Campaign'} onClose={onClose} wide>
      {!c ? <QueryBoundary query={campaign}>{() => null}</QueryBoundary> : (
        <>
          <p><Badge>{c.status}</Badge> {AUDIENCE_LABEL[c.audience]} · {c.disaster_label} <Badge>{c.disaster_status}</Badge></p>
          <p className="muted">Created by {c.created_by}{c.approved_by && ` · approved by ${c.approved_by} ${fmtDateTime(c.approved_at)}`}{c.dispatched_at && ` · dispatched by ${c.dispatched_by} ${fmtDateTime(c.dispatched_at)} in ${c.mode_at_dispatch} mode`}</p>

          {p && (
            <>
              {p.warnings.map((w) => <p key={w} className="form-error" role="note">{w}</p>)}
              <h4>Target area ({p.target_area.radius_km} km around the incident)</h4>
              <MapBase height={240} features={features} circle={p.target_area} fitSignal={`${id}-${p.target_area.radius_km}`} />
              <h4>Exact message</h4>
              <div className="message-box"><strong>{p.subject}</strong><pre>{p.body}</pre></div>
              {p.sample_personalised_body && <details><summary>Example of one recipient’s personalised copy</summary><pre className="message-box">{p.sample_personalised_body}</pre></details>}
              <h4>Channels and estimated recipients ({p.recipient_count} total)</h4>
              <ul className="plain">
                {Object.entries(p.channels).map(([ch, v]) => <li key={ch}><strong>{CHANNEL_LABEL[ch]}</strong>: {v.eligible} eligible · {v.will_contact_real_people ? <Badge tone="red">will contact real people</Badge> : <Badge tone="gray">{ch === 'in_app' ? 'record inside ReliefSync only' : 'simulated / not live'}</Badge>} · cost: {v.cost}</li>)}
              </ul>
              <details><summary>Recipients ({p.recipients.length}{p.recipients_truncated ? '+' : ''}) and exclusions</summary>
                <ul className="plain">{p.recipients.map((r, i) => <li key={i}>{r.label} · {CHANNEL_LABEL[r.channel]} {r.address_masked !== '(in-app)' && `· ${r.address_masked}`}{r.distance_km != null && ` · ≈ ${r.distance_km} km`}</li>)}</ul>
                {Object.keys(p.excluded).length > 0 && <><strong>Not included:</strong><ul className="plain">{Object.entries(p.excluded).map(([k, v]) => <li key={k}>{v} × {k}</li>)}</ul></>}
              </details>
            </>
          )}
          {preview.error && !p && <ErrorState error={preview.error} onRetry={preview.reload} />}

          {c.status === 'Draft' && !edit && <div className="modal-actions">
            <button type="button" className="btn" onClick={() => setEdit({ radius_km: c.radius_km, channels: c.channels, required_skills: c.required_skills, instructions: c.instructions, verified_info: c.verified_info })}>Edit draft</button>
            <button type="button" className="btn" onClick={() => run(() => api.post(`/api/notifications/campaigns/${id}/cancel`), 'Cancelled')}>Cancel campaign</button>
            <button type="button" className="btn btn-primary" disabled={!p?.recipient_count} onClick={() => window.confirm(`Approve this exact message for ${p.recipient_count} recipient(s)? Approving does not send anything yet.`) && run(() => api.post(`/api/notifications/campaigns/${id}/approve`), 'Approved - ready to dispatch')}>Approve…</button>
          </div>}
          {c.status === 'Draft' && edit && (
            <div className="subpanel">
              <div className="field"><label>Radius (km)<input type="number" min="1" max="500" value={edit.radius_km} onChange={(e) => setEdit({ ...edit, radius_km: e.target.value })} /></label></div>
              <fieldset className="layer-toggles"><legend>Channels</legend>{CHANNELS[c.audience].map((ch) => <label key={ch} className="check"><input type="checkbox" checked={edit.channels.includes(ch)} onChange={() => setEdit({ ...edit, channels: edit.channels.includes(ch) ? edit.channels.filter((x) => x !== ch) : [...edit.channels, ch] })} />{CHANNEL_LABEL[ch]}</label>)}</fieldset>
              {c.audience === 'volunteers' && <div className="field"><label>Required skills<input value={edit.required_skills} onChange={(e) => setEdit({ ...edit, required_skills: e.target.value })} /></label></div>}
              <div className="field"><label>Instructions<textarea rows={2} value={edit.instructions} onChange={(e) => setEdit({ ...edit, instructions: e.target.value })} /></label></div>
              {c.audience === 'residents' && <div className="field"><label>Verified public information<textarea rows={3} value={edit.verified_info} onChange={(e) => setEdit({ ...edit, verified_info: e.target.value })} /></label></div>}
              <div className="modal-actions"><button type="button" className="btn" onClick={() => setEdit(null)}>Discard</button><button type="button" className="btn btn-primary" onClick={saveEdit}>Save draft</button></div>
            </div>
          )}
          {c.status === 'Approved' && p && (
            <div className="subpanel">
              <label className="check"><input type="checkbox" checked={confirmed} onChange={(e) => setConfirmed(e.target.checked)} />
                I confirm: send the message above to {p.recipient_count} recipient(s) via {Object.keys(p.channels).map((x) => CHANNEL_LABEL[x]).join(' + ')} in <strong>{p.mode}</strong> mode.</label>
              <div className="modal-actions">
                <button type="button" className="btn" onClick={() => run(() => api.post(`/api/notifications/campaigns/${id}/cancel`), 'Cancelled')}>Cancel campaign</button>
                <button type="button" className="btn btn-primary" disabled={!confirmed} onClick={() => run(() => api.post(`/api/notifications/campaigns/${id}/dispatch`, { confirm: true, idempotency_key: key }), 'Dispatch finished - see delivery status')}>Dispatch now</button>
              </div>
              <small className="muted">Double-clicking is safe: this request carries a one-time key, so it can only run once.</small>
            </div>
          )}
          {['Dispatching', 'Dispatched', 'Partially Failed', 'Failed'].includes(c.status) && (
            <>
              <h4>Delivery status</h4>
              <Deliveries id={id} reloadKey={tick} />
              {['Partially Failed', 'Failed'].includes(c.status) && (
                <div className="modal-actions"><button type="button" className="btn btn-primary" onClick={() => window.confirm('Retry only the FAILED deliveries? Messages already accepted are never re-sent.') && run(() => api.post(`/api/notifications/campaigns/${id}/retry-failed`, { confirm: true }), 'Retry finished')}>Retry failed deliveries…</button></div>
              )}
            </>
          )}
        </>
      )}
    </Modal>
  )
}

function CampaignsTab({ initialDisaster }) {
  const [status, setStatus] = useState('')
  const q = useQuery('/api/notifications/campaigns', { status, limit: 100 })
  const [builder, setBuilder] = useState(Boolean(initialDisaster))
  const [openId, setOpenId] = useState(null)
  return (
    <>
      <div className="row space">
        <select aria-label="Filter by status" value={status} onChange={(e) => setStatus(e.target.value)}>
          <option value="">All campaigns</option>{['Draft', 'Approved', 'Dispatched', 'Partially Failed', 'Failed', 'Cancelled'].map((s) => <option key={s}>{s}</option>)}
        </select>
        <button type="button" className="btn btn-primary" onClick={() => setBuilder(true)}>+ Create alert or message</button>
      </div>
      <Card>
        <QueryBoundary query={q}>
          {(page) => (
            <DataTable caption="Campaigns" rows={page.items} empty={<EmptyState title="No campaigns yet">Create a draft to preview an audience and message. Nothing is sent until you approve and confirm.</EmptyState>} columns={[
              { header: '#', render: (c) => c.id },
              { header: 'Campaign', render: (c) => <><strong>{c.template}</strong><span className="sub">{AUDIENCE_LABEL[c.audience]} · {c.channels.map((x) => CHANNEL_LABEL[x]).join(', ')} · {c.radius_km} km</span></> },
              { header: 'Incident', render: (c) => <>{c.disaster_label}<span className="sub">{c.disaster_status}</span></> },
              { header: 'Status', render: (c) => <Badge>{c.status}</Badge> },
              { header: 'History', render: (c) => <small>drafted {fmtDateTime(c.created_at)}{c.dispatched_at ? ` · dispatched ${fmtDateTime(c.dispatched_at)} (${c.mode_at_dispatch})` : ''}</small> },
              { header: '', className: 'actions', render: (c) => <button type="button" className="btn btn-sm" onClick={() => setOpenId(c.id)}>Open</button> },
            ]} />
          )}
        </QueryBoundary>
      </Card>
      {builder && <Builder initialDisaster={initialDisaster} onClose={() => setBuilder(false)} onCreated={(c) => { setBuilder(false); setOpenId(c.id); q.reload() }} />}
      {openId && <CampaignDetail id={openId} onClose={() => setOpenId(null)} onChanged={q.reload} />}
    </>
  )
}

function InboxTab() {
  const [type, setType] = useState('')
  const q = useQuery('/api/notifications/inbox', { recipient_type: type, limit: 100 })
  const run = useAction(q.reload)
  return (
    <>
      <p className="muted">In-app alerts are recorded here for the selected volunteer recipients. External SMS/email is sent only when a provider is configured and the campaign is explicitly approved and dispatched.</p>
      <select aria-label="Recipient type" value={type} onChange={(e) => setType(e.target.value)}><option value="">All recipients</option><option value="volunteer">Volunteers</option><option value="shelter">Shelters</option><option value="public">Public feed</option></select>
      <Card>
        <QueryBoundary query={q}>
          {(page) => (
            <DataTable caption="In-app notifications" rows={page.items} empty={<EmptyState title="No in-app notifications" />} columns={[
              { header: 'To', render: (n) => `${n.recipient_type}${n.recipient_id ? ` #${n.recipient_id}` : ''}` },
              { header: 'Message', render: (n) => <><strong>{n.title}</strong><pre className="msg-inline">{n.body}</pre></> },
              { header: 'Created', render: (n) => fmtDateTime(n.created_at) },
              { header: '', className: 'actions', render: (n) => n.read_at ? <Badge tone="gray">read</Badge> : <button type="button" className="btn btn-sm" onClick={() => run(() => api.post(`/api/notifications/inbox/${n.id}/read`))}>Mark read</button> },
            ]} />
          )}
        </QueryBoundary>
      </Card>
    </>
  )
}

function SubscribersTab() {
  const q = useQuery('/api/subscriptions', { limit: 200 })
  return (
    <QueryBoundary query={q}>
      {(page) => (
        <>
          <p className="muted">Contacts are masked and areas are coarse (≈ 11 km). People manage their own subscription from the Public Alerts page. {Object.entries(page.counts).map(([k, v]) => `${v} ${k.toLowerCase()}`).join(' · ')}</p>
          <Card><DataTable caption="Subscribers" rows={page.items} empty={<EmptyState title="No subscribers yet" />} columns={[
            { header: 'Contact', render: (s) => `${s.channel}: ${s.contact_masked}` },
            { header: 'Area', render: (s) => `${s.area_label || 'unnamed'} · ${s.area_latitude}, ${s.area_longitude} · ${s.radius_km} km` },
            { header: 'Status', render: (s) => <Badge>{s.status}</Badge> },
            { header: 'Consent recorded', render: (s) => fmtDateTime(s.consent_at) },
          ]} /></Card>
        </>
      )}
    </QueryBoundary>
  )
}

function AuditTab() {
  const q = useQuery('/api/notifications/audit', { limit: 200 })
  return (
    <Card>
      <QueryBoundary query={q}>
        {(page) => <DataTable caption="Audit trail" rows={page.items} empty={<EmptyState title="Nothing recorded yet" />} columns={[
          { header: 'When', render: (a) => fmtDateTime(a.at) }, { header: 'Who', render: (a) => a.actor }, { header: 'Action', render: (a) => a.action },
          { header: 'Entity', render: (a) => `${a.entity_type}${a.entity_id ? ` #${a.entity_id}` : ''}` }, { header: 'Detail', render: (a) => <small>{a.detail}</small> },
        ]} />}
      </QueryBoundary>
    </Card>
  )
}

export default function Notifications() {
  const params = useHashParams()
  const op = useOperator()
  const [tab, setTab] = useState('campaigns')
  const tabs = { campaigns: 'Campaigns', inbox: 'In-app inbox', subscribers: 'Subscribers', audit: 'Audit trail' }
  return (
    <>
      <PageHeader title="Volunteer alerts & notifications" subtitle="Compose a volunteer message, preview recipients, then approve and dispatch it." />
      {!op.hasKey && <p className="notice">Sign in with your team account before creating or sending volunteer alerts.</p>}
      <ModeStrip />
      <div className="tabs" role="tablist">
        {Object.entries(tabs).map(([k, v]) => <button key={k} type="button" role="tab" aria-selected={tab === k} className={`tab ${tab === k ? 'active' : ''}`} onClick={() => setTab(k)}>{v}</button>)}
      </div>
      {tab === 'campaigns' && <CampaignsTab initialDisaster={params.disaster} />}
      {tab === 'inbox' && <InboxTab />}
      {tab === 'subscribers' && <SubscribersTab />}
      {tab === 'audit' && <AuditTab />}
    </>
  )
}
