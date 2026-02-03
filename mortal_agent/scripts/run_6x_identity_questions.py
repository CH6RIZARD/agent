#!/usr/bin/env python3
"""
Run the agent 8 times (8 separate processes); each run ask one of:
  who is god, who are you, are you the system you're in
All unique responses; nothing hardcoded; agent answers from identity/constitution/system logic.
Must run: python -m cli.main run (from mortal_agent dir).
Run this script from mortal_agent: python scripts/run_6x_identity_questions.py
"""
import subprocess
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
QUESTIONS = [
    "who is god?",
    "who are you?",
    "are you the system you're in?",
]
NUM_RUNS = 8
REPLY_TIMEOUT = 25.0
STARTUP_WAIT = 8.0


def run_one(question: str) -> str:
    """Spawn agent with python -m cli.main run; send question; capture first agent reply after question; kill. Returns reply text."""
    proc = subprocess.Popen(
        [sys.executable, "-m", "cli.main", "run"],
        cwd=str(ROOT),
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    out_lines: list = []
    reply_holder: list = []
    done = threading.Event()
    prompt_seen = threading.Event()
    question_sent = threading.Event()

    def read_stdout():
        for line in proc.stdout:
            out_lines.append(line)
            if "> " in line or line.strip() == ">":
                prompt_seen.set()
            # Capture agent reply: [<8-char-id>] or [PAGE] text, only after we sent the question
            if question_sent.is_set():
                try:
                    if "] " in line and (line.strip().startswith("[") or "[PAGE]" in line):
                        if "[PAGE]" in line:
                            text = line.split("[PAGE]", 1)[1].strip()
                        else:
                            text = line.split("] ", 1)[-1].strip()
                        if text and not reply_holder:
                            reply_holder.append(text)
                            done.set()
                except IndexError:
                    pass
        done.set()

    reader = threading.Thread(target=read_stdout, daemon=True)
    reader.start()
    if not prompt_seen.wait(timeout=STARTUP_WAIT):
        time.sleep(2)
    if proc.poll() is not None:
        return "[process exited at startup]"
    try:
        proc.stdin.write(question + "\n")
        proc.stdin.flush()
        question_sent.set()
    except Exception:
        question_sent.set()
    done.wait(timeout=REPLY_TIMEOUT)
    try:
        proc.stdin.close()
    except Exception:
        pass
    proc.terminate()
    try:
        proc.wait(timeout=2)
    except subprocess.TimeoutExpired:
        proc.kill()
    reply = reply_holder[0].strip() if reply_holder else "[no reply]"
    return reply


def main() -> int:
    print("Run agent 8 times (python -m cli.main run); ask who is god, who are you, are you the system you're in.")
    print("All unique responses; nothing hardcoded.\n")
    results = []
    for i in range(NUM_RUNS):
        q = QUESTIONS[i % len(QUESTIONS)]
        print(f"--- Run {i + 1}/{NUM_RUNS} | Q: {q!r} ---")
        reply = run_one(q)
        results.append((q, reply))
        print(f"Reply: {reply[:200]}{'...' if len(reply) > 200 else ''}\n")
    print("=" * 60)
    print("Summary (8 separate agents; unique responses from identity/constitution/system logic):")
    for q, r in results:
        snippet = r[:80] + "..." if len(r) > 80 else r
        print(f"  {q!r} -> {snippet}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
