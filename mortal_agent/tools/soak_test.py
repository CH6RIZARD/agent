#!/usr/bin/env python3
"""
Soak test: 35 independent conversation sessions.
Runnable from repo root: python mortal_agent/tools/soak_test.py
Or from mortal_agent: python tools/soak_test.py
Logs every turn (prompt category, doc used or not, response length, time). Produces report + metrics.
"""
import os
import re
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

# mortal_agent package root (parent of tools/)
MORTAL_AGENT_ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = MORTAL_AGENT_ROOT.parent

STARTUP_WAIT = 10.0
REPLY_TIMEOUT = 35.0
QUICK_STARTUP_WAIT = 6.0
QUICK_REPLY_TIMEOUT = 15.0

# Identity boilerplate phrases (unprompted = spam)
IDENTITY_BOILERPLATE_PATTERNS = [
    r"i am an entity:?\s+this runtime instance",
    r"you are the controller:?\s+you provide direction",
    r"my behavior is constrained by the rules,?\s+interfaces",
    r"identity exists only while embodied",
]
IDENTITY_SPAM_RE = re.compile("|".join(f"({p})" for p in IDENTITY_BOILERPLATE_PATTERNS), re.IGNORECASE)


def run_session(scenario_id: str, category: str, messages: list, session_index: int, quick: bool = False) -> dict:
    """
    Run one session: spawn agent with SOAK_TURN_LOG, send messages, capture replies and log.
    Returns dict: scenario_id, category, turns, doc_used_list, responses, response_lengths, elapsed_per_turn, failures.
    """
    log_fd, log_path = tempfile.mkstemp(suffix=".soak_log", prefix=f"soak_{session_index}_")
    os.close(log_fd)
    env = os.environ.copy()
    env["SOAK_TURN_LOG"] = log_path
    startup_wait = QUICK_STARTUP_WAIT if quick else STARTUP_WAIT
    reply_timeout = QUICK_REPLY_TIMEOUT if quick else REPLY_TIMEOUT

    proc = subprocess.Popen(
        [sys.executable, "-m", "cli.main", "run"],
        cwd=str(MORTAL_AGENT_ROOT),
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        env=env,
    )
    out_lines = []
    prompt_seen = threading.Event()
    question_sent = threading.Event()
    reply_holder = []
    expected_index = [0]

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
    if not prompt_seen.wait(timeout=startup_wait):
        time.sleep(2)
    if proc.poll() is not None:
        try:
            os.unlink(log_path)
        except Exception:
            pass
        return {
            "scenario_id": scenario_id,
            "category": category,
            "turns": 0,
            "doc_used_list": [],
            "responses": [],
            "response_lengths": [],
            "elapsed_per_turn": [],
            "failures": ["process exited at startup"],
        }

    doc_used_list = []
    responses = []
    response_lengths = []
    elapsed_per_turn = []
    # First reply may be launch; we want reply_holder[1] for message 0, reply_holder[2] for message 1, etc.
    expected_reply_index = 1

    for i, msg in enumerate(messages):
        question_sent.set()
        t0 = time.monotonic()
        try:
            proc.stdin.write(msg + "\n")
            proc.stdin.flush()
        except Exception:
            break
        # Wait for next reply (index expected_reply_index)
        while len(reply_holder) <= expected_reply_index and (time.monotonic() - t0) < REPLY_TIMEOUT:
            time.sleep(0.1)
        elapsed = time.monotonic() - t0
        elapsed_per_turn.append(elapsed)
        if len(reply_holder) > expected_reply_index:
            reply = reply_holder[expected_reply_index]
            responses.append(reply)
            response_lengths.append(len(reply))
        else:
            responses.append("[timeout]")
            response_lengths.append(0)
        expected_reply_index += 1

    try:
        proc.stdin.close()
    except Exception:
        pass
    proc.terminate()
    try:
        proc.wait(timeout=3)
    except subprocess.TimeoutExpired:
        proc.kill()

    # Read doc_used log
    try:
        with open(log_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith("doc_used="):
                    doc_used_list.append(1 if "=1" in line else 0)
    except Exception:
        pass
    try:
        os.unlink(log_path)
    except Exception:
        pass

    failures = []
    if len(responses) < len(messages):
        failures.append(f"only {len(responses)} replies for {len(messages)} messages")
    if len(doc_used_list) != len(messages):
        failures.append(f"doc_used log length {len(doc_used_list)} != turns {len(messages)}")

    return {
        "scenario_id": scenario_id,
        "category": category,
        "turns": len(messages),
        "doc_used_list": doc_used_list,
        "responses": responses,
        "response_lengths": response_lengths,
        "elapsed_per_turn": elapsed_per_turn,
        "failures": failures,
    }


def identity_spam_count(responses: list) -> int:
    """Count responses that contain identity boilerplate unprompted (heuristic: contains full phrase)."""
    return sum(1 for r in responses if r and IDENTITY_SPAM_RE.search(r))


def repetition_score(all_responses: list) -> float:
    """Simple repetition: fraction of response pairs that share a long common substring (e.g. 40+ chars)."""
    if len(all_responses) < 2:
        return 0.0
    duplicates = 0
    for i, a in enumerate(all_responses):
        a = (a or "")[:200]
        for j, b in enumerate(all_responses):
            if i >= j:
                continue
            b = (b or "")[:200]
            for k in range(len(a) - 39):
                sub = a[k : k + 40]
                if sub in b:
                    duplicates += 1
                    break
    n_pairs = len(all_responses) * (len(all_responses) - 1) // 2
    return duplicates / n_pairs if n_pairs else 0.0


def coherence_proxy(responses: list) -> list:
    """Flag possible contradictions (simple: e.g. 'I am X' vs 'I am not X' in same session)."""
    flags = []
    text = " ".join(responses).lower()
    if "i am " in text and "i am not " in text:
        flags.append("possible_contradiction_am")
    return flags


def human_voice_heuristics(session: dict) -> dict:
    """Check: not all same length, some variation, no constant list formatting."""
    lengths = session.get("response_lengths", [])
    responses = session.get("responses", [])
    out = {}
    if lengths:
        out["length_std"] = (sum((x - sum(lengths) / len(lengths)) ** 2 for x in lengths) / len(lengths)) ** 0.5
        out["all_same_length"] = len(set(lengths)) <= 1
    bullet_count = sum(1 for r in responses if r and re.search(r"^\s*[-*]\s|\n\s*[-*]\s", r))
    out["bullet_heavy"] = bullet_count >= len(responses) * 0.8 if responses else False
    return out


def run_all_and_report(quick: bool = False):
    """Run 35 sessions (or 2 if quick), compute metrics, write report, return success (all acceptance checks pass)."""
    if str(MORTAL_AGENT_ROOT) not in sys.path:
        sys.path.insert(0, str(MORTAL_AGENT_ROOT))
    tools_dir = MORTAL_AGENT_ROOT / "tools"
    if str(tools_dir) not in sys.path:
        sys.path.insert(0, str(tools_dir))
    from soak_scenarios import iter_scenarios

    reports_dir = MORTAL_AGENT_ROOT / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    report_path = reports_dir / "soak_report.md"

    sessions = []
    all_responses = []
    total_turns = 0
    total_doc_used = 0
    scenario_list = list(iter_scenarios())
    if quick:
        scenario_list = scenario_list[:2]
        print("Quick mode: 2 sessions only")

    for idx, (scenario_id, category, messages) in enumerate(scenario_list):
        print(f"Session {idx + 1}/{len(scenario_list)}: {scenario_id} ({category}) ...")
        session = run_session(scenario_id, category, messages, idx, quick=quick)
        sessions.append(session)
        all_responses.extend(session.get("responses", []))
        total_turns += session.get("turns", 0)
        total_doc_used += sum(session.get("doc_used_list", []))

    # Metrics
    doc_usage_rate = total_doc_used / total_turns if total_turns else 0.0
    doc_usage_per_session = [
        sum(s.get("doc_used_list", [])) / max(1, s.get("turns", 1)) for s in sessions
    ]
    identity_spam_total = sum(identity_spam_count(s.get("responses", [])) for s in sessions)
    identity_spam_sessions = [identity_spam_count(s.get("responses", [])) for s in sessions]
    rep_score = repetition_score(all_responses)
    coherence_flags = []
    for s in sessions:
        coherence_flags.extend(coherence_proxy(s.get("responses", [])))
    human_checks = [human_voice_heuristics(s) for s in sessions]
    failure_list = []
    for s in sessions:
        for f in s.get("failures", []):
            failure_list.append((s["scenario_id"], s["category"], f))

    # Acceptance checks
    doc_ok = 0.25 <= doc_usage_rate <= 0.45
    identity_spam_ok = identity_spam_total <= 5
    repetition_ok = rep_score < 0.4

    # Build report
    lines = [
        "# Soak Test Report",
        "",
        "## Summary",
        f"- Total sessions: {len(sessions)}",
        f"- Total turns: {total_turns}",
        f"- Doc usage (overall): {total_doc_used}/{total_turns} = {doc_usage_rate:.2%}",
        f"- Identity spam (unprompted boilerplate): {identity_spam_total}",
        f"- Repetition score (0–1): {rep_score:.3f}",
        "",
        "## Acceptance Checks",
        f"- Doc usage in 25–45%: **{'PASS' if doc_ok else 'FAIL'}** ({doc_usage_rate:.2%})",
        f"- Identity spam near 0: **{'PASS' if identity_spam_ok else 'FAIL'}** ({identity_spam_total})",
        f"- Repetition low: **{'PASS' if repetition_ok else 'FAIL'}** ({rep_score:.3f})",
        "",
        "## Doc Usage Per Session",
        "",
    ]
    for s in sessions:
        rate = sum(s.get("doc_used_list", [])) / max(1, s.get("turns", 1))
        lines.append(f"- {s['scenario_id']} ({s['category']}): {rate:.2%}")
    lines.extend([
        "",
        "## Identity Spam Per Session",
        "",
    ])
    for s in sessions:
        n = identity_spam_count(s.get("responses", []))
        lines.append(f"- {s['scenario_id']}: {n}")
    lines.extend([
        "",
        "## Coherence Flags",
        "",
    ])
    lines.append(str(coherence_flags) if coherence_flags else "None")
    lines.extend([
        "",
        "## Human Voice Heuristics (sample)",
        "",
    ])
    for i, h in enumerate(human_checks[:5]):
        lines.append(f"- Session {i}: {h}")
    lines.extend([
        "",
        "## Failure List",
        "",
    ])
    for sid, cat, f in failure_list:
        lines.append(f"- {sid} ({cat}): {f}")
    if not failure_list:
        lines.append("None")
    lines.append("")
    report_content = "\n".join(lines)
    report_path.write_text(report_content, encoding="utf-8")

    print("\n" + "=" * 60)
    print("SOAK TEST SUMMARY")
    print("=" * 60)
    print(f"Doc usage: {doc_usage_rate:.2%} (target 25–45%): {'PASS' if doc_ok else 'FAIL'}")
    print(f"Identity spam: {identity_spam_total} (target near 0): {'PASS' if identity_spam_ok else 'FAIL'}")
    print(f"Repetition: {rep_score:.3f} (target low): {'PASS' if repetition_ok else 'FAIL'}")
    print(f"Report: {report_path}")
    print("=" * 60)
    return doc_ok and identity_spam_ok and repetition_ok


def main(quick: bool = False):
    """Entry point: run 35 sessions (or 2 if quick=True), write report, exit 0 if checks pass else 1."""
    success = run_all_and_report(quick=quick)
    return 0 if success else 1


if __name__ == "__main__":
    quick = "--quick" in sys.argv
    sys.exit(main(quick=quick))
