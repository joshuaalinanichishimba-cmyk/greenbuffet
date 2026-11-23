<#
    The Green Buffet - database backup
    Run:  .\scripts\backup.ps1

    Writes a compressed dump into backups\ and deletes dumps older than 30 days.
    A backup you have never restored is not a backup: test one with restore.ps1.
#>
[CmdletBinding()]
param(
    [string] $DbName = 'greenbuffet_dev',
    [string] $DbUser = 'gb_dev',
    [int]    $KeepDays = 30
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$backupDir = Join-Path $root 'backups'
New-Item -ItemType Directory -Force -Path $backupDir | Out-Null

if (-not (Get-Command pg_dump -ErrorAction SilentlyContinue)) {
    $pg = Get-ChildItem 'C:\Program Files\PostgreSQL' -Directory -ErrorAction SilentlyContinue |
          Sort-Object Name -Descending | Select-Object -First 1
    if ($pg) { $env:PATH = $env:PATH + ';' + (Join-Path $pg.FullName 'bin') }
}
if (-not (Get-Command pg_dump -ErrorAction SilentlyContinue)) { throw 'pg_dump not found. Is PostgreSQL installed?' }

# Reuse the password already stored in backend\.env rather than asking again.
$envFile = Join-Path $root 'backend\.env'
if (Test-Path $envFile) {
    $line = Select-String -Path $envFile -Pattern '^DATABASE_URL=' | Select-Object -First 1
    if ($line -and $line.Line -match '://([^:]+):([^@]+)@') {
        $DbUser = $Matches[1]
        $env:PGPASSWORD = $Matches[2]
    }
}
if (-not $env:PGPASSWORD) {
    $secure = Read-Host "Password for $DbUser" -AsSecureString
    $env:PGPASSWORD = [Runtime.InteropServices.Marshal]::PtrToStringAuto(
        [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure))
}

$stamp = Get-Date -Format 'yyyy-MM-dd-HHmm'
$file  = Join-Path $backupDir ($DbName + '-' + $stamp + '.dump')

Write-Host ''
Write-Host ('  Backing up ' + $DbName) -ForegroundColor Green
pg_dump -U $DbUser -h localhost -d $DbName -F c -f $file
if ($LASTEXITCODE -ne 0) { throw 'pg_dump failed.' }

$size = [math]::Round((Get-Item $file).Length / 1MB, 2)
Write-Host ('    ' + $file) -ForegroundColor Cyan
Write-Host ('    ' + $size + ' MB') -ForegroundColor DarkGray

$cutoff = (Get-Date).AddDays(-$KeepDays)
$old = Get-ChildItem $backupDir -Filter '*.dump' | Where-Object { $_.LastWriteTime -lt $cutoff }
if ($old) {
    $old | Remove-Item -Force
    Write-Host ('    removed ' + $old.Count + ' backup(s) older than ' + $KeepDays + ' days') -ForegroundColor DarkGray
}
Write-Host ''
Write-Host '  Keep a copy off this laptop: a backup on the same machine does not survive theft or a dead disk.' -ForegroundColor Yellow
Write-Host ''
