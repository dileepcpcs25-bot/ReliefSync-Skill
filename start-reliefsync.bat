@echo off
setlocal EnableExtensions
set "APP=%~dp0"
set "RECOVERY=%TEMP%\reliefsync-skill-app-%RANDOM%.txt"
if not exist "%APP%backend\requirements.txt" (
  echo Locating the complete ReliefSync ZIP and extracting it...
  set "RELIEFSYNC_RECOVERY=%RECOVERY%"
  powershell -NoProfile -ExecutionPolicy Bypass -Command "$ErrorActionPreference='Stop'; $roots=@((Join-Path $env:USERPROFILE 'Downloads'),(Join-Path $env:USERPROFILE 'Desktop'),(Join-Path $env:USERPROFILE 'Documents\Codex')); $zip=$roots | Where-Object {Test-Path -LiteralPath $_} | ForEach-Object {Get-ChildItem -LiteralPath $_ -Filter 'ReliefSync-Skill*.zip' -File -Recurse -ErrorAction SilentlyContinue} | Sort-Object LastWriteTime -Descending | Select-Object -First 1; if(-not $zip){Write-Error 'Download the ReliefSync-Skill ZIP to Downloads, then click this launcher again.'; exit 2}; $dest=Join-Path $env:USERPROFILE ('ReliefSync-Skill-' + (Get-Date -Format 'yyyyMMdd-HHmmss-fff')); Expand-Archive -LiteralPath $zip.FullName -DestinationPath $dest; $app=Join-Path $dest 'ReliefSync-Skill'; if(-not (Test-Path (Join-Path $app 'backend\requirements.txt'))){Write-Error 'The ZIP does not contain the complete backend.'; exit 3}; Set-Content -LiteralPath $env:RELIEFSYNC_RECOVERY -Value $app"
  if errorlevel 1 (
    echo Could not find or extract the full ZIP. Download it to Downloads and try again.
    pause
    exit /b 1
  )
  set "APP="
  for /f "usebackq delims=" %%A in ("%RECOVERY%") do set "APP=%%A\"
  del "%RECOVERY%" >nul 2>&1
)
if not exist "%APP%backend\requirements.txt" (
  echo ReliefSync backend files are missing. Use the complete ReliefSync-Skill ZIP.
  pause
  exit /b 1
)
if not exist "%APP%run-reliefsync-internal.bat" (
  echo The app launcher is missing from this folder.
  pause
  exit /b 1
)
call "%APP%run-reliefsync-internal.bat"
endlocal
