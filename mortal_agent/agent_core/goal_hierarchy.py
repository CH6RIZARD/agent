"""
Goal hierarchy manager: drives → strategic goals → tactical objectives → immediate actions.
Goal drift: initial objectives evolve based on what is learned about world/self.
RAM only.
"""

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

# Top-level drives (must include)
DRIVE_CURIOSITY = "self_directed_curiosity"
DRIVE_CONSEQUENCE = "consequence_awareness"   # budget/reputation/time
DRIVE_COHERENCE = "self_coherence"            # avoid contradictions
DRIVE_SURVIVAL = "survival_pressure"          # avoid early death, preserve continuity

DEFAULT_DRIVE_WEIGHTS = {
    DRIVE_CURIOSITY: 0.4,
    DRIVE_CONSEQUENCE: 0.25,
    DRIVE_COHERENCE: 0.2,
    DRIVE_SURVIVAL: 0.15,
}

MAX_STRATEGIC = 10
MAX_TACTICAL = 20
MAX_ACTIONS_QUEUE = 15


@dataclass
class StrategicGoal:
    id: str
    description: str
    drive: str
    created_tick: float
    priority: float = 0.5
    active: bool = True


@dataclass
class TacticalObjective:
    id: str
    description: str
    strategic_id: str
    created_tick: float
    done: bool = False
    outcome: Optional[str] = None


@dataclass
class ImmediateAction:
    description: str
    tactical_id: Optional[str] = None
    low_risk: bool = False
    created_tick: float = 0.0


@dataclass
class GoalHierarchy:
    """
    Drives → strategic goals → tactical objectives → immediate actions.
    Goal drift: update strategic/tactical from learned state.
    """
    drive_weights: Dict[str, float] = field(default_factory=lambda: dict(DEFAULT_DRIVE_WEIGHTS))
    strategic_goals: List[StrategicGoal] = field(default_factory=list)
    tactical_objectives: List[TacticalObjective] = field(default_factory=list)
    actions_queue: List[ImmediateAction] = field(default_factory=list)
    current_tick: float = 0.0

    def set_tick(self, t: float) -> None:
        self.current_tick = t

    def add_strategic(self, description: str, drive: str = DRIVE_CURIOSITY, priority: float = 0.5) -> Optional[str]:
        if len(self.strategic_goals) >= MAX_STRATEGIC:
            return None
        gid = f"s_{len(self.strategic_goals)}_{int(time.monotonic() * 1000)}"
        self.strategic_goals.append(StrategicGoal(
            id=gid, description=(description or "")[:300], drive=drive, created_tick=self.current_tick, priority=priority
        ))
        return gid

    def add_tactical(self, description: str, strategic_id: str) -> Optional[str]:
        if len(self.tactical_objectives) >= MAX_TACTICAL:
            return None
        tid = f"t_{len(self.tactical_objectives)}_{int(time.monotonic() * 1000)}"
        self.tactical_objectives.append(TacticalObjective(
            id=tid, description=(description or "")[:300], strategic_id=strategic_id, created_tick=self.current_tick
        ))
        return tid

    def enqueue_action(self, description: str, tactical_id: Optional[str] = None, low_risk: bool = False) -> None:
        if len(self.actions_queue) >= MAX_ACTIONS_QUEUE:
            self.actions_queue.pop(0)
        self.actions_queue.append(ImmediateAction(
            description=(description or "")[:200], tactical_id=tactical_id, low_risk=low_risk, created_tick=self.current_tick
        ))

    def mark_tactical_done(self, tactical_id: str, outcome: str = "") -> None:
        for t in self.tactical_objectives:
            if t.id == tactical_id:
                t.done = True
                t.outcome = (outcome or "")[:200]
                break

    def drift_from_learning(self, learned_objective: str, learned_constraint: str) -> None:
        """Goal drift: evolve strategic goals from learned world/self."""
        if not learned_objective or not learned_objective.strip():
            return
        # Optionally add or adjust a strategic goal from learning
        for g in self.strategic_goals:
            if g.active and learned_constraint and learned_constraint.lower() in g.description.lower():
                g.priority = max(0.2, g.priority - 0.05)  # demote if constraint conflicts
        # Could add new strategic from learned_objective here
        if len(self.strategic_goals) < MAX_STRATEGIC and learned_objective.strip():
            self.add_strategic(learned_objective[:300], drive=DRIVE_COHERENCE, priority=0.4)

    def next_action(self) -> Optional[ImmediateAction]:
        if not self.actions_queue:
            return None
        return self.actions_queue.pop(0)

    def active_strategic(self) -> List[StrategicGoal]:
        return [g for g in self.strategic_goals if g.active][-5:]

    def pending_tactical(self) -> List[TacticalObjective]:
        return [t for t in self.tactical_objectives if not t.done][-10:]
