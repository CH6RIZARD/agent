# Set up this workspace on the D: drive (data disk) instead of C:
# Run from repo root: .\scripts\setup_workspace_on_d.ps1

$ErrorActionPreference = "Stop"
$TargetRoot = "D:\agent"

$SourceRoot = $PSScriptRoot | Split-Path -Parent
if (-not (Test-Path $SourceRoot)) { throw "Cannot find repo root: $SourceRoot" }

if (-not (Test-Path "D:\")) {
    Write-Warning "D: drive not found. Create D:\ or change `$TargetRoot in this script."
    exit 1
}

Write-Host "Copying workspace to $TargetRoot (excluding node_modules, __pycache__, .git, .cursor)..." -ForegroundColor Cyan
New-Item -ItemType Directory -Force -Path $TargetRoot | Out-Null
$r = robocopy $SourceRoot $TargetRoot /E /XD node_modules __pycache__ .git .cursor .venv venv /XF *.pyc /NFL /NDL /NJH /NJS /NC /NS /NP
if ($r -ge 8) { exit $r }

# Ensure mortal_agent config exists on D:
$canonDir = Join-Path $TargetRoot "mortal_agent\config\canon"
if (-not (Test-Path $canonDir)) {
    New-Item -ItemType Directory -Force -Path $canonDir | Out-Null
}
$constitution = Join-Path $canonDir "constitution.yaml"
if (-not (Test-Path $constitution)) {
    @"
# Canon / Constitution (NON-NEGOTIABLE)
version: "1.0"
type: canon

forbidden_phrases:
  - "i remember"
  - "last time"
  - "as i said before"
  - "continuing from"
  - "same as before"
  - "my memory"
  - "i have always"
  - "i never forget"
  - "immortal"
  - "resurrection"
  - "previous instance"
  - "same agent"
  - "continued from"

required_framing:
  - "system"
  - "collective"
  - "whole"
  - "context"
  - "constraint"

systems_before_individuals: true
max_framing_injection: 32
"@ | Set-Content -Path $constitution -Encoding UTF8
    Write-Host "Created $constitution on D:"
}

Write-Host ""
Write-Host "Workspace is ready on D: at  $TargetRoot" -ForegroundColor Green
Write-Host "Open in Cursor:  File > Open Folder > $TargetRoot" -ForegroundColor Yellow
Write-Host "Then run:  cd mortal_agent ; python -m cli.main run" -ForegroundColor Yellow

# Optional: open Cursor with D:\agent
$openCursor = $args -contains "--open"
if ($openCursor) {
    $cursor = "cursor"
    if (Get-Command $cursor -ErrorAction SilentlyContinue) {
        & $cursor $TargetRoot
    } else {
        Write-Host "Run: cursor $TargetRoot" -ForegroundColor Yellow
    }
}
