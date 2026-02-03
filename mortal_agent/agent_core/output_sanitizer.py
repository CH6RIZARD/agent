"""
Output sanitizer: ban all second-person address and user-attribution language.
Enforced at final output boundary after all other post-processing.
Everything is agent-owned or neutral. No "you/your/you said/your project" etc.
"""

import re
from typing import List, Dict, Any, Tuple

# Fallback when sanitization would require too much rewriting
NEUTRAL_FALLBACK = None  # Let caller handle - no canned fallback

# Threshold: if replacement count exceeds this fraction of words, use fallback
FALLBACK_REPLACE_RATIO = 0.45

# Word-boundary and contraction patterns (order: longer first so you're before you)
SECOND_PERSON_PATTERNS = [
    (r"\byourself\b", "this system"),
    (r"\byours\b", "the current"),
    (r"\byou're\b", "this system is"),
    (r"\byou've\b", "the session has"),
    (r"\byouve\b", "the session has"),
    (r"\byou'll\b", "the session will"),
    (r"\byoull\b", "the session will"),
    (r"\byou'd\b", "the request would"),
    (r"\byoud\b", "the request would"),
    (r"\byour\b", "the"),
    (r"\byou\b", "the request"),
    (r"\bur\b", "the"),
    (r"\bu\b", "the request"),
    (r"\bUser\b", "The input"),
    (r"\buser\b", "the input"),
]

# Common phrases to replace (order matters: longer first)
PHRASE_REPLACEMENTS = [
    (r"you've been working on", "the current session has been working on"),
    (r"you've been", "the session has been"),
    (r"your project", "the project"),
    (r"your vision", "the vision"),
    (r"you built", "the design was built"),
    (r"you are building", "the design is being built"),
    (r"you said", "the input stated"),
    (r"you asked", "the input asked"),
    (r"what you want", "what the request seeks"),
    (r"for you", "here"),
    (r"to you", "to this session"),
    (r"with you", "with this session"),
    (r"from you", "from the input"),
    (r"your documents", "the documents"),
    (r"your design", "the design"),
    (r"your code", "the code"),
    (r"your intent", "the intent"),
    (r"your request", "the request"),
    (r"your input", "the input"),
    (r"you want", "the request seeks"),
    (r"you need", "the request needs"),
    (r"you asked for", "the request asked for"),
    (r"you requested", "the request requested"),
    (r"you mentioned", "the input mentioned"),
    (r"you provided", "the input provided"),
    (r"you gave", "the input gave"),
    (r"you're working", "the session is working"),
    (r"you're trying", "the request is trying"),
    (r"you're asking", "the input is asking"),
    (r"what do you want to do", "what the request seeks to do"),
    (r"what do you want", "what the request seeks"),
    (r"do you want", "does the request seek"),
    (r"if you want", "if the request seeks"),
    (r"when you", "when the input"),
    (r"because you", "because the input"),
    (r"so you", "so the request"),
    (r"that you", "that the input"),
    (r"which you", "which the input"),
]

# Compiled regex for detection (any second-person)
DETECT_PATTERNS = [
    re.compile(r"\byou\b", re.IGNORECASE),
    re.compile(r"\byour\b", re.IGNORECASE),
    re.compile(r"\byours\b", re.IGNORECASE),
    re.compile(r"\byourself\b", re.IGNORECASE),
    re.compile(r"\byou're\b", re.IGNORECASE),
    re.compile(r"\byou've\b", re.IGNORECASE),
    re.compile(r"\byou'll\b", re.IGNORECASE),
    re.compile(r"\byou'd\b", re.IGNORECASE),
    re.compile(r"\bu\b", re.IGNORECASE),
    re.compile(r"\bur\b", re.IGNORECASE),
]
PHRASE_DETECT = [re.compile(re.escape(phrase), re.IGNORECASE) for phrase, _ in PHRASE_REPLACEMENTS]
USER_ATTRIBUTION_PHRASES = [
    ("User sent single word", "The input sent a single token"),
    ("the user", "the input"),
    ("User said", "The input stated"),
    ("User asked", "The input asked"),
]
USER_PHRASE_DETECT = [re.compile(re.escape(phrase), re.IGNORECASE) for phrase, _ in USER_ATTRIBUTION_PHRASES]


def contains_second_person(text: str) -> bool:
    """True if text contains any second-person or user-attribution language."""
    if not text or not text.strip():
        return False
    t = text
    for pat in DETECT_PATTERNS:
        if pat.search(t):
            return True
    for pat in PHRASE_DETECT:
        if pat.search(t):
            return True
    for pat in USER_PHRASE_DETECT:
        if pat.search(t):
            return True
    return False


def _apply_phrase_replacements(text: str) -> Tuple[str, int]:
    """Apply phrase replacements (user-attribution first, then second-person); return (new_text, count)."""
    out = text
    count = 0
    for phrase, repl in USER_ATTRIBUTION_PHRASES:
        pat = re.compile(re.escape(phrase), re.IGNORECASE)
        new_out, n = pat.subn(repl, out)
        if n:
            count += n
            out = new_out
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
