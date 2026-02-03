# Move this workspace entirely from C: to D:. Copy to D: then remove from C:.
# Run from repo root (agent folder):  .\scripts\move_workspace_to_d.ps1
# After it finishes, close Cursor and run the remove command it prints.

$ErrorActionPreference = "Stop"
$SourceRoot = $PSScriptRoot | Split-Path -Parent
$TargetRoot = "D:\agent"

if (-not (Test-Path "D:\")) {
    Write-Warning "D: drive not found."
    exit 1
}

Write-Host "Copying entire workspace to $TargetRoot ..." -ForegroundColor Cyan
New-Item -ItemType Directory -Force -Path $TargetRoot | Out-Null
$r = robocopy $SourceRoot $TargetRoot /E /XD .cursor node_modules __pycache__ .git .venv venv /XF *.pyc /NFL /NDL /NJH /NJS /NC /NS /NP
if ($r -ge 8) { exit $r }

# Ensure constitution on D:
$canonDir = Join-Path $TargetRoot "mortal_agent\config\canon"
New-Item -ItemType Directory -Force -Path $canonDir | Out-Null
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
}

Write-Host ""
Write-Host "Workspace is on D: at  $TargetRoot" -ForegroundColor Green
Write-Host ""
Write-Host "To REMOVE from C: (do this after closing Cursor and opening D:\agent):" -ForegroundColor Yellow
Write-Host "  Remove-Item -Recurse -Force '$SourceRoot'" -ForegroundColor White
Write-Host ""
Write-Host "Next: Open D:\agent in Cursor, then run the remove command above in PowerShell." -ForegroundColor Cyan
