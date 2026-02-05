"""
Learning & evolution patches.
- Experience replay buffer: revisit past successes/failures to extract patterns
- Meta-cognitive layer: reflect on own thinking processes, identify cognitive biases, improve reasoning strategies
Session-scoped only; nothing persists after death.
"""

import time
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field

REPLAY_MAX = 80


@dataclass
class ReplayEntry:
    outcome: str  # "success" | "failure" | "neutral"
    action_type: str
    payload: Dict[str, Any]
    result_summary: str
    instance_id: str
    at: float = field(default_factory=time.monotonic)


_replay: List[ReplayEntry] = []


def record_experience(
    outcome: str,
    action_type: str,
    payload: Dict[str, Any],
    result: Dict[str, Any],
    instance_id: str,
) -> None:
    """Append to experience replay buffer for later pattern extraction."""
    summary = (result.get("error") or result.get("note") or "ok")[:200]
    if isinstance(summary, dict):
        summary = str(summary)[:200]
    entry = ReplayEntry(
        outcome=outcome,
        action_type=action_type,
        payload=dict(payload),
        result_summary=summary,
        instance_id=instance_id,
    )
    _replay.append(entry)
    while len(_replay) > REPLAY_MAX:
        _replay.pop(0)


def replay_recent(n: int = 20) -> List[Dict[str, Any]]:
    """Return last n replay entries as dicts (for reflection or training)."""
    out = []
    for e in _replay[-n:]:
        out.append({
            "outcome": e.outcome,
            "action_type": e.action_type,
            "result_summary": e.result_summary,
            "at": e.at,
        })
    return out


def replay_successes(action_type: Optional[str] = None) -> List[Dict[str, Any]]:
    """Filter replay to successes only; optionally by action_type."""
    out = []
    for e in _replay:
        if e.outcome != "success":
            continue
        if action_type and e.action_type != action_type:
            continue
        out.append({"action_type": e.action_type, "result_summary": e.result_summary, "at": e.at})
    return out[-20:]


def meta_reflect(context: Dict[str, Any]) -> Dict[str, Any]:
    """
    Meta-cognitive reflection: reflect on thinking process, surface biases, suggest reasoning improvements.
    Returns { "biases_detected": [], "suggestions": [], "confidence_note": str }.
    """
    biases: List[str] = []
    suggestions: List[str] = []
    recent = replay_recent(10)
    # Repetition bias: same action type too often
    if len(recent) >= 5:
        types = [r.get("action_type") for r in recent]
        if len(set(types)) <= 2:
            biases.append("repetition_bias")
            suggestions.append("vary_action_types")
    # Failure streak
    failures = [r for r in recent if r.get("outcome") == "failure"]
    if len(failures) >= 3:
        biases.append("possible_frustration_loop")
        suggestions.append("try_lower_risk_or_different_approach")
    confidence_note = "ok" if not biases else "review_biases"
    return {
        "biases_detected": biases,
        "suggestions": suggestions,
        "confidence_note": confidence_note,
    }
