# ReliefSync learning guide

## Request path

```text
React page / event handler
  -> frontend/src/services/api.js (HTTP + operator headers + errors)
  -> FastAPI router (validation + operator authorization)
  -> service code (rules, external adapter, proximity calculations)
  -> SQLAlchemy session -> local SQLite operational tables
                         -> MongoDB external observation archive (optional)
  -> JSON response -> React state -> table/map/dashboard
```

FastAPI's `/docs` displays the active API schema. `GET` reads; `POST` creates a record or runs an explicit action; `PATCH` updates selected fields; `DELETE` removes only eligible records. Validation rejects malformed inputs before persistence. The shared operator key is a local demonstration guard, not individual identity management.

## React state and storage

Pages call `useQuery` for API data and `useAction` for user actions. Buttons call an explicit handler, refresh the affected query, and surface failures. Map filters use a local-storage hook for non-sensitive preferences. The operator key is held in session storage, not persisted as a durable account credential. Passwords and external API secrets are not stored in browser storage.

## Data and database

SQLAlchemy models store incidents, volunteers, shelters, assignments, stock, allocations, and notifications in the configured operational SQL database (SQLite by default). MongoDB stores an archive copy of refreshed external observations. External providers are normalized into the `external_events` table so source data stays separate from operator-entered incidents. Check constraints and API validation protect coordinates and resource state.

## External integrations

USGS and GDACS are no-key public feeds. NASA EONET v3 contributes global curated event metadata with no key. NASA FIRMS requires a free MAP_KEY. Open-Meteo supplies weather, and OpenStreetMap public services are used for maps, geocoding, and routing subject to fair-use limits. Every imported event retains source attribution and retrieval time; external records are never silently promoted to an operational incident.

ISRO/NRSC Bhuvan and NDEM provide India-focused services; NDEM datasets are not assumed to be public. MOSDAC supports dataset search and authenticated data download. ReliefSync links these portals and documents their access requirements; it does not claim an authorized ISRO API integration without account credentials/service permission.

## Map, priority, and resource lookup

Map features come from database coordinates only; unknown locations stay unknown. Priority and allocation helpers are deterministic rule-based scores and recommendations. The historical page matches a selected stored event to current volunteer/shelter rows using haversine straight-line distance. It does not reconstruct past availability. See `docs/REGIONAL-DATA.md` for data provenance and limits.

## Forecasting and LLMs

This version does not call an LLM and does not have a trained demand forecast. Smart Priority and Smart Allocation use deterministic rules. A future forecast should first check the completeness of logged requests/consumption and report insufficient data rather than treating affected-population counts as consumption.

## Notifications

Notification campaigns follow Draft → Preview → Approve → Dispatch. Development-mode in-app messages are stored in the database; external email/SMS sends are simulated, so no real address is contacted. A real provider needs credentials and an explicit live-mode configuration. Tests use a mocked network and cannot contact external messaging providers.
