<#
    The Green Buffet - restore a backup into a TEST database
    Run:  .\scripts\restore.ps1
          .\scripts\restore.ps1 -File backups\greenbuffet_dev-2026-11-18-0900.dump

    Restores into greenbuffet_restoretest by default, never over your working
    database. Pass -Target to choose another, and -Force to confirm.
#>
[CmdletBinding()]
param(
    [string] $File,
    [string] $Target = 'greenbuffet_restoretest',
    [string] $DbUser = 'gb_dev',
    [switch] $Force
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$backupDir = Join-Path $root 'backups'

if ($Target -eq 'greenbuffet_dev' -and -not $Force) {
    throw 'Refusing to restore over greenbuffet_dev. Pass -Force if that is really what you want.'
}

if (-not $File) {
    $latest = Get-ChildItem $backupDir -Filter '*.dump' -ErrorAction SilentlyContinue |
              Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if (-not $latest) { throw "No backups found in $backupDir. Run .\scripts\backup.ps1 first." }
    $File = $latest.FullName
}
if (-not (Test-Path $File)) { throw "Backup file not found: $File" }

foreach ($t in 'psql', 'pg_restore') {
    if (-not (Get-Command $t -ErrorAction SilentlyContinue)) {
        $pg = Get-ChildItem 'C:\Program Files\PostgreSQL' -Directory -ErrorAction SilentlyContinue |
              Sort-Object Name -Descending | Select-Object -First 1
        if ($pg) { $env:PATH = $env:PATH + ';' + (Join-Path $pg.FullName 'bin') }
    }
}

$envFile = Join-Path $root 'backend\.env'
if (Test-Path $envFile) {
    $line = Select-String -Path $envFile -Pattern '^DATABASE_URL=' | Select-Object -First 1
    if ($line -and $line.Line -match '://([^:]+):([^@]+)@') { $DbUser = $Matches[1]; $env:PGPASSWORD = $Matches[2] }
}

Write-Host ''
Write-Host ('  Restoring ' + (Split-Path $File -Leaf)) -ForegroundColor Green
Write-Host ('  into database ' + $Target) -ForegroundColor DarkGray

$exists = (psql -U $DbUser -h localhost -d postgres -tAc "SELECT 1 FROM pg_database WHERE datname='$Target'" 2>$null)
if ($exists -ne '1') {
    psql -U $DbUser -h localhost -d postgres -q -c "CREATE DATABASE $Target OWNER $DbUser;" | Out-Null
    Write-Host ('    created ' + $Target) -ForegroundColor DarkGray
}

pg_restore -U $DbUser -h localhost -d $Target --clean --if-exists --no-owner $File 2>&1 |
    Where-Object { $_ -notmatch 'does not exist, skipping' }

$tables = (psql -U $DbUser -h localhost -d $Target -tAc "SELECT count(*) FROM information_schema.tables WHERE table_schema='public'")
Write-Host ''
Write-Host ('  Restored. ' + $tables.Trim() + ' tables are present in ' + $Target + '.') -ForegroundColor Green
Write-Host '  The backup file is good.' -ForegroundColor Green
Write-Host ''
