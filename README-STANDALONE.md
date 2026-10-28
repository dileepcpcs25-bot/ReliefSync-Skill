# ReliefSync team-ready standalone

Start with `start-reliefsync.bat`. This copy runs on frontend port **5191** and API port **8015**, separate from the other ReliefSync checkout. The launcher creates a local Python virtual environment and installs dependencies if needed, installs frontend packages if needed, starts both services, and opens the dashboard. Python 3.11+ and Node.js 20.19+ are required.

## Multi-user sign-in

The local demo account is username `admin`, password `ReliefSync-admin-2026!`. Create more accounts from the sign-in page. Usernames are 3-32 letters/numbers/dot/dash/underscore; passwords are 12-128 characters. Passwords are salted PBKDF2-SHA256 hashes; signed bearer sessions expire after 8 hours and remain in sessionStorage. The demo admin password can be changed at Team sign-in → Change your current password. The demo secret is for local evaluation; change credentials and `AUTH_SECRET` before sharing/deploying.

## Dashboard/map data (prepopulated)

At first start, the backend automatically loads `sample-data/world_disaster_observations.csv`: 690 recent geolocated source observations from USGS, NASA EONET and GDACS, dated 21 Dec 2025 to 27 Oct 2026. This is a recent snapshot, not a complete all-time history of every disaster worldwide. Latest feed refresh is available from Map; internet/API availability and source rate limits can affect live refreshes.

The app seeds one synthetic Chennai flood exercise, five clearly marked demo volunteers, three demo shelters, five inventory items, two assignments and three sample allocations. These names, contacts, locations, capacity and event are invented training data. This ensures the dashboard and heatmap are populated on first run. The default heatmap visualizes recorded events; it does not predict future risk.

## Assignments and volunteer alerts

Assigning a volunteer sets their state to Assigned and updates dashboard counts; completing the assignment frees them again. Shelter occupancy edits update capacity totals. In Volunteers click **Alert volunteers** or open **Notifications** → **Create alert or message**. Choose the incident, audience, radius, skills, and instructions; preview recipients and the message; then approve and dispatch. Dispatch creates in-app notification records in ReliefSync. SMS is simulated until you add Twilio credentials and switch notifications to live mode. Real delivery should only be enabled after testing provider settings and obtaining volunteer consent.

## Storage and optional local LLM

Operational records use the SQLite file `backend/data/reliefsync.db`; fetched/snapshot observations are archived in MongoDB database `reliefsync_multiuser` at the configured local URI. Change `backend/.env` to use another MongoDB URI. Smart report explanation works with its transparent rule-based fallback. To enable free local LLM summaries, install Ollama, run `ollama pull qwen2.5:3b`, and keep Ollama on localhost:11434; choose its model in `backend/.env`. No hosted LLM key is needed.

API health: http://127.0.0.1:8015/health | API docs: http://127.0.0.1:8015/docs | Web: http://127.0.0.1:5191
