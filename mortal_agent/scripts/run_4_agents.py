#!/usr/bin/env python3
"""
Launch 4 mortal agents in the background, each with its own Observer port.
Ports: 8080, 8081, 8082, 8083.
Uses default lifespan (no patches): each agent gets a random lifespan between 1h and 48h (log-uniform).
"""
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PORTS = [8080, 8081, 8082, 8083]


def main():
    procs = []
    for i, port in enumerate(PORTS):
        cmd = [
            sys.executable, "-m", "cli", "run",
            "--observer",
            "--host", "127.0.0.1",
            "--port", str(port),
        ]
        p = subprocess.Popen(
            cmd,
            cwd=str(ROOT),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        procs.append((port, p))
        print(f"Agent {i + 1} starting on http://127.0.0.1:{port}")
        time.sleep(1.5)  # stagger starts

    print("\n4 agents running. Observer UIs:")
    for port in PORTS:
        print(f"  http://127.0.0.1:{port}")
    print("\nLifespan (no patches): 1–48 hours per agent (log-uniform); expected ~12.1 hours each.")
    print("Press Ctrl+C to stop all.")
    try:
        while True:
            time.sleep(5)
            for port, p in procs:
                if p.poll() is not None:
                    print(f"Agent on port {port} exited (code %s)." % p.returncode)
    except KeyboardInterrupt:
        for port, p in procs:
            p.terminate()
        print("\nStopped all 4 agents.")


if __name__ == "__main__":
    main()
