# One-off: commit current changes as "keep going (digi)" and push
$ErrorActionPreference = "Stop"
$root = (Get-Item $PSScriptRoot).Parent.FullName
Set-Location $root

git add mortal_agent/agent_core/llm_router.py mortal_agent/agent_core/mortal_agent.py
$status = git status --short
if (-not $status) {
    Write-Host "No changes to commit (files may already be committed)."
} else {
    git commit -m "keep going (digi)"
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    Write-Host "Committed."
}
git push origin HEAD
if ($LASTEXITCODE -ne 0) {
    Write-Host "Push failed. Check remote and auth."
    exit $LASTEXITCODE
}
Write-Host "Done. Pushed to GitHub."
