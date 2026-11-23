<#
    The Green Buffet - start the system for development
    Run:  .\scripts\run.ps1

    Opens the backend and the frontend in two windows. Close either window,
    or press Ctrl+C in it, to stop that part.
#>
[CmdletBinding()]
param([switch] $NoBrowser, [switch] $KeepRunning)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$backend  = Join-Path $root 'backend'
$frontend = Join-Path $root 'frontend'
$py = Join-Path $backend '.venv\Scripts\python.exe'

if (-not (Test-Path $py)) { throw 'Run .\scripts\setup.ps1 first.' }
if (-not (Test-Path (Join-Path $backend '.env'))) { throw 'backend\.env is missing. Run .\scripts\setup.ps1 first.' }
if (-not (Test-Path (Join-Path $frontend 'node_modules'))) { throw 'Run .\scripts\setup.ps1 first.' }

Write-Host ''
Write-Host '  Starting The Green Buffet' -ForegroundColor Green

# An earlier run often leaves the backend or the front end holding its port,
# and the second copy then fails with "Port 5173 is already in use". Stop the
# old ones first unless asked not to.
if (-not $KeepRunning) {
    foreach ($port in 8000, 5173) {
        $holders = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue |
                   Select-Object -ExpandProperty OwningProcess -Unique
        foreach ($id in $holders) {
            $name = (Get-Process -Id $id -ErrorAction SilentlyContinue).ProcessName
            Stop-Process -Id $id -Force -ErrorAction SilentlyContinue
            Write-Host ("    stopped the copy already on port {0} ({1})" -f $port, $name) -ForegroundColor DarkGray
        }
    }
    if ($holders) { Start-Sleep -Seconds 1 }
}

# The backend must run from backend\ so it finds .env.
Start-Process powershell -ArgumentList @(
    '-NoExit', '-Command',
    "Set-Location '$backend'; Write-Host 'Backend: http://localhost:8000/docs' -ForegroundColor Green; & '$py' -m uvicorn app.main:app --reload --port 8000"
)
Write-Host '    backend  : http://localhost:8000/docs' -ForegroundColor Cyan

Start-Process powershell -ArgumentList @(
    '-NoExit', '-Command',
    "Set-Location '$frontend'; Write-Host 'Frontend: http://localhost:5173' -ForegroundColor Green; npm run dev"
)
Write-Host '    frontend : http://localhost:5173' -ForegroundColor Cyan

if (-not $NoBrowser) {
    Write-Host ''
    Write-Host '  Waiting for the backend to answer...' -ForegroundColor DarkGray
    $ready = $false
    foreach ($i in 1..90) {
        Start-Sleep -Seconds 1
        try {
            $r = Invoke-RestMethod 'http://localhost:8000/api/v1/health' -TimeoutSec 2
            if ($r.status -eq 'ok') { $ready = $true; break }
        } catch { }
    }
    if ($ready) {
        Write-Host '  Backend is up and the database is connected.' -ForegroundColor Green
        Start-Process 'http://localhost:5173'
    } else {
        Write-Host '  The backend did not answer in 90 seconds. Check its window for the error.' -ForegroundColor Yellow
    }
}
Write-Host ''
