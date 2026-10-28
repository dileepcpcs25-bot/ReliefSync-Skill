# ReliefSync — Disaster Relief Intelligence System

A full-stack disaster-relief coordination platform: manage disasters, volunteers, supplies, shelters and
resource distribution in one interface, with **transparent, rule-based** prioritisation and allocation
recommendations.

> **Demonstration / decision-support system.** Scores and recommendations are explainable heuristics, **not**
> validated emergency predictions, and this is not a certified emergency-response tool.

## Verification status

- Frontend ESLint is clean, all 23 UI tests pass, and the production build succeeds.
- Backend tests: 192 passed. One third-party Starlette/httpx deprecation warning remains; it does not fail the suite.
- On Windows, extract the ZIP and run `start-reliefsync.bat`. It waits for the API and web server before opening the dashboard. Do not open `frontend/dist/index.html` directly; the app needs its local web server and API.
- Real SMS/email delivery needs your provider credentials and remains disabled by default.

See [Testing](TESTING.md) for exact commands and limits.
## Features

- **Disasters** — report, search/filter (severity, status, type, location), edit, change status, delete (blocked when history exists).
- **Smart Priority** — ranked open incidents with score, level and a plain-language explanation.
- **Volunteers & Assignments** — register volunteers; assign to disasters; one active assignment per volunteer (enforced by a DB partial unique index); availability stays consistent on complete/cancel/resolve.
- **Inventory** — CRUD, atomic stock adjustments (never negative), low-stock flags, category/location filters.
- **Shelters** — capacity and occupancy with enforced bounds; available places.
- **Smart Allocation** — explainable suggestions (read-only) that a user reviews and confirms.
- **Allocations** — history, status flow (Confirmed → In Transit → Delivered), safe cancellation that restores stock once.
- **Dashboard** — aggregates SQLite operations and worldwide observations; first start seeds a dated public-source snapshot and clearly labeled training data.
- **Map** — interactive Leaflet map of incidents, external observations, shelters, stores, allocation destinations (and approximate volunteer positions for operators), with layers, filters, place search, nearby shelters/volunteers, routes and weather. Map preferences persist in localStorage.
- **Operator sign-in** — backend validates the configured shared key; name and key stay in the browser session. Development mode allows local sign-in without a key.
- **How it works** — explains the API methods and what the main buttons do.
- **External Observations** — real data from USGS, GDACS, NASA EONET (no key), and NASA FIRMS (with a free key), cached, deduplicated and always labelled unverified.
- **Past events & resources** — historical event records with current nearby volunteer/shelter status and regional filters.
- **Notifications** — operator-approved, location-based campaigns for volunteers, shelters and opted-in residents, in a safe development mode by default.
- **Public Alerts** — public feed and opt-in subscription with consent, confirmation and one-click unsubscribe.

## Technology

| Layer | Stack |
| --- | --- |
| Frontend | React 19, Vite 8, React Leaflet, plain CSS, Fetch API, native `<dialog>`, `useSyncExternalStore` hash routing |
| Backend | Python 3.12+, FastAPI, SQLAlchemy 2.0 (typed `Mapped`), Pydantic v2, SQLite operational DB, MongoDB external-observation archive, Uvicorn |
| Quality | Pytest + FastAPI TestClient, ESLint 10 (flat config, `eslint-plugin-react-hooks` 7) |

Versions are lower-bounded ranges (see `requirements.txt` / `package.json`); the install resolves the newest compatible releases.

## Architecture

```
ReliefSync/
├── backend/
│   ├── app/
│   │   ├── main.py            # app, CORS, health, error handlers
│   │   ├── config.py          # env-driven settings
│   │   ├── database.py        # engine, sessions, SQLite pragmas (foreign keys, WAL)
│   │   ├── models.py          # tables + CHECK/UNIQUE/FK constraints
│   │   ├── schemas.py         # Pydantic request/response models
│   │   ├── constants.py       # allowed values (single source of truth)
│   │   ├── dependencies.py    # session dep, pagination, 404/409 helpers
│   │   ├── services/          # priority.py, allocation.py  (pure functions, no DB/web imports)
│   │   └── routers/           # disasters, volunteers, assignments, inventory, shelters,
│   │                          # allocations, intelligence, dashboard
│   └── tests/                 # test_services.py (pure), test_api.py (isolated temp DB)
└── frontend/src/
    ├── services/api.js        # all HTTP calls + error normalisation
    ├── hooks/                 # useQuery (abortable), useAction, useHashRoute, toast context
    ├── components/            # Layout, ui kit, FormModal, ToastProvider
    └── pages/                 # 9 pages
```

Business rules live in the database (constraints) and backend services; the frontend only validates for convenience.

## Easiest start on Windows (double-click)

1. Use the refreshed `ReliefSync-MultiUser-Final.zip`. Close previously opened ZIP windows so Windows does not keep showing a cached preview.
2. Right-click the ZIP and choose **Extract All**. Open the extracted `ReliefSync-MultiUser` folder and run `start-reliefsync.bat` there. The launcher also tries to find and extract the newest matching ZIP if it detects a partial preview, but extracting first is the reliable path.
3. Needs Python 3.11+ and Node.js 20.19+ (or 22.12+). The launcher installs backend/frontend dependencies, starts the app on frontend port 5191 and API port 8015, and opens the dashboard.

If the error still names `backend\requirements.txt`, the running batch file is from an old cached ZIP preview. Close that window, extract the refreshed ZIP to a regular folder, and run the batch file from that folder. The refreshed archive contains `ReliefSync-MultiUser/backend/requirements.txt`.

## Windows quick start (PowerShell)

Prerequisites: Python 3.11+, Node.js 20.19+ (or 22.12+).

**Terminal 1 — backend**

```powershell
cd ReliefSync-MultiUser\backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --host 127.0.0.1 --port 8015
```

**Terminal 2 — frontend**

```powershell
cd ReliefSync-MultiUser\frontend
npm ci
npm run dev
```

| What | URL |
| --- | --- |
| Frontend | http://127.0.0.1:5191 |
| API | http://127.0.0.1:8015 |
| Swagger docs | http://127.0.0.1:8015/docs |

Start MongoDB optionally with `docker compose up -d mongodb` from the project root.
## Geographic, external-data and notification features

For direct free API links, key setup, and MongoDB archive configuration, see [FREE-API-SETUP.md](FREE-API-SETUP.md). The collected public data snapshot is in [sample-data/world_disaster_observations.csv](sample-data/world_disaster_observations.csv); its date range and source limits are documented in [docs/REGIONAL-DATA.md](docs/REGIONAL-DATA.md).

### Data sources (what is used and why)

| Purpose | Provider | Key needed | Notes |
| --- | --- | --- | --- |
| Earthquakes | USGS Earthquake Hazards Program GeoJSON feeds | no | Public domain. Default feed `4.5_week`; change `USGS_FEED_URL` (e.g. `2.5_day`). An unknown feed name answers HTTP 200 with text; this is detected as malformed. |
| Global alerts (quake, cyclone, flood, volcano, drought, wildfire) | GDACS `gdacsapi/api/events/geteventlist/SEARCH` | no | Free with attribution, max 100 events per request (the UI says when truncated). Polygon hazards are placed at the centre of their bounding box and marked approximate. |
| Curated natural events (global) | NASA EONET v3 GeoJSON API | no | Public event metadata; fetched/stored by backend, filtered by region/date. See docs/REGIONAL-DATA.md. |
| Satellite fire detections | NASA FIRMS area CSV API | **yes, free** `MAP_KEY` | Disabled until `FIRMS_MAP_KEY` **and** `FIRMS_AREA` (`west,south,east,north`) are set. Low-confidence rows are dropped; shown as "thermal anomaly", not confirmed fires. |
| Weather | Open-Meteo forecast API | no | Non-commercial use, CC BY 4.0 attribution shown. |
| Geocoding | Nominatim (OpenStreetMap) | no | Policy followed: identifying `HTTP_USER_AGENT`, ≤ 1 request/second, results cached 30 days, no autocomplete or bulk use. Set `HTTP_USER_AGENT` to your own contact. |
| Road distance/time | OSRM (`router.project-osrm.org`) | no | Public demo server = light use only; results cached; `OSRM_URL` can point to your own server; `ROUTING_ENABLED=false` turns it off. |
| Map tiles | OpenStreetMap standard tiles by default | no | Light, non-commercial use only. For production set `VITE_MAP_TILE_URL` / `VITE_MAP_TILE_ATTRIBUTION` in `frontend/.env` to your own or a commercial provider. |

External data is **never** turned into an operational incident automatically. It lives in its own table (`external_events`, unique per source + source ID), is re-fetched at most once per refresh interval, cross-source duplicates (same earthquake in USGS and GDACS) are linked rather than double-counted, and failures are logged and shown — stored data stays, nothing is fabricated. An operator can *promote* an observation to a new **Monitoring** incident; later API updates never touch that incident.

### Labelling

Every datum is tagged: **Operational record** (entered in ReliefSync, not independently verified), **External observation (unverified)**, or **Estimate (rule-based)** (priority scores, external severity bands, straight-line distances, routing results).

### Decision-support rule

Priority scores and resource suggestions use transparent rules and the entered incident and stock data. Resolved incidents stay in the database but are excluded from rankings, map alerts, nearby-resource recommendations and active campaigns (the only exception is an *all-clear* notice, which can only be created for a resolved incident). The score breakdown (factor, input, points, basis) is shown with every ranking.

MongoDB is enabled by default at `mongodb://127.0.0.1:27017` for the external-observation archive. Set `MONGODB_URI` to your local MongoDB address if it differs. The API checks MongoDB connectivity and stores refreshed worldwide observations in the `external_observations` collection. Core operational records still use the SQLAlchemy database configured by `DATABASE_URL` (SQLite by default).

### Location data and privacy

- New nullable columns: `latitude`, `longitude`, `location_source` (`manual` | `map` | `geocoded` | `external`), `location_approximate` on disasters, volunteers, shelters and inventory; destination coordinates on allocations. Ranges are validated (API and database). Unknown stays **unknown**; coordinates are never invented.
- Geocoding fills only records that have *no* coordinates, only when the result is unambiguous, and marks them approximate. Ambiguous queries return the candidate list for a person to choose from.
- Volunteer coordinates and phone numbers are visible to **operators only** (when `OPERATOR_API_KEY` is set); the map rounds them to ≈ 1 km, and nearby-volunteer results contain neither.
- Resident subscriptions store a **coarse area (rounded to ≈ 11 km)**, the contact, the consent text and time — never an exact location. Operators see masked contacts.

### Authorisation (read this)

There are no user accounts. "Operator" means *a request carrying `X-Operator-Key`* equal to `OPERATOR_API_KEY` (UI: **Operator access** button, key kept in the browser tab only). If the key is **empty** and `APP_ENV=development`, everyone is an operator — fine for one person on localhost, **not** for sharing. With `APP_ENV=production` and no key, operator actions are refused. Operator-only: refreshing external data, promoting observations, geocoding records, nearby volunteers and assignment approval, everything under `/api/notifications` except the public alert feed, `GET /api/subscriptions`. Public: reading incidents/external data/map, nearby shelters, geocode/weather/route (rate-limited), subscribing/confirming/unsubscribing (rate-limited). A shared key is **not** per-person authentication; use real accounts before any wider deployment.

### Notification workflow

`Draft → preview → Approved → Dispatched` (or `Partially Failed` / `Failed` → retry failed). Preview shows the exact message, channels, eligible recipients (masked), exclusion reasons, target-area map, cost (only if you configured it) and warnings. Dispatch needs an explicit confirmation **and** a one-time idempotency key; the approved message is hashed, so changing it after approval blocks dispatch; eligibility (availability, assignment conflicts, consent, resolved status) is re-checked at dispatch; a database `UNIQUE (campaign, recipient, channel)` makes a double send impossible; recipients already notified about the incident within `NOTIFICATION_COOLDOWN_MINUTES` are skipped. Every step is written to the audit log (who, what, when — never contact details).

Delivery statuses are honest: `recorded_in_app` (a record inside ReliefSync only), `simulated` (development mode, **nothing sent**), `accepted_by_provider` (Twilio/SMTP took it — **delivery is not confirmed; ReliefSync receives no delivery receipts and never says "delivered"**), `failed` (with the error), `skipped`.

- **Development mode (default, `NOTIFICATIONS_MODE=development`)** never contacts anyone, even if credentials are present.
- **Live mode** needs `NOTIFICATIONS_MODE=live` *and* channel credentials (`TWILIO_*` for SMS, `SMTP_*` for email). Without credentials the delivery fails visibly. Cost lines appear only if you set `SMS_COST_PER_MESSAGE` / `EMAIL_COST_PER_MESSAGE`.
- **Consent:** volunteers need `sms_opt_in`; residents must subscribe with explicit consent, confirm with a code sent to their contact, and every message contains an unsubscribe link.
- **Messages** come from fixed templates, label unverified information, contain no casualty figures for the public, and never invent evacuation orders, phone numbers or instructions. Public messages include operator-entered *verified information* only; otherwise they say to follow official local emergency-management sources.

### Migration of an existing database

On startup, `app/migrations.py` adds the new columns to older databases with `ALTER TABLE … ADD COLUMN` only (no deletes, no rewrites, no sample data) after saving a consistent copy to `backend/data/backups/`. **Rollback = stop the app and copy that backup over `reliefsync.db`.** Preview with `python -m app.migrations --check`. Tested against a simulated old-schema database with data in every table.

### Limitations

- No browser push notifications; no delivery receipts; volunteers and shelter coordinators cannot log in (operators read their in-app inbox for them).
- ReliefSync **cannot broadcast to every phone in an area**. Official emergency alerts need an authorised public-warning system (e.g. a national CAP/cell-broadcast service); no such integration exists here and none is claimed.
- Operator authentication is a single shared key (see above); rate limiting is in-memory per process.
- Public OSM tiles, Nominatim and OSRM are fair-use services; production needs your own or commercial endpoints.
- Straight-line distances ignore terrain and roads; routing results are provider estimates; external severity bands are coarse estimates, not impact assessments.
- SQLite remains single-node; the `CHECK` that latitude and longitude come together is enforced by the API (and by the database only on newly created tables).

## Database behaviour

- SQLite file at `backend/data/reliefsync.db`, created on first start (git-ignored).
- Startup runs `create_all`, which **only creates missing tables** — it never drops, resets or alters existing data.
- No schema-migration tool is included. Before changing the schema of a database that holds real data, copy the `.db` file first (and adopt Alembic).
- Constraints enforced in the DB: non-negative quantities/occupancy/affected people, occupancy ≤ capacity, positive capacity and allocation quantities, allowed enum values, foreign keys (`RESTRICT`), one active assignment per volunteer.

## API overview

Interactive docs at `/docs`. Lists return `{ items, total, limit, offset }` (`limit` ≤ 500).
Errors use FastAPI's `{ "detail": ... }`: **404** not found, **409** business-rule conflict, **422** validation.

| Area | Endpoints (prefix `/api`) |
| --- | --- |
| Disasters | `GET/POST /disasters`, `GET/PATCH/DELETE /disasters/{id}`, `PATCH /disasters/{id}/status` |
| Volunteers | `GET/POST /volunteers`, `GET/PATCH /volunteers/{id}`, `PATCH /volunteers/{id}/availability` |
| Assignments | `GET/POST /assignments`, `GET /assignments/{id}`, `PATCH /assignments/{id}/status` |
| Inventory | `GET/POST /inventory` (`?low_stock=true`), `GET/PATCH/DELETE /inventory/{id}`, `PATCH /inventory/{id}/adjust` |
| Shelters | `GET/POST /shelters`, `GET/PATCH/DELETE /shelters/{id}`, `PATCH /shelters/{id}/occupancy` |
| Allocations | `GET/POST /allocations`, `GET/PATCH /allocations/{id}`, `PATCH /allocations/{id}/status` |
| Intelligence | `GET /intelligence/priority`, `GET /intelligence/recommendations` |
| Dashboard | `GET /dashboard` — plus `GET /health` (no prefix) |

## Priority scoring

`score = round((severity_points + population_points) × status_multiplier)`

| Severity | Points | People affected | Points | Status | Multiplier |
| --- | --- | --- | --- | --- | --- |
| Low | 10 | 0 | 0 | Active | 1.0 |
| Medium | 25 | 1–99 | 5 | Monitoring | 0.6 |
| High | 40 | 100–999 | 12 | Resolved | 0 (excluded from ranking) |
| Critical | 55 | 1,000–9,999 | 22 | | |
| | | 10,000–99,999 | 30 | | |
| | | ≥ 100,000 | 35 | | |

Levels: **Critical ≥ 70**, **High ≥ 50**, **Medium ≥ 30**, otherwise **Low** (max score 90).
Ranking order: score ↓, people affected ↓, id ↑ (deterministic). Code: `backend/app/services/priority.py`.

## Smart allocation logic

Pure function in `backend/app/services/allocation.py`; it reads current data and never changes stock.

1. Process non-resolved disasters by priority score (highest first).
2. Per-person targets by category: Water 3, Food 2, Clothing 1, Hygiene 0.5, Shelter 0.25, Medical 0.2 units. "Other" is never auto-recommended.
3. `need = ceil(people × target) − already allocated (non-cancelled) to that disaster in that category`.
4. A disaster may claim at most a share of an item's remaining stock: Critical 60%, High 40%, Medium 25%, Low 10%.
5. Stock is tracked across disasters in one run, so total suggested quantity never exceeds stock.
6. Each suggestion carries a written reasoning string. Confirming one creates a real allocation.

## Inventory accounting & concurrency

- **Confirm**: one transaction — conditional `UPDATE … SET quantity = quantity − q WHERE quantity ≥ q` (rowcount must be 1), then insert the allocation, then commit. Failure rolls back.
- **Cancel**: compare-and-set the status (`WHERE status IN ('Confirmed','In Transit')`) and only if that flipped, add the quantity back — so repeat cancels cannot restore twice.
- **Limits**: SQLite serialises writers, which makes these atomic, but it is not a production multi-node database. Use PostgreSQL for real deployments.
- Allocation quantity cannot be edited after confirmation (cancel and re-create).

## Testing

```powershell
# Backend (from backend/, venv active)
pip install -r requirements-dev.txt
pytest -v

# Frontend (from frontend/)
npm run lint
npm test
npm run build
```

API tests use a temp SQLite file set via `DATABASE_URL` before the app is imported, and refuse to run if the engine is not the test DB.
They cover CRUD, validation, priority, volunteer/assignment rules, stock deduction/rejection/restoration, repeated cancellation, parallel allocations, recommendations, dashboard stats, empty DB and persistence across an engine restart.

## Known limitations

- **Authentication is a single shared operator key** (see *Authorisation*); incident/volunteer/inventory CRUD endpoints are otherwise unauthenticated. Do not expose this to the public internet; it is a local demo.
- No background jobs (external data refreshes on demand); migrations are additive-only.
- Priority/allocation rules are simple, fixed heuristics (not configurable at runtime, not validated).
- Hash-based routing (no router library); frontend tests run in jsdom, not a real browser.

## Screenshots

_Add screenshots here after running the app (Dashboard, Smart Priority, Smart Allocation)._

## Future improvements

JWT auth with roles · Alembic migrations · PostgreSQL / PostGIS · configurable scoring weights · delivery receipts (Twilio status callbacks) · browser push · official CAP alert integration · CSV import/export · Playwright E2E in CI.

### World view, regional heatmap, accounts, and messaging

The seeded dashboard imports the dated global source snapshot, and the External Observations page can refresh USGS, GDACS, and NASA EONET records (NASA FIRMS needs a free key). The dashboard regional heatmap summarizes those stored observations and links into regional filters. Public feeds have different coverage and are not a complete archive of every disaster worldwide. The Map page's separate incident heat layer covers operational incidents with known coordinates.

Team members can register individual password accounts. Notifications supports in-app inbox entries and operator-reviewed regional campaigns. SMS and email are deliberately simulated by default; real delivery requires your own Twilio/SMTP credentials, explicit live mode, recipient consent, and operator approval. A provider acceptance response does not confirm handset or inbox delivery. For ISRO satellite products, see [Regional data and historical coverage](docs/REGIONAL-DATA.md): MOSDAC download access requires an account and dataset selection, and ReliefSync does not currently claim direct MOSDAC weather integration. Optional incident summaries use a local Ollama installation and always have a rule-based fallback.


### MongoDB and populated demo dashboard

The Windows launcher tries to start the included optional MongoDB service when Docker Compose is installed. The Compose service stores external-observation archive records in a persistent Docker volume; operational app records remain in SQLite. To start MongoDB manually, run `docker compose up -d mongodb` from the extracted project folder. Then restart ReliefSync or refresh external sources. The dashboard reports MongoDB connectivity and archived observation count. Without Docker, install MongoDB Community locally or configure `MONGODB_URI` in `backend/.env`; the rest of the app still works with SQLite.

On first start with `DEMO_SEED_DATA=true`, ReliefSync imports the included 690-row dated global observation snapshot and creates clearly labeled synthetic training records for an incident, volunteers, assignments, shelters, inventory, and allocations so the dashboard has meaningful figures. These synthetic operations are not live response data. The demo seeder is idempotent and adds missing sample rows to an existing database.

