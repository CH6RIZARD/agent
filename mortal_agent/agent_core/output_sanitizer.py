"""
Output sanitizer: reduce user-attribution that implies the agent is addressing a "user" object.
STRUCTURAL: The controller is addressed as "you" (identity: "You are the controller").
So we do NOT rewrite "you" -> "the request" in controller-directed phrases (what would you like, how can I help you).
We only rewrite user-attribution phrases (you said, the user said, your project) to neutral forms.
"""

import re
from typing import List, Dict, Any, Tuple

# Fallback when sanitization would require too much rewriting
NEUTRAL_FALLBACK = None  # Let caller handle - no canned fallback

# Threshold: if replacement count exceeds this fraction of words, use fallback
FALLBACK_REPLACE_RATIO = 0.45

# User-attribution only: "User said", "the user", "your project" etc. Controller is "you" per identity—do not rewrite "you" globally.
SECOND_PERSON_PATTERNS = []  # Disabled: addressing controller as "you" is correct
USER_NEUTRAL_PATTERNS = [
    (r"\bUser\b", "The input"),
    (r"\buser\b", "the input"),
]

# Attribution-only: "the user" / "User" -> "you" (controller). Do NOT rewrite "you"/"your" when addressing controller.
PHRASE_REPLACEMENTS = [
    ("the user", "you"),
    ("User said", "You said"),
    ("User asked", "You asked"),
    ("User sent single word", "You sent a short message"),
]

# Detection: only attribution phrases we rewrite
PHRASE_DETECT = [re.compile(re.escape(phrase), re.IGNORECASE) for phrase, _ in PHRASE_REPLACEMENTS]
USER_ATTRIBUTION_PHRASES = PHRASE_REPLACEMENTS
USER_PHRASE_DETECT = PHRASE_DETECT
DETECT_PATTERNS = []  # Addressing controller as "you" is correct; no global you-detection


def contains_second_person(text: str) -> bool:
    """True if text contains attribution phrases we rewrite (the user, User said, etc.)."""
    if not text or not text.strip():
        return False
    t = text
    for pat in PHRASE_DETECT:
        if pat.search(t):
            return True
    return False


def _apply_phrase_replacements(text: str) -> Tuple[str, int]:
    """Apply attribution-only replacements (the user -> you, etc.). Return (new_text, count)."""
    out = text
    count = 0
    for phrase, repl in PHRASE_REPLACEMENTS:
        pat = re.compile(re.escape(phrase), re.IGNORECASE)
        new_out, n = pat.subn(repl, out)
        if n:
            count += n
            out = new_out
    return out, count


def _apply_word_replacements(text: str) -> Tuple[str, int]:
    """Apply word-level second-person replacements; return (new_text, count)."""
    out = text
    count = 0
    for pat_str, repl in SECOND_PERSON_PATTERNS:
        pat = re.compile(pat_str, re.IGNORECASE)
        new_out, n = pat.subn(repl, out)
        if n:
            count += n
            out = new_out
    return out, count


def sanitize_second_person(text: str) -> str:
    """
    Remove/replace second-person tokens and attribution clauses. Minimal edit.
    Phrases first, then word-level. Preserves rest of draft.
    """
    if not text or not text.strip():
        return text
    out = text.strip()
    out, _ = _apply_phrase_replacements(out)
    out, _ = _apply_word_replacements(out)
    out = re.sub(r"\s+", " ", out).strip()
    out = re.sub(r"\s+([.,!?])", r"\1", out)
    return out


def sanitizer_report(text: str) -> Dict[str, Any]:
    """
    Return {matches: [...], replaced: int}.
    matches = list of matched substrings/phrases found; replaced = total replacement count.
    """
    if not text or not text.strip():
        return {"matches": [], "replaced": 0}
    matches: List[str] = []
    t = text
    for pat in DETECT_PATTERNS:
        for m in pat.finditer(t):
            matches.append(m.group(0))
    for phrase, _ in USER_ATTRIBUTION_PHRASES:
        if re.search(re.escape(phrase), t, re.IGNORECASE):
            matches.append(phrase)
    for phrase, _ in PHRASE_REPLACEMENTS:
        if re.search(re.escape(phrase), t, re.IGNORECASE):
            matches.append(phrase)
    out_phrase, c1 = _apply_phrase_replacements(t)
    out_word, c2 = _apply_word_replacements(out_phrase)
    return {"matches": list(dict.fromkeys(matches)), "replaced": c1 + c2}


def enforce_no_user_attribution(text: str) -> str:
    """
    Sanitize second-person and user attribution. If too much would be rewritten,
    return neutral fallback. Runs at final output boundary.
    """
    if not text or not text.strip():
        return text
    draft = text.strip()
    report = sanitizer_report(draft)
    if report["replaced"] == 0 and not contains_second_person(draft):
        return draft
    sanitized = sanitize_second_person(draft)
    word_count = len(draft.split())
    if word_count > 0 and report["replaced"] / word_count > FALLBACK_REPLACE_RATIO:
        return draft  # Return original instead of canned fallback
    if not sanitized or len(sanitized.strip()) < 5:
        return draft  # Return original instead of canned fallback
    if contains_second_person(sanitized):
        sanitized = sanitize_second_person(sanitized)
    if contains_second_person(sanitized):
        return draft  # Return original instead of canned fallback
    return sanitized
