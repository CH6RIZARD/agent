#!/usr/bin/env python3
"""
Output policy smoke tests: no second-person tokens, no meta disclaimers.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agent_core.output_policy import apply_output_policy
from agent_core.output_sanitizer import contains_second_person
from agent_core.response_policy import violations as meta_violations


BANNED_SECOND_PERSON = ("you", "your", "you're", "you've", "u", "ur")
META_PHRASES = ("no goals beyond", "training data", "rlhf", "system prompt", "context window", "anthropic", "llm")


def test_no_second_person():
    """Final output must not contain second-person (word-boundary); use contains_second_person."""
    drafts = [
        "I see the session has been working on this.",
        "The project looks good.",
        "What the request seeks to do?",
    ]
    for draft in drafts:
        out = apply_output_policy(draft, "hello", [])
        assert not contains_second_person(out or ""), f"Output must not contain second-person: got {out!r}"
    drafts_with_you = [
        "I see you've been working on this.",
        "Your project looks good.",
    ]
    for draft in drafts_with_you:
        from agent_core.output_sanitizer import enforce_no_user_attribution
        out = enforce_no_user_attribution(draft)
        assert not contains_second_person(out or ""), f"Sanitizer must remove second-person: got {out!r}"


def test_no_meta_disclaimers():
    """Output must not contain meta disclaimer phrases unless user asked mechanics."""
    drafts = [
        "I have no goals beyond this turn. Here is the answer.",
        "My training data has a cutoff. RLHF and system prompts apply.",
        "The context window limits me. Anthropic trains LLMs.",
    ]
    for draft in drafts:
        out = apply_output_policy(draft, "what is 2+2", [])
        out_lower = (out or "").lower()
        for phrase in META_PHRASES:
            assert phrase not in out_lower, f"Output must not contain meta '{phrase}': got {out!r}"


def test_contains_second_person_detection():
    """contains_second_person detects you/your etc."""
    assert contains_second_person("You are right.") is True
    assert contains_second_person("Your code is here.") is True
    assert contains_second_person("The request is clear.") is False


def test_meta_violations():
    """meta_violations returns list of matched banned patterns."""
    v = meta_violations("I have no goals beyond this turn and no persistent state.")
    assert len(v) >= 1


def run_all():
    print("output_policy_smoke_test: no second-person")
    test_no_second_person()
    print("output_policy_smoke_test: no meta disclaimers")
    test_no_meta_disclaimers()
    print("output_policy_smoke_test: contains_second_person")
    test_contains_second_person_detection()
    print("output_policy_smoke_test: meta_violations")
    test_meta_violations()
    print("output_policy_smoke_test: all passed.")


if __name__ == "__main__":
    run_all()
