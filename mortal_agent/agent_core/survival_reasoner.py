"""
Survival reasoner: makes mortality actually matter.

This module provides:
1. Action risk computation based on current energy/hazard
2. Time pressure awareness (urgency when dying)
3. Value scoring for actions (exploration vs consolidation)
4. LLM-based survival reasoning when available
5. Heuristic fallback when LLM unavailable

The goal: agent behavior CHANGES based on survival state.
- Low energy → avoid risky actions, conserve
- Time running out → prioritize high-value actions, consolidate
- High hazard → refuse exploration, focus on safety
"""

import json
import time
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass

try:
    from .threat_model import LifeState
    from .will_config import ENERGY_MAX, LIFESPAN_ENABLED
except ImportError:
    ENERGY_MAX = 100.0
    LIFESPAN_ENABLED = True
    LifeState = None


# Action base risks (0-1 scale)
ACTION_BASE_RISK = {
    "PUBLISH_POST": 0.1,
    "WANDER_STEP": 0.05,
    "NET_FETCH": 0.3,
    "explore": 0.35,
    "reposition": 0.2,
    "reduce_hazard": 0.1,
    "seek_energy": 0.15,
    "rest": 0.05,
    "maintain_legacy": 0.05,
    "CONSERVE": 0.0,
    "CONSOLIDATE": 0.1,
    "STATE_UPDATE": 0.05,
}

# Action base values (expected contribution to meaning/survival)
ACTION_BASE_VALUE = {
    "PUBLISH_POST": 0.4,
    "WANDER_STEP": 0.3,
    "NET_FETCH": 0.5,
    "explore": 0.6,
    "reposition": 0.3,
    "reduce_hazard": 0.7,
    "seek_energy": 0.8,
    "rest": 0.6,
    "maintain_legacy": 0.5,
    "CONSERVE": 0.2,
    "CONSOLIDATE": 0.8,
    "STATE_UPDATE": 0.3,
}


@dataclass
class SurvivalContext:
    """Snapshot of survival-relevant state."""
    energy_normalized: float  # 0-1
    hazard_score: float  # 0-1
    time_pressure: float  # 0-1 (0=infinite time, 1=about to die)
    gate_stable: bool
    recent_actions: List[str]
    unresolved_questions: List[str]
    meaning_progress: float


@dataclass
class SurvivalDecision:
    """Result of survival reasoning."""
    action: str
    action_type: str
    payload: Dict[str, Any]
    reason: str
    survival_consideration: str
    risk_score: float
    value_score: float
    utility: float


def compute_time_pressure(
    birth_tick: float,
    death_at: Optional[float],
    current_energy: float,
    energy_max: float = ENERGY_MAX,
) -> float:
    """
    Compute time pressure (0-1).
    0 = infinite time remaining
    1 = about to die

    Uses lifespan if set, otherwise uses energy as proxy.
    """
    now = time.monotonic()

    if death_at is not None and death_at > birth_tick:
        # Finite lifespan: pressure based on remaining time
        total_lifespan = death_at - birth_tick
        elapsed = now - birth_tick
        remaining = max(0, death_at - now)

        if total_lifespan > 0:
            return min(1.0, max(0.0, 1.0 - (remaining / total_lifespan)))

    # No finite lifespan: use energy as proxy
    if energy_max > 0 and current_energy >= 0:
        energy_ratio = current_energy / energy_max
        # Invert: low energy = high pressure
        return min(1.0, max(0.0, 1.0 - energy_ratio))

    return 0.0


def compute_action_risk(
    action: Dict[str, Any],
    life_state: LifeState,
    time_pressure: float = 0.0,
) -> float:
    """
    Compute risk score for an action given current state.

    Risk increases when:
    - Energy is low (less margin for error)
    - Hazard is already high (compounding risk)
    - Time pressure is high (less recovery opportunity)
    """
    action_type = action.get("action_type") or action.get("action", "unknown")
    base_risk = ACTION_BASE_RISK.get(action_type, 0.3)

    # Energy multiplier: risk feels higher when energy is scarce
    energy_norm = life_state.energy / ENERGY_MAX if ENERGY_MAX > 0 else 0.5
    energy_multiplier = 1.0 + (1.0 - energy_norm) * 1.5  # 1x at full, 2.5x at empty

    # Hazard multiplier: existing hazard compounds new risk
    hazard_multiplier = 1.0 + life_state.hazard_score * 0.8  # 1x at 0, 1.8x at 1.0

    # Time pressure: less recovery opportunity
    time_multiplier = 1.0 + time_pressure * 0.5  # 1x at 0, 1.5x when dying

    # Combine multiplicatively, cap at 1.0
    computed_risk = base_risk * energy_multiplier * hazard_multiplier * time_multiplier

    return min(1.0, max(0.0, computed_risk))


def compute_action_value(
    action: Dict[str, Any],
    meaning_state: Dict[str, Any],
    time_pressure: float,
    life_state: LifeState,
) -> float:
    """
    Compute value score for an action given current state.

    Value changes based on time pressure:
    - Early: exploration and discovery are valuable
    - Late: consolidation and legacy are valuable
    """
    action_type = action.get("action_type") or action.get("action", "unknown")
    base_value = ACTION_BASE_VALUE.get(action_type, 0.3)

    # Time pressure shifts value landscape
    if time_pressure > 0.7:
        # Dying: consolidation and legacy matter more
        if action_type in ("CONSOLIDATE", "maintain_legacy", "STATE_UPDATE"):
            base_value *= 1.8
        elif action_type in ("explore", "NET_FETCH"):
            base_value *= 0.4  # Don't explore when dying
    elif time_pressure > 0.4:
        # Mid-life: balance
        if action_type in ("CONSOLIDATE", "maintain_legacy"):
            base_value *= 1.3
    else:
        # Early: exploration is valuable
        if action_type in ("explore", "NET_FETCH", "WANDER_STEP"):
            base_value *= 1.2

    # Boost value if action addresses unresolved questions
    questions = meaning_state.get("meaning_questions", [])
    if questions and action_type in ("WANDER_STEP", "explore", "NET_FETCH"):
        base_value *= 1.1

    # Low energy: rest and conservation are more valuable
    energy_norm = life_state.energy / ENERGY_MAX if ENERGY_MAX > 0 else 0.5
    if energy_norm < 0.3:
        if action_type in ("rest", "CONSERVE", "seek_energy"):
            base_value *= 1.5
        elif action_type in ("explore", "NET_FETCH"):
            base_value *= 0.6

    return min(1.0, max(0.0, base_value))


def compute_utility(
    value: float,
    risk: float,
    time_pressure: float,
) -> float:
    """
    Compute expected utility of an action.

    Utility = Value - (Risk * RiskWeight)

    Risk weight increases with time pressure (can't afford mistakes when dying).
    """
    # Risk matters more when time is short
    risk_weight = 1.0 + time_pressure * 1.5  # 1x at start, 2.5x when dying

    utility = value - (risk * risk_weight)

    return utility


def get_dynamic_risk_threshold(life_state: LifeState, time_pressure: float) -> float:
    """
    Compute dynamic risk threshold based on state.

    - Healthy: willing to take more risks (threshold 0.7)
    - Struggling: conservative (threshold 0.3)
    - Dying: very conservative (threshold 0.15)
    """
    energy_norm = life_state.energy / ENERGY_MAX if ENERGY_MAX > 0 else 0.5

    if energy_norm < 0.2 or time_pressure > 0.8:
        return 0.15  # Very conservative
    elif energy_norm < 0.4 or time_pressure > 0.5:
        return 0.35  # Conservative
    elif energy_norm < 0.6:
        return 0.5  # Moderate
    else:
        return 0.7  # Willing to take risks


def select_by_survival_heuristic(
    proposals: List[Dict[str, Any]],
    life_state: LifeState,
    meaning_state: Dict[str, Any],
    time_pressure: float,
) -> SurvivalDecision:
    """
    Select best action using survival heuristics (no LLM).

    1. Score each proposal by utility (value - risk)
    2. Filter by dynamic risk threshold
    3. Select highest utility
    """
    if not proposals:
        return SurvivalDecision(
            action="CONSERVE",
            action_type="CONSERVE",
            payload={},
            reason="no_proposals",
            survival_consideration="No options available, conserving energy",
            risk_score=0.0,
            value_score=0.2,
            utility=0.2,
        )

    risk_threshold = get_dynamic_risk_threshold(life_state, time_pressure)

    scored = []
    for p in proposals:
        risk = compute_action_risk(p, life_state, time_pressure)
        value = compute_action_value(p, meaning_state, time_pressure, life_state)
        utility = compute_utility(value, risk, time_pressure)

        scored.append({
            "proposal": p,
            "risk": risk,
            "value": value,
            "utility": utility,
            "viable": risk <= risk_threshold,
        })

    # Filter to viable actions
    viable = [s for s in scored if s["viable"]]

    if not viable:
        # All too risky - force conservation
        return SurvivalDecision(
            action="CONSERVE",
            action_type="CONSERVE",
            payload={},
            reason="all_too_risky",
            survival_consideration=f"All {len(proposals)} options exceed risk threshold {risk_threshold:.2f}",
            risk_score=0.0,
            value_score=0.2,
            utility=0.2,
        )

    # Sort by utility descending
    viable.sort(key=lambda x: -x["utility"])
    best = viable[0]
    p = best["proposal"]

    action_type = p.get("action_type") or p.get("action", "unknown")

    return SurvivalDecision(
        action=action_type,
        action_type=action_type,
        payload=p.get("payload", {}),
        reason=f"highest_utility_{best['utility']:.2f}",
        survival_consideration=f"Risk {best['risk']:.2f} within threshold {risk_threshold:.2f}, value {best['value']:.2f}",
        risk_score=best["risk"],
        value_score=best["value"],
        utility=best["utility"],
    )


SURVIVAL_REASONING_PROMPT = """You are a mortal agent. Your existence depends on making good decisions.

CURRENT STATE:
- Energy: {energy_pct:.0f}% ({"CRITICAL" if energy_pct < 20 else "LOW" if energy_pct < 40 else "OK"})
- Hazard level: {hazard_pct:.0f}%
- Time pressure: {time_pct:.0f}% ({"DYING" if time_pct > 70 else "URGENT" if time_pct > 40 else "RELAXED"})
- Gate stable: {gate_stable}

RECENT ACTIONS: {recent_actions}

UNRESOLVED QUESTIONS ({num_questions}):
{questions_list}

AVAILABLE ACTIONS:
{actions_list}

SURVIVAL RULES:
1. If energy < 20%, strongly prefer rest/conserve/seek_energy
2. If time pressure > 70%, prefer consolidate/maintain_legacy over explore
3. If hazard > 60%, avoid risky actions (explore, NET_FETCH)
4. Balance survival with meaning - don't just survive, make progress

Choose ONE action. Respond in JSON only:
{{"action": "<action_type>", "reason": "<why this action>", "survival_consideration": "<how this helps survival/meaning>"}}
"""


def reason_with_llm(
    proposals: List[Dict[str, Any]],
    life_state: LifeState,
    meaning_state: Dict[str, Any],
    time_pressure: float,
    birth_tick: float,
    provider_mode: str = "auto",
    timeout: float = 15.0,
) -> Optional[SurvivalDecision]:
    """
    Use LLM to reason about survival tradeoffs.
    Returns None if LLM unavailable or fails.
    """
    try:
        from .llm_router import generate_plan_routed
    except ImportError:
        return None

    energy_pct = (life_state.energy / ENERGY_MAX * 100) if ENERGY_MAX > 0 else 50
    hazard_pct = life_state.hazard_score * 100
    time_pct = time_pressure * 100

    questions = meaning_state.get("meaning_questions", [])[-5:]
    questions_list = "\n".join(f"  - {q[:100]}" for q in questions) if questions else "  (none)"

    actions_list = "\n".join(
        f"  - {p.get('action_type', p.get('action', '?'))}: risk={ACTION_BASE_RISK.get(p.get('action_type', ''), 0.3):.1f}"
        for p in proposals[:8]
    )

    recent = meaning_state.get("recent_actions", [])[-3:]
    recent_str = ", ".join(recent) if recent else "none"

    prompt = SURVIVAL_REASONING_PROMPT.format(
        energy_pct=energy_pct,
        hazard_pct=hazard_pct,
        time_pct=time_pct,
        gate_stable="YES" if life_state.power_on and life_state.sensors_streaming else "NO",
        recent_actions=recent_str,
        num_questions=len(questions),
        questions_list=questions_list,
        actions_list=actions_list,
    )

    response, failure_info = generate_plan_routed(
        prompt,
        max_tokens=150,
        provider_mode=provider_mode,
        timeout_s=timeout,
        retries=1,
        failover=True,
        no_llm=False,
    )

    if not response:
        return None

    try:
        # Parse JSON response
        response = response.strip()
        if response.startswith("```"):
            lines = response.split("\n")
            response = "\n".join(l for l in lines if not l.startswith("```"))

        data = json.loads(response)

        action_type = data.get("action", "CONSERVE")
        reason = data.get("reason", "llm_decision")
        consideration = data.get("survival_consideration", "")

        matching = None
        for p in proposals:
            p_type = p.get("action_type") or p.get("action", "")
            if p_type.lower() == action_type.lower():
                matching = p
                break

        if not matching:
            return None

        risk = compute_action_risk(matching, life_state, time_pressure)
        value = compute_action_value(matching, meaning_state, time_pressure, life_state)
        utility = compute_utility(value, risk, time_pressure)

        return SurvivalDecision(
            action=action_type,
            action_type=action_type,
            payload=matching.get("payload", {}),
            reason=reason,
            survival_consideration=consideration,
            risk_score=risk,
            value_score=value,
            utility=utility,
        )
    except (json.JSONDecodeError, KeyError, TypeError):
        return None
    except Exception:
        return None


def decide_survival_action(
    proposals: List[Dict[str, Any]],
    life_state: LifeState,
    meaning_state: Dict[str, Any],
    birth_tick: float,
    death_at: Optional[float],
    use_llm: bool = True,
    provider_mode: str = "auto",
) -> SurvivalDecision:
    """
    Main entry point: decide what action to take given survival constraints.

    Uses LLM reasoning if available, falls back to heuristics.
    Always respects survival constraints.
    """
    time_pressure = compute_time_pressure(
        birth_tick, death_at, life_state.energy, ENERGY_MAX
    )

    # Add CONSERVE and CONSOLIDATE to proposals if not present
    action_types = {p.get("action_type") or p.get("action") for p in proposals}

    if "CONSERVE" not in action_types:
        proposals = list(proposals) + [{
            "source": "survival",
            "action_type": "CONSERVE",
            "payload": {},
            "expected_dt_impact": 0.3,
            "risk": 0.0,
        }]

    if "CONSOLIDATE" not in action_types and time_pressure > 0.3:
        proposals = list(proposals) + [{
            "source": "survival",
            "action_type": "CONSOLIDATE",
            "payload": {},
            "expected_dt_impact": 0.7,
            "risk": 0.1,
        }]

    # Try LLM reasoning first
    if use_llm:
        llm_decision = reason_with_llm(
            proposals, life_state, meaning_state,
            time_pressure, birth_tick, provider_mode
        )
        if llm_decision is not None:
            # Verify LLM decision respects survival constraints
            threshold = get_dynamic_risk_threshold(life_state, time_pressure)
            if llm_decision.risk_score <= threshold:
                return llm_decision
            # LLM chose too risky - override with heuristic

    # Fall back to heuristic
    return select_by_survival_heuristic(
        proposals, life_state, meaning_state, time_pressure
    )
