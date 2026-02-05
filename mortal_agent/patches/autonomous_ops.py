"""
Autonomous operation patches.
- Task scheduling: decide what to work on when; balance exploration vs exploitation
- Resource budgeting: track API calls, compute costs, time; strategic allocation
- Risk assessment: evaluate actions for rewards vs consequences (wired to will_kernel)
- Self-monitoring / health checks: detect stuck, confused, or suboptimal operation
"""

import time
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field

# Resource budget (RAM only; session-scoped)
@dataclass
class ResourceBudget:
    api_calls_today: int = 0
    api_cap_per_day: int = 500
    compute_cost_units: float = 0.0
    compute_cap_units: float = 100.0
    last_reset_day: str = ""

    def can_spend_api(self, n: int = 1) -> bool:
        return self.api_calls_today + n <= self.api_cap_per_day

    def spend_api(self, n: int = 1) -> bool:
        if not self.can_spend_api(n):
            return False
        self.api_calls_today += n
        return True

    def can_spend_compute(self, units: float) -> bool:
        return self.compute_cost_units + units <= self.compute_cap_units

    def spend_compute(self, units: float) -> bool:
        if not self.can_spend_compute(units):
            return False
        self.compute_cost_units += units
        return True


_budget = ResourceBudget()


def resource_budget() -> ResourceBudget:
    return _budget


def task_schedule(
    proposals: List[Dict[str, Any]],
    life_state: Any,
    meaning_state: Optional[Dict[str, Any]] = None,
    exploration_weight: float = 0.3,
) -> List[Dict[str, Any]]:
    """
    Decide ordering/priority of proposals: balance exploration vs exploitation.
    Does not remove proposals; reorders or tags with suggested_priority.
    """
    if not proposals:
        return []
    # Simple heuristic: higher expected_dt_impact first; inject exploration by boosting low-risk explore
    scored = []
    for i, p in enumerate(proposals):
        impact = float(p.get("expected_dt_impact", 0.5))
        risk = float(p.get("risk", 0.3))
        at = (p.get("action_type") or "")
        if at in ("explore", "web_browse", "WEB_SCRAPE", "RSS_FEED", "WIKI_TRAVERSE"):
            impact += exploration_weight * (1.0 - risk)
        scored.append((impact, risk, i, p))
    scored.sort(key=lambda x: (-x[0], x[1]))
    out = []
    for _, _, _, p in scored:
        out.append(p)
    return out


def risk_assess(
    proposal: Dict[str, Any],
    life_state: Any,
    time_pressure: float = 0.0,
) -> Dict[str, Any]:
    """
    Evaluate potential action for rewards vs consequences. Complements will_kernel.
    Returns { "risk_score", "reward_estimate", "consequence_notes" }.
    """
    risk = float(proposal.get("risk", 0.3))
    value = float(proposal.get("expected_dt_impact", 0.5))
    # Amplify risk when time pressure high
    if time_pressure > 0.6:
        risk = min(1.0, risk * 1.3)
    consequence_notes = []
    if risk > 0.6:
        consequence_notes.append("high_risk_prefer_safer_action")
    if value > 0.7 and risk < 0.4:
        consequence_notes.append("high_value_low_risk")
    return {
        "risk_score": risk,
        "reward_estimate": value,
        "consequence_notes": consequence_notes,
    }


def self_monitor(
    life_kernel: Any,
    last_action: str,
    last_result: Dict[str, Any],
    delta_t: float,
) -> Dict[str, Any]:
    """
    Self-monitoring / health check: detect stuck, confused, or suboptimal.
    Returns { "ok": bool, "signals": [...], "suggestion": str or None }.
    """
    signals: List[str] = []
    suggestion: Optional[str] = None
    if not life_kernel:
        return {"ok": True, "signals": [], "suggestion": None}
    recent = getattr(life_kernel, "recent_actions", []) or []
    # Stuck: same action repeated many times
    if len(recent) >= 5 and len(set(recent[-5:])) == 1:
        signals.append("repeated_action")
        suggestion = "consider_different_action_or_goal"
    # Confused: many refusals
    overrides = getattr(life_kernel, "survival_overrides", 0) or 0
    if overrides > 3:
        signals.append("frequent_survival_overrides")
        suggestion = "conserve_or_reduce_risk"
    # Suboptimal: low energy but still exploring
    energy = getattr(life_kernel, "energy", 100.0)
    if energy < 20 and last_action in ("explore", "web_browse"):
        signals.append("low_energy_exploring")
        suggestion = "conserve_energy"
    ok = len(signals) == 0
    return {"ok": ok, "signals": signals, "suggestion": suggestion}
