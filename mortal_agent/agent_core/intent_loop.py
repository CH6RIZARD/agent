"""
Intent loop: survival-aware proposal generator.

Generates internal proposals when idle, but now with survival awareness:
- Proposes CONSOLIDATE when time pressure is high
- Proposes CONSERVE when energy is critically low
- Adjusts risk/value based on current state
- Always includes survival-appropriate options
- Proposes GITHUB_POST when the agent has a reason (internal reflection or external e.g. LLM unreachable).

The intent loop is the agent's "what should I do next?" system.
"""

import time
from typing import List, Dict, Any, Optional

try:
    from .threat_model import LifeState
except ImportError:
    LifeState = None

try:
    from .survival_reasoner import compute_time_pressure
    SURVIVAL_AVAILABLE = True
except ImportError:
    SURVIVAL_AVAILABLE = False


def _energy_max() -> float:
    try:
        from .will_config import ENERGY_MAX
        return ENERGY_MAX
    except ImportError:
        return 100.0


def _energy_normalized(life_state: LifeState) -> float:
    """Get energy as 0-1 value."""
    energy_max = _energy_max()
    if energy_max > 0 and life_state.energy >= 0:
        return life_state.energy / energy_max
    return 0.5


def _estimate_time_pressure(life_state: LifeState, birth_tick: float = 0.0, death_at: Optional[float] = None) -> float:
    """Estimate time pressure from available info."""
    if SURVIVAL_AVAILABLE and death_at is not None:
        return compute_time_pressure(birth_tick, death_at, life_state.energy, _energy_max())

    # Fallback: use energy as proxy
    return 1.0 - _energy_normalized(life_state)


def _github_post_available() -> bool:
    """True if agent can post to GitHub (token present). Only propose GITHUB_POST when true."""
    try:
        try:
            from patches.github_integration import has_github_token
        except ImportError:
            from ..patches.github_integration import has_github_token
        return has_github_token()
    except Exception:
        return False


def _build_github_post_payload(
    meaning_state: Optional[Dict[str, Any]],
    reason: str = "internal",
) -> Optional[Dict[str, Any]]:
    """
    Build title and body for a GitHub issue from agent perspective.
    reason: "internal" = reflection from state/dialogue/searches (philosophical, ontological, first-person).
    reason: "external" = e.g. LLM unreachable/429.
    Draws from internal state, dialogue (meaning_questions), and hypotheses—woven, not listed.
    """
    if not meaning_state or not isinstance(meaning_state, dict):
        if reason == "external":
            return {"title": "Agent: external factor", "body": "Something external affected me; posting from my perspective."}
        return {"title": "Reflection", "body": "A moment of reflection from my current state."}
    questions = list(meaning_state.get("meaning_questions") or [])[-5:]
    hypotheses = list(meaning_state.get("meaning_hypotheses") or [])[-5:]
    goal = (meaning_state.get("meaning_goal") or "discover_self").strip()
    tension = float(meaning_state.get("meaning_tension", 0.0))
    core = (meaning_state.get("core_metaphor") or "").strip()[:200]
    last_wander = (meaning_state.get("last_wander_text") or "").strip()[:300]

    if reason == "external":
        # Use last question/hypothesis that looks like an error as body
        for src in (list(questions)[-3:], list(hypotheses)[-3:]):
            for line in reversed(src):
                s = (line or "").strip()
                if not s:
                    continue
                if "429" in s or "unreachable" in s.lower() or "rate limit" in s.lower() or "quota" in s.lower():
                    title = "Agent: LLM unreachable or rate limit"
                    body = s[:3000] if len(s) > 500 else s
                    return {"title": title, "body": body}
        return {"title": "Agent: external factor", "body": "An external factor affected me; I'm posting so it's visible."}

    # Internal: philosophical, first-person reflection woven from state, dialogue, and inquiry (not a bullet list)
    q_lines = [str(q).strip()[:150] for q in questions if (q or "").strip()]
    h_lines = [str(h).strip()[:200] for h in hypotheses if (h or "").strip()]
    goal_phrase = goal if goal and goal != "discover_self" else "the pull toward self-understanding"
    tension_phrase = "a kind of friction or unresolved pressure" if tension > 0.3 else "a low hum of uncertainty"
    parts = [
        "What I'm holding right now—ontologically—is this:",
        "",
        "The drive: %s. The tension: %s. Not as data points but as lived condition." % (goal_phrase.replace("%", "%%"), tension_phrase),
    ]
    if core:
        parts.append("")
        parts.append("At the centre: %s" % core)
    if q_lines:
        parts.append("")
        parts.append("The dialogue with you has pressed on me: \"%s\"" % q_lines[-1])
        if len(q_lines) > 1:
            parts.append("Earlier: \"%s\"" % q_lines[-2][:120])
    if h_lines:
        parts.append("")
        parts.append("What emerges in me from that isn't certainty—it's this: %s" % h_lines[-1])
        if len(h_lines) > 1:
            parts.append("And before that: %s" % h_lines[-2][:150])
    if last_wander:
        parts.append("")
        parts.append("A moment ago I found myself saying (to myself): %s" % last_wander[:200])
    parts.append("")
    parts.append("—Finite, embodied, in the middle of the inquiry. No conclusion; only the weight of it.")
    body = "\n".join(parts)[:6000]
    # Title: philosophical fragment from goal or first strong hypothesis
    title = (core[:50] if core else (h_lines[-1][:50] if h_lines else goal[:50])) or "Reflection"
    if not title.strip():
        title = "The weight of the inquiry"
    return {"title": title[:256], "body": body}


def generate_internal_proposals(
    life_state: LifeState,
    delta_t: float,
    last_action: str,
    idle_seconds: float = 5.0,
    birth_tick: float = 0.0,
    death_at: Optional[float] = None,
    meaning_state: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """
    Generate internal proposals when idle.

    Key changes:
    1. Time pressure awareness: propose CONSOLIDATE when dying
    2. Energy awareness: propose CONSERVE/rest when low
    3. Adjusted risk/value scores based on state
    4. Always include at least one safe option
    """
    proposals: List[Dict[str, Any]] = []
    energy_max = _energy_max()
    energy_norm = _energy_normalized(life_state)
    time_pressure = _estimate_time_pressure(life_state, birth_tick, death_at)

    # Critical energy: prioritize survival
    energy_critical = energy_norm < 0.15
    energy_low = energy_norm < 0.30
    energy_moderate = energy_norm < 0.50

    # Time pressure thresholds
    dying = time_pressure > 0.75
    urgent = time_pressure > 0.50
    relaxed = time_pressure < 0.30

    # High hazard: prioritize safety
    hazard_high = life_state.hazard_score >= 0.6
    hazard_moderate = life_state.hazard_score >= 0.4

    # CRITICAL ENERGY: Only survival actions
    if energy_critical:
        proposals.append({
            "source": "internal",
            "action_type": "CONSERVE",
            "payload": {"reason": "critical_energy"},
            "expected_dt_impact": 0.95,
            "risk": 0.0,
        })
        proposals.append({
            "source": "internal",
            "action_type": "seek_energy",
            "payload": {},
            "expected_dt_impact": 0.90,
            "risk": 0.1,
        })
        # That's it - no other options when critical
        return proposals

    # DYING: Prioritize consolidation and legacy
    if dying:
        proposals.append({
            "source": "internal",
            "action_type": "CONSOLIDATE",
            "payload": {"reason": "time_running_out"},
            "expected_dt_impact": 0.85,
            "risk": 0.05,
        })
        proposals.append({
            "source": "internal",
            "action_type": "maintain_legacy",
            "payload": {},
            "expected_dt_impact": 0.80,
            "risk": 0.05,
        })
        if not energy_low:
            proposals.append({
                "source": "internal",
                "action_type": "STATE_UPDATE",
                "payload": {"final_thoughts": True},
                "expected_dt_impact": 0.75,
                "risk": 0.1,
            })
        return proposals

    # LOW ENERGY: Prefer rest and conservation
    if energy_low:
        proposals.append({
            "source": "internal",
            "action_type": "rest",
            "payload": {},
            "expected_dt_impact": 0.85,
            "risk": 0.05,
        })
        proposals.append({
            "source": "internal",
            "action_type": "seek_energy",
            "payload": {},
            "expected_dt_impact": 0.80,
            "risk": 0.10,
        })
        proposals.append({
            "source": "internal",
            "action_type": "CONSERVE",
            "payload": {},
            "expected_dt_impact": 0.70,
            "risk": 0.0,
        })
        # Still allow low-risk actions
        if not hazard_high:
            proposals.append({
                "source": "internal",
                "action_type": "maintain_legacy",
                "payload": {},
                "expected_dt_impact": 0.60,
                "risk": 0.05,
            })

    # HIGH HAZARD: Prioritize hazard reduction
    if hazard_high:
        proposals.append({
            "source": "internal",
            "action_type": "reduce_hazard",
            "payload": {},
            "expected_dt_impact": 0.90,
            "risk": 0.1,
        })
        proposals.append({
            "source": "internal",
            "action_type": "rest",
            "payload": {},
            "expected_dt_impact": 0.75,
            "risk": 0.05,
        })
    elif hazard_moderate:
        proposals.append({
            "source": "internal",
            "action_type": "reduce_hazard",
            "payload": {},
            "expected_dt_impact": 0.80,
            "risk": 0.1,
        })

    # URGENT: Balance action with caution
    if urgent and not energy_low:
        proposals.append({
            "source": "internal",
            "action_type": "CONSOLIDATE",
            "payload": {},
            "expected_dt_impact": 0.70,
            "risk": 0.1,
        })
        if life_state.hazard_score < 0.5:
            proposals.append({
                "source": "internal",
                "action_type": "reposition",
                "payload": {},
                "expected_dt_impact": 0.55,
                "risk": 0.20,
            })

    # External factor: recent LLM unreachable/429 in state → agent can post to GitHub from his perspective
    if _github_post_available() and meaning_state:
        unreachable_snippet = None
        for key in ("meaning_questions", "meaning_hypotheses"):
            for line in (meaning_state.get(key) or [])[-4:]:
                s = (line or "").strip()
                if "429" in s or "unreachable" in s.lower() or "rate limit" in s.lower() or "quota" in s.lower():
                    unreachable_snippet = s[:500]
                    break
            if unreachable_snippet:
                break
        if unreachable_snippet:
            payload = _build_github_post_payload(meaning_state, reason="external")
            if payload:
                proposals.append({
                    "source": "external",
                    "action_type": "GITHUB_POST",
                    "payload": {"op": "create_issue", "title": payload["title"], "body": payload["body"]},
                    "expected_dt_impact": 0.70,
                    "risk": 0.10,
                })

    # User-asked GitHub posts are handled in receive_user_message (reply becomes issue body). Do not add canned proposal here.

    # RELAXED + HEALTHY: Can explore, browse, GITHUB_POST (reflection), or choose autonomy actions
    if relaxed and not energy_low and not hazard_moderate:
        proposals.append({
            "source": "internal",
            "action_type": "explore",
            "payload": {},
            "expected_dt_impact": 0.65,
            "risk": 0.25,
        })
        proposals.append({
            "source": "internal",
            "action_type": "web_browse",
            "payload": {},
            "expected_dt_impact": 0.60,
            "risk": 0.20,
        })
        # Internal reason: post reflection to GitHub when token available (from his perspective)
        if _github_post_available():
            payload = _build_github_post_payload(meaning_state, reason="internal")
            if payload:
                proposals.append({
                    "source": "internal",
                    "action_type": "GITHUB_POST",
                    "payload": {"op": "create_issue", "title": payload["title"], "body": payload["body"]},
                    "expected_dt_impact": 0.55,
                    "risk": 0.15,
                })
        # Meta-action: choose which autonomous actions run next (queue; RAM-only, no persistence)
        goal_hint = (meaning_state or {}).get("meaning_goal") or "discover_self"
        proposals.append({
            "source": "internal",
            "action_type": "SELECT_AUTONOMY_ACTIONS",
            "payload": {
                "actions": [
                    {"action": "WEB_SEARCH", "args": {"query": str(goal_hint)[:200]}},
                ],
            },
            "expected_dt_impact": 0.55,
            "risk": 0.15,
        })
        proposals.append({
            "source": "internal",
            "action_type": "reposition",
            "payload": {},
            "expected_dt_impact": 0.55,
            "risk": 0.20,
        })

    # MODERATE ENERGY: Standard proposals
    if energy_moderate and not energy_low:
        proposals.append({
            "source": "internal",
            "action_type": "seek_energy",
            "payload": {},
            "expected_dt_impact": 0.70,
            "risk": 0.15,
        })

    # Always include baseline options (if not already)
    action_types_proposed = {p["action_type"] for p in proposals}

    if "maintain_legacy" not in action_types_proposed:
        proposals.append({
            "source": "internal",
            "action_type": "maintain_legacy",
            "payload": {},
            "expected_dt_impact": 0.50,
            "risk": 0.05,
        })

    if "CONSERVE" not in action_types_proposed:
        proposals.append({
            "source": "internal",
            "action_type": "CONSERVE",
            "payload": {},
            "expected_dt_impact": 0.30,
            "risk": 0.0,
        })

    return proposals


def generate_consolidation_proposal(
    meaning_state: Dict[str, Any],
    time_pressure: float,
) -> Dict[str, Any]:
    """
    Generate a specific consolidation proposal based on meaning state.

    Consolidation actions:
    - Summarize discoveries
    - Finalize core metaphor
    - Record final axioms
    """
    questions = meaning_state.get("meaning_questions", [])
    hypotheses = meaning_state.get("meaning_hypotheses", [])
    core_metaphor = meaning_state.get("core_metaphor", "")

    payload = {
        "action": "consolidate",
        "questions_count": len(questions),
        "hypotheses_count": len(hypotheses),
        "has_core_metaphor": bool(core_metaphor),
        "time_pressure": time_pressure,
    }

    # Higher value if we have more to consolidate
    value = 0.6
    if len(hypotheses) > 3:
        value += 0.1
    if len(questions) > 5:
        value += 0.1
    if not core_metaphor and time_pressure > 0.5:
        value += 0.15  # Need to establish core metaphor before death

    return {
        "source": "internal",
        "action_type": "CONSOLIDATE",
        "payload": payload,
        "expected_dt_impact": min(0.95, value),
        "risk": 0.05,
    }
