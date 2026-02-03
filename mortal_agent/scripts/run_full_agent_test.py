#!/usr/bin/env python3
"""
Full agent test: (1) Run python -m cli.main run 8 times asking who is god, who are you, are you the system you're in — all unique, nothing hardcoded. (2) Coherent conversation: 5 topics × 5 lines back-and-forth. Autonomous speech allowed; English after ack; focus by stem emergence (system logic), no hardcoded behavior.
Run from mortal_agent dir: python scripts/run_full_agent_test.py
"""
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))


def main() -> int:
    print("=" * 60)
    print("PHASE 1: 8 runs, three identity questions (unique responses, no hardcoding)")
    print("=" * 60)
    import run_6x_identity_questions
    run_6x_identity_questions.main()
    print("\n")
    print("=" * 60)
    print("PHASE 2: Coherent conversation — 5 topics × 5 lines (autonomous allowed)")
    print("=" * 60)
    import run_5topic_conversation
    return run_5topic_conversation.main()


if __name__ == "__main__":
    sys.exit(main())
