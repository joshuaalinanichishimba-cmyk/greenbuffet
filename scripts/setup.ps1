<#
    The Green Buffet - one-time setup
    Run from the project folder:
        .\scripts\setup.ps1

    Creates the Python environment, installs everything, creates the database,
    creates the tables and the first owner account. Safe to run again.
#>
[CmdletBinding()]
param(
    [string] $DbName     = 'greenbuffet_dev',
    [string] $DbUser     = 'gb_dev',
    [string] $OwnerEmail = 'owner@greenbuffet.zm',
    [switch] $SkipDatabase
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$backend  = Join-Path $root 'backend'
$frontend = Join-Path $root 'frontend'

function Step($text) {
    Write-Host ''
    Write-Host ('  == ' + $text) -ForegroundColor Green
}
function Ok($text)   { Write-Host ('     ' + $text) -ForegroundColor DarkGray }
function Warn($text) { Write-Host ('     ' + $text) -ForegroundColor Yellow }

Write-Host ''
Write-Host '  The Green Buffet - setup' -ForegroundColor Green
Write-Host ('  Project: ' + $root) -ForegroundColor DarkGray

# --- 1. prerequisites -------------------------------------------------------
Step 'Checking tools'
foreach ($t in 'python', 'node', 'npm') {
    if (-not (Get-Command $t -ErrorAction SilentlyContinue)) {
        throw "$t is not installed or not on PATH. Run .\scripts\check.ps1 first, then open a NEW PowerShell window."
    }
    Ok ($t + ' ' + ((& $t --version 2>&1 | Select-Object -First 1)))
}

# PostgreSQL usually installs without putting psql on PATH.
if (-not (Get-Command psql -ErrorAction SilentlyContinue)) {
    $pg = Get-ChildItem 'C:\Program Files\PostgreSQL' -Directory -ErrorAction SilentlyContinue |
          Sort-Object Name -Descending | Select-Object -First 1
    if ($pg) {
        $env:PATH = $env:PATH + ';' + (Join-Path $pg.FullName 'bin')
        Ok ('added to PATH for this session: ' + (Join-Path $pg.FullName 'bin'))
    }
}
if (-not $SkipDatabase -and -not (Get-Command psql -ErrorAction SilentlyContinue)) {
    throw 'PostgreSQL is not installed. Run: winget install --id PostgreSQL.PostgreSQL.16 -e'
}

# --- 2. database ------------------------------------------------------------
$dbPassword = $null
if (-not $SkipDatabase) {
    Step 'Database'
    $existing = Join-Path $backend '.env'
    if (Test-Path $existing) {
        $line = Select-String -Path $existing -Pattern '^DATABASE_URL=' | Select-Object -First 1
        if ($line -and $line.Line -match '://[^:]+:([^@]+)@') {
            $dbPassword = $Matches[1]
            Ok 'reusing the database password already in backend\.env'
        }
    }
    if (-not $dbPassword) {
        $secure = Read-Host 'Choose a password for the database user gb_dev' -AsSecureString
        $dbPassword = [Runtime.InteropServices.Marshal]::PtrToStringAuto(
            [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure))
        if ([string]::IsNullOrWhiteSpace($dbPassword)) { throw 'The database password cannot be empty.' }
    }

    $superSecure = Read-Host 'PostgreSQL superuser (postgres) password, set during install' -AsSecureString
    $env:PGPASSWORD = [Runtime.InteropServices.Marshal]::PtrToStringAuto(
        [Runtime.InteropServices.Marshal]::SecureStringToBSTR($superSecure))

    $userExists = (psql -U postgres -h localhost -tAc "SELECT 1 FROM pg_roles WHERE rolname='$DbUser'" 2>$null)
    if ($userExists -ne '1') {
        psql -U postgres -h localhost -q -c "CREATE USER $DbUser WITH PASSWORD '$dbPassword';" | Out-Null
        Ok ('created database user ' + $DbUser)
    } else {
        psql -U postgres -h localhost -q -c "ALTER USER $DbUser WITH PASSWORD '$dbPassword';" | Out-Null
        Ok ('database user ' + $DbUser + ' already existed, password synchronised')
    }

    $dbExists = (psql -U postgres -h localhost -tAc "SELECT 1 FROM pg_database WHERE datname='$DbName'" 2>$null)
    if ($dbExists -ne '1') {
        psql -U postgres -h localhost -q -c "CREATE DATABASE $DbName OWNER $DbUser;" | Out-Null
        Ok ('created database ' + $DbName)
    } else {
        Ok ('database ' + $DbName + ' already existed')
    }

    $env:PGPASSWORD = $dbPassword
    $check = (psql -U $DbUser -h localhost -d $DbName -tAc 'SELECT 1' 2>$null)
    if ($check -ne '1') { throw "Could not connect to $DbName as $DbUser. Check the password and that PostgreSQL is running." }
    Ok 'connection tested'
}

# --- 3. backend environment file -------------------------------------------
Step 'Backend settings'
$envPath = Join-Path $backend '.env'
if (Test-Path $envPath) {
    Ok 'backend\.env already exists, leaving it alone'
} else {
    $secret = (python -c "import secrets; print(secrets.token_urlsafe(48))").Trim()
    $lines = @(
        "DATABASE_URL=postgresql+psycopg://${DbUser}:${dbPassword}@localhost:5432/${DbName}",
        "JWT_SECRET=$secret",
        'JWT_EXPIRE_MINUTES=480',
        'CORS_ORIGINS=http://localhost:5173',
        'ENVIRONMENT=development',
        'APP_TIMEZONE=Africa/Lusaka'
    )
    # UTF-8 without a byte order mark: a BOM breaks python-dotenv on the first key.
    [IO.File]::WriteAllLines($envPath, $lines, (New-Object Text.UTF8Encoding $false))
    Ok ('wrote ' + $envPath + ' (' + (Get-Item $envPath).Length + ' bytes)')
}

$feEnv = Join-Path $frontend '.env.development'
if (-not (Test-Path $feEnv)) {
    [IO.File]::WriteAllLines($feEnv, @('VITE_API_BASE_URL=http://localhost:8000/api/v1'),
        (New-Object Text.UTF8Encoding $false))
    Ok 'wrote frontend\.env.development'
}

# --- 4. python environment --------------------------------------------------
Step 'Python environment'
Push-Location $backend
try {
    if (-not (Test-Path (Join-Path $backend '.venv'))) {
        python -m venv .venv
        Ok 'created backend\.venv'
    } else {
        Ok 'backend\.venv already exists'
    }
    $py = Join-Path $backend '.venv\Scripts\python.exe'
    if (-not (Test-Path $py)) { throw 'The virtual environment looks broken. Delete backend\.venv and run setup again.' }

    & $py -m pip install --quiet --upgrade pip
    Ok 'installing backend packages, this takes a few minutes'
    & $py -m pip install --quiet -r (Join-Path $backend 'requirements.txt')
    if ($LASTEXITCODE -ne 0) { throw 'Installing the backend packages failed. Check your internet connection.' }
    Ok 'backend packages installed'

    if (-not $SkipDatabase) {
        Ok 'creating tables and the first owner account'
        & $py -m app.seed $OwnerEmail
        if ($LASTEXITCODE -ne 0) { throw 'Creating the tables failed. Check the database settings in backend\.env.' }
    }
} finally {
    Pop-Location
}

# --- 5. frontend ------------------------------------------------------------
Step 'Frontend'
Push-Location $frontend
try {
    Ok 'installing frontend packages'
    npm install --silent
    if ($LASTEXITCODE -ne 0) { throw 'npm install failed.' }
    Ok 'frontend packages installed'
} finally {
    Pop-Location
}

Write-Host ''
Write-Host '  Setup finished.' -ForegroundColor Green
Write-Host ''
Write-Host '  Start the system with:   .\scripts\run.ps1' -ForegroundColor Cyan
Write-Host '  Then open:               http://localhost:5173' -ForegroundColor Cyan
Write-Host ''
Write-Host '  Sign in with the owner email and the password printed above.' -ForegroundColor DarkGray
Write-Host '  You will be asked to choose your own password straight away.' -ForegroundColor DarkGray
Write-Host ''
