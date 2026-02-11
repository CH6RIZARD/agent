# Commit and push the GitHub-post invariant so the repo keeps this behavior.
# Run from repo root: .\mortal_agent\scripts\commit_and_push_github_post.ps1
# Or from mortal_agent: .\scripts\commit_and_push_github_post.ps1

$root = (Get-Item $PSScriptRoot).Parent.Parent.FullName
Set-Location $root

git add mortal_agent/patches/github_integration.py mortal_agent/patches/__init__.py mortal_agent/agent_core/capabilities.py mortal_agent/.env.example mortal_agent/docs/AUTONOMY_PATCHES.md
git status
git commit -m "Invariant: agent can post to GitHub issues when he has a reason (no MORTAL_DEPLOY); capability uses has_github_token()"
git push
