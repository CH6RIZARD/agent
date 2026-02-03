#!/usr/bin/env python3
"""
Launcher: run agent in a loop. On process exit (death or crash), restart automatically
and rebind Observer port (127.0.0.1:8080). No manual steps beyond running this once.
"""

import os
import sys
import time
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PORT = 8080


def main():
    os.chdir(ROOT)
    port = int(os.environ.get("OBSERVER_PORT", DEFAULT_PORT))
    cmd = [sys.executable, "-m", "cli.main", "run", "--host", "127.0.0.1", "--port", str(port)]
    while True:
        proc = subprocess.run(cmd, cwd=str(ROOT))
        time.sleep(1)
        # Restart: new instance_id, new birth_tick, same Observer port (127.0.0.1:8080)


if __name__ == "__main__":
    main()
