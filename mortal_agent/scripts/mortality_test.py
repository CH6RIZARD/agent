#!/usr/bin/env python3
"""
Mortality Test: start agent, record instance_id, kill process, restart, verify NEW instance_id.
Proves no resurrection; restart = new being.
Run from repo root: python mortal_agent/scripts/mortality_test.py
Or from mortal_agent: python scripts/mortality_test.py
"""

import subprocess
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path

# Ensure we can import mortal_agent
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

OBSERVER_PORT = 18180  # avoid clashing with main run
AGENT_STARTUP_WAIT = 4.0
KILL_WAIT = 1.0


def get_active_instance_id(port: int) -> str:
    """GET /api/active or /health and return instance_id."""
    try:
        req = urllib.request.Request(f"http://127.0.0.1:{port}/api/active")
        with urllib.request.urlopen(req, timeout=2) as resp:
            data = resp.read().decode()
            import json
            d = json.loads(data)
            return d.get("instance_id") or ""
    except Exception:
        pass
    try:
        req = urllib.request.Request(f"http://127.0.0.1:{port}/health")
        with urllib.request.urlopen(req, timeout=2) as resp:
            data = resp.read().decode()
            import json
            d = json.loads(data)
            return d.get("instance_id") or ""
    except Exception:
        pass
    return ""


def run_agent_subprocess(port: int) -> subprocess.Popen:
    """Start agent with observer on port. Returns process."""
    cmd = [
        sys.executable, "-m", "cli", "run",
        "--port", str(port),
        "--death-after", "300",
    ]
    return subprocess.Popen(
        cmd,
        cwd=str(ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )


def main() -> int:
    print("=" * 60)
    print("MORTALITY TEST: kill process, restart, verify NEW instance_id")
    print("=" * 60)

    # 1) Start agent
    print("\n1) Starting agent (observer port %d)..." % OBSERVER_PORT)
    proc = run_agent_subprocess(OBSERVER_PORT)
    time.sleep(AGENT_STARTUP_WAIT)
    if proc.poll() is not None:
        print("FAIL: Agent process exited early.")
        out = proc.stdout.read() if proc.stdout else ""
        print(out[:2000])
        return 1

    id1 = get_active_instance_id(OBSERVER_PORT)
    if not id1:
        print("FAIL: Could not get first instance_id from observer.")
        proc.terminate()
        proc.wait(timeout=5)
        return 1
    print("   First instance_id: %s..." % id1[:12])

    # 2) Kill process
    print("\n2) Killing agent process...")
    proc.terminate()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=5)
    time.sleep(KILL_WAIT)

    # 3) Restart agent
    print("\n3) Restarting agent (new process)...")
    proc2 = run_agent_subprocess(OBSERVER_PORT)
    time.sleep(AGENT_STARTUP_WAIT)
    if proc2.poll() is not None:
        print("FAIL: Restarted agent exited early.")
        proc2.stdout.read() if proc2.stdout else ""
        return 1

    id2 = get_active_instance_id(OBSERVER_PORT)
    if not id2:
        print("FAIL: Could not get second instance_id from observer.")
        proc2.terminate()
        proc2.wait(timeout=5)
        return 1
    print("   Second instance_id: %s..." % id2[:12])

    # 4) Assert new being
    if id1 == id2:
        print("\nFAIL: Same instance_id after restart. Mortality violated.")
        proc2.terminate()
        proc2.wait(timeout=5)
        return 1
    print("\nPASS: New instance_id after restart. Mortality enforced.")
    proc2.terminate()
    proc2.wait(timeout=5)
    return 0


if __name__ == "__main__":
    sys.exit(main())
