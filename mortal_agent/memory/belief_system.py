"""
Belief system: tracks which philosophies the agent has discovered and adopted.

Used by discovery_tools and mortal_agent. Beliefs are RAM-only; they inform
prompts and decisions but are not persisted across process restarts (identity invariant).
"""

from typing import Any, Dict, List


def adopted_beliefs_to_source_text(adopted_beliefs: List[Dict[str, Any]]) -> str:
    """
    Build a single source-context string from adopted beliefs for use in prompts.
    Called when building effective source_context so autonomy/chat see only what
    the agent has chosen to adopt.
    """
    if not adopted_beliefs:
        return ""
    parts: List[str] = []
    for b in adopted_beliefs:
        source = b.get("source", "")
        principles = b.get("principles", [])
        if not principles:
            continue
        block = f"[Adopted from {source}]\n" + "\n".join(f"- {p}" for p in principles)
        parts.append(block)
    return "\n\n".join(parts) if parts else ""
