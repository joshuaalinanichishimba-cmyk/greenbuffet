<#
    The Green Buffet - prerequisite check
    Run:  .\scripts\check.ps1
    Reports what is installed and what is missing. Changes nothing.
#>
$ErrorActionPreference = 'Continue'

Write-Host ''
Write-Host '  The Green Buffet - environment check' -ForegroundColor Green
Write-Host '  ------------------------------------' -ForegroundColor DarkGray

$os  = Get-CimInstance Win32_OperatingSystem
$cs  = Get-CimInstance Win32_ComputerSystem
$cpu = Get-CimInstance Win32_Processor | Select-Object -First 1
$ram = [math]::Round($cs.TotalPhysicalMemory / 1GB, 1)
$free = [math]::Round((Get-PSDrive C).Free / 1GB, 1)

Write-Host ''
Write-Host ('  OS        : ' + $os.Caption + ' (' + $os.Version + ')')
Write-Host ('  CPU       : ' + $cpu.Name.Trim())
Write-Host ('  RAM       : ' + $ram + ' GB')
Write-Host ('  Free on C : ' + $free + ' GB')
Write-Host ('  PowerShell: ' + $PSVersionTable.PSVersion)

if ($ram -lt 8) {
    Write-Host '  NOTE: under 8 GB of RAM. Run PostgreSQL in Docker or use a hosted dev database.' -ForegroundColor Yellow
}

$tools = [ordered]@{
    'git'    = 'Git.Git'
    'python' = 'Python.Python.3.12'
    'node'   = 'OpenJS.NodeJS.LTS'
    'npm'    = ''
    'psql'   = 'PostgreSQL.PostgreSQL.16'
    'code'   = 'Microsoft.VisualStudioCode'
}

Write-Host ''
Write-Host '  Tools' -ForegroundColor Green
$missing = @()
foreach ($name in $tools.Keys) {
    $cmd = Get-Command $name -ErrorAction SilentlyContinue
    if ($cmd) {
        $version = (& $name --version 2>&1 | Select-Object -First 1)
        Write-Host ('    [ok]      {0,-8} {1}' -f $name, $version) -ForegroundColor Green
    } else {
        Write-Host ('    [missing] {0}' -f $name) -ForegroundColor Yellow
        if ($tools[$name]) { $missing += $tools[$name] }
    }
}

# PostgreSQL often installs without adding psql to PATH.
if (-not (Get-Command psql -ErrorAction SilentlyContinue)) {
    $pg = Get-ChildItem 'C:\Program Files\PostgreSQL' -Directory -ErrorAction SilentlyContinue |
          Sort-Object Name -Descending | Select-Object -First 1
    if ($pg) {
        Write-Host ('    note: PostgreSQL found at ' + $pg.FullName + ' but psql is not on PATH.') -ForegroundColor Yellow
        Write-Host '          setup.ps1 adds it automatically for its own session.' -ForegroundColor DarkGray
        $missing = $missing | Where-Object { $_ -ne 'PostgreSQL.PostgreSQL.16' }
    }
}

Write-Host ''
if ($missing.Count -gt 0) {
    Write-Host '  Install what is missing, then open a NEW PowerShell window:' -ForegroundColor Yellow
    foreach ($id in ($missing | Select-Object -Unique)) {
        Write-Host ('    winget install --id ' + $id + ' -e') -ForegroundColor Cyan
    }
} else {
    Write-Host '  Everything needed is installed. Next: .\scripts\setup.ps1' -ForegroundColor Green
}
Write-Host ''
