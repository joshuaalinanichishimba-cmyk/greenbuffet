<#
  Fixes "password authentication failed for user gb_dev".

  The system signs in to PostgreSQL with the password written in
  backend\.env. If PostgreSQL holds a different password for that user (setup
  was run twice, the password was changed by hand, PostgreSQL was
  reinstalled), every request fails. This script makes PostgreSQL agree with
  backend\.env, then restarts the system.

  It also checks for a DATABASE_URL Windows environment variable, which
  quietly overrides backend\.env.

  Usage (from the project folder):   .\scripts\fix-database.ps1
  You will be asked for the PostgreSQL superuser (postgres) password, the one
  chosen when PostgreSQL was installed.
#>
param([int] $Port = 8000)
# 'Continue', not 'Stop': Windows PowerShell treats psql's error text as a
# script-stopping error under 'Stop', and reading that text is the whole point.
$ErrorActionPreference = 'Continue'
$ProgressPreference = 'SilentlyContinue'

$root = Split-Path -Parent $PSScriptRoot
$envFile = Join-Path $root 'backend\.env'
function Line($text, $colour = 'Gray') { Write-Host ('     ' + $text) -ForegroundColor $colour }
function Head($text) { Write-Host ''; Write-Host ('  == ' + $text) -ForegroundColor Cyan }

Write-Host ''
Write-Host '  The Green Buffet - fix the database password' -ForegroundColor Green

# ---- 1. an environment variable that overrides backend\.env -------------------
Head 'Windows environment variable'
$override = $false
foreach ($scope in 'User', 'Machine') {
    $value = [Environment]::GetEnvironmentVariable('DATABASE_URL', $scope)
    if ($value) {
        $override = $true
        Line ("DATABASE_URL is set for the {0}. It is used INSTEAD of backend\.env." -f $scope.ToLower()) Yellow
        $answer = Read-Host '     Remove it so backend\.env is used? (y/n)'
        if ($answer -match '^[yY]') {
            try {
                [Environment]::SetEnvironmentVariable('DATABASE_URL', $null, $scope)
                Line 'Removed.' Green
            } catch {
                Line 'Could not remove it. Run this script as Administrator (it is a computer-wide setting).' Red
                exit 1
            }
        }
    }
}
if (-not $override) { Line 'None set, good: backend\.env is what the system uses.' Green }
Remove-Item Env:DATABASE_URL -ErrorAction SilentlyContinue

# ---- 2. what backend\.env says ------------------------------------------------
Head 'backend\.env'
if (-not (Test-Path $envFile)) {
    Line 'backend\.env is missing. Run .\scripts\setup.ps1 to create it.' Red
    exit 1
}
$line = Select-String -Path $envFile -Pattern '^DATABASE_URL=' | Select-Object -First 1
if (-not $line -or $line.Line -notmatch '://([^:]+):([^@]*)@([^:/]+):?(\d*)/(.+)$') {
    Line 'No readable DATABASE_URL line in backend\.env.' Red
    exit 1
}
$dbUser = $Matches[1]; $dbPassword = [Uri]::UnescapeDataString($Matches[2])
$dbHost = $Matches[3]; $dbPort = if ($Matches[4]) { $Matches[4] } else { '5432' }; $dbName = $Matches[5].Trim()
Line ("Database {0} as user {1} on {2}:{3}" -f $dbName, $dbUser, $dbHost, $dbPort)

# ---- 3. find psql -------------------------------------------------------------
$psql = (Get-Command psql -ErrorAction SilentlyContinue).Source
if (-not $psql) {
    $psql = Get-ChildItem 'C:\Program Files\PostgreSQL\*\bin\psql.exe' -ErrorAction SilentlyContinue |
        Sort-Object FullName -Descending | Select-Object -First 1 -ExpandProperty FullName
}
if (-not $psql) { Line 'psql.exe not found. Is PostgreSQL installed?' Red; exit 1 }

function Test-Login {
    $env:PGPASSWORD = $dbPassword
    $result = & $psql -U $dbUser -h $dbHost -p $dbPort -d $dbName -tAc 'SELECT 1' 2>&1
    Remove-Item Env:PGPASSWORD -ErrorAction SilentlyContinue
    return ($result -join '') -match '^\s*1\s*$'
}

# ---- 4. test, and fix if needed -----------------------------------------------
Head 'Signing in as the system does'
if (Test-Login) {
    Line 'The password in backend\.env works.' Green
} else {
    Line 'PostgreSQL refuses that password. Setting it to match backend\.env.' Yellow
    $secure = Read-Host '     PostgreSQL superuser (postgres) password' -AsSecureString
    $env:PGPASSWORD = [Runtime.InteropServices.Marshal]::PtrToStringAuto(
        [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure))
    $quoted = $dbPassword.Replace("'", "''")
    $exists = (& $psql -U postgres -h $dbHost -p $dbPort -tAc "SELECT 1 FROM pg_roles WHERE rolname='$dbUser'" 2>&1) -join ''
    if ($LASTEXITCODE -ne 0) {
        Remove-Item Env:PGPASSWORD -ErrorAction SilentlyContinue
        Line 'The postgres password was not accepted either. Try again with the one set at install.' Red
        exit 1
    }
    if ($exists.Trim() -eq '1') {
        & $psql -U postgres -h $dbHost -p $dbPort -q -c "ALTER USER $dbUser WITH PASSWORD '$quoted';" | Out-Null
    } else {
        & $psql -U postgres -h $dbHost -p $dbPort -q -c "CREATE USER $dbUser WITH PASSWORD '$quoted';" | Out-Null
        & $psql -U postgres -h $dbHost -p $dbPort -q -c "ALTER DATABASE $dbName OWNER TO $dbUser;" 2>$null | Out-Null
    }
    Remove-Item Env:PGPASSWORD -ErrorAction SilentlyContinue
    if (Test-Login) { Line 'Fixed: PostgreSQL now accepts the password in backend\.env.' Green }
    else { Line 'Still refused. Send the output of .\scripts\status.ps1.' Red; exit 1 }
}

# ---- 5. restart so the running copy picks it up --------------------------------
Head 'Restarting'
if (Get-ScheduledTask -TaskName 'Green Buffet' -ErrorAction SilentlyContinue) {
    Stop-ScheduledTask -TaskName 'Green Buffet' -ErrorAction SilentlyContinue
    Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
        ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }
    Start-Sleep -Seconds 2
    Start-ScheduledTask -TaskName 'Green Buffet'
    $ok = $false
    foreach ($i in 1..40) {
        Start-Sleep -Seconds 1
        try { if ((Invoke-RestMethod "http://127.0.0.1:$Port/api/v1/health" -TimeoutSec 4).status -eq 'ok') { $ok = $true; break } } catch { }
    }
    if ($ok) { Line "Running, database connected. Open http://localhost:$Port and sign in." Green }
    else { Line 'Not answering yet. Run .\scripts\status.ps1 in a minute.' Yellow }
} else {
    Line 'No scheduled task installed; start it with .\scripts\run.ps1' Gray
}
Write-Host ''
