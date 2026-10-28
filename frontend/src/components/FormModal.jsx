import { lazy, Suspense, useId, useState } from 'react'
import { Modal, Spinner } from './ui'

const LocationPicker = lazy(() => import('./LocationPicker'))

function validate(fields, values) {
  const errors = {}
  for (const f of fields) {
    if (f.type === 'location') {
      const n = f.names
      const la = values[n.lat], lo = values[n.lng]
      const blank = (x) => x === '' || x === undefined || x === null
      if (blank(la) !== blank(lo)) errors[f.name] = 'Enter both latitude and longitude, or neither.'
      else if (!blank(la)) {
        const a = Number(la), b = Number(lo)
        if (!Number.isFinite(a) || a < -90 || a > 90) errors[f.name] = 'Latitude must be a number from -90 to 90.'
        else if (!Number.isFinite(b) || b < -180 || b > 180) errors[f.name] = 'Longitude must be a number from -180 to 180.'
      }
      continue
    }
    const v = values[f.name]
    const empty = v === '' || v === undefined || v === null
    if (f.required && empty) errors[f.name] = 'This field is required.'
    else if (f.type === 'number' && !empty) {
      const n = Number(v)
      if (!Number.isFinite(n) || !Number.isInteger(n)) errors[f.name] = 'Enter a whole number.'
      else if (f.min !== undefined && n < f.min) errors[f.name] = `Must be at least ${f.min}.`
      else if (f.max !== undefined && n > f.max) errors[f.name] = `Must be at most ${f.max}.`
    }
  }
  return errors
}

/**
 * Config-driven form dialog. `fields`: [{ name, label, type, options, required, min, max, placeholder, help }]
 * `onSubmit(values)` must resolve to { ok, error } (see useAction with { inline: true }).
 */
export default function FormModal({ title, fields, initial = {}, submitLabel = 'Save', onSubmit, onClose }) {
  const formId = useId()
  const [values, setValues] = useState(() => {
    const out = {}
    for (const f of fields) {
      if (f.type === 'location') {
        for (const key of Object.values(f.names)) if (key) out[key] = initial[key] ?? ''
      } else {
        out[f.name] = initial[f.name] ?? (f.type === 'checkbox' ? false : '')
      }
    }
    return out
  })
  const [errors, setErrors] = useState({})
  const [serverError, setServerError] = useState('')
  const [busy, setBusy] = useState(false)

  const set = (name, value) => setValues((v) => ({ ...v, [name]: value }))

  async function handleSubmit(e) {
    e.preventDefault()
    const found = validate(fields, values)
    setErrors(found)
    if (Object.keys(found).length) return
    const payload = Object.fromEntries(
      fields.filter((f) => f.type !== 'location').map((f) => [f.name, f.type === 'number' ? Number(values[f.name]) : f.type === 'select-number' ? Number(values[f.name]) : values[f.name]]),
    )
    for (const f of fields.filter((x) => x.type === 'location')) {
      const n = f.names
      if (values[n.lat] !== '' && values[n.lng] !== '') {
        payload[n.lat] = Number(values[n.lat])
        payload[n.lng] = Number(values[n.lng])
        if (values[n.source]) payload[n.source] = values[n.source]
        if (n.approx) payload[n.approx] = ['geocoded', 'external'].includes(values[n.source])
      }
    }
    setBusy(true)
    setServerError('')
    const result = await onSubmit(payload)
    setBusy(false)
    if (result.ok) onClose()
    else setServerError(result.error)
  }

  return (
    <Modal title={title} onClose={onClose}>
      <form onSubmit={handleSubmit} noValidate>
        {fields.map((f) => {
          const id = `${formId}-${f.name}`
          if (f.type === 'location') {
            const n = f.names
            return (
              <div className="field" key={f.name}>
                <span className="label-like">{f.label}</span>
                <Suspense fallback={<Spinner label="Loading map…" />}>
                  <LocationPicker
                    searchText={f.searchFrom ? values[f.searchFrom] : ''}
                    value={{ latitude: values[n.lat], longitude: values[n.lng], source: values[n.source], approximate: values[n.approx] }}
                    onChange={(p) => setValues((v) => ({
                      ...v,
                      ...(p.latitude !== undefined && { [n.lat]: p.latitude }),
                      ...(p.longitude !== undefined && { [n.lng]: p.longitude }),
                      ...(p.source !== undefined && { [n.source]: p.source }),
                      ...(n.approx && p.approximate !== undefined && { [n.approx]: p.approximate }),
                    }))}
                  />
                </Suspense>
                {errors[f.name] && <small className="field-error" role="alert">{errors[f.name]}</small>}
              </div>
            )
          }
          if (f.type === 'checkbox') {
            return (
              <div className="field" key={f.name}>
                <label className="check" htmlFor={id}><input id={id} type="checkbox" checked={Boolean(values[f.name])} onChange={(e) => set(f.name, e.target.checked)} />{f.label}</label>
                {f.help && <small className="muted">{f.help}</small>}
              </div>
            )
          }
          const common = {
            id,
            value: values[f.name],
            onChange: (e) => set(f.name, e.target.value),
            'aria-invalid': Boolean(errors[f.name]),
            'aria-describedby': errors[f.name] ? `${id}-err` : f.help ? `${id}-help` : undefined,
            required: f.required,
          }
          return (
            <div className="field" key={f.name}>
              <label htmlFor={id}>{f.label}{f.required && <span aria-hidden="true"> *</span>}</label>
              {f.type === 'textarea' ? (
                <textarea rows={3} {...common} placeholder={f.placeholder} />
              ) : f.type === 'select' || f.type === 'select-number' ? (
                <select {...common}>
                  <option value="">Select…</option>
                  {f.options.map((o) => {
                    const opt = typeof o === 'object' ? o : { value: o, label: o }
                    return <option key={opt.value} value={opt.value}>{opt.label}</option>
                  })}
                </select>
              ) : (
                <input type={f.type ?? 'text'} min={f.min} max={f.max} placeholder={f.placeholder} {...common} />
              )}
              {f.help && !errors[f.name] && <small id={`${id}-help`} className="muted">{f.help}</small>}
              {errors[f.name] && <small id={`${id}-err`} className="field-error">{errors[f.name]}</small>}
            </div>
          )
        })}
        {serverError && <p className="form-error" role="alert">{serverError}</p>}
        <div className="modal-actions">
          <button type="button" className="btn" onClick={onClose}>Cancel</button>
          <button type="submit" className="btn btn-primary" disabled={busy}>{busy ? 'Saving…' : submitLabel}</button>
        </div>
      </form>
    </Modal>
  )
}
