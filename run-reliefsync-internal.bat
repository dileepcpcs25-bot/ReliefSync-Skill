@echo off
setlocal EnableExtensions
set "ROOT=%~dp0"
set "API_PORT=8015"
set "WEB_PORT=5191"
if exist "%ROOT%.reliefsync-ports" (
  set /p API_PORT=<"%ROOT%.reliefsync-ports"
  for /f "usebackq skip=1 delims=" %%P in ("%ROOT%.reliefsync-ports") do set "WEB_PORT=%%P"
)
set "API_URL=http://127.0.0.1:%API_PORT%"
set "WEB_URL=http://127.0.0.1:%WEB_PORT%/#/dashboard"

if not exist "%ROOT%backend\requirements.txt" (
  echo ReliefSync backend files are missing. Run Open-ReliefSync.bat from the complete folder.
  goto setup_error
)
where python >nul 2>&1 || (echo Python is not installed or is missing from PATH.& goto setup_error)
where npm >nul 2>&1 || (echo Node.js/npm is not installed or is missing from PATH.& goto setup_error)

powershell -NoProfile -Command "try{$a=Invoke-WebRequest '%API_URL%/health' -TimeoutSec 2 -UseBasicParsing; $w=Invoke-WebRequest 'http://127.0.0.1:%WEB_PORT%/' -TimeoutSec 2 -UseBasicParsing; if($a.StatusCode -eq 200 -and $w.StatusCode -ge 200 -and $w.StatusCode -lt 400){exit 0}}catch{}; exit 1" >nul 2>&1
if not errorlevel 1 (
  echo ReliefSync is already running. Opening the dashboard...
  start "" "%WEB_URL%"
  goto done
)

set "PORT_FILE=%TEMP%\reliefsync-ports-%RANDOM%.txt"
powershell -NoProfile -ExecutionPolicy Bypass -Command "function Find-Free([int]$from,[int]$to){for($p=$from;$p -le $to;$p++){ $l=$null; try{$l=[Net.Sockets.TcpListener]::new([Net.IPAddress]::Loopback,$p); $l.Start(); $l.Stop(); return $p}catch{if($l){try{$l.Stop()}catch{}}} }; throw 'No free local port found'}; $api=Find-Free 8015 8115; $web=Find-Free 5191 5291; Set-Content -LiteralPath '%PORT_FILE%' -Value @($api,$web)"
if errorlevel 1 (
  echo Could not find free local ports for ReliefSync.
  goto setup_error
)
set /p API_PORT=<"%PORT_FILE%"
for /f "usebackq skip=1 delims=" %%P in ("%PORT_FILE%") do set "WEB_PORT=%%P"
del "%PORT_FILE%" >nul 2>&1
set "API_URL=http://127.0.0.1:%API_PORT%"
set "WEB_URL=http://127.0.0.1:%WEB_PORT%/#/dashboard"

if not exist "%ROOT%backend\.env" copy "%ROOT%backend\.env.example" "%ROOT%backend\.env" >nul
if not exist "%ROOT%backend\.venv\Scripts\python.exe" (
  echo Creating the Python environment...
  python -m venv "%ROOT%backend\.venv"
  if errorlevel 1 goto setup_error
)
if not exist "%ROOT%backend\.venv\.deps_installed" (
  echo Installing backend dependencies. This can take a few minutes...
  "%ROOT%backend\.venv\Scripts\python.exe" -m pip install --disable-pip-version-check --no-cache-dir -r "%ROOT%backend\requirements.txt"
  if errorlevel 1 goto setup_error
  echo ready>"%ROOT%backend\.venv\.deps_installed"
)
if not exist "%ROOT%frontend\node_modules\vite\bin\vite.js" (
  echo Installing website dependencies. This can take a few minutes...
  pushd "%ROOT%frontend"
  call npm ci --no-audit --no-fund
  if errorlevel 1 (popd& goto setup_error)
  popd
)

docker info >nul 2>&1
if not errorlevel 1 (
  echo Starting optional MongoDB archive...
  docker compose -f "%ROOT%docker-compose.yml" up -d mongodb
) else (
  echo Docker Desktop is unavailable. ReliefSync will use its local SQLite database.
)

pushd "%ROOT%backend"
start "ReliefSync API" cmd /k ""%ROOT%backend\.venv\Scripts\python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port %API_PORT%"
popd
pushd "%ROOT%frontend"
start "ReliefSync Web" cmd /k "set RELIEFSYNC_API_PORT=%API_PORT% && set RELIEFSYNC_FRONTEND_PORT=%WEB_PORT% && npm run dev -- --host 127.0.0.1 --port %WEB_PORT% --strictPort"
popd
>"%ROOT%.reliefsync-ports" echo %API_PORT%
>>"%ROOT%.reliefsync-ports" echo %WEB_PORT%

echo Waiting for both ReliefSync servers before opening the dashboard...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$urls=@('%API_URL%/health','http://127.0.0.1:%WEB_PORT%/'); foreach($u in $urls){$ok=$false; for($i=0;$i -lt 90;$i++){try{$r=Invoke-WebRequest -Uri $u -TimeoutSec 2 -UseBasicParsing; if($r.StatusCode -ge 200 -and $r.StatusCode -lt 400){$ok=$true; break}}catch{}; Start-Sleep -Seconds 1}; if(-not $ok){Write-Output ('Not ready: ' + $u); exit 1}}"
if errorlevel 1 (
  echo ReliefSync did not become ready. Read the API and Web windows for the startup error.
  echo Python and Node.js/npm must be installed, and first-time setup needs internet access.
  pause
  goto done
)
start "" "%WEB_URL%"
echo ReliefSync is running at %WEB_URL%
goto done

:setup_error
echo Startup stopped. Fix the message above and run Open-ReliefSync.bat again.
pause
:done
endlocal
