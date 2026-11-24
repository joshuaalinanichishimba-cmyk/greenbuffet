<#
  Sets a new temporary password when nobody can sign in.

  .\scripts\reset-owner.ps1                               the owner account
  .\scripts\reset-owner.ps1 someone@greenbuffet.zm        any other account

  Prints the new password; you choose your own at the next sign-in. It also
  lifts the 15-minute lock after too many wrong tries. Run it on the server
  computer, in the project folder.
#>
param([string] $Email = 'owner@greenbuffet.zm')
$root = Split-Path -Parent $PSScriptRoot
$backend = Join-Path $root 'backend'
$py = Join-Path $backend '.venv\Scripts\python.exe'
Push-Location $backend
try { & $py -m app.reset_owner $Email } finally { Pop-Location }
