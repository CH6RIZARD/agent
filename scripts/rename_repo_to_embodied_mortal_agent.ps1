# Rename GitHub repo to embodied-mortal-agent and set description.
# Requires: $env:GITHUB_TOKEN with repo scope (or pass -Token).
# Run from repo root: .\scripts\rename_repo_to_embodied_mortal_agent.ps1

param([string]$Token = $env:GITHUB_TOKEN)

$ErrorActionPreference = "Stop"
$owner = "CH6RIZARD"
$repo = "agent"
$newName = "embodied-mortal-agent"
$description = "Embodied agent whose identity exists only while it's running. Death is terminal; restart is a new being."

if (-not $Token) {
    Write-Host "No GITHUB_TOKEN. Set it or pass -Token."
    Write-Host "Opening repo Settings so you can rename and set description manually..."
    Start-Process "https://github.com/$owner/$repo/settings"
    exit 1
}

$uri = "https://api.github.com/repos/$owner/$repo"
$body = @{ name = $newName; description = $description } | ConvertTo-Json
$headers = @{
    "Authorization" = "Bearer $Token"
    "Accept"        = "application/vnd.github+json"
    "X-GitHub-Api-Version" = "2022-11-28"
    "Content-Type"  = "application/json"
}

Write-Host "PATCH $uri -> name=$newName, description=..."
$resp = Invoke-RestMethod -Uri $uri -Method PATCH -Headers $headers -Body $body
Write-Host "Renamed to: $($resp.full_name). Description: $($resp.description)"

# Update local remote and push
Set-Location (Resolve-Path "$PSScriptRoot\..")
git remote set-url origin "https://github.com/$owner/$newName.git"
git push -u origin main
Write-Host "Remote updated and pushed."
