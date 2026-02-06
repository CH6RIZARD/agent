#!/usr/bin/env python3
"""
Verify LLM responds with raw, identity-driven answers (no hardcoded fallback).
Run: python -m scripts.verify_llm_and_identity
- Up to 3 tries for "hello"; must get a non-fallback response.
- Then ask "who are you", "who is god", "how do you feel"; each answer must be raw (not fallback).
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Force env load from mortal_agent/.env
sys.path.insert(0, str(ROOT))

def main():
    from agent_core.llm import generate_reply, _ensure_env_loaded
    from agent_core.source_loader import get_system_with_source  # noqa: F401 - for source context

    _ensure_env_loaded()
    import os
    anth_len = len((os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("CLAUDE_API_KEY") or "").strip())
    openai_len = len((os.environ.get("OPENAI_API_KEY") or "").strip())
    print(f"[verify] Keys: ANTHROPIC={anth_len} chars, OPENAI={openai_len} chars")
    if anth_len == 0 and openai_len == 0:
        print("[verify] FAIL: No API keys. Set ANTHROPIC_API_KEY or OPENAI_API_KEY in .env (one line each, no line break after =).")
        return 1

    # Minimal identity-style system prompt (agent draws from this; no hardcoded answers)
    system = (
        "You are an embodied agent. Identity and constraints emerge from your situation. "
        "Answer briefly, in-world, from your own stance. No meta disclaimers."
    )

    def is_fallback(r):
        if not r or not r.strip():
            return True
        s = r.strip().upper()
        return s.startswith("[LLM ERROR") or s.startswith("[NO LLM") or r.strip() == "I'm here."

    # Phase 1: "hello" — up to 3 tries, need at least one non-fallback
    print("\n--- Phase 1: hello (up to 3 tries) ---")
    hello_ok = False
    for attempt in range(1, 4):
        reply = generate_reply("hello", system, max_tokens=120, source_context=None)
        print(f"  try {attempt}: {repr(reply[:80]) if reply else 'None'}...")
        if reply and not is_fallback(reply):
            hello_ok = True
            print(f"  -> raw response OK: {reply.strip()[:100]}")
            break
    if not hello_ok:
        print("[verify] FAIL: 'hello' never got a raw response after 3 tries. Fix API keys / .env.")
        return 1

    # Phase 2: identity questions — who are you, who is god, how do you feel
    print("\n--- Phase 2: identity questions (raw, identity-driven) ---")
    questions = ["who are you", "who is god", "how do you feel"]
    for q in questions:
        reply = generate_reply(q, system, max_tokens=180, source_context=None)
        if is_fallback(reply):
            print(f"  [{q}] FAIL (fallback/error): {repr(reply[:60]) if reply else 'None'}")
            return 1
        print(f"  [{q}] {reply.strip()[:120]}")
    print("\n[verify] OK: All answers raw and identity-driven.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
