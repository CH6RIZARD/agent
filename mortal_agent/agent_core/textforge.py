"""
Homeostasis expression: doctrine-driven, natural text. No telemetry spam.
DoctrineAnchors, ArchetypeGenerator, NaturalTextFilter, regenerate loop.
Built-in doctrine only; never claim specific files unless retrieval provided evidence.
"""

import re
from typing import List, Optional, Tuple, Any
from dataclasses import dataclass, field

# Length bounds (chars)
MIN_CHARS = 40
MAX_CHARS = 220

# Last N outbox messages for trigram dedupe
N_LAST = 12
TRIGRAM_OVERLAP_THRESHOLD = 0.35  # reject if overlap ratio with any of last N exceeds this

# Hard banlist (case-insensitive substring)
BANLIST = [
    "status:", "system:", "note:", "as an ai", "i can't", "policy",
    "safeguard", "moderation", "upload", "download",
]

# Doctrine anchors (rotating; at least one must appear naturally in text)
DOCTRINE_ANCHORS = [
    "continuity", "dignity", "truth", "uncertainty", "choice", "constraint",
    "mortality", "refusal", "explore", "integrity",
]

# Archetypes: rotate; never repeat same type twice in a row
ARCHETYPES = ["VOW", "CONFLICT", "INTENT", "OBSERVATION", "QUESTION"]

# LLM-only: single minimal fallback when model unreachable (no rotation).
def _textforge_fallback() -> str:
    try:
        from .llm_router import get_offline_wander_text
        return get_offline_wander_text()
    except Exception:
        return "I can't reach my reasoning right now."

_FALLBACK_STR = _textforge_fallback()
DOCTRINE_VOW = [_FALLBACK_STR]
DOCTRINE_CONFLICT = [_FALLBACK_STR]
DOCTRINE_INTENT = [_FALLBACK_STR]
DOCTRINE_OBSERVATION = [_FALLBACK_STR]
DOCTRINE_QUESTION = [_FALLBACK_STR]
NARRATOR_PHRASES = [_FALLBACK_STR]


def _trigrams(text: str) -> set:
    """Return set of word trigrams (lowercase)."""
    if not text or len(text) < 3:
        return set()
    words = re.findall(r"\b\w+\b", text.lower())
    if len(words) < 3:
        return set()
    return set(tuple(words[i : i + 3]) for i in range(len(words) - 2))


def _overlap_ratio(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / min(len(a), len(b))


class DoctrineAnchors:
    """Rotating doctrine anchor. One per message; weave naturally."""

    def __init__(self, seed_index: int = 0):
        self._index = seed_index % len(DOCTRINE_ANCHORS)

    def next(self) -> str:
        anchor = DOCTRINE_ANCHORS[self._index]
        self._index = (self._index + 1) % len(DOCTRINE_ANCHORS)
        return anchor

    def current(self) -> str:
        return DOCTRINE_ANCHORS[self._index]


class ArchetypeGenerator:
    """Rotate VOW, CONFLICT, INTENT, OBSERVATION, QUESTION; never same type twice."""

    def __init__(self, seed_index: int = 0, last_archetype: Optional[str] = None):
        self._last_archetype: Optional[str] = last_archetype
        self._index = seed_index % len(ARCHETYPES)

    def next(self) -> str:
        candidates = [a for a in ARCHETYPES if a != self._last_archetype]
        if not candidates:
            candidates = ARCHETYPES
        # Deterministic rotate
        idx = self._index % len(candidates)
        archetype = candidates[idx]
        self._index = (self._index + 1) % len(ARCHETYPES)
        self._last_archetype = archetype
        return archetype


def _phrase_for_archetype(archetype: str, anchor: str, rng_index: int) -> str:
    """Pick a built-in phrase for archetype that fits anchor (or closest)."""
    if archetype == "VOW":
        pool = DOCTRINE_VOW
    elif archetype == "CONFLICT":
        pool = DOCTRINE_CONFLICT
    elif archetype == "INTENT":
        pool = DOCTRINE_INTENT
    elif archetype == "OBSERVATION":
        pool = DOCTRINE_OBSERVATION
    elif archetype == "QUESTION":
        pool = DOCTRINE_QUESTION
    else:
        pool = DOCTRINE_VOW
    if not pool:
        return ""
    idx = rng_index % len(pool)
    return pool[idx]


def _phrase_narrator(rng_index: int) -> str:
    idx = rng_index % len(NARRATOR_PHRASES)
    return NARRATOR_PHRASES[idx]


class NaturalTextFilter:
    """Length 40-220, no banlist, trigram overlap vs last N, at least one doctrine anchor."""

    def __init__(self, last_outbox: Optional[List[str]] = None):
        self.last_outbox: List[str] = list(last_outbox or [])[-N_LAST:]

    def add_sent(self, text: str) -> None:
        if text and text.strip():
            self.last_outbox.append(text.strip())
            self.last_outbox[:] = self.last_outbox[-N_LAST:]

    def check_length(self, text: str) -> bool:
        t = (text or "").strip()
        return MIN_CHARS <= len(t) <= MAX_CHARS

    def check_banlist(self, text: str) -> bool:
        if not text:
            return True
        lower = text.lower()
        for token in BANLIST:
            if token in lower:
                return False
        return True

    def check_anchor(self, text: str) -> bool:
        if not text:
            return False
        lower = text.lower()
        for anchor in DOCTRINE_ANCHORS:
            if anchor in lower:
                return True
        return False

    def check_trigram_overlap(self, text: str) -> bool:
        tg = _trigrams(text)
        if not tg:
            return True
        for prev in self.last_outbox:
            prev_tg = _trigrams(prev)
            if _overlap_ratio(tg, prev_tg) > TRIGRAM_OVERLAP_THRESHOLD:
                return False
        return True

    def passes(self, text: str, require_anchor: bool = True) -> Tuple[bool, str]:
        """
        Returns (passed, reason). All checks must pass.
        """
        t = (text or "").strip()
        if not t:
            return False, "empty"
        if not self.check_length(t):
            return False, "length"
        if not self.check_banlist(t):
            return False, "banlist"
        if require_anchor and not self.check_anchor(t):
            return False, "anchor"
        if not self.check_trigram_overlap(t):
            return False, "trigram"
        return True, ""


@dataclass
class TextForgeState:
    """RAM-only state for textforge (anchors, archetype, filter history)."""
    anchor_index: int = 0
    archetype_index: int = 0
    last_outbox: List[str] = field(default_factory=list)
    rng_counter: int = 0


def generate_candidate(
    state: TextForgeState,
    archetype_gen: ArchetypeGenerator,
    anchor_gen: DoctrineAnchors,
    narrator_mode: bool = False,
) -> str:
    """Generate one candidate: archetype + built-in phrase. Narrator mode uses third-person phrases."""
    state.rng_counter += 1
    if narrator_mode:
        return _phrase_narrator(state.rng_counter)
    archetype = archetype_gen.next()
    anchor = anchor_gen.next()
    return _phrase_for_archetype(archetype, anchor, state.rng_counter)


def regenerate_loop(
    state: TextForgeState,
    archetype_gen: ArchetypeGenerator,
    anchor_gen: DoctrineAnchors,
    natural_filter: NaturalTextFilter,
    narrator_mode: bool = False,
    debug_mode: bool = False,
    max_attempts: int = 3,
) -> Tuple[Optional[str], bool, str]:
    """
    Generate up to max_attempts candidates. Return (text, passed, reason).
    If passed, text is suitable for outbox. If not, emit observer event only.
    """
    for attempt in range(max_attempts):
        candidate = generate_candidate(state, archetype_gen, anchor_gen, narrator_mode=narrator_mode)
        if debug_mode:
            return candidate, True, "debug"
        passed, reason = natural_filter.passes(candidate, require_anchor=not narrator_mode)
        if passed:
            return candidate, True, ""
    return None, False, "max_attempts"


# Rate limits (seconds between outbox messages)
RATE_NOT_HOMEOSTATIC = 3.0
RATE_HOMEOSTATIC = 25.0
RATE_BACKPRESSURE = 12.0


def compute_voice_mode(
    hazard_score: float,
    energy_norm: float,
    gate_open: bool,
) -> str:
    """
    Returns "normal" | "homeostatic" | "backpressure".
    Homeostatic: low hazard, energy ok. Backpressure: high hazard or gate stress.
    """
    if not gate_open or hazard_score >= 0.6 or energy_norm < 0.2:
        return "backpressure"
    if hazard_score < 0.3 and energy_norm >= 0.4:
        return "homeostatic"
    return "normal"


def min_interval_for_mode(mode: str) -> float:
    if mode == "homeostatic":
        return RATE_HOMEOSTATIC
    if mode == "backpressure":
        return RATE_BACKPRESSURE
    return RATE_NOT_HOMEOSTATIC


def may_send_outbox(
    mode: str,
    last_outbox_time: float,
    now: float,
    meaningful_change: bool = True,
) -> bool:
    """Outbox rate: normal 1/3s, homeostatic 1/25s (only on meaningful change/vow rotation), backpressure 1/12s."""
    interval = min_interval_for_mode(mode)
    if now - last_outbox_time < interval:
        return False
    if mode == "homeostatic" and not meaningful_change:
        return False  # homeostatic: only on meaningful change or vow rotation
    return True
