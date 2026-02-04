# Rename GitHub repo to embodied-mortal-agent and set description (one-time).
# Requires: GitHub Personal Access Token with repo scope.
#
# 1. Create a token: https://github.com/settings/tokens (classic, scope: repo)
# 2. Run: $env:GITHUB_TOKEN = "ghp_xxxx"; .\scripts\rename_repo_and_description.ps1
#    Or:   .\scripts\rename_repo_and_description.ps1 -Token "ghp_xxxx"

param(
    [string] $Token = $env:GITHUB_TOKEN,
    [string] $Owner = "CH6RIZARD",
    [string] $CurrentRepo = "agent",
    [string] $NewName = "embodied-mortal-agent",
    [string] $Description = "Embodied agent whose identity exists only while it's running. Death is terminal; restart is a new being."
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot\..

if (-not $Token) {
    Write-Host "Usage: Set GITHUB_TOKEN or pass -Token, then run this script."
    Write-Host "  Example: `$env:GITHUB_TOKEN = 'ghp_xxx'; .\scripts\rename_repo_and_description.ps1"
    exit 1
}

$headers = @{
    "Authorization" = "Bearer $Token"
    "Accept"        = "application/vnd.github+json"
    "X-GitHub-Api-Version" = "2022-11-28"
}
$body = @{
    name        = $NewName
    description = $Description
} | ConvertTo-Json

$uri = "https://api.github.com/repos/$Owner/$CurrentRepo"
Write-Host "PATCH $uri (name=$NewName, description=...)"
try {
    $response = Invoke-RestMethod -Uri $uri -Method Patch -Headers $headers -Body $body -ContentType "application/json"
    Write-Host "Done. Repo is now: $($response.html_url)"
    Write-Host "Description: $($response.description)"
} catch {
    Write-Host "Error: $_"
    exit 1
}
