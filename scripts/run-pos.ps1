[CmdletBinding()]
param(
    [ValidateSet('127.0.0.1', '0.0.0.0')]
    [string] $ListenAddress = '127.0.0.1',
    [ValidateRange(1, 65535)]
    [int] $Port = 8088,
    [string] $TlsCertificate,
    [string] $TlsKey
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$backend = Join-Path $root 'backend'
$python = Join-Path $backend '.venv\Scripts\python.exe'
$frontend = Join-Path $root 'frontend\dist'

if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
    throw 'The backend virtual environment is missing. Run scripts\setup.ps1 on a new installation.'
}
if (-not (Test-Path -LiteralPath (Join-Path $backend '.env') -PathType Leaf)) {
    throw 'The Windows POS requires backend\.env.'
}
if (-not (Test-Path -LiteralPath (Join-Path $frontend 'index.html') -PathType Leaf)) {
    throw 'Run scripts\build-pos.ps1 first.'
}
if (([bool] $TlsCertificate -ne [bool] $TlsKey) -or ($ListenAddress -eq '0.0.0.0' -and -not $TlsCertificate)) {
    throw 'Provide both -TlsCertificate and -TlsKey for HTTPS. LAN access requires HTTPS.'
}

$uvicornArgs = @('app.main:app', '--host', $ListenAddress, '--port', $Port, '--no-access-log', '--log-level', 'warning')
if ($TlsCertificate) {
    $certificate = (Resolve-Path -LiteralPath $TlsCertificate).ProviderPath
    $key = (Resolve-Path -LiteralPath $TlsKey).ProviderPath
    $uvicornArgs += @('--ssl-certfile', $certificate, '--ssl-keyfile', $key)
}
$oldDatabaseUrl = $env:DATABASE_URL
$oldJwtSecret = $env:JWT_SECRET
$oldFrontend = $env:POS_FRONTEND_DIR
$oldEnvironment = $env:ENVIRONMENT
$oldCorsOrigins = $env:CORS_ORIGINS
$env:POS_FRONTEND_DIR = $frontend
$env:ENVIRONMENT = 'production'
$env:CORS_ORIGINS = ' '
Remove-Item Env:DATABASE_URL, Env:JWT_SECRET -ErrorAction SilentlyContinue
Push-Location $backend
try {
    & $python -m uvicorn @uvicornArgs
    if ($LASTEXITCODE -ne 0) { throw 'The POS server exited with an error.' }
} finally {
    $env:DATABASE_URL = $oldDatabaseUrl
    $env:JWT_SECRET = $oldJwtSecret
    $env:POS_FRONTEND_DIR = $oldFrontend
    $env:ENVIRONMENT = $oldEnvironment
    $env:CORS_ORIGINS = $oldCorsOrigins
    Pop-Location
}
