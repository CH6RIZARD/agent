# Run 20 sessions to verify autonomous output is not hardcoded (prompt-only planner fix).
$ErrorActionPreference = "Continue"
$base = "d:\agent\mortal_agent"
$inputs = Join-Path $base "reports\run_20\inputs"
$logs = Join-Path $base "reports\run_20\logs"
Set-Location $base
foreach ($i in 1..20) {
    $num = "{0:D2}" -f $i
    $inFile = Join-Path $inputs "session_$num.txt"
    $logFile = Join-Path $logs "session_$num.log"
    if (-not (Test-Path $inFile)) { Write-Host "Missing $inFile"; continue }
    Write-Host "Run $num..."
    Get-Content $inFile -Encoding UTF8 | python -m cli.main run 2>&1 | Out-File -FilePath $logFile -Encoding utf8
    Write-Host "  -> $logFile"
}
Write-Host "Done. Check logs for autonomous lines (should be context-specific, not stock mottos)."
