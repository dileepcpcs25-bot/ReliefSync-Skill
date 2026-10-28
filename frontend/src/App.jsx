import { lazy, Suspense } from 'react'
import Layout from './components/Layout'
import ToastProvider from './components/ToastProvider'
import { EmptyState, Spinner } from './components/ui'
import { useHashRoute } from './hooks/useHashRoute'
import Allocations from './pages/Allocations'
import Assignments from './pages/Assignments'
import Dashboard from './pages/Dashboard'
import Disasters from './pages/Disasters'
import Guide from './pages/Guide'
import History from './pages/History'
import Inventory from './pages/Inventory'
import Login from './pages/Login'
import Shelters from './pages/Shelters'
import SmartAllocation from './pages/SmartAllocation'
import SmartPriority from './pages/SmartPriority'
import Volunteers from './pages/Volunteers'

// Pages that include the map library are loaded on demand to keep the first screen fast.
const MapPage = lazy(() => import('./pages/MapPage'))
const Notifications = lazy(() => import('./pages/Notifications'))
const Alerts = lazy(() => import('./pages/Alerts'))
const ExternalObservations = lazy(() => import('./pages/ExternalObservations'))

const PAGES = {
  dashboard: Dashboard,
  login: Login,
  guide: Guide,
  history: History,
  disasters: Disasters,
  priority: SmartPriority,
  volunteers: Volunteers,
  assignments: Assignments,
  inventory: Inventory,
  shelters: Shelters,
  'smart-allocation': SmartAllocation,
  allocations: Allocations,
  map: MapPage,
  external: ExternalObservations,
  notifications: Notifications,
  alerts: Alerts,
}

export default function App() {
  const route = useHashRoute()
  const Page = PAGES[route]
  return (
    <ToastProvider>
      <Layout route={route}>
        {Page ? <Suspense fallback={<Spinner />}><Page /></Suspense> : <EmptyState title="Page not found">Choose a section from the navigation.</EmptyState>}
      </Layout>
    </ToastProvider>
  )
}
