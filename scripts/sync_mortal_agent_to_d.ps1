# Sync mortal_agent (canon, cli, ensure_constitution) to D: so the same entity works there.
# Run from repo root (agent folder):  .\scripts\sync_mortal_agent_to_d.ps1
# Then on D: run:  cd D:\Desktop\agent\mortal_agent ; python -m cli.main run

$ErrorActionPreference = "Stop"
$SourceRoot = $PSScriptRoot | Split-Path -Parent
$TargetRoot = "D:\Desktop\agent"
if (-not (Test-Path "D:\")) { Write-Warning "D: not found."; exit 1 }

$ma = "mortal_agent"
$src = Join-Path $SourceRoot $ma
$dst = Join-Path $TargetRoot $ma
if (-not (Test-Path $dst)) { New-Item -ItemType Directory -Force -Path $dst | Out-Null }

Write-Host "Syncing $ma to $TargetRoot (same entity)..." -ForegroundColor Cyan
robocopy (Join-Path $src "agent_core") (Join-Path $dst "agent_core") canon.py /NFL /NDL /NJH /NJS /NC /NS /NP | Out-Null
robocopy (Join-Path $src "cli") (Join-Path $dst "cli") main.py /NFL /NDL /NJH /NJS /NC /NS /NP | Out-Null
Copy-Item (Join-Path $src "ensure_constitution.py") (Join-Path $dst "ensure_constitution.py") -Force
if (Test-Path (Join-Path $src "ensure_constitution.ps1")) { Copy-Item (Join-Path $src "ensure_constitution.ps1") (Join-Path $dst "ensure_constitution.ps1") -Force }
$canonDst = Join-Path $dst "config\canon"
New-Item -ItemType Directory -Force -Path $canonDst | Out-Null
if (Test-Path (Join-Path $src "config\canon\constitution.yaml")) {
    Copy-Item (Join-Path $src "config\canon\constitution.yaml") $canonDst -Force
}

Write-Host "Done. On D: run:" -ForegroundColor Green
Write-Host "  cd $dst" -ForegroundColor White
Write-Host "  python -m cli.main run" -ForegroundColor White
