#!/usr/bin/env python3
"""
LLM smoke test: one-line prompt via router; prints provider, first 200 chars, latency, tokens.
Run from mortal_agent: python -m tools.llm_smoke_test
"""
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main():
    print("[llm_smoke_test] Starting...", flush=True)
    try:
        from agent_core.llm_router import generate_reply_routed
    except ImportError as e:
        print(f"[llm_smoke_test] FAIL: {e}", file=sys.stderr)
        return 1

    prompt = "Say hello in exactly one short sentence."
    system = "You are helpful. Reply briefly."
    start = time.perf_counter()
    reply, failure = generate_reply_routed(
        prompt,
        system,
        max_tokens=80,
        source_context=None,
        provider_mode="auto",
        failover=True,
        no_llm=False,
    )
    elapsed = time.perf_counter() - start

    if not reply:
        print("provider: (all failed)")
        print(f"latency_s: {elapsed:.2f}")
        if failure:
            print(f"error: {failure.get('detail', '')[:200]}")
        print(flush=True)
        return 1

    first_200 = (reply or "")[:200]
    print("provider: (success; Claude first, then OpenRouter/OpenAI)")
    print(f"response (first 200 chars): {first_200!r}")
    print(f"latency_s: {elapsed:.2f}")
    print(flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
