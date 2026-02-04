"""
Intent loop: survival-aware proposal generator.

Generates internal proposals when idle, but now with survival awareness:
- Proposes CONSOLIDATE when time pressure is high
- Proposes CONSERVE when energy is critically low
- Adjusts risk/value based on current state
- Always includes survival-appropriate options

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

    # RELAXED + HEALTHY: Can explore and browse (fetch/search chosen by will kernel or autonomy fetch prompt)
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
