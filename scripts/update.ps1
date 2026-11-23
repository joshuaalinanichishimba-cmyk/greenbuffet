<#
    Brings an installed copy up to the latest stage.

    Run it after extracting a newer package over the project folder. It leaves
    backend\.env, the database and the backups alone, and only refreshes the
    parts that a new stage can change: Python packages, front-end packages and
    the permission and settings rows.

    Usage:
        cd "D:\The Green Buffet"
        .\scripts\update.ps1
#>
[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$backend = Join-Path $root 'backend'
$frontend = Join-Path $root 'frontend'

function Step($text) { Write-Host ''; Write-Host ('  == ' + $text) -ForegroundColor Green }
function Ok($text) { Write-Host ('     ' + $text) -ForegroundColor DarkGray }
function Warn($text) { Write-Host ('     ' + $text) -ForegroundColor Yellow }

Write-Host ''
Write-Host '  The Green Buffet - update' -ForegroundColor Green
Write-Host ('  Project: ' + $root) -ForegroundColor DarkGray

if (-not (Test-Path (Join-Path $backend '.env'))) {
    throw 'No backend\.env found. This copy has not been set up yet - run .\scripts\setup.ps1 instead.'
}

$py = Join-Path $backend '.venv\Scripts\python.exe'
if (-not (Test-Path $py)) {
    throw 'No virtual environment found. Run .\scripts\setup.ps1 instead.'
}

Step 'Stopping anything still running'
Get-Process -Name python, node -ErrorAction SilentlyContinue |
    Where-Object { $_.Path -and $_.Path.StartsWith($root) } |
    ForEach-Object {
        Ok ('stopped ' + $_.ProcessName + ' (' + $_.Id + ')')
        Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue
    }

Step 'Backend packages'
Push-Location $backend
try {
    & $py -m pip install --quiet --upgrade pip
    & $py -m pip install --quiet -r requirements.txt
    if ($LASTEXITCODE -ne 0) { throw 'Installing the backend packages failed.' }
    Ok 'up to date'

    Step 'Database'
    # Creates any new tables and adds new permissions, roles and settings.
    # Existing rows are untouched.
    & $py -m app.seed
    if ($LASTEXITCODE -ne 0) { throw 'The database update failed.' }

    # Loads the starting menu, but only if the menu is still empty.
    & $py -m app.seed_menu
} finally {
    Pop-Location
}

Step 'Frontend packages'
Push-Location $frontend
try {
    npm install --silent
    if ($LASTEXITCODE -ne 0) { Warn 'npm reported a problem; check the output above.' }
    else { Ok 'up to date' }
} finally {
    Pop-Location
}

Write-Host ''
Write-Host '  Update finished.' -ForegroundColor Green
Write-Host '  Start it again with:  .\scripts\run.ps1' -ForegroundColor DarkGray
Write-Host ''
