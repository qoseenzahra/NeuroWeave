# LOCAL DEMO ONLY: installs prerequisites, downloads the Task B branch with the
# demo login, starts backend and frontend, and opens the browser.
$ErrorActionPreference = "Stop"
function Step($text) { Write-Host "`n=== $text ===" -ForegroundColor Cyan }
function Refresh-Path { $env:Path = [Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [Environment]::GetEnvironmentVariable("Path","User") }

Step "1/6 Installing Git, Python 3.11 and Node.js (skipped if already installed)"
$apps = @(@{Id="Git.Git"; Cmd="git"}, @{Id="Python.Python.3.11"; Cmd="py"}, @{Id="OpenJS.NodeJS.LTS"; Cmd="npm"})
foreach ($app in $apps) {
  Refresh-Path
  if (-not (Get-Command $app.Cmd -ErrorAction SilentlyContinue)) {
    winget install -e --id $app.Id --silent --accept-package-agreements --accept-source-agreements
  } else { Write-Host "$($app.Cmd) already installed" }
}
Refresh-Path

$root = Join-Path $HOME "NeuroWeave-demo"
Step "2/6 Downloading NeuroWeave (Task B + demo login)"
if (-not (Test-Path $root)) { git clone -b local-demo https://github.com/qoseenzahra/NeuroWeave.git $root }
else { git -C $root pull }

Step "3/6 Preparing backend (Python packages, takes a few minutes)"
Set-Location $root
if (-not (Test-Path "bakend\.venv")) { py -3.11 -m venv bakend\.venv }
& bakend\.venv\Scripts\python -m pip install --no-deps -r bakend\requirements-dev.lock

Step "4/6 Starting backend in a new window"
Start-Process powershell -ArgumentList "-NoExit","-Command","Set-Location '$root\bakend'; .\.venv\Scripts\python -m uvicorn demo_app:app --host 127.0.0.1 --port 8010"

Step "5/6 Preparing and starting frontend (takes a few minutes)"
Set-Location "$root\frontend"
npm ci
Start-Process powershell -ArgumentList "-NoExit","-Command","Set-Location '$root\frontend'; npm run dev -- --host 127.0.0.1 --port 5173"

Step "6/6 Opening the demo in your browser"
Start-Sleep -Seconds 15
Start-Process "http://127.0.0.1:5173/api/demo/login/alice"
Write-Host "`nDone. Switch user: http://127.0.0.1:5173/api/demo/login/bob   Log out: http://127.0.0.1:5173/api/demo/logout" -ForegroundColor Green
Write-Host "To stop: close the two other PowerShell windows." -ForegroundColor Green
