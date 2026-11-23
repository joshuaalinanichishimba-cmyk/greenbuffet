<#
Starts the client demo using an existing, empty PostgreSQL database whose name ends in _demo.
Run from the separate demo source folder. Set DATABASE_URL in this PowerShell first.
#>
[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$backend = Join-Path $root 'backend'
$frontend = Join-Path $root 'frontend'
$py = Join-Path $backend '.venv\Scripts\python.exe'
if (-not (Test-Path $py)) { throw 'Create the Python virtual environment in the demo folder first.' }
if (-not (Test-Path (Join-Path $frontend 'node_modules'))) { throw 'Run npm ci in the demo frontend folder first.' }
if (-not $env:DATABASE_URL) { throw 'Set DATABASE_URL to the isolated PostgreSQL demo database.' }
if (Get-NetTCPConnection -LocalPort 8002, 5174 -State Listen -ErrorAction SilentlyContinue) {
    throw 'Port 8002 or 5174 is already in use. Close the existing demo windows before starting again.'
}

$saved = @{}
$startup = @{
    DEMO_ENABLED = 'true'
    CORS_ORIGINS = 'http://localhost:5174'
    VITE_API_BASE_URL = 'http://localhost:8002/api/v1'
    VITE_DEMO_ENABLED = 'true'
}
$startup.JWT_SECRET = (& $py -c "import secrets; print(secrets.token_urlsafe(48))").Trim()
if ($LASTEXITCODE -ne 0 -or -not $startup.JWT_SECRET) { throw 'Could not generate a session signing key.' }

try {
    foreach ($name in $startup.Keys) {
        $saved[$name] = [Environment]::GetEnvironmentVariable($name, 'Process')
        [Environment]::SetEnvironmentVariable($name, $startup[$name], 'Process')
    }
    Push-Location $backend
    try {
        & $py -m app.seed
        if ($LASTEXITCODE -ne 0) { throw 'Demo database initialization failed.' }
        & $py -m app.seed_menu
        if ($LASTEXITCODE -ne 0) { throw 'Demo menu initialization failed.' }
    } finally {
        Pop-Location
    }

    Start-Process powershell -WorkingDirectory $backend -ArgumentList @(
        '-NoExit', '-Command', '.\.venv\Scripts\python.exe -m uvicorn app.main:app --port 8002 --no-access-log'
    )

    Start-Process powershell -WorkingDirectory $frontend -ArgumentList @(
        '-NoExit', '-Command', 'npm run dev -- --port 5174 --strictPort'
    )
    Write-Host 'Customer demo: http://localhost:5174/demo'
    Write-Host 'Staff sign in: http://localhost:5174/login'
} finally {
    foreach ($name in $saved.Keys) {
        [Environment]::SetEnvironmentVariable($name, $saved[$name], 'Process')
    }
}
