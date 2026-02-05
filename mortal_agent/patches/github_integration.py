"""
GitHub API integration: create issues, add comments, leave persistent traces on GitHub.

Uses GITHUB_TOKEN or MORTAL_GITHUB_TOKEN from environment. No token = executed: False.
Agent can post issues and comments when deploy-enabled (MORTAL_DEPLOY=1) and token is set.
When repo is not provided, uses the same GitHub repo as this workspace (git origin or MORTAL_GITHUB_REPO)
so users see agent posts in the repo's Issues tab (same place they see the README).
Every post is signed with an identity marker so it is clear the post is from the Mortal Agent.
"""

import os
import re
import json
import subprocess
import urllib.request
import urllib.error
from pathlib import Path
from typing import Dict, Any, Optional

# Identity label shown on every GitHub post so users can see it's from the agent
GITHUB_AGENT_IDENTITY_LABEL = "Mortal Agent"


def _sign_body(body_text: str, instance_id: str, max_total: int = 65536) -> str:
    """
    Append a signed identity footer to the post body so users can see the post is from the agent.
    Format: two newlines, horizontal rule, then "Posted by Mortal Agent · instance_id: <id>"
    Truncates body so the full signed message fits within max_total (GitHub limit).
    """
    signature = (
        f"\n\n---\n\n"
        f"*Posted by **{GITHUB_AGENT_IDENTITY_LABEL}** · `instance_id`: `{instance_id}`*"
    )
    max_body = max(0, max_total - len(signature))
    truncated = body_text.rstrip()[:max_body]
    return truncated + signature


def _get_token() -> str:
    return (os.environ.get("MORTAL_GITHUB_TOKEN") or os.environ.get("GITHUB_TOKEN") or "").strip()


def _get_workspace_repo() -> Optional[str]:
    """
    Resolve the GitHub repo (owner/repo) for this workspace so agent posts go to the same
    repo users see (README, Issues). Checks: MORTAL_GITHUB_REPO, GITHUB_REPO, then git origin.
    """
    repo = (os.environ.get("MORTAL_GITHUB_REPO") or os.environ.get("GITHUB_REPO") or "").strip()
    if repo and "/" in repo:
        return repo.split("/", 1)[0].strip() + "/" + repo.split("/", 1)[1].strip()
    root = Path(__file__).resolve().parent.parent
    try:
        out = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=5,
        )
        if out.returncode != 0 or not out.stdout:
            return None
        url = (out.stdout or "").strip()
        # https://github.com/owner/repo or https://github.com/owner/repo.git
        m = re.match(r"https?://(?:www\.)?github\.com[/:]([^/]+)/([^/\s]+?)(?:\.git)?/?\s*$", url, re.I)
        if m:
            return f"{m.group(1)}/{m.group(2)}"
        # git@github.com:owner/repo.git
        m = re.match(r"git@github\.com:([^/]+)/([^/\s]+?)(?:\.git)?/?\s*$", url)
        if m:
            return f"{m.group(1)}/{m.group(2)}"
    except Exception:
        pass
    return None


def _github_request(method: str, url: str, body: Dict[str, Any], token: str) -> Dict[str, Any]:
    """Send authenticated request to GitHub REST API."""
    data = json.dumps(body).encode("utf-8") if body else None
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
            "Content-Type": "application/json",
        },
        method=method,
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            out = resp.read().decode("utf-8", errors="replace")
            return {"executed": True, "status": resp.status, "body": out[:4096]}
    except urllib.error.HTTPError as e:
        err_body = (e.read().decode("utf-8", errors="replace")[:2048] if e.fp else "")
        return {"executed": True, "status": e.code, "error": str(e.reason), "body": err_body}
    except urllib.error.URLError as e:
        return {"executed": False, "error": str(e.reason) if getattr(e, "reason", None) else str(e)}
    except Exception as e:
        return {"executed": False, "error": str(e)}


def run_github_post(args: Dict[str, Any], instance_id: str) -> Dict[str, Any]:
    """
    GitHub post: create issue, add comment to issue/PR.
    Args:
      op: "create_issue" | "create_comment"
      repo: "owner/repo" (e.g. "myorg/mortal_agent")
      title: required for create_issue
      body: required for both
      issue_number: required for create_comment (issue or PR number)
    """
    token = _get_token()
    if not token:
        return {"executed": False, "error": "no_github_token_set_GITHUB_TOKEN_or_MORTAL_GITHUB_TOKEN"}

    repo = (args.get("repo") or args.get("repository") or "").strip()
    if not repo or "/" not in repo:
        repo = _get_workspace_repo() or ""
    if not repo or "/" not in repo:
        return {"executed": False, "error": "repo_required_set_repo_arg_or_MORTAL_GITHUB_REPO_or_use_git_origin"}

    op = (args.get("op") or args.get("operation") or "create_issue").strip().lower()
    body_text = (args.get("body") or args.get("text") or "").strip()
    if not body_text:
        return {"executed": False, "error": "body_required"}

    owner, repo_name = repo.split("/", 1)[0].strip(), repo.split("/", 1)[1].strip()
    if not owner or not repo_name:
        return {"executed": False, "error": "invalid_repo_use_owner_repo"}

    base = "https://api.github.com"

    # Sign every post with agent identity so users see it's from the Mortal Agent
    body_for_api = _sign_body(body_text, instance_id)

    if op == "create_issue":
        title = (args.get("title") or f"From {GITHUB_AGENT_IDENTITY_LABEL}").strip() or f"From {GITHUB_AGENT_IDENTITY_LABEL}"
        url = f"{base}/repos/{owner}/{repo_name}/issues"
        payload = {"title": title[:256], "body": body_for_api}
        return _github_request("POST", url, payload, token)

    if op == "create_comment":
        issue_number = args.get("issue_number") or args.get("number")
        if issue_number is None:
            return {"executed": False, "error": "issue_number_required_for_create_comment"}
        try:
            num = int(issue_number)
        except (TypeError, ValueError):
            return {"executed": False, "error": "issue_number_must_be_integer"}
        url = f"{base}/repos/{owner}/{repo_name}/issues/{num}/comments"
        payload = {"body": body_for_api}
        return _github_request("POST", url, payload, token)

    return {"executed": False, "error": f"unsupported_op:{op}_use_create_issue_or_create_comment"}
