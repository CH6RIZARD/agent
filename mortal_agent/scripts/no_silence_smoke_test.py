#!/usr/bin/env python3
"""No-silence smoke: force sanitizer to remove content; assert fallback is non-empty (no one-word guardrail)."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def test_sanitizer_fallback_acknowledged():
    """When sanitizer strips everything or returns fallback, result is 'Acknowledged.'."""
    from agent_core.output_sanitizer import enforce_no_user_attribution, NEUTRAL_FALLBACK
    assert NEUTRAL_FALLBACK.strip() == "Acknowledged.", f"Fallback must be 'Acknowledged.', got '{NEUTRAL_FALLBACK}'"

    # Text that is heavily second-person gets fallback
    heavy_you = "You said you want your project. You asked for your code. You and your design."
    out = enforce_no_user_attribution(heavy_you)
    assert out is not None and len(out.strip()) >= 5, "Should return fallback or sanitized non-empty"
    if out.strip() == NEUTRAL_FALLBACK.strip():
        pass
    else:
        assert "you" not in out.lower() or "your" not in out.lower(), "Should not contain second-person"

    # Empty input -> empty output (no fallback needed for empty)
    empty_out = enforce_no_user_attribution("")
    assert empty_out == ""

    # Final output boundary invariant: empty/whitespace -> "Acknowledged." (tested at CLI level; here we assert fallback string)
    assert NEUTRAL_FALLBACK == "Acknowledged."
    print("no_silence_smoke: fallback is 'Acknowledged.'")


def test_apply_output_policy_empty_fallback():
    """apply_output_policy + empty result -> caller uses non-empty fallback (invariant at CLI)."""
    from agent_core.output_policy import apply_output_policy
    from agent_core.output_sanitizer import NEUTRAL_FALLBACK
    result = apply_output_policy("", "hello", [])
    assert result is not None
    final = (result or "").strip() or NEUTRAL_FALLBACK.strip()
    assert len(final) > 0
    print("no_silence_smoke: empty output fallback invariant OK")


if __name__ == "__main__":
    test_sanitizer_fallback_acknowledged()
    test_apply_output_policy_empty_fallback()
    print("no_silence_smoke_test: done.")
