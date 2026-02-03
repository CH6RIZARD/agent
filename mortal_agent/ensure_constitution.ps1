# Creates config/canon/constitution.yaml if missing. Run from mortal_agent folder:
#   cd D:\Desktop\agent\mortal_agent
#   .\ensure_constitution.ps1

$canonDir = Join-Path $PSScriptRoot "config\canon"
$file = Join-Path $canonDir "constitution.yaml"
if (Test-Path $file) {
    Write-Host "Already exists: $file"
    exit 0
}
New-Item -ItemType Directory -Force -Path $canonDir | Out-Null
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
"@ | Set-Content -Path $file -Encoding UTF8
Write-Host "Created: $file"
Write-Host "Run: python -m cli.main run"
