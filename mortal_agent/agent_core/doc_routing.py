"""
Doc routing: relevance gate for when to inject base docs into chat.
No agent behavioral logic (life/death/continuity). Only: should this turn use source_context?
Target: ~35% of turns use docs. Anti-spam: cooldown after use unless query strongly triggers.
"""

import re
from typing import List, Tuple

# Cooldown turns after using docs before allowing again (unless high relevance)
DOC_COOLDOWN_TURNS = 1

# Triggers that suggest doc relevance (user likely asking about doctrine, constitution, deploy, etc.)
DOC_RELEVANCE_PATTERNS = [
    r"\b(constitution|doctrine|theology|belief|faith|god|scripture)\b",
    r"\b(deploy|vps|server|hosting|integration|api|build|ci)\b",
    r"\b(how do you work|how does this work|what are your (limits|constraints))\b",
    r"\b(according to|from the doc|in the (text|source|constitution))\b",
    r"\b(debug|troubleshoot|error|fix|broken)\b",
    r"\b(ethical|boundary|allowed|forbidden)\b",
    r"\b(constraint|rule|canon)\b",
]
DOC_RELEVANCE_RE = re.compile("|".join(f"({p})" for p in DOC_RELEVANCE_PATTERNS), re.IGNORECASE)

# Strong triggers: use docs even during cooldown
STRONG_DOC_PATTERNS = [
    r"\b(quote|cite|reference|from (the )?constitution|from (the )?doctrine)\b",
    r"\b(what does (the )?(constitution|doctrine) say)\b",
]
STRONG_DOC_RE = re.compile("|".join(f"({p})" for p in STRONG_DOC_PATTERNS), re.IGNORECASE)


def doc_relevance_score(message: str, recent_turns: List[str]) -> float:
    """
    Score 0.0–1.0 for how relevant base docs are to this turn.
    Based on current message and recent context (last 2 user messages).
    """
    if not message or not message.strip():
        return 0.0
    text = (message + " " + " ".join(recent_turns[-2:])).lower()
    if STRONG_DOC_RE.search(text):
        return 0.95
    if DOC_RELEVANCE_RE.search(text):
        return 0.6
    # Slight baseline so we don't need 100% keyword match
    if len(message.strip()) > 80:
        return 0.15
    return 0.0


def should_use_docs_for_turn(
    message: str,
    recent_turns: List[str],
    cooldown_remaining: int,
    target_fraction: float = 0.35,
    rng_uniform: float = 0.5,
) -> Tuple[bool, int]:
    """
    Decide whether to inject source_context this turn.
    Returns (use_docs: bool, new_cooldown_remaining: int).
    Uses relevance + cooldown + target fraction so over many turns ~35% use docs.
    """
    score = doc_relevance_score(message, recent_turns)
    strong_trigger = score >= 0.9
    if cooldown_remaining > 0 and not strong_trigger:
        return False, max(0, cooldown_remaining - 1)
    # Probabilistic gate: target ~35% of turns use docs (25-45% band)
    use = score >= 0.4 or (score >= 0.05 and rng_uniform < 0.38)
    if use:
        return True, DOC_COOLDOWN_TURNS
    return False, max(0, cooldown_remaining - 1)
