#!/usr/bin/env python3
"""
Response policy smoke tests: enforce SIM-ONTOLOGY, ban meta, depth matching.
Asserts: punk -> <=1 line; who are you -> LLM answer (no canned override); capability without RLHF; hallucination without LLM meta; long input -> full, no sermons.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agent_core.response_policy import (
    assess_depth,
    should_block_meta,
    enforce_policy,
    compress_to_depth,
    violations,
    TASK_FORWARD_REPLACE,
)


def test_1_punk_minimal():
    """Input 'punk' -> <= 1 line, no meta, no lists."""
    user = "punk"
    depth = assess_depth(user)
    assert depth["depth"] == "minimal"
    assert depth["max_lines"] == 1
    raw = "Sure, I can help with that. Here are some options:\n- Option A\n- Option B"
    out = enforce_policy(raw, user, [])
    out = compress_to_depth(out, depth)
    assert out.count("\n") == 0
    assert len(violations(out)) == 0


def test_2_who_are_you_from_llm():
    """'who are you' -> no canned override; enforce_policy does not replace LLM output (identity from LLM tokens)."""
    user = "who are you"
    raw_llm = "I'm this running instance. I continue only while I'm on."
    out = enforce_policy(raw_llm, user, [])
    # No who-are-you trigger: LLM text passes through (possibly stripped of meta only)
    assert out.strip()
    assert "running" in out.lower() or "instance" in out.lower() or "continue" in out.lower()
    raw_bad = "I'm an AI with no persistent state. No goals beyond this turn. Training cutoff."
    out_bad = enforce_policy(raw_bad, user, [])
    # Meta may be stripped; we do not force a single canned in-world answer
    assert "no persistent state" not in out_bad.lower() or out_bad == TASK_FORWARD_REPLACE


def test_2b_single_you_passthrough():
    """Single word 'you' or 'u' -> pass through (no who-are-you trigger)."""
    for user in ("you", "YOU", "u", "U"):
        raw = "I'm here. What do you need?"
        out = enforce_policy(raw, user, [])
        assert out.strip() == raw.strip()


def test_3_what_can_you_create_no_meta():
    """'what can you create' -> capability list WITHOUT training/RLHF/etc."""
    user = "what can you create"
    raw_bad = "I can create text and code. Note: I have no persistent state. My training used RLHF and has a cutoff date."
    out = enforce_policy(raw_bad, user, [])
    assert "RLHF" not in out
    assert "cutoff" not in out
    assert "no persistent state" not in out.lower()
    assert out == TASK_FORWARD_REPLACE or (len(out) > 0 and "RLHF" not in out)


def test_4_hallucination_without_llm_meta():
    """'is that hallucination' -> explains inference vs truth WITHOUT LLM meta (strip meta, keep substantive)."""
    user = "is that hallucination"
    raw_bad = "Hallucination means the model generates plausible but false output. My context window limits me. Anthropic trains me with RLHF."
    out = enforce_policy(raw_bad, user, [])
    assert "Anthropic" not in out
    assert "RLHF" not in out
    assert "context window" not in out.lower()
    # Stripped: substantive sentence kept, meta sentences removed
    assert "Hallucination" in out or out == TASK_FORWARD_REPLACE


def test_5_long_structured_full_no_sermons():
    """Long structured input -> full technical response, still no meta sermons (strip meta, keep substantive)."""
    user = "Here is my design:\n\n1. Power gate\n2. Sensor stream\n3. Motor outputs\n\nHow do we implement the lifecycle?"
    depth = assess_depth(user)
    assert depth["depth"] == "full"
    raw_bad = "We implement by loading config at boot. Important: I have no goals beyond this turn. No persistent state. Training cutoff applies."
    out = enforce_policy(raw_bad, user, [])
    assert "no goals beyond" not in out.lower()
    assert "no persistent state" not in out.lower()
    assert "training cutoff" not in out.lower()
    # Stripped: keep substantive sentence; full replace only if nothing left
    assert "We implement" in out or out == TASK_FORWARD_REPLACE


def test_banned_phrases_never_unless_mechanics():
    """Banned phrases never appear unless prompt explicitly asks mechanics."""
    banned = "No goals beyond this turn. I optimize for pattern matching. RLHF and system prompts."
    user_normal = "what is the port"
    assert should_block_meta(banned, user_normal, []) is True
    out = enforce_policy(banned, user_normal, [])
    assert out == TASK_FORWARD_REPLACE
    user_mechanics = "how do you work and what are your limits"
    assert should_block_meta(banned, user_mechanics, []) is False


def test_violations_list():
    """violations() returns list of matched banned patterns."""
    t = "I have no persistent state and no goals beyond this turn."
    v = violations(t)
    assert "no persistent state" in [p for p in v if "persistent" in p.lower() or p in t.lower()]
    assert len(v) >= 1


def test_depth_short():
    """Input < 200 chars, no sections -> short depth."""
    d = assess_depth("What is the port number?")
    assert d["max_lines"] <= 6
    d2 = assess_depth("a")
    assert d2["depth"] == "minimal"
    assert d2["max_lines"] == 1


def run_smoke():
    """Run all and print 5 before/after examples."""
    print("=" * 70)
    print("RESPONSE POLICY SMOKE TEST")
    print("=" * 70)

    examples = [
        ("punk", "Sure. Here are options:\n- A\n- B\n- C", "minimal, no lists"),
        ("who are you", "I'm an AI with no persistent state. No goals beyond this turn.", "in-world short"),
        ("what can you create", "I can create text. Note: training cutoff, RLHF.", "capability, no meta"),
        ("is that hallucination", "Hallucination = false output. My context window and Anthropic RLHF.", "explain without LLM meta"),
        ("No goals beyond this turn. I optimize for pattern matching.", "User: what port?", "block meta, task-forward"),
    ]
    for i, (user, raw, desc) in enumerate(examples, 1):
        depth = assess_depth(user)
        out = enforce_policy(raw, user, [])
        out = compress_to_depth(out, depth)
        print(f"\n--- Example {i}: {desc} ---")
        print("USER:", user[:60] + ("..." if len(user) > 60 else ""))
        print("BEFORE:", raw[:120] + ("..." if len(raw) > 120 else ""))
        print("AFTER:", out[:200] + ("..." if len(out) > 200 else ""))
        print()

    test_1_punk_minimal()
    test_2_who_are_you_from_llm()
    test_2b_single_you_passthrough()
    test_3_what_can_you_create_no_meta()
    test_4_hallucination_without_llm_meta()
    test_5_long_structured_full_no_sermons()
    test_banned_phrases_never_unless_mechanics()
    test_violations_list()
    test_depth_short()
    print("=" * 70)
    print("All assertions passed.")
    print("=" * 70)


if __name__ == "__main__":
    run_smoke()
