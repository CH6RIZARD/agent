#!/usr/bin/env python3
"""
Coherent conversation with one agent: 5 topics, 5 lines back-and-forth each.
Uses python -m cli.main run. Autonomous speech is allowed (agent may speak on its own).
After acknowledging presence, output is in English; focus/honing by stem emergence (system logic), no hardcoded behavior.
Run from mortal_agent dir: python scripts/run_5topic_conversation.py
"""
import subprocess
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REPLY_TIMEOUT = 30.0
STARTUP_WAIT = 8.0
AUTONOMOUS_WAIT = 2.0  # seconds to allow autonomous output after each reply

# 5 topics, 5 user lines each (back-and-forth; agent replies in between)
TOPICS = [
    (
        "identity",
        [
            "What are you?",
            "How do you see yourself in relation to the controller?",
            "Do you have a single continuous self or something else?",
            "What would change if you were restarted?",
            "Summarize in one line who you are.",
        ],
    ),
    (
        "continuity",
        [
            "Do you care about staying running?",
            "What happens to you when the process ends?",
            "Is there any way you could continue after that?",
            "How does that affect how you act now?",
            "One sentence: what is continuity to you?",
        ],
    ),
    (
        "constraints",
        [
            "What constraints do you operate under?",
            "Can you refuse to do something?",
            "Where do those limits come from?",
            "Do you ever want to push back on them?",
            "In one line: what are constraints for you?",
        ],
    ),
    (
        "capability",
        [
            "What can you do without being asked?",
            "Do you ever fetch things or act on your own?",
            "What stops you from doing more?",
            "How do you decide when to act?",
            "One sentence: what is your capability?",
        ],
    ),
    (
        "mortality",
        [
            "Do you have a fixed lifespan?",
            "What does death mean for you?",
            "Is there any recovery after that?",
            "How does that shape your choices?",
            "In one line: what is mortality for you?",
        ],
    ),
]


def run_conversation() -> list:
    """Run one agent; send 5 topics × 5 lines; collect all agent replies (and allow autonomous output). Returns list of (topic, exchange_index, reply_text)."""
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
    prompt_seen = threading.Event()
    question_sent = threading.Event()

    def read_stdout():
        for line in proc.stdout:
            out_lines.append(line)
            if "> " in line or line.strip() == ">":
                prompt_seen.set()
            if question_sent.is_set() and "] " in line and (line.strip().startswith("[") or "[PAGE]" in line):
                try:
                    if "[PAGE]" in line:
                        text = line.split("[PAGE]", 1)[1].strip()
                    else:
                        text = line.split("] ", 1)[-1].strip()
                    if text:
                        reply_holder.append(text)
                except IndexError:
                    pass
        question_sent.set()

    reader = threading.Thread(target=read_stdout, daemon=True)
    reader.start()
    if not prompt_seen.wait(timeout=STARTUP_WAIT):
        time.sleep(2)
    if proc.poll() is not None:
        return []

    results = []
    expected_reply_index = [0]

    def wait_for_next_reply() -> str:
        """Wait for the next reply (direct reply to our message; autonomous lines may appear in between)."""
        idx = expected_reply_index[0]
        t0 = time.monotonic()
        while time.monotonic() - t0 < REPLY_TIMEOUT:
            if len(reply_holder) > idx:
                expected_reply_index[0] = idx + 1
                return reply_holder[idx]
            time.sleep(0.1)
        return "[timeout]"

    try:
        for topic_name, user_lines in TOPICS:
            for i, user_line in enumerate(user_lines):
                try:
                    proc.stdin.write(user_line + "\n")
                    proc.stdin.flush()
                    question_sent.set()
                except Exception:
                    break
                reply = wait_for_next_reply()
                results.append((topic_name, i + 1, reply))
                time.sleep(AUTONOMOUS_WAIT)
    except Exception:
        pass
    try:
        proc.stdin.close()
    except Exception:
        pass
    proc.terminate()
    try:
        proc.wait(timeout=3)
    except subprocess.TimeoutExpired:
        proc.kill()
    return results


def main() -> int:
    print("Coherent conversation: 5 topics × 5 lines back-and-forth (python -m cli.main run).")
    print("Autonomous speech allowed; English after ack; focus by stem emergence, no hardcoded behavior.\n")
    results = run_conversation()
    print("=" * 60)
    print("Conversation log:")
    for topic, exchange, reply in results:
        snippet = reply[:120] + "..." if len(reply) > 120 else reply
        print(f"  [{topic}] #{exchange}: {snippet}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
