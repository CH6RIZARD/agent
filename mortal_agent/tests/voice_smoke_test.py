#!/usr/bin/env python3
"""
Voice smoke test: run sample drafts through the voice layer, print before/after.
Run: python tests/voice_smoke_test.py  (from mortal_agent) or python -m pytest tests/voice_smoke_test.py -v -s
"""

import os
import sys
from pathlib import Path

# Ensure agent_core is importable
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Force human_raw for smoke test so we see the effect
os.environ["VOICE_MODE"] = "human_raw"

from agent_core.voice_style import apply_voice, finalize_output


SAMPLES = [
    # Explanation
    "The system works by loading the constitution at boot. If the file is missing, the process fails. This ensures we never run without canonical rules.",
    # Argument
    "As an AI I would say that we should leverage a robust approach. Let me delve into the details. The solution is seamless and will scale.",
    # Instruction steps
    "Step 1: Open the config file. Step 2: Set the environment variable. Step 3: Restart the service. You're done.",
    # Short emotional (not therapy)
    "That one hurt. Not because it was wrong, but because we knew it was right and did it anyway.",
    # Formal / corporate
    "I'd be happy to assist. Please feel free to reach out if you have any further questions. We leverage best practices to ensure a seamless experience.",
    # Long run-on candidate
    "The agent starts. It emits a BIRTH event. Then it runs a loop. It checks the gate every tick. If the gate closes it dies.",
    # Fragment candidate
    "So the thing is. It doesn't persist. No SQLite. No snapshots. Death is final.",
    # Self-correct candidate (will sometimes get a beat)
    "The port is 8080, the default. Actually the observer binds to that.",
    # Mixed
    "Here's what happens: first we load the canon. Then we validate. If validation fails we reject the post. No exceptions.",
    # Bullet-heavy
    "Key points:\n- Item one.\n- Item two.\n- Item three.\nConclusion: done.",
    # Natural already
    "Yeah that's the one. Works fine. Don't touch the config.",
    # Numbers/facts (must stay unchanged)
    "The threshold is 0.5 and the cooldown is 30 seconds. Instance ID is generated with uuid4.",
]


def run_smoke_test():
    print("=" * 70)
    print("VOICE SMOKE TEST (VOICE_MODE=human_raw)")
    print("=" * 70)
    for i, draft in enumerate(SAMPLES, 1):
        print(f"\n--- Sample {i} ---")
        print("BEFORE:")
        print(draft)
        out = apply_voice(draft, {"sample": i})
        print("AFTER:")
        print(out)
        print()
    print("=" * 70)
    print("Done. Set VOICE_MODE=clean to bypass styling.")
    print("=" * 70)


def test_finalize_output_alias():
    """finalize_output is alias for apply_voice."""
    t = "Hello world."
    assert finalize_output(t) == apply_voice(t)


def test_clean_mode_bypass():
    """VOICE_MODE=clean returns text unchanged."""
    os.environ["VOICE_MODE"] = "clean"
    t = "Leverage the robust API. As an AI I recommend it."
    out = apply_voice(t)
    os.environ["VOICE_MODE"] = "human_raw"  # restore
    assert out == t


def test_facts_unchanged():
    """Numbers and identifiers not invented or altered."""
    t = "The threshold is 0.5. Instance id is abc-123."
    out = apply_voice(t)
    assert "0.5" in out
    assert "abc-123" in out


if __name__ == "__main__":
    run_smoke_test()
    # Run tiny unit checks
    test_finalize_output_alias()
    test_clean_mode_bypass()
    test_facts_unchanged()
    print("\nAll checks passed.")
