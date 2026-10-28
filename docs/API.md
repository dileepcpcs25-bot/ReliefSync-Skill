# API reference for the regional/history extension

The running FastAPI API publishes interactive OpenAPI docs at `http://127.0.0.1:8000/docs`. JSON errors use the FastAPI `detail` field. Validation errors return 422; missing records return 404; state/coordinate conflicts return 409; an unavailable upstream feed returns a per-source error in refresh results while previously stored observations remain intact.

## Dashboard and external observations

| Method and path | Access | Behavior and response |
|---|---|---|
| `GET /api/dashboard` | Read | Current operational counts, `external_observations` totals by provider, and five recent external events. |
| `GET /api/external/status` | Read | Source configuration/freshness and MongoDB connectivity. |
| `GET /api/external/events?source=&since=&until=&west=&south=&east=&north=&limit=&offset=` | Read | Paginated stored observation rows with source attribution, event time, retrieval time, location, and review state. |
| `POST /api/external/refresh` | Operator | JSON `{ "sources": ["eonet"], "force": false }`; fetches and upserts sources. `sources` may be `usgs`, `gdacs`, `eonet`, or `firms`. Returns per-source status and new/updated/skipped counts. NASA FIRMS reports `not_configured` until a key and area are set. |

## Past events and resource lookup

Both endpoints require operator access (`X-Operator-Key` when configured).

| Method and path | Request | Response |
|---|---|---|
| `GET /api/history/events?since=&until=&west=&south=&east=&north=&limit=&offset=` | Optional UTC date bounds and map bounds; max page size 500 | Stored ReliefSync incidents and already-fetched external observations, each with a stable `local:<id>` or `external:<id>` key and its timestamp basis. |
| `GET /api/history/events/{event-key}/resources?radius_km=100&include_unavailable=true` | `event-key` is `local:<id>` or `external:<id>`; radius 0–2000 km | Volunteers and shelters within straight-line radius, current status, distance, and unlocated counts. Volunteer phone numbers and exact coordinates are omitted. Returns 409 when an event has no coordinates. |

Resource status is current because the schema has no time-versioned volunteer/shelter history. Distances are estimates. Region bounds crossing the antimeridian are supported.

## Existing endpoints

Incidents, volunteers, assignments, inventory, shelters, allocations, intelligence, geocoding, nearby matching, and notification campaigns are grouped by tags in `/docs`. They use real HTTP methods (`GET`, `POST`, `PATCH`, and `DELETE` where appropriate), Pydantic validation, and SQL persistence. Notifications remain simulated for email/SMS while `NOTIFICATIONS_MODE=development`; in-app records are persisted and campaign actions are auditable. The given test email is not contacted by development mode or test runs.
