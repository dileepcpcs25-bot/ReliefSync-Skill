import 'leaflet/dist/leaflet.css'
import L from 'leaflet'
import { useEffect, useMemo } from 'react'
import { Circle, MapContainer, Marker, Polyline, TileLayer, useMap, useMapEvents } from 'react-leaflet'
import { KINDS, SEVERITY_RING, TILE_ATTRIBUTION, TILE_URL, WORLD_VIEW } from './mapConfig'

const iconCache = new Map()
function pinIcon(kind, { selected, approximate, severity }) {
  const k = KINDS[kind] ?? KINDS.disaster
  const key = `${kind}|${selected}|${approximate}|${severity ?? ''}`
  if (!iconCache.has(key)) {
    const ring = severity && SEVERITY_RING[severity] ? `box-shadow:0 0 0 3px ${SEVERITY_RING[severity]}55;` : ''
    iconCache.set(key, L.divIcon({
      className: 'pin-wrap',
      html: `<span class="pin pin-${k.shape} ${approximate ? 'pin-approx' : ''} ${selected ? 'pin-selected' : ''}" style="--pin:${k.color};${ring}"><i>${k.symbol}</i></span>`,
      iconSize: [30, 30],
      iconAnchor: [15, 15],
    }))
  }
  return iconCache.get(key)
}

const pickIcon = L.divIcon({ className: 'pin-wrap', html: '<span class="pin pin-circle pin-selected" style="--pin:#175cd3"><i>+</i></span>', iconSize: [30, 30], iconAnchor: [15, 15] })

function IncidentHeatLayer({ features, heatSeverityWeight }) {
  const map = useMap()
  useEffect(() => {
    const layer = L.gridLayer({ tileSize: 256, opacity: 0.78, zIndex: 390 })
    layer.createTile = (coords, done) => {
      const tile = document.createElement('canvas')
      tile.width = 256
      tile.height = 256
      const context = tile.getContext('2d')
      const origin = L.point(coords.x * 256, coords.y * 256)
      if (!context) { done(null, tile); return tile }
      for (const f of features) {
        const p = map.project([f.latitude, f.longitude], coords.z).subtract(origin)
        const radius = 46
        if (p.x < -radius || p.x > 256 + radius || p.y < -radius || p.y > 256 + radius) continue
        const severity = { Critical: 1, High: 0.82, Medium: 0.64, Low: 0.46 }[f.severity] ?? 0.46
        const affected = Math.max(0, Number(f.details?.people_affected) || 0)
        const populationFactor = Math.min(1, Math.log10(affected + 1) / 6)
        const severityWeight = heatSeverityWeight / 100
        const intensity = Math.min(1, severity * severityWeight + populationFactor * (1 - severityWeight))
        const gradient = context.createRadialGradient(p.x, p.y, 2, p.x, p.y, radius)
        gradient.addColorStop(0, `rgba(185, 28, 28, ${0.26 + intensity * 0.50})`)
        gradient.addColorStop(0.45, `rgba(234, 88, 12, ${0.12 + intensity * 0.26})`)
        gradient.addColorStop(1, 'rgba(250, 204, 21, 0)')
        context.fillStyle = gradient
        context.fillRect(p.x - radius, p.y - radius, radius * 2, radius * 2)
      }
      done(null, tile)
      return tile
    }
    layer.addTo(map)
    return () => map.removeLayer(layer)
  }, [features, heatSeverityWeight, map])
  return null
}
function Fit({ points, signal }) {
  const map = useMap()
  useEffect(() => {
    if (!points.length) return
    if (points.length === 1) map.setView(points[0], Math.max(map.getZoom(), 9))
    else map.fitBounds(L.latLngBounds(points), { padding: [40, 40], maxZoom: 12 })
    // refit only when the caller asks (signal changes), not on every data refresh
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [signal])
  return null
}

function Focus({ focus }) {
  const map = useMap()
  useEffect(() => {
    if (focus) map.flyTo([focus.latitude, focus.longitude], focus.zoom ?? 11, { duration: 0.6 })
  }, [focus, map])
  return null
}

function Picker({ onPick }) {
  useMapEvents({ click: (e) => onPick?.(Number(e.latlng.lat.toFixed(6)), Number(e.latlng.lng.toFixed(6))) })
  return null
}

/**
 * features: [{ kind, id, latitude, longitude, title, approximate, severity }]; onSelect(feature)
 * circle: { latitude, longitude, radius_km } target-area preview; route: [[lat,lng],...]; picked: { latitude, longitude }
 */
export default function MapBase({ features = [], selectedKey, onSelect, circle, route, picked, onPick, focus, fitSignal, height = 520, heatPoints = [], heatSeverityWeight = 65 }) {
  const points = useMemo(() => features.map((f) => [f.latitude, f.longitude]), [features])
  return (
    <MapContainer center={WORLD_VIEW.center} zoom={WORLD_VIEW.zoom} minZoom={2} worldCopyJump style={{ height, width: '100%', borderRadius: 10 }} scrollWheelZoom>
      <TileLayer url={TILE_URL} attribution={TILE_ATTRIBUTION} maxZoom={19} />
      {heatPoints.length > 0 && <IncidentHeatLayer features={heatPoints} heatSeverityWeight={heatSeverityWeight} />}
      {features.map((f) => (
        <Marker
          key={`${f.kind}-${f.id}`}
          position={[f.latitude, f.longitude]}
          icon={pinIcon(f.kind, { selected: selectedKey === `${f.kind}-${f.id}`, approximate: f.approximate, severity: f.severity })}
          title={f.title}
          eventHandlers={{ click: () => onSelect?.(f) }}
        />
      ))}
      {circle && <Circle center={[circle.latitude, circle.longitude]} radius={circle.radius_km * 1000} pathOptions={{ color: '#175cd3', weight: 2, fillOpacity: 0.07, dashArray: '6 6' }} />}
      {route?.length > 1 && <Polyline positions={route} pathOptions={{ color: '#175cd3', weight: 4, opacity: 0.8 }} />}
      {picked && <Marker position={[picked.latitude, picked.longitude]} icon={pickIcon} />}
      {onPick && <Picker onPick={onPick} />}
      <Fit points={circle ? [...points, [circle.latitude, circle.longitude]] : points} signal={fitSignal} />
      <Focus focus={focus} />
    </MapContainer>
  )
}



