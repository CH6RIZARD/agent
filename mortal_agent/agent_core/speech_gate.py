"""
Speech Suppression Gate: runs BEFORE any text is produced.
Outputs whether to speak, reason, max_words, and style_profile.
"""

from dataclasses import dataclass
from typing import Any, Dict, Optional

from .output_medium import (
    OUTPUT_MEDIUM_DEFAULT,
    SUPPRESSED_MEDIA,
    EXPRESSIVE_MEDIA,
    normalize_output_medium,
)

# Silence token when gate says should_speak=False (per spec)
SILENCE_TOKEN = "…"


@dataclass
class GateResult:
    should_speak: bool
    speak_reason: str
    max_words: int
    style_profile: str


# Threshold: state delta must exceed this to force speak in suppressed media (e.g. energy/tension change)
STATE_DELTA_THRESHOLD = 0.12
# Seconds since last spoke below which we treat as "no new state delta" for heartbeat
HEARTBEAT_MIN_INTERVAL = 20.0


def speech_suppression_gate(
    internal_state: Dict[str, Any],
    narrator_context: Dict[str, Any],
    output_medium: str = OUTPUT_MEDIUM_DEFAULT,
    *,
    explicit_user_prompt: bool = False,
    time_critical: bool = False,
    loop_trigger: Optional[str] = None,
) -> GateResult:
    """
    Gate runs before text production.

    Inputs:
      internal_state: energy, tension, uncertainty, last_spoke_ts, cooldown, loop_trigger, etc.
      narrator_context: ideology snippets, source snippets, last outputs, constraints
      output_medium: chat | status | log | github | social | longform

    Outputs:
      should_speak: false if no new state delta AND not time-critical AND medium is chat/status/log
                    true if state delta exceeds threshold OR medium is github/social/longform OR explicit user prompt
      speak_reason: short label
      max_words: chat/status/log 25 default 60 emergency; github/longform 800; social 250
      style_profile: compressed_philosopher | expressive_structured
    """
    medium = normalize_output_medium(output_medium)
    is_suppressed = medium in SUPPRESSED_MEDIA
    is_expressive = medium in EXPRESSIVE_MEDIA

    # max_words by medium
    if medium == "social":
        max_words = 250
    elif medium in ("github", "longform"):
        max_words = 800
    else:
        # chat, status, log: default 25, emergency 60
        max_words = 25

    # style_profile
    if is_suppressed:
        style_profile = "compressed_philosopher"
    else:
        style_profile = "expressive_structured"

    # should_speak logic
    if explicit_user_prompt:
        if is_suppressed:
            max_words = 60  # emergency cap for direct user ask
        return GateResult(
            should_speak=True,
            speak_reason="prompted",
            max_words=max_words,
            style_profile=style_profile,
        )

    if is_expressive:
        return GateResult(
            should_speak=True,
            speak_reason="expressive_medium",
            max_words=max_words,
            style_profile=style_profile,
        )

    if time_critical:
        max_words = 60
        return GateResult(
            should_speak=True,
            speak_reason="time_critical",
            max_words=max_words,
            style_profile=style_profile,
        )

    # Suppressed media: need state delta or heartbeat_minimal
    last_spoke_ts = internal_state.get("last_spoke_ts") or 0.0
    now = internal_state.get("now_ts") or last_spoke_ts
    time_since_spoke = now - last_spoke_ts if last_spoke_ts else 999.0

    # State delta: compare current vs last observed state
    energy = internal_state.get("energy")
    tension = internal_state.get("tension")
    uncertainty = internal_state.get("uncertainty")
    last_energy = narrator_context.get("last_energy")
    last_tension = narrator_context.get("last_tension")
    last_uncertainty = narrator_context.get("last_uncertainty")

    state_delta = 0.0
    if energy is not None and last_energy is not None:
        state_delta = max(state_delta, abs(float(energy) - float(last_energy)))
    if tension is not None and last_tension is not None:
        state_delta = max(state_delta, abs(float(tension) - float(last_tension)))
    if uncertainty is not None and last_uncertainty is not None:
        state_delta = max(state_delta, abs(float(uncertainty) - float(last_uncertainty)))

    if state_delta >= STATE_DELTA_THRESHOLD:
        return GateResult(
            should_speak=True,
            speak_reason="state_delta",
            max_words=max_words,
            style_profile=style_profile,
        )

    # Heartbeat minimal: long silence, allow one short utterance
    if time_since_spoke >= HEARTBEAT_MIN_INTERVAL and loop_trigger in ("wander", "heartbeat", "presence", None):
        return GateResult(
            should_speak=True,
            speak_reason="heartbeat_minimal",
            max_words=25,
            style_profile=style_profile,
        )

    # No new state delta, not time-critical, suppressed medium -> don't speak
    return GateResult(
        should_speak=False,
        speak_reason="suppressed_no_delta",
        max_words=max_words,
        style_profile=style_profile,
    )


def gate_result_for_reply(
    output_medium: str,
    internal_state: Optional[Dict[str, Any]] = None,
    narrator_context: Optional[Dict[str, Any]] = None,
    explicit_user_prompt: bool = True,
) -> GateResult:
    """Convenience: gate for a direct user reply (always allowed to speak; max_words/style by medium)."""
    return speech_suppression_gate(
        internal_state or {},
        narrator_context or {},
        output_medium,
        explicit_user_prompt=explicit_user_prompt,
    )
