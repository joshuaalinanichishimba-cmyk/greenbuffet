<#
    What is running, and if The Green Buffet is not answering, why.

        .\scripts\status.ps1

    It answers four questions, in the order you would ask them:
      1. Is anything listening on port 8000, and what is it?
      2. Does it answer as The Green Buffet, and which version?
      3. What does the installed task say about its last start?
      4. What were the last lines the server wrote before it stopped?
#>
[CmdletBinding()]
param([int] $Port = 8000)

$root = Split-Path -Parent $PSScriptRoot
$log = Join-Path $root 'logs\server.log'

function Head($text) { Write-Host ''; Write-Host ('  == ' + $text) -ForegroundColor Green }
function Line($text, $colour = 'Gray') { Write-Host ('     ' + $text) -ForegroundColor $colour }

Write-Host ''
Write-Host '  The Green Buffet - status' -ForegroundColor Green

# ---- 1. who holds the port -------------------------------------------------
Head "Port $Port"
$listeners = @(Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue)
if (-not $listeners.Count) {
    Line 'Nothing is listening. The system is not running.' Yellow
} else {
    foreach ($l in $listeners) {
        $p = Get-Process -Id $l.OwningProcess -ErrorAction SilentlyContinue
        $what = if ($p) { "$($p.ProcessName) (process $($p.Id))" } else { "process $($l.OwningProcess)" }
        Line ("{0} on {1}" -f $what, $l.LocalAddress)
        if ($p -and $p.Path) { Line ('  ' + $p.Path) DarkGray }
    }
    $owners = @($listeners | Select-Object -ExpandProperty OwningProcess -Unique)
    if ($owners.Count -gt 1) {
        Line 'More than one program is listening. Screens will talk to whichever answers' Red
        Line 'first and some will fail. Stop them all and start one:' Red
        Line '  Get-Process python, node -ErrorAction SilentlyContinue | Stop-Process -Force' Cyan
        Line "  Start-ScheduledTask -TaskName 'Green Buffet'" Cyan
    }
}

# ---- 2. does it answer as us ---------------------------------------------------
Head 'Answering'
try {
    $health = Invoke-RestMethod "http://localhost:$Port/api/v1/health" -TimeoutSec 4
    Line ("Yes: {0}, database {1}" -f $health.business, $health.database) Green
    try {
        $null = Invoke-WebRequest "http://localhost:$Port/api/v1/dashboard/service" -UseBasicParsing -TimeoutSec 4
        Line 'Current version (stage 17 or later).' Green
    } catch {
        $code = $_.Exception.Response.StatusCode.value__
        if ($code -eq 401 -or $code -eq 403) {
            Line 'Current version (stage 17 or later).' Green
        } else {
            Line 'An OLDER version is answering. Something from before the last update is still running.' Red
            Line 'Run .\scripts\update.ps1 again; it stops every old copy first.' Red
        }
    }
} catch {
    # A 503 still carries a body that says what is wrong.
    $reply = $_.ErrorDetails.Message
    if ($reply -and $reply -match '"reason":\s*"password"') {
        Line 'The server is running and PostgreSQL is up, but it refuses the password in backend\.env.' Red
        Line 'Fix it with:  .\scripts\fix-database.ps1' Cyan
    } elseif ($reply -and $reply -match 'unreachable') {
        Line 'The server is running, but it cannot reach the database.' Red
        Line 'Start PostgreSQL: open services.msc, find postgresql, and press Start.' Red
        Line '  or, as Administrator:  Get-Service postgresql* | Start-Service' Cyan
    } else {
        Line 'No answer at all.' Yellow
    }
}

# ---- 3. the installed task -----------------------------------------------------
Head 'Starts by itself'
$task = Get-ScheduledTask -TaskName 'Green Buffet' -ErrorAction SilentlyContinue
if (-not $task) {
    Line 'Not installed. To make it start with the computer: .\scripts\install-service.ps1 (as Administrator)' Yellow
} else {
    $info = Get-ScheduledTaskInfo -TaskName 'Green Buffet'
    $result = switch ($info.LastTaskResult) {
        0 { 'finished normally' }
        267009 { 'running now' }
        267011 { 'has never run' }
        default { "failed with code $($info.LastTaskResult)" }
    }
    Line ("Installed. State: {0}. Last start: {1}, {2}." -f $task.State, $info.LastRunTime, $result)
}

# ---- 4. what the server last said ----------------------------------------------
Head 'Last lines of the server log'
if (Test-Path $log) {
    Get-Content $log -Tail 12 | ForEach-Object {
        $colour = if ($_ -match ' ERROR ') { 'Red' } elseif ($_ -match ' WARNING ') { 'Yellow' } else { 'DarkGray' }
        Line $_ $colour
    }
    Line ''
    Line ("The whole log: " + $log) DarkGray
} else {
    Line 'No log yet. It is written from stage 18 onwards, the first time the server starts.' DarkGray
}
Write-Host ''
