# Run 35 soak sessions: pipe each input file to CLI and save logs (UTF-8).
$ErrorActionPreference = "Continue"
$base = "d:\agent\mortal_agent"
$inputs = Join-Path $base "reports\soak_35\inputs"
$logs = Join-Path $base "reports\soak_35\logs"
Set-Location $base
foreach ($i in 1..35) {
    $num = "{0:D2}" -f $i
    $inFile = Join-Path $inputs "session_$num.txt"
    $logFile = Join-Path $logs "session_$num.log"
    Write-Host "Running session $num..."
    Get-Content $inFile -Encoding UTF8 | python -m cli.main run 2>&1 | Out-File -FilePath $logFile -Encoding utf8
    Write-Host "  -> $logFile"
}
