"""
Attention / salience filter: choose what deserves processing time based on:
novelty, importance to active goals, risk/cost, unresolved uncertainty.
"""

from typing import Any, Dict, List, Optional

from .goal_hierarchy import GoalHierarchy


def salience(
    item: Dict[str, Any],
    active_goals: List[Any],
    recent_items: List[Dict[str, Any]],
    uncertainty: float = 0.5,
) -> float:
    """
    Salience score in [0, 1]. Higher = more deserving of processing.
    Factors: novelty, importance to active goals, risk/cost, unresolved uncertainty.
    """
    score = 0.0
    # Novelty: not in recent
    key = item.get("key") or item.get("id") or str(item.get("summary", ""))[:80]
    is_new = not any((r.get("key") or r.get("id") or "") == key for r in (recent_items or [])[-20:])
    if is_new:
        score += 0.3
    # Importance to active goals
    summary = (item.get("summary") or item.get("description") or "").lower()
    goal_text = " ".join((getattr(g, "description", "") or str(g) for g in (active_goals or []))).lower()
    if goal_text and summary and any(w in summary for w in goal_text.split() if len(w) > 3):
        score += 0.35
    # Risk/cost: higher salience for moderate risk (don't ignore, don't over-focus on trivial)
    risk = item.get("risk") or item.get("cost_risk") or 0.0
    if isinstance(risk, str):
        risk = 0.5 if risk == "medium" else (0.2 if risk == "low" else 0.8)
    if 0.2 <= risk <= 0.6:
        score += 0.2
    elif risk > 0.6:
        score += 0.25
    # Unresolved uncertainty
    if uncertainty > 0.5:
        score += 0.2
    elif uncertainty > 0.3:
        score += 0.1
    return min(1.0, score)


def select_by_salience(
    items: List[Dict[str, Any]],
    goal_hierarchy: Optional[GoalHierarchy] = None,
    recent: Optional[List[Dict[str, Any]]] = None,
    uncertainty: float = 0.5,
    top_k: int = 5,
) -> List[Dict[str, Any]]:
    """Return items sorted by salience (highest first), capped to top_k."""
    goals = goal_hierarchy.active_strategic() if goal_hierarchy else []
    recent = recent or []
    scored = [(item, salience(item, goals, recent, uncertainty)) for item in items]
    scored.sort(key=lambda x: -x[1])
    return [x[0] for x in scored[:top_k]]
