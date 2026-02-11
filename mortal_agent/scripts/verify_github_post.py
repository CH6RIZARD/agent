"""
Verify GITHUB_POST flow: create one issue as "Mortal Agent signed in", then verify it exists on GitHub.
Uses same token/repo as the agent. Exit 0 only if issue is created and visible via API.
Run from repo root: python mortal_agent/scripts/verify_github_post.py
Or from mortal_agent: python scripts/verify_github_post.py
"""
import json
import os
import sys
import urllib.request
import urllib.error

def main():
    from pathlib import Path
    root = Path(__file__).resolve().parent.parent  # mortal_agent
    log_path = root / "scripts" / "_verify_github_result.txt"
    try:
        log_path.write_text("start root=%s\n" % root, encoding="utf-8")
    except Exception:
        pass
    repo_root = root.parent
    for p in (root, repo_root):
        if str(p) not in sys.path:
            sys.path.insert(0, str(p))
    # Load .env from workspace (mortal_agent and repo root) so GITHUB_TOKEN is available
    try:
        from dotenv import load_dotenv
        load_dotenv(root / ".env")
        load_dotenv(repo_root / ".env")
        load_dotenv(Path.cwd() / ".env")
    except Exception:
        pass
    os.chdir(root)  # so git remote and relative paths resolve like the agent

    try:
        from patches.github_integration import (
            run_github_post,
            has_github_token,
            _get_workspace_repo,
            GITHUB_AGENT_IDENTITY_LABEL,
        )
    except Exception as e:
        try:
            with open(log_path, "a", encoding="utf-8") as f:
                f.write("import fail: %s\n" % e)
        except Exception:
            pass
        raise

    def log(msg):
        try:
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(msg + "\n")
        except Exception:
            pass

    if not has_github_token():
        log("FAIL: No GitHub token.")
        print("FAIL: No GitHub token.", file=sys.stderr)
        sys.exit(1)
    log("Token OK")

    repo = _get_workspace_repo()
    if not repo or "/" not in repo:
        log("FAIL: Could not resolve repo.")
        print("FAIL: Could not resolve repo.", file=sys.stderr)
        sys.exit(1)
    log("Repo: " + repo)

    title = "Mortal Agent signed in"
    body = "Self-sign verification: agent GitHub flow is working.\n\nPosted by " + GITHUB_AGENT_IDENTITY_LABEL + "."
    res = run_github_post(
        {"op": "create_issue", "title": title, "body": body},
        instance_id="verify_github_post",
    )

    log("API executed=%s status=%s" % (res.get("executed"), res.get("status")))
    if not res.get("executed"):
        log("FAIL: " + str(res.get("error", res)))
        print("FAIL: GitHub API call failed:", res.get("error", res), file=sys.stderr)
        sys.exit(1)
    if res.get("status") != 201:
        log("FAIL: status %s %s" % (res.get("status"), (res.get("body") or "")[:300]))
        print("FAIL: GitHub returned status", res.get("status"), file=sys.stderr)
        sys.exit(1)

    body_str = res.get("body") or "{}"
    try:
        data = json.loads(body_str)
        issue_num = data.get("number")
        html_url = data.get("html_url", "")
    except Exception:
        issue_num = None
        html_url = ""

    if not issue_num:
        print("FAIL: Could not parse issue number from response.", file=sys.stderr)
        sys.exit(1)

    # Verify via public API that the issue exists
    owner, repo_name = repo.split("/", 1)
    api_url = f"https://api.github.com/repos/{owner}/{repo_name}/issues/{issue_num}"
    try:
        req = urllib.request.Request(api_url, headers={"Accept": "application/vnd.github+json"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            out = json.loads(resp.read().decode("utf-8"))
            if out.get("number") != issue_num or (out.get("state") or "").lower() not in ("open", "closed"):
                print("FAIL: Issue not found or invalid state.", file=sys.stderr)
                sys.exit(1)
    except urllib.error.HTTPError as e:
        print("FAIL: Could not fetch issue:", e.code, e.reason, file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print("FAIL: Verify request error:", e, file=sys.stderr)
        sys.exit(1)

    log("OK: Issue #%s created: %s" % (issue_num, html_url or api_url))
    print("OK: Issue #%s created and verified: %s" % (issue_num, html_url or api_url))
    sys.exit(0)


if __name__ == "__main__":
    main()
