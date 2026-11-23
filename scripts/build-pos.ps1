[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$frontend = Join-Path (Split-Path -Parent $PSScriptRoot) 'frontend'
$oldApiBase = $env:VITE_API_BASE_URL

Push-Location $frontend
try {
    if (-not (Test-Path 'node_modules' -PathType Container)) {
        & npm.cmd ci
        if ($LASTEXITCODE -ne 0) { throw 'Installing frontend packages failed.' }
    }
    $env:VITE_API_BASE_URL = '/api/v1'
    & npm.cmd run build
    if ($LASTEXITCODE -ne 0) { throw 'Building the POS frontend failed.' }
} finally {
    $env:VITE_API_BASE_URL = $oldApiBase
    Pop-Location
}
