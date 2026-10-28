export const SEVERITIES = ['Low', 'Medium', 'High', 'Critical']
export const DISASTER_STATUSES = ['Active', 'Monitoring', 'Resolved']
export const CATEGORIES = ['Food', 'Water', 'Medical', 'Shelter', 'Clothing', 'Hygiene', 'Other']
export const ALLOCATION_STATUSES = ['Confirmed', 'In Transit', 'Delivered', 'Cancelled']
export const MAX_PRIORITY_SCORE = 90

export const TONES = {
  Critical: 'red', High: 'amber', Medium: 'blue', Low: 'green',
  Active: 'red', Monitoring: 'amber', Resolved: 'gray',
  Available: 'green', Assigned: 'blue', Unavailable: 'gray',
  Completed: 'green', Cancelled: 'gray',
  Confirmed: 'blue', 'In Transit': 'amber', Delivered: 'green',
  Unreviewed: 'amber', Reviewed: 'blue', Dismissed: 'gray', Promoted: 'green',
  Draft: 'gray', Approved: 'blue', Dispatching: 'amber', Dispatched: 'green', 'Partially Failed': 'amber', Failed: 'red',
  Pending: 'amber', Open: 'green', Full: 'red', 'Low stock': 'amber', 'In stock': 'green',
  recorded_in_app: 'blue', simulated: 'gray', accepted_by_provider: 'green', failed: 'red', pending: 'amber', skipped: 'gray',
}

export const STATUS_RULE_TEXT = 'Resolved incidents are excluded.'
export const DELIVERY_LABELS = {
  recorded_in_app: 'Recorded in app',
  simulated: 'Simulated (nothing sent)',
  accepted_by_provider: 'Accepted by provider (delivery not confirmed)',
  failed: 'Failed',
  pending: 'Pending',
  skipped: 'Skipped',
}

export const ROUTES = [
  { id: 'login', label: 'Sign in', icon: 'login' },
  { id: 'guide', label: 'How it works', icon: 'guide' },
  { id: 'dashboard', label: 'Dashboard', icon: 'dashboard' },
  { id: 'disasters', label: 'Disasters', icon: 'alert' },
  { id: 'map', label: 'Map', icon: 'map' },
  { id: 'external', label: 'External Observations', icon: 'globe' },
  { id: 'history', label: 'Past events & resources', icon: 'clock' },
  { id: 'priority', label: 'Smart Priority', icon: 'bars' },
  { id: 'volunteers', label: 'Volunteers', icon: 'users' },
  { id: 'assignments', label: 'Assignments', icon: 'clipboard' },
  { id: 'inventory', label: 'Inventory', icon: 'box' },
  { id: 'shelters', label: 'Shelters', icon: 'home' },
  { id: 'smart-allocation', label: 'Smart Allocation', icon: 'spark' },
  { id: 'allocations', label: 'Allocations', icon: 'truck' },
  { id: 'notifications', label: 'Notifications', icon: 'bell' },
  { id: 'alerts', label: 'Public Alerts', icon: 'radio' },
]

export const fmt = (n) => Number(n ?? 0).toLocaleString()
export const fmtDate = (iso) => new Date(iso).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })
export const plural = (n, one, many = `${one}s`) => `${fmt(n)} ${Number(n) === 1 ? one : many}`

export const locationField = (searchFrom) => ({
  name: 'position', type: 'location', label: 'Map location (optional)', searchFrom,
  names: { lat: 'latitude', lng: 'longitude', source: 'location_source', approx: 'location_approximate' },
})

export const fmtDateTime = (iso) => (iso ? new Date(iso).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' }) : '-')

export const REGIONS = [
  { id: '', label: 'Anywhere in the world' },
  { id: 'south-asia', label: 'India & South Asia', box: { west: 60, south: 5, east: 100, north: 38 } },
  { id: 'east-asia', label: 'East & Southeast Asia', box: { west: 95, south: -11, east: 150, north: 55 } },
  { id: 'europe-africa', label: 'Europe, Middle East & Africa', box: { west: -25, south: -36, east: 60, north: 72 } },
  { id: 'americas', label: 'The Americas', box: { west: -170, south: -56, east: -30, north: 72 } },
  { id: 'oceania', label: 'Oceania', box: { west: 110, south: -50, east: 180, north: -1 } },
]
export const EXTERNAL_SOURCES = [
  { id: 'usgs', label: 'USGS (earthquakes)' },
  { id: 'gdacs', label: 'GDACS (global alerts)' },
  { id: 'firms', label: 'NASA FIRMS (fires)' },
  { id: 'eonet', label: 'NASA EONET (natural events)' },
]
