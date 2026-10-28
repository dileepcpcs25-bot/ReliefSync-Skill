# Free data and database setup

ReliefSync is wired to free/public data sources by default. You do not need to request keys for the USGS, GDACS, Open-Meteo, OpenStreetMap Nominatim, or public OSRM integrations. These public services have fair-use or rate limits; do not run bulk jobs against them.

## APIs and signup links

| Feature | Free source | Key needed | Get started |
|---|---|---:|---|
| Worldwide earthquakes | USGS GeoJSON feeds | No | [USGS feeds and API documentation](https://earthquake.usgs.gov/earthquakes/feed/v1.0/) |
| Worldwide disaster alerts (earthquakes, cyclones, floods, volcanoes, droughts, wildfires) | GDACS API | No | [GDACS API quick start](https://www.gdacs.org/Documents/2025/GDACS_API_quickstart_v1.pdf) · [API browser](https://www.gdacs.org/gdacsapi/swagger/index.html) |
| Global natural-event metadata | NASA EONET v3 | No | [EONET v3 documentation](https://eonet.gsfc.nasa.gov/docs/v3) |
| Satellite thermal anomalies / fire detections | NASA FIRMS | Yes, free MAP_KEY | [Request your free NASA FIRMS key](https://firms.modaps.eosdis.nasa.gov/api/map_key) · [API docs](https://firms.modaps.eosdis.nasa.gov/api/area/) |
| Weather | Open-Meteo | No | [API docs](https://open-meteo.com/en/docs) |
| Place search | OpenStreetMap Nominatim | No | [Usage policy](https://operations.osmfoundation.org/policies/nominatim/) |
| Road routes | OSRM public demo | No | [OSRM API docs](https://project-osrm.org/docs/v5.24.0/api/) |
| MongoDB hosting (optional) | MongoDB Atlas M0 | Free cluster | [Create an Atlas Free cluster](https://www.mongodb.com/docs/atlas/tutorial/deploy-free-tier-cluster/) |

USGS and GDACS provide worldwide coverage directly. NASA FIRMS uses a geographic bounding box in this app, so configure the region you want to query in `FIRMS_AREA`; one huge global request can be slow or exceed provider limits.

NASA EONET v3 is enabled by default and refreshes up to 500 events from the past year without a key. See [Regional data and history](docs/REGIONAL-DATA.md) for ISRO/NRSC and MOSDAC access limits.

## Add your NASA key

1. Request a free MAP_KEY from NASA FIRMS and copy it from the email.
2. Copy `backend/.env.example` to `backend/.env`.
3. Set `FIRMS_MAP_KEY=your_key` and `FIRMS_AREA=west,south,east,north`, for example `-180,-90,180,90` for a global bounding box. NASA imposes request limits, so a smaller box is more reliable.
4. Set `HTTP_USER_AGENT` to identify your deployment and contact address, as required by the public geocoding service policy.
5. Restart the backend and use **Fetch latest external data** in ReliefSync.

Never put keys in the frontend `.env`, source code, screenshots, or Git. The backend `.env` is ignored by Git.

## Optional MongoDB Atlas

If you want the optional external-observation archive, create a free M0 cluster, add a database user, and allow your development machine's IP in Atlas Network Access. By default the app connects to local MongoDB at `mongodb://127.0.0.1:27017` (no API key). If your local server uses another address, set `MONGODB_URI` in `backend/.env`. For cloud hosting, an Atlas connection string also works. Set `MONGODB_DATABASE=reliefsync`. On the first successful refresh, observations are upserted into the `external_observations` collection with a 2dsphere location index. The API status endpoint checks whether MongoDB is reachable.

At this stage MongoDB stores the fetched external observation archive only. ReliefSync operational records (incidents, volunteers, supplies, shelters, assignments, allocations, and notification campaigns) still use the `DATABASE_URL` SQLAlchemy database (SQLite by default).

## Keep API costs at zero

The app defaults notifications to development mode: in-app notifications are stored locally, and SMS/email delivery is simulated. Do not set `NOTIFICATIONS_MODE=live` or add Twilio/SMTP credentials if you want to avoid paid messaging. Public OSM tiles, Nominatim, and OSRM are light-use community services, not guaranteed production infrastructure.



## MongoDB archive

The app keeps operational state in SQLite and archives source observations separately in MongoDB. With Docker Desktop installed and running, use `docker compose up -d mongodb` in the project root. The included Compose file persists MongoDB data in a named volume and exposes it only on localhost port 27017. The default `MONGODB_URI` in `backend/.env.example` points there. The dashboard shows whether the archive is connected and how many observations it contains.
