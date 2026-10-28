import { Card, DataTable, PageHeader } from '../components/ui'

const actions = [
  { name: 'Fetch latest external data', api: 'POST /api/external/refresh', effect: 'Fetches current USGS and GDACS observations; NASA FIRMS runs only when its free key and area are configured.' },
  { name: 'Refresh map', api: 'GET /api/map/features', effect: 'Reloads known incident, observation, shelter, inventory and allocation locations.' },
  { name: 'Search a place', api: 'GET /api/geo/geocode', effect: 'Looks up a place with the public OpenStreetMap Nominatim service.' },
  { name: 'Recalculate priority', api: 'GET /api/intelligence/priority', effect: 'Applies the documented severity, population and status scoring rules to current incidents.' },
  { name: 'Refresh suggestions', api: 'GET /api/intelligence/recommendations', effect: 'Calculates suggested resource quantities without deducting stock.' },
  { name: 'Confirm allocation', api: 'POST /api/allocations', effect: 'Records a reviewed allocation and deducts stock using backend validation.' },
  { name: 'Dispatch notification', api: 'POST /api/notifications/campaigns/{id}/dispatch', effect: 'Rechecks eligibility and records delivery results; development mode simulates email/SMS.' },
]

export default function Guide() {
  return (
    <>
      <PageHeader title="How ReliefSync works" subtitle="A small, inspectable stack: React + Vite, FastAPI, SQLAlchemy for operational records, and MongoDB for the external observation archive." />
      <Card title="Button actions and API methods">
        <DataTable caption="Action to API mapping" columns={[{ header: 'Button', key: 'name' }, { header: 'API method', key: 'api' }, { header: 'What happens', key: 'effect' }]} rows={actions} rowKey={(r) => r.name} />
      </Card>
      <Card title="Data and storage">
        <ul>
          <li>Public live feeds: USGS earthquakes and GDACS global alerts. NASA FIRMS is optional and uses a free key.</li>
          <li>Map layers and filters are saved in this browser with localStorage. Operator credentials remain in sessionStorage and are cleared when the tab closes.</li>
          <li>Forms validate in the browser for quick feedback; FastAPI validates every request again before saving.</li>
          <li>Priority and allocation calculations run in the backend, where their rules can be reviewed in <code>backend/app/services/priority.py</code> and <code>allocation.py</code>.</li>
          <li>This app uses React/Vite and FastAPI consistently; adding another framework would duplicate routing and validation without improving the requested workflows.</li>
        </ul>
      </Card>
    </>
  )
}
