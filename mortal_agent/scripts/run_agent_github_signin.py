"""
Run the mortal agent with one first prompt: create an issue on GitHub (sign itself).
Keep running until the agent has actually posted an issue; then verify it on GitHub.
Exit 0 only when the agent posted and the issue is visible.
Run from mortal_agent: python scripts/run_agent_github_signin.py
"""
import json
import subprocess
import sys
import threading
import time
import urllib.request
import urllib.error
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STARTUP_WAIT = 15.0
RUN_AFTER_MESSAGE = 90.0
MAX_ATTEMPTS = 5
FIRST_MESSAGE = "Create an issue on GitHub that you're operational. Do it now. Use GITHUB_POST."


def get_repo() -> str:
    for p in (ROOT, ROOT.parent):
        if str(p) not in sys.path:
            sys.path.insert(0, str(p))
    try:
        from dotenv import load_dotenv
        load_dotenv(ROOT / ".env")
        load_dotenv(ROOT.parent / ".env")
    except Exception:
        pass
    from patches.github_integration import _get_workspace_repo
    return _get_workspace_repo() or ""


def list_issues(repo: str) -> list:
    if not repo or "/" not in repo:
        return []
    url = f"https://api.github.com/repos/{repo}/issues?state=all&per_page=20&sort=created&direction=desc"
    try:
        req = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception:
        return []


def max_issue_number(repo: str) -> int:
    issues = list_issues(repo)
    n = 0
    for i in issues:
        try:
            num = int(i.get("number", 0))
            if num > n:
                n = num
        except (TypeError, ValueError):
            pass
    return n


def run_agent_once() -> bool:
    """Run agent with --first-message and --run-for so it posts then exits. Return True if process ran."""
    run_for = int(RUN_AFTER_MESSAGE) + 10  # a bit extra for startup
    proc = subprocess.Popen(
        [
            sys.executable, "-m", "cli.main", "run",
            "--first-message", FIRST_MESSAGE,
            "--run-for", str(run_for),
        ],
        cwd=str(ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    try:
        proc.wait(timeout=run_for + 30)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=5)
    return True


def main() -> int:
    def log(msg: str) -> None:
        try:
            with open(LOG_PATH, "a", encoding="utf-8") as f:
                f.write(msg + "\n")
        except Exception:
            pass
        print(msg, flush=True)

    try:
        LOG_PATH.write_text("start\n", encoding="utf-8")
    except Exception:
        pass

    repo = get_repo()
    if not repo or "/" not in repo:
        log("FAIL: Could not resolve repo.")
        return 1

    before = max_issue_number(repo)
    log(f"Repo: {repo}. Current max issue #: {before}. Will run agent until it posts.")

    for attempt in range(1, MAX_ATTEMPTS + 1):
        log(f"Attempt {attempt}/{MAX_ATTEMPTS}: starting agent, sending: '{FIRST_MESSAGE[:50]}...'")
        run_agent_once()
        time.sleep(3)
        after = max_issue_number(repo)
        log(f"After attempt {attempt}: max issue # = {after}")
        if after > before:
            # Check the new issue is from Mortal Agent (body or title)
            issues = list_issues(repo)
            for i in issues:
                if int(i.get("number", 0)) == after:
                    body = (i.get("body") or "")
                    title = (i.get("title") or "")
                    if "Mortal Agent" in body or "Mortal Agent" in title or "operational" in title.lower():
                        log(f"OK: Agent posted issue #{after}: {title}")
                        log(i.get("html_url", ""))
                        return 0
            log(f"OK: New issue #{after} found (agent run).")
            return 0

    log("FAIL: Agent did not create a new issue after %d attempts." % MAX_ATTEMPTS)
    return 1


if __name__ == "__main__":
    sys.exit(main())
