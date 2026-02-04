# Run this AFTER creating an empty repo at https://github.com/new (e.g. name: agent)
# Usage: .\scripts\push_to_github.ps1
#    Or: .\scripts\push_to_github.ps1 -RepoUrl "https://github.com/YOUR_USERNAME/agent.git"

param(
    [string] $RepoUrl = ""
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot\..

if (-not $RepoUrl) {
    $username = git config user.name
    if (-not $username) { $username = "YOUR_USERNAME" }
    $RepoUrl = "https://github.com/$username/agent.git"
    Write-Host "Using repo: $RepoUrl"
    Write-Host "(To use a different URL: .\scripts\push_to_github.ps1 -RepoUrl 'https://github.com/User/Repo.git')"
}

git remote remove origin 2>$null
git remote add origin $RepoUrl
git push -u origin master

Write-Host "Done. This folder is now tied to $RepoUrl"
