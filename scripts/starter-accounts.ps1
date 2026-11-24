<#
  Makes one account for each kind of staff that does not have one yet:
  admin@, manager@, accountant@, cashier@, kitchen@ and inventory@greenbuffet.zm.

  .\scripts\starter-accounts.ps1

  Prints each new account's temporary password once. Rename them to real
  people under Staff & roles. Running it again changes nothing.
#>
$root = Split-Path -Parent $PSScriptRoot
$backend = Join-Path $root 'backend'
$py = Join-Path $backend '.venv\Scripts\python.exe'
Push-Location $backend
try { & $py -m app.starter_accounts } finally { Pop-Location }
