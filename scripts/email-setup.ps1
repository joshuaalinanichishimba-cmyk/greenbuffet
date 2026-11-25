# Sets up email for The Green Buffet: sign-in codes, password reset links
# and security notices.
#
#   .\scripts\email-setup.ps1
#   .\scripts\email-setup.ps1 -Off        stop sending email
#
# To start with, it sends from a Gmail account using a Google "App Password",
# a separate 16-letter password made only for this. It never uses the Gmail
# account's own password. Make one at:
#   https://myaccount.google.com/apppasswords
# (Google only offers it once 2-Step Verification is on for that account.)
#
# The App Password is typed here, hidden, and written only to backend\.env on
# this computer. It is never sent anywhere else, never printed, and the push
# script refuses to send .env to GitHub. Cancel it at any time at the address
# above, and email stops until this is run again.
#
# Later, with the restaurant's own domain, run this again with that mailbox's
# SMTP details (Resend, Brevo and others give SMTP settings).
param(
    [switch] $Off,
    [string] $Address = 'joshuaalinanichishimba@gmail.com',
    [string] $SmtpHost = 'smtp.gmail.com',
    [int] $Port = 587
)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$backend = Join-Path $root 'backend'
$envFile = Join-Path $backend '.env'
$python = Join-Path $backend '.venv\Scripts\python.exe'

if (-not (Test-Path $envFile)) {
    Write-Host 'backend\.env is missing. Run .\scripts\setup.ps1 first.' -ForegroundColor Red
    exit 1
}

$keys = 'EMAIL_MODE', 'SMTP_HOST', 'SMTP_PORT', 'SMTP_USER', 'SMTP_PASSWORD', 'EMAIL_FROM', 'EMAIL_FROM_NAME', 'APP_URL'
$kept = Get-Content $envFile | Where-Object {
    $line = $_
    -not ($keys | Where-Object { $line -match "^\s*$_\s*=" })
}

if ($Off) {
    [IO.File]::WriteAllLines($envFile, [string[]]($kept + 'EMAIL_MODE=off'), (New-Object Text.UTF8Encoding $false))
    Write-Host 'Email is off. Restart the system for it to take effect: .\scripts\update.ps1'
    exit 0
}

Write-Host ''
Write-Host '  Email for The Green Buffet'
Write-Host "  Sending from: $Address (through $SmtpHost)"
Write-Host ''
Write-Host '  Paste the 16-letter App Password from https://myaccount.google.com/apppasswords'
Write-Host '  (not the Gmail password). It will not show as you type.'
$secure = Read-Host '  App Password' -AsSecureString
$plain = [Runtime.InteropServices.Marshal]::PtrToStringAuto([Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure))
$plain = $plain -replace '\s', ''
# A Google App Password is always 16 letters. Anything else is a paste that
# did not take, or the Gmail password by mistake.
if ($SmtpHost -eq 'smtp.gmail.com' -and $plain -notmatch '^[a-zA-Z]{16}$') {
    Write-Host "  That was $($plain.Length) characters. A Google App Password is 16 letters." -ForegroundColor Red
    Write-Host '  Copy it again from Google and paste with a right-click. Nothing was changed.' -ForegroundColor Red
    exit 1
}
if ($plain.Length -lt 8) {
    Write-Host '  That is too short to be a mailbox password. Nothing was changed.' -ForegroundColor Red
    exit 1
}

$url = Read-Host '  Address staff use to open the system (Enter for http://localhost:8000)'
if (-not $url) { $url = 'http://localhost:8000' }
$url = $url.Trim().TrimEnd('/')
if ($url -notmatch '^https?://[^\s]+$') {
    Write-Host "  '$url' is not a web address. Use something like http://localhost:8000. Nothing was changed." -ForegroundColor Red
    exit 1
}

# Written without a byte-order mark: with one, the first setting in the file
# would not be read.
[IO.File]::WriteAllLines($envFile, [string[]]($kept + @(
    'EMAIL_MODE=smtp',
    "SMTP_HOST=$SmtpHost",
    "SMTP_PORT=$Port",
    "SMTP_USER=$Address",
    "SMTP_PASSWORD=$plain",
    "EMAIL_FROM=$Address",
    'EMAIL_FROM_NAME=The Green Buffet',
    "APP_URL=$url"
)), (New-Object Text.UTF8Encoding $false))
$plain = $null
Write-Host '  Saved in backend\.env (this computer only).'

Write-Host ''
Write-Host "  Sending a test email to $Address ..."
Push-Location $backend
try {
    & $python -m app.email_check $Address
    $ok = $LASTEXITCODE -eq 0
} finally {
    Pop-Location
}
if (-not $ok) {
    Write-Host '  The test email did not go. Check the App Password and try again.' -ForegroundColor Red
    exit 1
}
Write-Host ''
Write-Host '  Restart the system so it starts sending: .\scripts\update.ps1' -ForegroundColor Green
Write-Host '  Then each person confirms their address under Profile, Security.'
