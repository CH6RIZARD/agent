# Commit and push the "agent can post to GitHub issues when he has a reason" behavior.
# Run from repo root: .\scripts\commit_and_push_github_posting.ps1
# Ensures: has_github_token(), capability check, GITHUB_POST without deploy, and docs stay as-is on origin.

$ErrorActionPreference = "Stop"
$root = (Get-Item $PSScriptRoot).Parent.FullName
Set-Location $root

$files = @(
    "mortal_agent/patches/github_integration.py",
    "mortal_agent/patches/__init__.py",
    "mortal_agent/agent_core/capabilities.py",
    "mortal_agent/.env.example",
    "mortal_agent/docs/AUTONOMY_PATCHES.md"
)

$existing = @()
foreach ($f in $files) {
    if (Test-Path $f) { $existing += $f }
}
if ($existing.Count -eq 0) {
    Write-Host "None of the expected files found."
    exit 1
}

git add $existing
$status = git status --short
if (-not $status) {
    Write-Host "No changes to commit (already committed)."
} else {
    git commit -m "Agent can post to GitHub issues when he has a reason (internal or external)

- has_github_token() + capability check use git credential or GITHUB_TOKEN/MORTAL_GITHUB_TOKEN
- GITHUB_POST allowed without MORTAL_DEPLOY; doc invariant: keep this when pushing"
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

git push origin main
if ($LASTEXITCODE -ne 0) {
    Write-Host "Push failed. Fix remote/auth and run again."
    exit $LASTEXITCODE
}
Write-Host "Done. GitHub posting behavior is committed and pushed to origin/main."
