<#
    Asks Windows to back the database up every night.

    Run once, in an Administrator PowerShell:
        cd "D:\The Green Buffet"
        .\scripts\schedule-backup.ps1

    It creates a scheduled task that runs backup.ps1 at the time given, whether
    or not anyone is signed in. backup.ps1 keeps 30 days and deletes older ones.

    To stop it:  Unregister-ScheduledTask -TaskName 'Green Buffet backup'
#>
[CmdletBinding()]
param(
    [string] $At = '23:30',
    [string] $TaskName = 'Green Buffet backup',
    [switch] $Remove
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$script = Join-Path $PSScriptRoot 'backup.ps1'

$admin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()
         ).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $admin) {
    throw 'Run this in an Administrator PowerShell: right-click PowerShell and choose "Run as administrator".'
}

if ($Remove) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
    Write-Host ''
    Write-Host "  Nightly backup removed." -ForegroundColor Green
    Write-Host ''
    return
}

if (-not (Test-Path $script)) { throw "backup.ps1 is missing from $PSScriptRoot." }

$action = New-ScheduledTaskAction -Execute 'powershell.exe' `
    -Argument ('-NoProfile -ExecutionPolicy Bypass -File "{0}"' -f $script) `
    -WorkingDirectory $root
$trigger = New-ScheduledTaskTrigger -Daily -At $At
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -DontStopIfGoingOnBatteries `
    -AllowStartIfOnBatteries -ExecutionTimeLimit (New-TimeSpan -Hours 1)

Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings `
    -Description 'Backs up The Green Buffet database and keeps 30 days.' `
    -RunLevel Highest -User 'SYSTEM' | Out-Null

Write-Host ''
Write-Host "  Nightly backup set for $At." -ForegroundColor Green
Write-Host "  Backups land in $root\backups" -ForegroundColor DarkGray
Write-Host '  Check it ran:  Get-ScheduledTaskInfo -TaskName ''Green Buffet backup''' -ForegroundColor DarkGray
Write-Host '  Keep a copy off this computer as well.' -ForegroundColor Yellow
Write-Host ''
