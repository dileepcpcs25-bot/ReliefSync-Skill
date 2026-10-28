# Regional and historical data extension

## What is connected

| Source | Coverage | App integration | Access |
|---|---|---|---|
| NASA EONET v3 | Worldwide curated natural-event metadata | Backend fetch, persistent external-event records, region/date filters, map/table and historical event lookup | Public, no key; events returned are unverified curated metadata |
| USGS GeoJSON | Worldwide earthquakes | Existing backend feed, map, region filters, MongoDB archive | Public, no key |
| GDACS | Worldwide disaster alerts | Existing backend feed, map, region filters, MongoDB archive | Public with attribution; API caps each response |
| NASA FIRMS | Satellite thermal anomalies | Existing adapter and backend archive | Free MAP_KEY required; not enabled without configured key and area |
| ISRO/NRSC Bhuvan and NDEM | India-focused geospatial and disaster-management portals | Linked from External Observations; no direct feed is claimed | Bhuvan exposes portal/map services; NDEM access is intended for authorized users and individual services may require permission |
| ISRO MOSDAC | Indian satellite weather/ocean products | Linked from External Observations; no protected data is copied into ReliefSync | Dataset search is available; data download needs a MOSDAC account, and selected products may have extra access terms |

The dashboard now groups the fetched, geolocated records into five broad regional views and shows the database date range, source-record totals, and located operational incidents, volunteers, and shelters. Broad regions can overlap and the UI warns against summing them. The EONET adapter requests `status=all`, `days=365`, and `limit=500`; USGS uses a current GeoJSON feed, while GDACS uses its configured recent date window and can cap each response. These feeds are not a complete archive of every disaster ever recorded worldwide. In the included snapshot, source event dates range from 2025-12-21 through 2026-10-27. The downloaded CSV is a dated snapshot, not a live feed. NASA event metadata is not impact or severity validation. Polygon locations are represented by an approximate bounding-box centre and flagged as approximate.

To use NASA FIRMS, request a free key from <https://firms.modaps.eosdis.nasa.gov/api/map_key>, set `FIRMS_MAP_KEY` and a smaller region in `FIRMS_AREA` in `backend/.env`, then restart the backend and refresh. Do not request the full globe at high cadence; FIRMS documents transaction limits.

ISRO links:

- Bhuvan: <https://bhuvan.nrsc.gov.in/>
- MOSDAC: <https://mosdac.gov.in/>
- MOSDAC API access manual: <https://www.mosdac.gov.in/downloadapi-manual>
- NASA EONET v3 docs: <https://eonet.gsfc.nasa.gov/docs/v3>
- NASA FIRMS area API: <https://firms.modaps.eosdis.nasa.gov/api/area>

## Map intensity view

The Map page has marker, incident heatmap, and table views. The heatmap draws only operator-entered incidents with known coordinates. Its per-incident intensity weight is `0.65 × severity factor + 0.35 × min(1, log10(reported affected + 1) / 6)`, with severity factors Critical=1.00, High=0.82, Medium=0.64, Low=0.46. These configurable-in-code factors visualize recorded values; they are not probabilities or a validated risk model. External observations remain separately identified markers.

## Past events and resource matching

The **Past events & resources** page lists incident records already held by ReliefSync and external observations already fetched into its database. A recorded incident timestamp is labelled as its database creation time; an external record uses the source-reported observation time. Choosing an event runs `GET /api/history/events/{event-key}/resources?radius_km=...`.

The endpoint requires operator access. It calculates straight-line distances from stored coordinates; unknown coordinates are excluded and counted. It returns current volunteer availability/assignment and shelter occupancy/capacity. This database does not keep time-versioned resource snapshots, so those current values must not be read as the historical status at the time of an event. The endpoint withholds volunteer phone numbers and exact volunteer coordinates.

## Notifications

Notifications are stored and auditable in ReliefSync. In development mode the in-app inbox is written to the database and email/SMS provider delivery is simulated; the simulator records the result but does not send to a real address. Live delivery requires provider credentials and an explicitly configured live mode. No message to a real recipient is sent by tests.



## Downloaded data snapshot

`../sample-data/world_disaster_observations.csv` contains 690 unique public-source observation rows collected from the configured feeds on 2026-10-27. It includes source, type, title, coordinates, event date, estimated severity, and source link. It is included to make the example dashboard data inspectable and can become stale; use **Refresh now** in the app for updated source observations.

Free-source limitations: the [USGS event service](https://earthquake.usgs.gov/fdsnws/event/1/) supports historical earthquake queries, while the default ReliefSync integration uses a current GeoJSON feed. NASA EONET documents date-range queries, but ReliefSync currently requests only its latest year and a capped result set. GDACS provides paginated, bounded event queries and caps each result page. No single source covers all disaster types, countries, and historical years.

The dashboard's regional intensity cards shade regions by the square-root-scaled count of stored, unique public observations. They are an at-a-glance view of collected records, not relative hazard risk; source coverage and update periods differ. Clicking a card opens the matching regional observation list. The dashboard's underlying incident, volunteer, shelter, and source counts remain separate.

### ISRO/MOSDAC and weather access

MOSDAC provides ISRO meteorological and oceanographic satellite products and weather services. Its published data-download API requires a MOSDAC SSO account and a chosen dataset ID; the portal says anonymous users receive metadata/images/open data, while other access depends on account permissions. ReliefSync does not ask for or store MOSDAC credentials and does not currently call a MOSDAC weather endpoint. Use the linked MOSDAC portal/API manually for authorized products. ReliefSync's live point weather is currently supplied by Open-Meteo; NASA's EONET and FIRMS are the integrated satellite/natural-event feeds. Never treat these sources as official local emergency warnings.

### Language model summaries

The optional `GET /api/intelligence/explain/{disaster_id}` route asks a local Ollama model to summarize recorded incident fields. It falls back to a deterministic rule explanation when Ollama is unavailable. The model does not ingest every internet disaster report, certify observations, send alerts, or replace operator review. Configure `OLLAMA_BASE_URL` and `OLLAMA_MODEL` in `backend/.env` and install/run Ollama with the selected model to enable it.
