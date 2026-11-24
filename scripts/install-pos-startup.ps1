#Requires -RunAsAdministrator
[CmdletBinding()]
param(
    [PSCredential] $Credential,
    [ValidateSet('127.0.0.1', '0.0.0.0')]
    [string] $ListenAddress = '127.0.0.1',
    [ValidateRange(1, 65535)]
    [int] $Port = 8088,
    [string] $TlsCertificate,
    [string] $TlsKey
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$launcher = Join-Path $PSScriptRoot 'run-pos.ps1'
$taskName = 'Green Buffet POS'

if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) {
    throw "A task named '$taskName' already exists. Review the task in Windows Task Scheduler before replacing it."
}
if (-not (Test-Path -LiteralPath (Join-Path $root 'frontend\dist\index.html') -PathType Leaf)) {
    throw 'Run scripts\build-pos.ps1 first.'
}
if (([bool] $TlsCertificate -ne [bool] $TlsKey) -or ($ListenAddress -eq '0.0.0.0' -and -not $TlsCertificate)) {
    throw 'Provide both -TlsCertificate and -TlsKey for HTTPS. LAN access requires HTTPS.'
}

$actionArgs = '-NoLogo -NoProfile -NonInteractive -File "{0}" -ListenAddress {1} -Port {2}' -f $launcher, $ListenAddress, $Port
if ($TlsCertificate) {
    $certificate = (Resolve-Path -LiteralPath $TlsCertificate).ProviderPath
    $key = (Resolve-Path -LiteralPath $TlsKey).ProviderPath
    $actionArgs += ' -TlsCertificate "{0}" -TlsKey "{1}"' -f $certificate, $key
}
if (-not $Credential) {
    $Credential = Get-Credential -Message 'Windows account that can run this POS installation at startup'
}
if (-not $Credential) { throw 'A Windows account is required for the startup task.' }

$action = New-ScheduledTaskAction -Execute (Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe') -Argument $actionArgs -WorkingDirectory $root
$trigger = New-ScheduledTaskTrigger -AtStartup
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit ([TimeSpan]::Zero) -RestartCount 10 -RestartInterval (New-TimeSpan -Minutes 1) -MultipleInstances IgnoreNew

Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Settings $settings `
    -User $Credential.UserName -Password $Credential.GetNetworkCredential().Password -RunLevel Limited | Out-Null
Start-ScheduledTask -TaskName $taskName
Write-Host 'Registered and started the Green Buffet POS startup task.'
