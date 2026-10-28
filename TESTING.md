# ReliefSync testing and local startup

## Start on Windows

1. Close old ZIP preview windows, extract the refreshed `ReliefSync-MultiUser-Final.zip`, and run `start-reliefsync.bat` from the extracted project folder.
2. The launcher installs Python and Node dependencies, starts the API at `http://127.0.0.1:8015` and web app at `http://127.0.0.1:5191`, then opens the dashboard. If Docker Desktop is running, it also starts the optional MongoDB archive.
3. The default local demo account is username `admin`, password `ReliefSync-admin-2026!`. Change it before sharing the installation.

First start imports the dated public-observation snapshot and seeds synthetic demo operations. The dashboard shows stored SQLite and MongoDB archive counts separately. In External Observations, use **Fetch latest external data** to refresh public feeds.

## Automated checks

Backend: from `backend`, install `requirements-dev.txt`, then run `python -m pytest`. Test fixtures disable demo seeding and use an isolated temporary SQLite database. Frontend: from `frontend`, run `npm ci`, `npm run lint`, `npm test`, and `npm run build`.

Latest checks in this workspace: backend 192 tests passed; frontend lint clean, 23 tests passed, production build succeeded. The backend emitted one third-party Starlette/httpx deprecation warning.

Real SMS/email delivery and the end-to-end Windows first-run installer need provider credentials and a normal desktop environment. Default notification mode is development simulation; tests never contact real recipients.