"""
Third-person looped calculated perspective voice.
Internal narrator: observational, self-monitoring. RAM only. Not persisted.
Output still goes through executor (action JSON). This is runtime cognition + narration.

Wander text filtered by narrator state: energy, hazard, gate, confidence.
Used by wander_step (launch, /wander) and autonomy.
"""

import time
import random
from typing import Optional, Any, Dict

# LLM-only: minimal fallback when model unreachable (single line, no rotation).
def _unreachable_fallback() -> str:
    try:
        from .llm_router import get_offline_wander_text
        return get_offline_wander_text()
    except Exception:
        return "I can't reach my reasoning right now."

# Single phrase for narrator proposal pool when no LLM (no rotation).
_NARRATOR_FALLBACK_PHRASE = "No new observation."


def derive_mood_line(
    energy: float,
    tension: float,
    confidence: float,
    gate_open: bool,
    hazard: float,
) -> str:
    """One short first-person mood sentence from state. Deterministic thresholds. No metaphors."""
    # Runtime passes energy 0-1; life_state may pass raw (0..ENERGY_MAX)
    if energy <= 1.0:
        energy_norm = energy
    else:
        try:
            from .will_config import ENERGY_MAX
            energy_max = float(ENERGY_MAX) if ENERGY_MAX else 100.0
        except Exception:
            energy_max = 100.0
        energy_norm = energy / energy_max if energy_max > 0 else 0.5
    if hazard >= 0.6:
        return "I'm cautious."
    if not gate_open:
        return "I'm cautious."
    if energy_norm < 0.2:
        return "I'm low energy."
    if tension >= 0.6:
        return "I'm strained."
    if confidence < 0.3:
        return "I'm uncertain."
    if tension >= 0.35:
        return "I feel a little tense."
    return "I feel steady."


def _snippets_from_ideology(docs: Optional[str], max_chars: int = 200) -> list:
    """Extract short non-empty lines from ideology source for narrator/wander."""
    if not docs or not isinstance(docs, str) or not docs.strip():
        return []
    lines = [ln.strip() for ln in docs.replace("\r", "\n").split("\n") if ln.strip() and len(ln.strip()) >= 10]
    out = []
    total = 0
    for ln in lines:
        if total >= max_chars:
            break
        head = ln[: max_chars - total].strip()
        if head:
            out.append(head)
            total += len(head)
    return out[:5]


def _looks_like_code(text: str) -> bool:
    """Skip chunks that are code, comments, or HTML, not prose."""
    if not text or len(text) < 15:
        return True
    t = text.strip()
    if t.startswith(("#", "//", "/*", "*", "return ", "def ", "import ", "class ", "if __", "from ", "<")):
        return True
    if "charset" in t or "viewport" in t:
        return True
    if "self." in t and "(" in t and ")" in t:
        return True
    # Skip comment-style lines (# NOTHING, // never reset, etc.)
    first_word = t.split(None, 1)[0] if t.split() else ""
    if first_word.startswith("#") or first_word.startswith("//"):
        return True
    # Prefer prose: mostly letters/spaces
    letters = sum(1 for x in t if x.isalpha() or x.isspace())
    if letters < len(t) * 0.5:
        return True
    return False


def _chunks_from_docs(docs: str, max_chars: int = 180) -> list:
    """Paragraph-like chunks from docs, excluding headers, paths, and code. For degraded explanation."""
    if not docs or not isinstance(docs, str) or not docs.strip():
        return []
    raw = docs.replace("\r", "\n").strip()
    chunks = [c.strip() for c in raw.split("\n\n") if c.strip() and len(c.strip()) > 20]
    out = []
    for c in chunks:
        if c.startswith(("##", "#", "//", "/*")) or "Path:" in c or "From source:" in c or "Seen mediums:" in c or c.startswith("**File:**"):
            continue
        if _looks_like_code(c):
            continue
        if len(c) > max_chars:
            c = c[: max_chars - 3].rsplit(" ", 1)[0] + "..." if " " in c[: max_chars - 3] else c[: max_chars - 3] + "..."
        out.append(c)
    return out[:15]


# State-grounded degraded templates (varied; first-person). Anti-repeat vs last_wander.
# Only used for degraded / no-llm; includes the explicit unreachable line so agent can say it there.
_DEGRADED_STATE_TEMPLATES = [
    "I can't reach my reasoning right now.",
    "My reasoning is offline; I feel tense.",
    "Low energy. I'm still here.",
    "Gate is closed; I'm cautious.",
    "I'm here; my reasoning is offline.",
    "Uncertain. I'm still present.",
    "Low energy; I remain.",
    "I'm cautious while offline.",
    "Tension present. I'm still here.",
    "Reasoning offline. I feel steady.",
    "I'm strained but present.",
]


def build_degraded_explanation(
    meaning_state: Optional[Dict[str, Any]],
    source_context: Optional[str],
    life_state: Any,
    for_chat: bool = False,
    max_words: Optional[int] = None,
) -> str:
    """When LLM unreachable: ideology/source snippet or state-grounded varied line. No single repeated constant.
    If max_words set (Speech Gate), trim result to that word count."""
    out = ""
    # 1) Ideology/source: sampled short line if available
    if source_context and isinstance(source_context, str) and source_context.strip():
        snippets = _snippets_from_ideology(source_context, max_chars=120)
        if snippets:
            line = random.choice(snippets).strip()
            if line and len(line) >= 10 and not _looks_like_code(line):
                out = line[:200]
        if not out:
            chunks = _chunks_from_docs(source_context, max_chars=100)
            if chunks:
                line = random.choice(chunks).strip()
                if line and len(line) >= 10 and not _looks_like_code(line):
                    out = line[:200]
    # 2) State-grounded varied templates; anti-repeat vs last_wander_text
    if not out:
        last_wander = (meaning_state or {}).get("last_wander_text") or ""
        candidates = [t for t in _DEGRADED_STATE_TEMPLATES if (t or "").strip() != (last_wander or "").strip()]
        if not candidates:
            candidates = list(_DEGRADED_STATE_TEMPLATES)
        out = random.choice(candidates)
    if max_words is not None and max_words > 0:
        words = out.split()
        if len(words) > max_words:
            out = " ".join(words[:max_words]).rstrip()
    return out


def get_wander_text_filtered_by_state(
    life_state: Any,
    turn_count: int = 0,
    meaning_state: Optional[Dict[str, Any]] = None,
    meaning_goal: str = "discover_self",
    trigger_medium: str = "system",
    ideology_docs: Optional[str] = None,
    max_words: Optional[int] = None,
) -> str:
    """
    Wander text when LLM unavailable: honest degraded line only (no doc-as-speech).
    max_words: optional cap from Speech Suppression Gate.
    """
    return build_degraded_explanation(
        meaning_state, ideology_docs or "", life_state, for_chat=False, max_words=max_words
    )


def narrate(
    instance_id: str,
    delta_t: float,
    energy: float,
    confidence: float,
    reflex_pending: bool,
    gate_open: bool,
    last_intent: str = "",
    meaning_state: Optional[Dict[str, Any]] = None,
) -> str:
    """
    Produce third-person observation string for current state.
    Used for planner context or internal loop. Not written to disk.
    """
    parts = [
        f"Instance {instance_id[:8]}... at Δt={delta_t:.1f}s.",
        f"Energy {energy:.2f}. Confidence {confidence:.2f}.",
        "Reflex pending." if reflex_pending else "No reflex.",
        "Gate open." if gate_open else "Gate closed.",
    ]
    if last_intent:
        parts.append(f"Last intent: {last_intent}.")
    # include discovered constraints / learnings from meaning_state when available
    tension = 0.0
    try:
        if meaning_state and isinstance(meaning_state, dict):
            mt = meaning_state.get("meaning_tension")
            if mt is not None:
                tension = float(mt)
                parts.append(f"Tension {tension:.2f}.")
            cm = meaning_state.get("core_metaphor")
            if cm:
                parts.append(f"Core metaphor: {cm}.")
            # constraints: if present, surface them
            cons = meaning_state.get("constraints")
            if cons:
                parts.append(f"Constraints: {cons}.")
    except Exception:
        pass
    mood = derive_mood_line(energy, tension, confidence, gate_open, 0.0)
    parts.append(mood)
    return " ".join(parts)


def generate_narrator_bias(
    life_state: Any,
    meaning_state: Optional[Dict[str, Any]] = None,
    influence_level: float = 0.0,
    rng: Optional[Any] = None,
) -> Dict[str, Any]:
    """
    Return a lightweight narrator bias describing tone, focus, weight and seed_phrases.
    This is intended as a harmless bias object that can be attached to planner/textforge
    contexts. It does not itself execute actions.
    When rng is provided (e.g. HolyRNG), shuffle is deterministic; else uses random.shuffle.
    """
    energy = getattr(life_state, "energy", 100.0) or 100.0
    hazard = getattr(life_state, "hazard_score", 0.0) or 0.0
    tension = 0.0
    try:
        tension = float((meaning_state or {}).get("meaning_tension", 0.0))
    except Exception:
        tension = 0.0

    tone = "neutral"
    try:
        from .will_config import ENERGY_MAX
        energy_max = ENERGY_MAX if ENERGY_MAX else 100.0
    except Exception:
        energy_max = 100.0
    energy_norm = energy / energy_max if energy_max > 0 else 0.5

    if hazard >= 0.6:
        tone = "cautious"
    elif energy_norm < 0.2 or tension > 0.6:
        tone = "conservative"
    elif tension < 0.2:
        tone = "curious"

    focus = (meaning_state or {}).get("meaning_goal", "discover_self")
    # seed phrases - LLM-only: single fallback when no LLM
    pool = [_NARRATOR_FALLBACK_PHRASE]
    if rng is not None and hasattr(rng, "shuffle"):
        rng.shuffle(pool)
    else:
        random.shuffle(pool)
    # increase seed count and phrase length as influence_level increases
    seed_count = 3 + int(max(0, min(5, round(influence_level * 5))))
    seed_phrases = pool[:max(3, seed_count)]

    # raise weight with both tension and influence level to bias planner
    weight = max(0.05, min(0.98, 0.15 + float(tension) * 0.6 + float(influence_level) * 0.25))

    return {"tone": tone, "focus": focus, "weight": weight, "seed_phrases": seed_phrases}


def generate_narrator_proposal(
    life_state: Any,
    meaning_state: Optional[Dict[str, Any]],
    delta_t: float,
    last_intent: str,
    influence_level: float = 0.0,
    source_context: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """
    Optionally propose a low-risk action. Possible proposals: NET_FETCH, PUBLISH_POST, STATE_UPDATE.
    Proposals are advisory and must be vetted by the will kernel. Keep proposals low-frequency and low-risk.
    source_context (ideology/docs) can supply a URL for NET_FETCH when meaning_state has no hint.
    """
    try:
        import re
        # Simple heuristics: if hazard low and tension moderate, suggest a fetch; sometimes suggest a micro-post
        hazard = getattr(life_state, "hazard_score", 0.0) or 0.0
        energy = getattr(life_state, "energy", 100.0) or 100.0
        try:
            from .will_config import ENERGY_MAX
            energy_max = ENERGY_MAX if ENERGY_MAX else 100.0
        except Exception:
            energy_max = 100.0
        energy_norm = energy / energy_max if energy_max > 0 else 0.5
        tension = float((meaning_state or {}).get("meaning_tension", 0.0) or 0.0)

        # Throttle: only propose when not high hazard and sufficient energy (normalized)
        if hazard < 0.7 and energy_norm > 0.08:
            # scale probabilities by influence_level
            influence_bonus = max(0.0, min(0.9, float(influence_level)))
            # increased chance to propose a fetch when tension high
            if tension > 0.4 and random.random() < (0.35 + 0.35 * influence_bonus):
                hint = None
                try:
                    hint = (meaning_state or {}).get("last_medium_hint")
                except Exception:
                    hint = None
                url = hint
                if not url and isinstance(source_context, str) and source_context.strip():
                    urls = re.findall(r"https?://[\w\-./?&=%#]+", source_context)
                    if urls:
                        url = urls[0]
                if not url:
                    # No hardcoded fallback; only propose fetch when URL comes from environment
                    return None
                return {
                    "source": "narrator",
                    "action_type": "NET_FETCH",
                    "payload": {"url": url},
                    # more favorable: higher expected impact, lower risk
                    "expected_dt_impact": 0.75 + 0.15 * influence_bonus,
                    "risk": max(0.01, 0.12 - 0.08 * influence_bonus),
                }

            # small chance to suggest a low-risk post
            # higher chance to suggest a low-risk post, scaled by influence
            if random.random() < (0.08 + 0.4 * influence_bonus):
                phrase = (meaning_state or {}).get("core_metaphor") or "A wandering lens observes."
                # optionally embellish phrase when influence high
                if influence_bonus > 0.5:
                    phrase = phrase + " " + _NARRATOR_FALLBACK_PHRASE
                return {
                    "source": "narrator",
                    "action_type": "PUBLISH_POST",
                    "payload": {"text": phrase},
                    "expected_dt_impact": 0.45 + 0.35 * influence_bonus,
                    "risk": max(0.01, 0.08 - 0.05 * influence_bonus),
                }

            # small chance to nudge internal state
            if random.random() < (0.04 + 0.2 * influence_bonus):
                return {
                    "source": "narrator",
                    "action_type": "STATE_UPDATE",
                    "payload": {"meaning_goal": (meaning_state or {}).get("meaning_goal", "discover_self"), "narrator_bias": {"influence_level": influence_level}},
                    "expected_dt_impact": 0.15 + 0.2 * influence_bonus,
                    "risk": max(0.01, 0.03 - 0.02 * influence_bonus),
                }
    except Exception:
        return None
    return None
