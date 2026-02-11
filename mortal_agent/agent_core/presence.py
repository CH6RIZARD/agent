"""
Presence: continuous expression layer.

Expression is conditional: either a concrete plan/action or a presence line, or silence.
Presence lines are first-person, ≤25 words, grounded in exactly one internal state signal
(energy, tension, hazard, confidence, time-passing). No filler; only when a real internal
signal exists. Return empty string when no meaningful signal (silence is valid).
"""

from typing import Optional, Dict, Any, List

MAX_WORDS = 25


def _energy_normalized(life_state: Any, raw_energy: float) -> float:
    if life_state is None or raw_energy <= 1.0:
        return min(1.0, max(0.0, float(raw_energy)))
    try:
        from .will_config import ENERGY_MAX
        m = float(ENERGY_MAX) if ENERGY_MAX else 100.0
        return raw_energy / m if m > 0 else 0.5
    except Exception:
        return 0.5


def _phrase_energy(value: float) -> str:
    if value < 0.2:
        return "My energy is low."
    if value < 0.45:
        return "I notice my energy is modest."
    if value < 0.7:
        return "My energy feels adequate."
    return "I have enough energy for now."


def _phrase_tension(value: float) -> str:
    if value < 0.2:
        return "Tension is low right now."
    if value < 0.5:
        return "I feel some tension building."
    if value < 0.75:
        return "Tension is noticeable."
    return "I feel the tension."


def _phrase_hazard(value: float) -> str:
    if value < 0.2:
        return "Hazard feels minimal."
    if value < 0.45:
        return "I sense a little hazard."
    if value < 0.65:
        return "I'm aware of hazard."
    return "I'm cautious; hazard is up."


def _phrase_confidence(value: float) -> str:
    if value < 0.25:
        return "I'm uncertain."
    if value < 0.5:
        return "My confidence is modest."
    if value < 0.75:
        return "I feel somewhat sure."
    return "I feel steady."


def _phrase_time_passing(delta_t: float) -> str:
    if delta_t < 30:
        return "Time is just starting."
    if delta_t < 120:
        return "A little time has passed."
    if delta_t < 600:
        return "I notice time passing."
    return "Time keeps moving."


def _word_count(s: str) -> int:
    return len((s or "").strip().split())


def get_presence_line(
    life_state: Optional[Any],
    meaning_state: Optional[Dict[str, Any]],
    runtime_state: Optional[Any],
    delta_t: float = 0.0,
    recent_lines: Optional[List[str]] = None,
    rng: Optional[Any] = None,
) -> str:
    """
    One first-person presence line grounded in exactly one internal state signal.
    ≤20 words; varies by rotating signal and value-driven phrasing.
    """
    recent = list(recent_lines or [])[-10:]
    signals = []

    if life_state is not None:
        try:
            e_raw = getattr(life_state, "energy", 0.5) or 0.5
            e_norm = _energy_normalized(life_state, e_raw)
            signals.append(("energy", _phrase_energy(e_norm)))
        except Exception:
            pass
        try:
            h = float(getattr(life_state, "hazard_score", 0.0) or 0.0)
            signals.append(("hazard", _phrase_hazard(min(1.0, max(0.0, h)))))
        except Exception:
            pass

    if meaning_state and isinstance(meaning_state, dict):
        try:
            t = float(meaning_state.get("meaning_tension", 0.0) or 0.0)
            signals.append(("tension", _phrase_tension(min(1.0, max(0.0, t)))))
        except Exception:
            pass

    if runtime_state is not None:
        try:
            c = float(getattr(runtime_state, "confidence", 0.5) or 0.5)
            signals.append(("confidence", _phrase_confidence(min(1.0, max(0.0, c)))))
        except Exception:
            pass

    signals.append(("time_passing", _phrase_time_passing(delta_t)))

    # Silence when no meaningful signal (do not speak to fill silence).
    if not signals:
        return ""

    # Vary: prefer a signal whose recent phrase we haven't just used (by rotation)
    idx = int(delta_t) % len(signals)
    if rng is not None and hasattr(rng, "random"):
        idx = int(rng.random() * len(signals)) % len(signals)
    _, line = signals[idx]

    if _word_count(line) > MAX_WORDS:
        words = line.strip().split()[:MAX_WORDS]
        line = " ".join(words)
    line = line.strip() or ""
    # Allow silence when only generic time/placeholder would be said (do not speak to fill silence).
    if line and line in ("Time is just starting.", "A little time has passed.", "I'm here."):
        return ""
    return line
