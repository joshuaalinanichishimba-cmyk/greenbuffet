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
    $LiveDb = 'greenbuffet_dev'
    if ($line -and $line.Line -match '://([^:]+):([^@]+)@[^/]+/([^?\s]+)') {
        $DbUser = $Matches[1]; $env:PGPASSWORD = [Uri]::UnescapeDataString($Matches[2]); $LiveDb = $Matches[3]
    }
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

# A restore only proves something if the data came back. Compare the rows in
# the tables that matter with the working database. The live database can
# only have more rows than the backup (sales since), never fewer.
$check = 'orders', 'payments', 'shifts', 'stock_moves', 'journal_entries', 'journal_lines', 'users', 'products', 'payslips', 'audit_log'
$ok = $true
Write-Host ''
Write-Host ('  {0,-18} {1,10} {2,10}' -f 'table', 'backup', 'working') -ForegroundColor DarkGray
foreach ($t in $check) {
    $inBackup = (psql -U $DbUser -h localhost -d $Target -tAc "SELECT count(*) FROM $t" 2>$null)
    $inLive = (psql -U $DbUser -h localhost -d $LiveDb -tAc "SELECT count(*) FROM $t" 2>$null)
    if (-not $inBackup) { $inBackup = 'missing'; $ok = $false }
    elseif ($inLive -and [int]$inBackup -gt [int]$inLive) { $ok = $false }
    Write-Host ('  {0,-18} {1,10} {2,10}' -f $t, "$inBackup".Trim(), "$inLive".Trim())
}
Write-Host ''
if ($ok) {
    Write-Host '  Verified: the backup restores, and its records match the working database up to when it was taken.' -ForegroundColor Green
} else {
    Write-Host '  Something is missing from the restored copy. Do not rely on this backup; send this output for support.' -ForegroundColor Red
}
Write-Host ('  The test copy ' + $Target + ' can be left; the next restore overwrites it.') -ForegroundColor DarkGray
Write-Host ''
