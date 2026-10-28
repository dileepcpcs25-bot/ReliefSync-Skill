export const TILE_URL = import.meta.env.VITE_MAP_TILE_URL || 'https://tile.openstreetmap.org/{z}/{x}/{y}.png'
export const TILE_ATTRIBUTION = import.meta.env.VITE_MAP_TILE_ATTRIBUTION || '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
export const USING_PUBLIC_OSM_TILES = !import.meta.env.VITE_MAP_TILE_URL

export const WORLD_VIEW = { center: [20, 10], zoom: 2 }

/** One entry per category. Shape + colour + symbol differ so categories are distinguishable without colour alone. */
export const KINDS = {
  disaster: { label: 'Disaster report (operational record)', color: '#d92d20', symbol: '!', shape: 'circle', layer: 'disasters' },
  external: { label: 'External observation (unverified)', color: '#7a5af8', symbol: 'E', shape: 'diamond', layer: 'external' },
  shelter: { label: 'Shelter', color: '#17a362', symbol: 'S', shape: 'square', layer: 'shelters' },
  inventory: { label: 'Inventory storage', color: '#1570ef', symbol: 'I', shape: 'square', layer: 'inventory' },
  allocation: { label: 'Allocation destination', color: '#f79009', symbol: 'A', shape: 'diamond', layer: 'allocations' },
  volunteer: { label: 'Volunteer (approximate, operators only)', color: '#0e9384', symbol: 'V', shape: 'circle', layer: 'volunteers' },
}

export const LAYER_OPTIONS = [
  { id: 'disasters', label: 'Disaster reports' },
  { id: 'external', label: 'External observations' },
  { id: 'shelters', label: 'Shelters' },
  { id: 'inventory', label: 'Inventory storage' },
  { id: 'allocations', label: 'Allocation destinations' },
  { id: 'volunteers', label: 'Volunteers (operators)' },
]

export const SEVERITY_RING = { Low: '#98a2b3', Medium: '#f79009', High: '#f04438', Critical: '#7a271a' }
