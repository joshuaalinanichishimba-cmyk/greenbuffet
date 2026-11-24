<#
  Test mode for the sign-in screen: tap a card, press Enter.

  .\scripts\test-sign-in.ps1        every account gets the test password, and
                                    the sign-in screen fills it in
  .\scripts\test-sign-in.ps1 -Off   back to typing passwords

  For trying the system out only. It refuses on a computer set to
  production, and the server never fills passwords in production.
#>
param([switch] $Off)
$root = Split-Path -Parent $PSScriptRoot
$backend = Join-Path $root 'backend'
$py = Join-Path $backend '.venv\Scripts\python.exe'
Push-Location $backend
try {
    if ($Off) { & $py -m app.test_sign_in --off } else { & $py -m app.test_sign_in }
} finally { Pop-Location }
