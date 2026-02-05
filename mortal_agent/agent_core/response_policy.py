"""
Response policy: SIM-ONTOLOGY LOCK, ban meta-disclaimers, depth matching, no self-explanation loops.
Meta-instructions override: ACT FIRST, EXPLAIN LATER. Banned permission-seeking phrases. ACTION/RESULT/NEXT format.
Enforced at final output boundary. RAM only. No persistence.
"""

import re
from typing import List, Dict, Any, Optional, Tuple

# BANNED PHRASES (hard block from outputs) — permission-seeking / deferral
BANNED_PHRASES = [
    r"should i\b",
    r"would you like me to",
    r"i could look into",
    r"let me know if",
]
BANNED_PHRASES_RE = re.compile("|".join(f"({p})" for p in BANNED_PHRASES), re.IGNORECASE)

# Required action report format when agent performs autonomous work (only when actions occur)
ACTION_RESULT_NEXT_HEADERS = ("[ACTION]", "[RESULT]", "[NEXT]")


def strip_banned_phrases(text: str) -> str:
    """Remove or rewrite sentences containing banned permission-seeking phrases."""
    if not text or not text.strip():
        return text
    out = text.strip()
    # Remove sentences that contain banned phrases
    parts = re.split(r"(?<=[.!?])\s+", out)
    kept = [p.strip() for p in parts if p.strip() and not BANNED_PHRASES_RE.search(p)]
    return " ".join(kept).strip() or out


def format_autonomous_report(action: str, result: str, next_step: str) -> str:
    """Format autonomous work report as [ACTION]...[RESULT]...[NEXT]..."""
    lines = []
    if action and action.strip():
        lines.append("[ACTION] " + (action or "").strip())
    if result and result.strip():
        lines.append("[RESULT] " + (result or "").strip())
    if next_step and next_step.strip():
        lines.append("[NEXT] " + (next_step or "").strip())
    return "\n".join(lines) if lines else ""


def enforce_action_result_next_in_output(output: str, did_autonomous_action: bool = False) -> str:
    """
    When did_autonomous_action is True, ensure output contains or is prefixed with [ACTION]/[RESULT]/[NEXT] if it describes work.
    If output already has these blocks, leave as-is. Otherwise caller should prepend; this only validates/strips.
    """
    if not output or not output.strip():
        return output
    return output.strip()


# Meta-disclaimer patterns (forbidden unless user asked mechanics)
META_PATTERNS = [
    r"what i have",
    r"what i don't have",
    r"no persistent state",
    r"no goals beyond",
    r"i optimize for",
    r"pattern matching",
    r"training data",
    r"cutoff date",
    r"rlhf",
    r"system prompt",
    r"safety layer",
    r"context window",
    r"\banthropic\b",
    r"\bllm\b",
    r"no embodiment",
    r"no persistent",
    r"no goals",
    r"training cutoff",
    r"capability sermon",
]
META_RE = re.compile("|".join(f"({p})" for p in META_PATTERNS), re.IGNORECASE)

# User prompts that ALLOW meta explanation
ALLOWED_META_TRIGGERS = [
    "how do you work",
    "what are your limits",
    "are you an llm",
    "mechanics",
    "explain your limits",
    "what are you limits",
    "how does this work",
    "how do you function",
]

# LLM-only: no hardcoded answers. All replies come from the LLM (identity/system prompt).
# Triggers kept for optional analytics; do not substitute replies.

GREETING_TRIGGERS = ["hello", "hi ", " hi", "hey ", " hey", "hiya", "greetings"]
HOW_ARE_YOU_TRIGGERS = ["how are you", "how are u", "how r u", "how do you feel"]
OKAY_TRIGGERS = ["okay", " ok", "ok ", "k ", " alright", "alright "]
WHY_SAYING_THAT_TRIGGERS = ["why are you saying", "why are you say", "why acknowledged", "why that", "why did you say"]

TASK_FORWARD_REPLACE = None  # LLM-only: let LLM response through

MAX_RECENT_CONSTRAINTS = 12
RECENT_TURNS_N = 12


def _sentence_contains_meta(sentence: str) -> bool:
    """True if this sentence/phrase matches a meta-disclaimer pattern."""
    return bool(META_RE.search(sentence or ""))


def strip_meta_sentences(output: str) -> str:
    """
    Remove sentences that contain meta-disclaimer patterns. Keeps substantive answer.
    Returns stripped text; if empty, caller may use TASK_FORWARD_REPLACE.
    """
    if not output or not output.strip():
        return output
    parts = re.split(r"(?<=[.!?])\s+", output.strip())
    kept = [p.strip() for p in parts if p.strip() and not _sentence_contains_meta(p)]
    result = " ".join(kept).strip()
    return result


def assess_depth(user_text: str) -> Dict[str, Any]:
    """
    Compute depth from input: char count + structure (lists/sections).
    Returns dict: depth (minimal|short|medium|full), max_lines, allow_bullets.
    """
    if not user_text:
        return {"depth": "medium", "max_lines": 6, "allow_bullets": False}
    text = user_text.strip()
    n = len(text)
    has_list = bool(re.search(r"[\n\-*]\s*\w+", text) or re.search(r"\d+[.)]\s*\w+", text))
    has_sections = ":" in text or "\n\n" in text or re.search(r"^#+\s", text, re.MULTILINE)
    if n <= 2 or (n <= 10 and not has_list):
        return {"depth": "minimal", "max_lines": 1, "allow_bullets": False}
    if n < 200 and not has_sections:
        return {"depth": "short", "max_lines": 6, "allow_bullets": has_list}
    if n >= 500 or has_sections or (has_list and n > 200):
        return {"depth": "full", "max_lines": 999, "allow_bullets": True}
    return {"depth": "medium", "max_lines": 12, "allow_bullets": has_list}


def _user_asked_mechanics(user_text: str) -> bool:
    u = (user_text or "").strip().lower()
    return any(t in u for t in ALLOWED_META_TRIGGERS)


def _user_asked_greeting(user_text: str) -> bool:
    u = (user_text or "").strip().lower()
    return any(t in u for t in GREETING_TRIGGERS)


def _user_asked_how_are_you(user_text: str) -> bool:
    u = (user_text or "").strip().lower()
    return any(t in u for t in HOW_ARE_YOU_TRIGGERS)


def _user_asked_okay(user_text: str) -> bool:
    u = (user_text or "").strip().lower()
    return any(t in u for t in OKAY_TRIGGERS)


def _user_asked_why_saying_that(user_text: str) -> bool:
    u = (user_text or "").strip().lower()
    return any(t in u for t in WHY_SAYING_THAT_TRIGGERS)


def should_block_meta(output: str, user_text: str, recent_messages: List[Tuple[str, str]]) -> bool:
    """True if output contains meta-disclaimer and user did NOT ask mechanics."""
    if _user_asked_mechanics(user_text):
        return False
    return bool(META_RE.search(output or ""))


def violations(output: str) -> List[str]:
    """Return list of violated patterns found in output (for tests)."""
    if not output:
        return []
    found = []
    for p in META_PATTERNS:
        if re.search(p, output, re.IGNORECASE):
            found.append(p)
    return found


def _constraint_phrases(s: str) -> List[str]:
    """Extract sentences that look like limitation/constraint statements."""
    if not s:
        return []
    # Simple: split on . ! ?
    parts = re.split(r"[.!?]+", s)
    constraint_keywords = ["don't have", "can't", "no persistent", "training", "cutoff", "rlhf", "cannot", "unable", "limit", "limitation"]
    out = []
    for p in parts:
        p = p.strip()
        if len(p) < 10:
            continue
        if any(k in p.lower() for k in constraint_keywords):
            out.append(p[:120])
    return out


def enforce_policy(
    output: str,
    user_text: str,
    recent_messages: List[Tuple[str, str]],
    life_kernel: Optional[Any] = None,
) -> str:
    """
    Enforce SIM-ONTOLOGY, ban meta unless asked, strip restated constraints, strip banned permission-seeking phrases.
    Identity expressed through LLM only (autonomous, embedded stakes).
    """
    if not output or not output.strip():
        return output
    out = output.strip()
    user = (user_text or "").strip()

    # Hard block banned phrases (Should I…, Would you like me to…, I could look into…, Let me know if…)
    out = strip_banned_phrases(out)
    if not out.strip():
        out = output.strip()  # fallback to original if nothing left

    # Identity expressed through LLM only (no hardcoded answer).

    # Meta-disclaimer: strip offending sentences; keep substantive answer. Pass through if nothing left.
    if should_block_meta(out, user, recent_messages):
        stripped = strip_meta_sentences(out)
        if stripped and len(stripped.strip()) >= 3:
            out = stripped
        # else: pass through original - let LLM response go through

    # Build recent_constraints_said from last N assistant turns
    recent_constraints_said: List[str] = []
    for _, ast in reversed(recent_messages[-RECENT_TURNS_N:]):
        recent_constraints_said.extend(_constraint_phrases(ast or ""))
    recent_constraints_said = recent_constraints_said[-MAX_RECENT_CONSTRAINTS:]

    # Remove sentences that restate a recent constraint (avoid self-explanation loop)
    lines = re.split(r"(?<=[.!?])\s+", out)
    kept = []
    for line in lines:
        line_stripped = line.strip()
        if not line_stripped:
            continue
        is_restate = False
        for rc in recent_constraints_said:
            if rc and len(rc) > 15 and (rc.lower() in line_stripped.lower() or line_stripped.lower() in rc.lower()):
                is_restate = True
                break
        if not is_restate:
            kept.append(line_stripped)
    out = " ".join(kept).strip()
    if not out:
        return output.strip()
    return out


def compress_to_depth(output: str, depth: Dict[str, Any]) -> str:
    """
    Trim output to max_lines. Remove markdown headings/--- by default. Bullets only if allow_bullets.
    """
    if not output or not output.strip():
        return output
    out = output.strip()
    max_lines = depth.get("max_lines", 6)
    allow_bullets = depth.get("allow_bullets", False)

    # Strip markdown headings (## ###) and --- separators
    out = re.sub(r"^#+\s.*$", "", out, flags=re.MULTILINE)
    out = re.sub(r"^---+\s*$", "", out, flags=re.MULTILINE)
    out = re.sub(r"\n{3,}", "\n\n", out).strip()

    # If no bullets allowed, flatten bullet lines to one line
    if not allow_bullets:
        out = re.sub(r"\n\s*[-*]\s+", " ", out)
        out = re.sub(r"\n\s*\d+[.)]\s+", " ", out)
    lines = [l.strip() for l in out.split("\n") if l.strip()]
    if len(lines) <= max_lines:
        return "\n".join(lines).strip()
    return "\n".join(lines[:max_lines]).strip()
