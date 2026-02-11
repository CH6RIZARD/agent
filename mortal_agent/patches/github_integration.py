"""
GitHub API integration: create issues, add comments on GitHub.

Every time the agent posts (GITHUB_POST), it goes to the same place: this repo's Issues.
Token: same one git uses when you push (checked first). Only set GITHUB_TOKEN in .env if you use SSH for git and want to reuse that token.
Repo = this workspace (git origin) unless you set MORTAL_GITHUB_REPO. Every post is signed as from the Mortal Agent.

Invariant: GITHUB_POST runs without MORTAL_DEPLOY so the agent can post when he has a reason (internal or external).
Capability reporting uses has_github_token() as the source of truth. See docs/AUTONOMY_PATCHES.md.
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


def _get_token_from_git() -> str:
    """Same token git uses when you push (git credential for github.com). No .env needed if you can push."""
    root = Path(__file__).resolve().parent.parent
    # Try both request styles; some helpers key off url=
    for request in ("protocol=https\nhost=github.com\n\n", "url=https://github.com/\n\n"):
        try:
            proc = subprocess.run(
                ["git", "credential", "fill"],
                input=request,
                capture_output=True,
                text=True,
                timeout=5,
                cwd=root,
            )
            if proc.returncode != 0 or not (proc.stdout or "").strip():
                continue
            for line in (proc.stdout or "").splitlines():
                line = line.strip()
                if line.startswith("password="):
                    token = line.split("=", 1)[1].strip()
                    if token:
                        return token
        except Exception:
            pass
    return ""


def _get_token() -> str:
    # Ensure workspace .env is loaded so GITHUB_TOKEN / MORTAL_GITHUB_TOKEN are available
    try:
        from pathlib import Path
        _root = Path(__file__).resolve().parent.parent  # mortal_agent
        _repo = _root.parent
        for _env_path in (_root / ".env", _repo / ".env", Path.cwd() / ".env"):
            if _env_path.exists():
                try:
                    from dotenv import load_dotenv
                    load_dotenv(_env_path)
                except Exception:
                    pass
                break
    except Exception:
        pass
    # Use same token as git push first; then env (workspace .env above)
    token = _get_token_from_git()
    if token:
        return token
    return (os.environ.get("MORTAL_GITHUB_TOKEN") or os.environ.get("GITHUB_TOKEN") or "").strip()


def has_github_token() -> bool:
    """True if the agent can post to GitHub (same resolution as _get_token: git credential or env)."""
    return bool(_get_token().strip())


def _get_workspace_repo() -> Optional[str]:
    """
    Resolve the GitHub repo (owner/repo) for this workspace. Agent always posts here unless
    the action explicitly passes a different repo. Order: MORTAL_GITHUB_REPO, GITHUB_REPO, then git origin.
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
        return {"executed": False, "error": "no_github_token_agent_uses_same_as_git_push_if_you_use_SSH_put_that_token_in_env_as_GITHUB_TOKEN"}

    # Default: post here (this workspace's repo). Override only if caller passes repo in args.
    repo = (args.get("repo") or args.get("repository") or "").strip()
    if not repo or "/" not in repo:
        repo = _get_workspace_repo() or ""
    if not repo or "/" not in repo:
        return {"executed": False, "error": "repo_required_set_MORTAL_GITHUB_REPO_or_ensure_git_origin_points_to_github"}

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
        out = _github_request("POST", url, payload, token)
        # Add agent-visible summary so reply can be tied to actual result (patch 2).
        if out.get("executed") and out.get("status") == 201 and out.get("body"):
            try:
                data = json.loads(out["body"])
                num = data.get("number")
                html_url = data.get("html_url") or ""
                out["issue_number"] = num
                out["html_url"] = html_url
                out["github_result_summary"] = (
                    f"created issue #{num}: \"{title[:60]}\" at {html_url}" if num and html_url
                    else f"created issue: \"{title[:60]}\""
                )
            except Exception:
                out["github_result_summary"] = "created (see body)" if out.get("executed") else ""
        elif not out.get("executed") or out.get("status", 0) != 201:
            err = out.get("error") or (out.get("body", "")[:200] if out.get("body") else "unknown")
            out["github_result_summary"] = f"failed: {err}"
        return out

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


def list_issues(repo: Optional[str] = None, token: Optional[str] = None, state: str = "all", per_page: int = 100) -> list:
    """List issues (with optional auth). Returns list of issue dicts (number, title, body, state, html_url, ...)."""
    t = token or _get_token()
    if not repo or "/" not in repo:
        repo = _get_workspace_repo() or ""
    if not repo or "/" not in repo:
        return []
    owner, repo_name = repo.split("/", 1)[0].strip(), repo.split("/", 1)[1].strip()
    url = f"https://api.github.com/repos/{owner}/{repo_name}/issues?state={state}&per_page={per_page}&sort=created&direction=desc"
    headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
    if t:
        headers["Authorization"] = f"Bearer {t}"
    req = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception:
        return []


def update_issue(issue_number: int, title: Optional[str] = None, body: Optional[str] = None,
                 repo: Optional[str] = None, instance_id: str = "script", sign_with_agent: bool = True,
                 state: Optional[str] = None) -> Dict[str, Any]:
    """PATCH an issue's title, body, and/or state. state can be 'open' or 'closed'. If sign_with_agent, append Mortal Agent footer to body."""
    token = _get_token()
    if not token:
        return {"executed": False, "error": "no_github_token"}
    r = (repo or _get_workspace_repo() or "").strip()
    if not r or "/" not in r:
        return {"executed": False, "error": "repo_required"}
    owner, repo_name = r.split("/", 1)[0].strip(), r.split("/", 1)[1].strip()
    url = f"https://api.github.com/repos/{owner}/{repo_name}/issues/{issue_number}"
    payload: Dict[str, Any] = {}
    if title is not None:
        payload["title"] = title[:256]
    if body is not None:
        payload["body"] = _sign_body(body, instance_id) if sign_with_agent and instance_id else body
    if state is not None and state in ("open", "closed"):
        payload["state"] = state
    if not payload:
        return {"executed": False, "error": "nothing_to_update"}
    out = _github_request("PATCH", url, payload, token)
    if out.get("executed") and out.get("status") == 200:
        out["github_result_summary"] = f"updated issue #{issue_number}" + (f" (state={state})" if state else "")
    return out


def close_issue(issue_number: int, repo: Optional[str] = None) -> Dict[str, Any]:
    """Close an issue (GitHub does not support deleting issues)."""
    return update_issue(issue_number, repo=repo, state="closed")
