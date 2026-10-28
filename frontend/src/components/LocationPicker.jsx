import 'leaflet/dist/leaflet.css'
import { useState } from 'react'
import { api, qs } from '../services/api'
import MapBase from './map/MapBase'

const SOURCE_LABEL = { manual: 'typed in', map: 'picked on the map', geocoded: 'found by address search (approximate)', external: 'from an external observation (approximate)' }

/**
 * Pick a position by clicking the map, searching for an address, or typing coordinates.
 * value: { latitude, longitude, source, approximate }; onChange(partial value). Coordinates are never invented:
 * an empty picker means "position unknown".
 */
export default function LocationPicker({ value, onChange, searchText }) {
  const [query, setQuery] = useState('')
  const [busy, setBusy] = useState(false)
  const [result, setResult] = useState(null)
  const [error, setError] = useState('')
  const lat = value.latitude === '' || value.latitude == null ? null : Number(value.latitude)
  const lng = value.longitude === '' || value.longitude == null ? null : Number(value.longitude)
  const has = Number.isFinite(lat) && Number.isFinite(lng)
  const q = query || searchText || ''

  async function search() {
    if (q.trim().length < 3) { setError('Type at least 3 characters to search.'); return }
    setBusy(true); setError(''); setResult(null)
    try { setResult(await api.get(`/api/geo/geocode${qs({ q })}`)) } catch (e) { setError(e.message) }
    setBusy(false)
  }
  const choose = (c) => { onChange({ latitude: c.latitude, longitude: c.longitude, source: 'geocoded', approximate: true }); setResult(null) }

  return (
    <div className="picker">
      <div className="picker-search">
        <input type="search" aria-label="Search for a place" placeholder={searchText ? `Search (default: ${searchText})` : 'Search for a place or address'} value={query}
          onChange={(e) => setQuery(e.target.value)} onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); search() } }} />
        <button type="button" className="btn" onClick={search} disabled={busy}>{busy ? 'Searching…' : 'Find on map'}</button>
      </div>
      {error && <p className="field-error" role="alert">{error}</p>}
      {result && (
        <div className="picker-results" role="group" aria-label="Search results">
          {result.candidates.length === 0 && <p className="muted">No place found. Click the map to set the position yourself.</p>}
          {result.ambiguous && <p className="form-error">Several different places match. Choose the correct one - ReliefSync will not guess.</p>}
          {result.candidates.map((c) => (
            <button type="button" key={c.osm_ref + c.display_name} className="btn btn-block" onClick={() => choose(c)}>{c.display_name}</button>
          ))}
          <small className="muted">{result.attribution}{result.cached ? ' (cached result)' : ''}</small>
        </div>
      )}
      <MapBase height={230} picked={has ? { latitude: lat, longitude: lng } : null} focus={has ? { latitude: lat, longitude: lng, zoom: 12 } : null}
        onPick={(la, lo) => onChange({ latitude: la, longitude: lo, source: 'map', approximate: false })} />
      <div className="picker-coords">
        <label>Latitude<input inputMode="decimal" value={value.latitude ?? ''} onChange={(e) => onChange({ latitude: e.target.value, source: 'manual', approximate: false })} placeholder="e.g. 13.0827" /></label>
        <label>Longitude<input inputMode="decimal" value={value.longitude ?? ''} onChange={(e) => onChange({ longitude: e.target.value, source: 'manual', approximate: false })} placeholder="e.g. 80.2707" /></label>
        <button type="button" className="btn" onClick={() => onChange({ latitude: '', longitude: '', source: '', approximate: false })} disabled={!has && value.latitude === ''}>Clear</button>
      </div>
      <small className="muted">
        {has ? `Position ${SOURCE_LABEL[value.source] ?? 'entered'}${value.approximate ? ' - marked approximate' : ''}.` : 'Position unknown. Click the map, search, or type coordinates. Leave empty if you do not know it.'}
        {' '}Map: click to place the marker.
      </small>
    </div>
  )
}
