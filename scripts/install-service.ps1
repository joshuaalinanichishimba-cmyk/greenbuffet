<#
    Makes The Green Buffet start with Windows and stay running.

    Run once, in an Administrator PowerShell:
        cd "D:\The Green Buffet"
        .\scripts\install-service.ps1

    It does three things:
      1. opens the port in the Windows firewall, for phones and tablets on the
         restaurant wifi;
      2. registers a task that starts the system when the computer starts,
         before anyone signs in;
      3. starts it now.

    To undo it all:  .\scripts\install-service.ps1 -Remove
#>
[CmdletBinding()]
param([int] $Port = 8000, [string] $TaskName = 'Green Buffet', [switch] $Remove)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$serve = Join-Path $PSScriptRoot 'serve.ps1'
$ruleName = 'Green Buffet system'

$admin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()
         ).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $admin) {
    throw 'Run this in an Administrator PowerShell: right-click PowerShell and choose "Run as administrator".'
}

if ($Remove) {
    Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
    Remove-NetFirewallRule -DisplayName $ruleName -ErrorAction SilentlyContinue
    Write-Host ''
    Write-Host '  Removed. The system no longer starts with Windows.' -ForegroundColor Green
    Write-Host ''
    return
}

Write-Host ''
Write-Host '  Setting The Green Buffet up to run by itself' -ForegroundColor Green

# 1. the firewall
Remove-NetFirewallRule -DisplayName $ruleName -ErrorAction SilentlyContinue
New-NetFirewallRule -DisplayName $ruleName -Direction Inbound -Action Allow `
    -Protocol TCP -LocalPort $Port -Profile Private, Domain | Out-Null
Write-Host "     port $Port opened for the local network" -ForegroundColor DarkGray

# 2. the startup task
$action = New-ScheduledTaskAction -Execute 'powershell.exe' `
    -Argument ('-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File "{0}" -Port {1} -SkipBuild' -f $serve, $Port) `
    -WorkingDirectory $root
$trigger = New-ScheduledTaskTrigger -AtStartup
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -DontStopIfGoingOnBatteries `
    -AllowStartIfOnBatteries -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1) `
    -ExecutionTimeLimit ([TimeSpan]::Zero)

Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings `
    -Description 'Runs The Green Buffet management system.' -RunLevel Highest -User 'SYSTEM' | Out-Null
Write-Host '     starts automatically when the computer starts' -ForegroundColor DarkGray

# 3. build once, then start
Write-Host '     building the front end...' -ForegroundColor DarkGray
Push-Location (Join-Path $root 'frontend')
try { npm run build | Out-Null } finally { Pop-Location }

Start-ScheduledTask -TaskName $TaskName
Start-Sleep -Seconds 8

$addresses = Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
    Where-Object { $_.IPAddress -notlike '127.*' -and $_.IPAddress -notlike '169.254.*' } |
    Select-Object -ExpandProperty IPAddress

Write-Host ''
try {
    $health = Invoke-RestMethod "http://127.0.0.1:$Port/api/v1/health" -TimeoutSec 10
    Write-Host "  Running. Database: $($health.database)." -ForegroundColor Green
} catch {
    Write-Host '  Started, but it is not answering yet. Give it a minute, then check:' -ForegroundColor Yellow
    Write-Host "     Get-ScheduledTaskInfo -TaskName '$TaskName'" -ForegroundColor DarkGray
}

Write-Host ''
Write-Host '  On this computer:   ' -NoNewline -ForegroundColor Green
Write-Host "http://localhost:$Port" -ForegroundColor Cyan
foreach ($address in $addresses) {
    Write-Host '  On the wifi:        ' -NoNewline -ForegroundColor Green
    Write-Host "http://${address}:$Port" -ForegroundColor Cyan
}
Write-Host ''
Write-Host '  Write the wifi address on a card by the till.' -ForegroundColor DarkGray
Write-Host '  After installing a new stage, run this again so the front end is rebuilt.' -ForegroundColor DarkGray
Write-Host ''
