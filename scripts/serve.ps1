<#
    Runs The Green Buffet for real use, as opposed to development.

        .\scripts\serve.ps1

    The difference from run.ps1:
      - the front end is built once and served by the backend, so there is one
        address and one window instead of two;
      - it listens on the network, so a phone, a kitchen tablet or the
        manager's laptop on the restaurant wifi can reach it;
      - nothing reloads when a file changes.

    Options:
      -Port 8000     a different port
      -LocalOnly     keep it to this computer
      -SkipBuild     reuse the front end built last time
#>
[CmdletBinding()]
param([int] $Port = 8000, [switch] $LocalOnly, [switch] $SkipBuild)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'   # the web-request progress bar leaves blank lines in pasted output
$root = Split-Path -Parent $PSScriptRoot
$backend = Join-Path $root 'backend'
$frontend = Join-Path $root 'frontend'
$py = Join-Path $backend '.venv\Scripts\python.exe'

if (-not (Test-Path $py)) { throw 'Run .\scripts\setup.ps1 first.' }
if (-not (Test-Path (Join-Path $backend '.env'))) { throw 'backend\.env is missing. Run .\scripts\setup.ps1 first.' }

Write-Host ''
Write-Host '  The Green Buffet' -ForegroundColor Green

if (-not $SkipBuild) {
    Write-Host '  Building the front end (about a minute)...' -ForegroundColor DarkGray
    Push-Location $frontend
    try {
        npm run build
        if ($LASTEXITCODE -ne 0) { throw 'The front end did not build. Run .\scripts\update.ps1 and try again.' }
    } finally {
        Pop-Location
    }
}
if (-not (Test-Path (Join-Path $frontend 'dist\index.html'))) {
    throw 'There is no built front end. Run this again without -SkipBuild.'
}

# Anything on the restaurant wifi can reach it unless told otherwise.
$bind = if ($LocalOnly) { '127.0.0.1' } else { '0.0.0.0' }

$addresses = @("http://localhost:$Port")
if (-not $LocalOnly) {
    Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
        Where-Object { $_.IPAddress -notlike '127.*' -and $_.IPAddress -notlike '169.254.*' } |
        ForEach-Object { $addresses += "http://$($_.IPAddress):$Port" }
}

Write-Host ''
Write-Host '  Open it at:' -ForegroundColor Green
foreach ($address in $addresses) { Write-Host "    $address" -ForegroundColor Cyan }
if (-not $LocalOnly) {
    Write-Host ''
    Write-Host '  Other devices on the same wifi use the second address.' -ForegroundColor DarkGray
    Write-Host '  If they cannot reach it, run .\scripts\install-service.ps1 once as' -ForegroundColor DarkGray
    Write-Host '  Administrator; it opens the port in the Windows firewall.' -ForegroundColor DarkGray
}
Write-Host ''
Write-Host '  Ctrl+C stops it. Closing this window stops it too.' -ForegroundColor DarkGray
Write-Host ''

# run_server.py writes everything to logs\server.log as well as this window,
# which is the only way to know why the installed copy, running hidden, did
# not start. It also refuses to start if the port is already taken.
Write-Host ('  Log: ' + (Join-Path $root 'logs\server.log')) -ForegroundColor DarkGray
Write-Host ''
Push-Location $backend
try {
    & $py run_server.py --host $bind --port $Port
} finally {
    Pop-Location
}
