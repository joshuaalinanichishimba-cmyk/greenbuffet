# Puts the system's code on GitHub, on its own branch.
#
#   .\scripts\push-to-github.ps1
#   .\scripts\push-to-github.ps1 -Repo https://github.com/you/another-repo -Branch system
#
# Needs Git for Windows (https://git-scm.com/download/win). The first push
# opens a browser window to sign in to GitHub.
#
# What is never sent: .env (database password and secrets), backups, logs,
# .venv, node_modules and dist. The .gitignore file lists them.
#
# The branch is "system", so the demo website on "main" is not touched.
param(
    [string] $Repo = 'https://github.com/joshuaalinanichishimba-cmyk/greenbuffet.git',
    [string] $Branch = 'system',
    [string] $Message = ''
)
# Git writes ordinary progress to stderr, which Windows PowerShell treats as an
# error under 'Stop'. Each git step is checked with $LASTEXITCODE instead.
$ErrorActionPreference = 'Continue'
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    Write-Host 'Git is not installed. Install Git for Windows from https://git-scm.com/download/win, then run this again.' -ForegroundColor Red
    exit 1
}

if (-not (Test-Path (Join-Path $root '.git'))) {
    Write-Host '== Making the Git repository in this folder'
    git init -q
    git checkout -q -b $Branch
}

if (-not (git config user.name)) {
    $name = Read-Host 'Your name for the history (for example Joshua Chishimba)'
    git config user.name $name
}
if (-not (git config user.email)) {
    $mail = Read-Host 'Your GitHub email'
    git config user.email $mail
}

# symbolic-ref works on a brand-new repository with no saves yet; rev-parse does not.
$current = (git symbolic-ref --short HEAD 2>&1) | Out-String
if ($current.Trim() -ne $Branch) {
    git checkout -q -B $Branch 2>&1 | Out-Null
}

git add -A 2>&1 | Out-Null
if ($LASTEXITCODE -ne 0) {
    Write-Host 'Git could not read the project files. Is a folder inside it its own Git repository?' -ForegroundColor Red
    exit 1
}

# Stop before anything secret goes out, whatever .gitignore says.
$bad = git diff --cached --name-only | Where-Object {
    $_ -match '(^|/)\.env$' -or $_ -match '\.dump$' -or $_ -match '^(backups|logs)/' -or $_ -match '(^|/)(\.venv|node_modules)/'
}
if ($bad) {
    Write-Host 'These files must not go to GitHub, so nothing was sent:' -ForegroundColor Red
    $bad | ForEach-Object { Write-Host "  $_" }
    git reset -q
    exit 1
}

if (git diff --cached --name-only) {
    if (-not $Message) { $Message = "Update $(Get-Date -Format 'yyyy-MM-dd HH:mm')" }
    git commit -q -m $Message
    if ($LASTEXITCODE -ne 0) { Write-Host 'Git could not save the changes.' -ForegroundColor Red; exit 1 }
    Write-Host "== Saved: $Message"
} else {
    Write-Host '== Nothing has changed since the last save.'
}

$remote = @(git remote) -contains 'origin'
if ($remote) { git remote set-url origin $Repo } else { git remote add origin $Repo }

Write-Host "== Sending to $Repo, branch $Branch"
git push -u origin $Branch
if ($LASTEXITCODE -ne 0) {
    Write-Host 'The push did not go through. Check you are signed in to the GitHub account that owns the repository.' -ForegroundColor Red
    exit 1
}
Write-Host "Done. The code is on GitHub, branch $Branch." -ForegroundColor Green
