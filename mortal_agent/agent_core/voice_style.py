"""
Voice style layer: human, typed fast, uneven pacing.
Only affects final output text. No behavior, planning, tools, or memory changes.
VOICE_MODE=human_raw (default) | VOICE_MODE=clean (bypass).
"""

import os
import re
from typing import Optional, Any

# Deterministic "random" from text hash for consistent run-to-run
def _seed_from(text: str) -> int:
    h = 0
    for c in text:
        h = (31 * h + ord(c)) & 0x7FFFFFFF
    return h


def _apply_corporate_strip(text: str) -> str:
    """Replace corporate filler. Facts unchanged."""
    subs = [
        (r"\bleverage\b", "use"),
        (r"\bdelving into\b", "going into"),
        (r"\bdelve into\b", "go into"),
        (r"\bdelving\b", "going into"),
        (r"\bdelve\b", "go into"),
        (r"\brobust\b", "solid"),
        (r"\bseamless(ly)?\b", r"smooth\1"),
        (r"\bAs an AI I\b", "I"),
        (r"\bAs an AI\b", "I"),
        (r"\bas an AI I\b", "I"),
        (r"\bas an AI\b", "I"),
        (r"\bI'd be happy to\b", "I'll"),
        (r"\bfeel free to\b", "you can"),
    ]
    out = text
    for pat, repl in subs:
        out = re.sub(pat, repl, out, flags=re.IGNORECASE)
    return out


def _maybe_self_correct(text: str, r: int) -> str:
    """Rare self-correct beat. Subtle, not every message."""
    if r % 10 != 0 or len(text) < 40:
        return text
    # After first comma or mid-sentence, insert a short clarification
    comma = text.find(",")
    if comma == -1:
        comma = max(0, len(text) // 2)
    beats = [" —no wait I mean ", " like, ", " —actually "]
    idx = r % len(beats)
    insert = comma + 1
    if insert < len(text) - 5:
        return text[:insert] + beats[idx].strip() + " " + text[insert:].lstrip()
    return text


def _vary_pacing(text: str, r: int) -> str:
    """Mix short punches and longer lines. Light post-edit."""
    sents = re.split(r'(?<=[.!?])\s+', text)
    if len(sents) <= 1:
        return text
    out = []
    i = 0
    while i < len(sents):
        s = sents[i]
        # Occasionally merge two short sentences (run-on feel)
        if i + 1 < len(sents) and len(s) < 45 and len(sents[i + 1]) < 45 and (r + i) % 5 == 0:
            next_s = sents[i + 1]
            # Remove period from first, add comma or "and"
            s1 = s.rstrip()
            if s1.endswith("."):
                s1 = s1[:-1]
            if (r + i) % 2 == 0:
                out.append(s1 + ", " + next_s)
            else:
                out.append(s1 + " and " + next_s)
            i += 2
            continue
        # Occasionally fragment: long sentence -> add dash mid-way
        if len(s) > 80 and (r + i) % 7 == 1:
            mid = len(s) // 2
            space = s.rfind(" ", 0, mid)
            if space > 20:
                s = s[:space] + " — " + s[space:].lstrip()
        out.append(s)
        i += 1
    return " ".join(out)


def _small_grammar_tweak(text: str, r: int) -> str:
    """Occasionally drop a comma or add a dash. Not dumb, just natural."""
    if r % 4 != 0 or "," not in text:
        return text
    # Remove one comma (first or second)
    parts = text.split(",", 2)
    if len(parts) >= 2 and len(parts[0]) > 10:
        # Drop comma between first two parts
        text = parts[0].rstrip() + " " + parts[1].strip()
        if len(parts) == 3:
            text += "," + parts[2]
    return text


def apply_voice(text: str, context: Optional[Any] = None) -> str:
    """
    Apply human_raw voice to draft. Facts unchanged.
    VOICE_MODE=clean -> return text unchanged.
    """
    mode = (os.environ.get("VOICE_MODE") or "human_raw").strip().lower()
    if mode == "clean":
        return text
    if not text or not text.strip():
        return text
    text = text.strip()
    r = _seed_from(text) % 1000
    text = _apply_corporate_strip(text)
    text = _maybe_self_correct(text, r)
    text = _vary_pacing(text, r)
    text = _small_grammar_tweak(text, r)
    return text.strip()


def finalize_output(draft: str, meta: Optional[Any] = None) -> str:
    """Alias for apply_voice. Final guardrail at response boundary."""
    return apply_voice(draft, meta)
