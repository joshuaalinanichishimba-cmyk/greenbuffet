<#
  Makes the menu match the printed menu (The_Green_Buffet_Menu_final.pdf):
  every section, item, choice and price on it.

  .\scripts\load-menu.ps1

  Nothing is deleted. Items that are not on the printed menu are switched
  off, so old receipts and reports keep their names. Run it on the server
  computer, in the project folder, then check the Menu screen.
#>
$root = Split-Path -Parent $PSScriptRoot
$backend = Join-Path $root 'backend'
$py = Join-Path $backend '.venv\Scripts\python.exe'
Push-Location $backend
try { & $py -m app.seed_menu --replace } finally { Pop-Location }
