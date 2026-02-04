# Rename repo to embodied-mortal-agent and set description via GitHub API.
# Requires: $env:GITHUB_TOKEN with repo scope (or pass -Token)
# Run from repo root: .\scripts\github-rename-and-description.ps1

param(
    [string] $Token = $env:GITHUB_TOKEN,
    [string] $Owner = "CH6RIZARD",
    [string] $CurrentRepo = "agent",
    [string] $NewName = "embodied-mortal-agent",
    [string] $Description = "Embodied agent whose identity exists only while it's running. Death is terminal; restart is a new being."
)

$ErrorActionPreference = "Stop"
$api = "https://api.github.com/repos/$Owner/$CurrentRepo"
$headers = @{
    "Accept" = "application/vnd.github+json"
    "X-GitHub-Api-Version" = "2022-11-28"
}
if ($Token) { $headers["Authorization"] = "Bearer $Token" }

if (-not $Token) {
    Write-Host "No GITHUB_TOKEN set. Opening repo Settings in browser so you can rename and set description manually."
    Start-Process "https://github.com/$Owner/$CurrentRepo/settings"
    Write-Host "  -> Repository name: change to '$NewName'"
    Write-Host "  -> Description (in About): $Description"
    exit 0
}

$body = @{
    name = $NewName
    description = $Description
} | ConvertTo-Json

try {
    $r = Invoke-RestMethod -Uri $api -Method PATCH -Headers $headers -Body $body -ContentType "application/json"
    Write-Host "OK: Renamed to $($r.name), description set."
} catch {
    Write-Host "API error: $_"
    exit 1
}
