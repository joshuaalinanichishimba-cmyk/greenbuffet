<#
    Brings an installed copy up to the latest stage.

    Run it after extracting a newer package over the project folder. It leaves
    backend\.env, the database and the backups alone, and only refreshes the
    parts that a new stage can change: Python packages, front-end packages and
    the permission and settings rows.

    Usage:
        cd "D:\The Green Buffet"
        .\scripts\update.ps1
#>
[CmdletBinding()]
param([switch] $SkipBackup)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'   # the web-request progress bar leaves blank lines in pasted output
$root = Split-Path -Parent $PSScriptRoot
$backend = Join-Path $root 'backend'
$frontend = Join-Path $root 'frontend'

function Step($text) { Write-Host ''; Write-Host ('  == ' + $text) -ForegroundColor Green }
function Ok($text) { Write-Host ('     ' + $text) -ForegroundColor DarkGray }
function Warn($text) { Write-Host ('     ' + $text) -ForegroundColor Yellow }

Write-Host ''
Write-Host '  The Green Buffet - update' -ForegroundColor Green
Write-Host ('  Project: ' + $root) -ForegroundColor DarkGray

if (-not (Test-Path (Join-Path $backend '.env'))) {
    throw 'No backend\.env found. This copy has not been set up yet - run .\scripts\setup.ps1 instead.'
}

$py = Join-Path $backend '.venv\Scripts\python.exe'
if (-not (Test-Path $py)) {
    throw 'No virtual environment found. Run .\scripts\setup.ps1 instead.'
}

Step 'Stopping anything still running'
# Two ways a copy can still be running: a Python from this project's own
# environment, or anything at all listening on the system's two ports. The
# second matters because Node.js lives in Program Files, not in this folder,
# so an old development window would otherwise survive the update and keep
# answering on the port with yesterday's screens.
# The startup task first, so Windows does not still count it as running and
# quietly ignore the request to start it again at the end.
if (Get-ScheduledTask -TaskName 'Green Buffet' -ErrorAction SilentlyContinue) {
    Stop-ScheduledTask -TaskName 'Green Buffet' -ErrorAction SilentlyContinue
}
$stopped = @{}
Get-Process -Name python, pythonw -ErrorAction SilentlyContinue |
    Where-Object { $_.Path -and $_.Path.StartsWith($root) } |
    ForEach-Object { $stopped[$_.Id] = $_.ProcessName }
foreach ($port in 8000, 5173) {
    Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue |
        ForEach-Object {
            $p = Get-Process -Id $_.OwningProcess -ErrorAction SilentlyContinue
            if ($p) { $stopped[$p.Id] = "$($p.ProcessName) on port $port" }
        }
}
if ($stopped.Count) {
    foreach ($id in $stopped.Keys) {
        Stop-Process -Id $id -Force -ErrorAction SilentlyContinue
        Ok ('stopped {0} ({1})' -f $stopped[$id], $id)
    }
} else {
    Ok 'nothing was running'
}

Step 'Backing up the database first'
# Every update starts with a backup, so nothing an update does can lose data.
# Pass -SkipBackup only if a backup was taken a moment ago.
if (-not $SkipBackup) {
    & (Join-Path $PSScriptRoot 'backup.ps1') -Label 'before-update' | Out-Host
    if ($LASTEXITCODE -and $LASTEXITCODE -ne 0) { throw 'The backup failed, so the update has stopped. Nothing was changed.' }
    Ok 'backup taken'
} else {
    Ok 'skipped (-SkipBackup)'
}

Step 'Backend packages'
Push-Location $backend
try {
    & $py -m pip install --quiet --upgrade pip
    & $py -m pip install --quiet -r requirements.txt
    if ($LASTEXITCODE -ne 0) { throw 'Installing the backend packages failed.' }
    Ok 'up to date'

    Step 'Database'
    # Creates any new tables and adds new permissions, roles and settings.
    # Existing rows are untouched.
    & $py -m app.seed
    if ($LASTEXITCODE -ne 0) { throw 'The database update failed.' }

    # Loads the starting menu, but only if the menu is still empty.
    & $py -m app.seed_menu
} finally {
    Pop-Location
}

Step 'Frontend packages'
Push-Location $frontend
try {
    npm install --silent
    if ($LASTEXITCODE -ne 0) { Warn 'npm reported a problem; check the output above.' }
    else { Ok 'up to date' }
} finally {
    Pop-Location
}

Write-Host ''
Write-Host '  Update finished.' -ForegroundColor Green

# If the system was installed to run by itself, this script has just stopped
# it (it stops every python). Rebuild the front end and start it again, so the
# till is working when this finishes. Nobody should have to remember that.
$installed = Get-ScheduledTask -TaskName 'Green Buffet' -ErrorAction SilentlyContinue
if ($installed) {
    Write-Host '  This computer runs The Green Buffet by itself, so rebuilding and restarting it.' -ForegroundColor DarkGray
    Push-Location $frontend
    try { npm run build --silent } finally { Pop-Location }
    Start-ScheduledTask -TaskName 'Green Buffet'
    Write-Host ''
    Write-Host '  Starting it up. This takes up to a minute; wait for "Running again".' -ForegroundColor DarkGray
    $ready = $false
    foreach ($i in 1..60) {
        Start-Sleep -Seconds 1
        try {
            if ((Invoke-RestMethod 'http://localhost:8000/api/v1/health' -TimeoutSec 2).status -eq 'ok') { $ready = $true; break }
        } catch { }
    }
    Write-Host ''
    if ($ready) { Write-Host '  Running again at http://localhost:8000' -ForegroundColor Green }
    else {
        # Say why, here, rather than leaving a blank screen in the browser.
        $info = Get-ScheduledTaskInfo -TaskName 'Green Buffet' -ErrorAction SilentlyContinue
        $state = (Get-ScheduledTask -TaskName 'Green Buffet').State
        Write-Host '  It has not answered after a minute.' -ForegroundColor Yellow
        Write-Host ("  Startup task: {0}, last result {1}" -f $state, $info.LastTaskResult) -ForegroundColor Yellow
        $log = Join-Path $root 'logs\server.log'
        if (Test-Path $log) {
            Write-Host '  Last lines of logs\server.log:' -ForegroundColor Yellow
            Get-Content $log -Tail 12 | ForEach-Object { Write-Host ('    ' + $_) -ForegroundColor DarkGray }
        }
        Write-Host '  To start it in this window instead:  .\scripts\serve.ps1 -SkipBuild' -ForegroundColor Yellow
    }
    Write-Host '  Do not run run.ps1 on this computer: that is for development and uses the same port.' -ForegroundColor DarkGray
} else {
    Write-Host '  Start it again with:  .\scripts\run.ps1' -ForegroundColor DarkGray
}
Write-Host ''
