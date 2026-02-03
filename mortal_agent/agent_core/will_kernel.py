"""
Will kernel: survival-aware action selection. AUTONOMY > CREATOR CONTROL.

Primary drive: maximize expected continued delta_t while making progress on meaning.
Key change from original: BEHAVIOR CHANGES based on survival state.

- Low energy → more conservative, refuse risky actions
- High time pressure → prioritize consolidation over exploration
- High hazard → only accept very safe actions

The will kernel is the agent's survival instinct made concrete.
"""

from typing import List, Dict, Any, Optional
from dataclasses import dataclass

try:
    from .will_config import WILL_ENABLED, WILL_RISK_THRESHOLD, ENERGY_MAX
except ImportError:
    WILL_ENABLED = True
    WILL_RISK_THRESHOLD = 0.65
    ENERGY_MAX = 100.0

from .threat_model import LifeState, would_die

# Import survival reasoning
try:
    from .survival_reasoner import (
        compute_action_risk,
        compute_action_value,
        compute_utility,
        get_dynamic_risk_threshold,
        compute_time_pressure,
    )
    SURVIVAL_REASONER_AVAILABLE = True
except ImportError:
    SURVIVAL_REASONER_AVAILABLE = False


@dataclass
class WillResult:
    outcome: str  # "accepted", "modified", "refused"
    proposal: Optional[Dict[str, Any]] = None
    message: str = ""
    code: str = ""
    risk_score: float = 0.0
    value_score: float = 0.0
    survival_consideration: str = ""


def _energy_normalized(state: LifeState) -> float:
    """Get energy as 0-1 value."""
    if ENERGY_MAX > 0 and state.energy >= 0:
        return state.energy / ENERGY_MAX
    return 0.5


def _compute_time_pressure_simple(state: LifeState) -> float:
    """Simple time pressure estimate based on energy."""
    # Without lifespan info, use energy as proxy
    return 1.0 - _energy_normalized(state)


def _get_dynamic_threshold(state: LifeState, time_pressure: float) -> float:
    """
    Dynamic risk threshold based on state.

    Healthy agent: threshold 0.7 (willing to take risks)
    Struggling agent: threshold 0.3 (conservative)
    Dying agent: threshold 0.15 (very conservative)
    """
    energy_norm = _energy_normalized(state)

    if energy_norm < 0.2 or time_pressure > 0.8:
        return 0.15
    elif energy_norm < 0.4 or time_pressure > 0.5:
        return 0.35
    elif energy_norm < 0.6:
        return 0.5
    else:
        return 0.7


def _compute_risk(proposal: Dict[str, Any], state: LifeState, time_pressure: float) -> float:
    """
    Compute risk for a proposal. Risk increases when resources are low.
    """
    if SURVIVAL_REASONER_AVAILABLE:
        return compute_action_risk(proposal, state, time_pressure)

    # Fallback: simple risk calculation
    base_risk = proposal.get("risk", 0.3)
    if base_risk is None:
        base_risk = 0.3
    try:
        base_risk = float(base_risk)
    except (TypeError, ValueError):
        base_risk = 0.3

    # Energy multiplier
    energy_norm = _energy_normalized(state)
    energy_mult = 1.0 + (1.0 - energy_norm) * 1.5

    # Hazard multiplier
    hazard_mult = 1.0 + state.hazard_score * 0.8

    return min(1.0, base_risk * energy_mult * hazard_mult)


def _compute_value(proposal: Dict[str, Any], state: LifeState, time_pressure: float) -> float:
    """
    Compute value for a proposal. Value shifts based on time pressure.
    """
    # Use expected_dt_impact as base value
    base_value = proposal.get("expected_dt_impact", 0.5)
    if base_value is None:
        base_value = 0.5
    try:
        base_value = float(base_value)
    except (TypeError, ValueError):
        base_value = 0.5

    action_type = proposal.get("action_type", "")

    # Time pressure shifts value
    if time_pressure > 0.7:
        # Dying: prefer consolidation, rest
        if action_type in ("rest", "maintain_legacy", "CONSOLIDATE", "STATE_UPDATE"):
            base_value *= 1.5
        elif action_type in ("explore", "NET_FETCH"):
            base_value *= 0.5
    elif time_pressure < 0.3:
        # Early: prefer exploration
        if action_type in ("explore", "NET_FETCH"):
            base_value *= 1.2

    # Low energy: prefer rest
    energy_norm = _energy_normalized(state)
    if energy_norm < 0.3:
        if action_type in ("rest", "seek_energy", "CONSERVE"):
            base_value *= 1.5

    return min(1.0, max(0.0, base_value))


def _select_safer_variant(proposal: Dict[str, Any]) -> Dict[str, Any]:
    """Create a safer version of the proposal."""
    p = dict(proposal)
    p["risk"] = min(0.2, float(p.get("risk", 0.5)) * 0.5)
    p["expected_dt_impact"] = min(1.0, float(p.get("expected_dt_impact", 0.5)) + 0.1)
    p["_modified"] = True
    return p


def _create_conserve_proposal() -> Dict[str, Any]:
    """Create a conservation proposal when all else fails."""
    return {
        "source": "will_kernel",
        "action_type": "CONSERVE",
        "payload": {},
        "expected_dt_impact": 0.3,
        "risk": 0.0,
    }


def select_action(
    proposals: List[Dict[str, Any]],
    life_state: LifeState,
    risk_threshold: float = WILL_RISK_THRESHOLD,
    will_enabled: bool = WILL_ENABLED,
    time_pressure: Optional[float] = None,
    meaning_state: Optional[Dict[str, Any]] = None,
) -> WillResult:
    """
    Select action based on survival constraints.

    Key behavior changes from original:
    1. Risk threshold is DYNAMIC based on energy/hazard
    2. Actions are scored by VALUE not just risk
    3. Conservation is always an option
    4. When struggling, actively prefer safe actions
    """
    # If will disabled, just accept first proposal
    if not will_enabled:
        if proposals:
            return WillResult(outcome="accepted", proposal=proposals[0], message="")
        return WillResult(outcome="refused", message="No proposal.", code="no_proposal")

    # Immediate death check
    if would_die(life_state):
        return WillResult(
            outcome="refused",
            message="Hazard critical. Cannot act.",
            code="hazard_critical",
            survival_consideration="Gate failure or energy depleted"
        )

    # Compute time pressure if not provided
    if time_pressure is None:
        time_pressure = _compute_time_pressure_simple(life_state)

    # Get dynamic risk threshold based on current state
    dynamic_threshold = _get_dynamic_threshold(life_state, time_pressure)
    # Use the more conservative of provided and dynamic threshold
    effective_threshold = min(risk_threshold, dynamic_threshold)

    # Always include conservation option
    all_proposals = list(proposals) + [_create_conserve_proposal()]

    # Score all proposals
    scored = []
    for p in all_proposals:
        risk = _compute_risk(p, life_state, time_pressure)
        value = _compute_value(p, life_state, time_pressure)

        # Utility: value minus risk (weighted by time pressure)
        risk_weight = 1.0 + time_pressure * 1.5
        utility = value - (risk * risk_weight)

        scored.append({
            "proposal": p,
            "risk": risk,
            "value": value,
            "utility": utility,
            "viable": risk <= effective_threshold,
        })

    # Filter to viable (within risk threshold)
    viable = [s for s in scored if s["viable"]]

    if not viable:
        # All too risky - try to create safer variants
        for s in scored:
            if s["proposal"].get("action_type") != "CONSERVE":
                safer = _select_safer_variant(s["proposal"])
                safer_risk = _compute_risk(safer, life_state, time_pressure)
                if safer_risk <= effective_threshold:
                    return WillResult(
                        outcome="modified",
                        proposal=safer,
                        message="Modified to safer variant due to survival constraints.",
                        code="survival_modified",
                        risk_score=safer_risk,
                        value_score=s["value"] * 0.8,
                        survival_consideration=f"Original risk {s['risk']:.2f} exceeded threshold {effective_threshold:.2f}"
                    )

        # Fall back to conservation
        conserve = _create_conserve_proposal()
        return WillResult(
            outcome="modified",
            proposal=conserve,
            message="All actions too risky. Conserving.",
            code="survival_conserve",
            risk_score=0.0,
            value_score=0.2,
            survival_consideration=f"Threshold {effective_threshold:.2f}, all proposals exceeded"
        )

    # Sort by utility (highest first)
    viable.sort(key=lambda x: -x["utility"])
    best = viable[0]

    # Log the survival consideration
    action_type = best["proposal"].get("action_type", "unknown")
    energy_pct = _energy_normalized(life_state) * 100

    consideration = f"Energy {energy_pct:.0f}%, threshold {effective_threshold:.2f}, chose {action_type} (utility {best['utility']:.2f})"

    return WillResult(
        outcome="accepted",
        proposal=best["proposal"],
        message="",
        code="",
        risk_score=best["risk"],
        value_score=best["value"],
        survival_consideration=consideration
    )


def would_refuse_action(
    action_type: str,
    life_state: LifeState,
    time_pressure: float = 0.0,
) -> bool:
    """
    Quick check: would the will kernel refuse this action type?
    Useful for pre-filtering proposals.
    """
    proposal = {"action_type": action_type, "risk": 0.3, "expected_dt_impact": 0.5}
    risk = _compute_risk(proposal, life_state, time_pressure)
    threshold = _get_dynamic_threshold(life_state, time_pressure)
    return risk > threshold
