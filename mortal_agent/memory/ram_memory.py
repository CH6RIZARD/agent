"""
Multi-tier memory system (RAM only). No disk persistence. Resets on restart.

- Working memory: current context, constraints, recent user messages, current objective
- Episodic memory: timestamped experiences/events/decisions/outcomes
- Semantic memory: learned facts/concepts/relationships extracted during run
- Procedural memory: strategies that worked ("when X then Y" learned in-run)

Experience Replay Buffer: periodically revisit episodes, extract patterns.
Meta-Cognitive Layer: reflect on failures/biases, adjust strategy weights.
"""

import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

# Bounds (RAM only)
MAX_WORKING_RECENT = 20
MAX_EPISODIC = 200
MAX_SEMANTIC = 150
MAX_PROCEDURAL = 80
REPLAY_BATCH = 10
META_COGNITIVE_INTERVAL_TICKS = 15


@dataclass
class WorkingMemory:
    """Current context, constraints, recent user messages, current objective."""
    current_objective: str = ""
    current_constraints: List[str] = field(default_factory=list)
    recent_user_messages: deque = field(default_factory=lambda: deque(maxlen=MAX_WORKING_RECENT))
    recent_context: deque = field(default_factory=lambda: deque(maxlen=32))
    tick: float = 0.0

    def push_user_message(self, msg: str) -> None:
        if msg and msg.strip():
            self.recent_user_messages.append((time.monotonic(), (msg or "").strip()[:500]))

    def set_objective(self, obj: str) -> None:
        self.current_objective = (obj or "").strip()[:300]

    def set_constraints(self, constraints: List[str]) -> None:
        self.current_constraints = [(c or "")[:200] for c in (constraints or [])][-10:]

    def push_context(self, text: str) -> None:
        if text and text.strip():
            self.recent_context.append((time.monotonic(), (text or "").strip()[:300]))

    def snapshot(self) -> Dict[str, Any]:
        return {
            "objective": self.current_objective,
            "constraints": list(self.current_constraints),
            "recent_user": list(self.recent_user_messages)[-5:],
            "recent_context": list(self.recent_context)[-5:],
            "tick": self.tick,
        }


@dataclass
class Episode:
    ts: float
    tick: float
    event_type: str
    summary: str
    outcome: str
    decision: Optional[str] = None
    cost_risk: Optional[str] = None


@dataclass
class EpisodicMemory:
    """Timestamped experiences/events/decisions/outcomes."""
    episodes: List[Episode] = field(default_factory=list)

    def add(self, tick: float, event_type: str, summary: str, outcome: str, decision: Optional[str] = None, cost_risk: Optional[str] = None) -> None:
        self.episodes.append(Episode(
            ts=time.monotonic(), tick=tick, event_type=event_type, summary=(summary or "")[:300],
            outcome=(outcome or "")[:200], decision=(decision or "")[:200] if decision else None,
            cost_risk=(cost_risk or "")[:80] if cost_risk else None,
        ))
        if len(self.episodes) > MAX_EPISODIC:
            self.episodes.pop(0)

    def tail(self, n: int = 30) -> List[Episode]:
        return self.episodes[-n:] if self.episodes else []


@dataclass
class SemanticEntry:
    fact: str
    source: str  # "episode" | "extraction" | "user"
    tick: float
    strength: float = 1.0


@dataclass
class SemanticMemory:
    """Learned facts/concepts/relationships extracted during run."""
    facts: List[SemanticEntry] = field(default_factory=list)

    def add(self, fact: str, source: str = "extraction", tick: float = 0.0, strength: float = 1.0) -> None:
        if not fact or len(fact.strip()) < 3:
            return
        self.facts.append(SemanticEntry(
            fact=(fact or "").strip()[:400], source=source[:20], tick=tick, strength=max(0.0, min(1.0, strength))
        ))
        if len(self.facts) > MAX_SEMANTIC:
            self.facts.pop(0)

    def recent(self, n: int = 20) -> List[SemanticEntry]:
        return self.facts[-n:] if self.facts else []


@dataclass
class ProceduralEntry:
    condition: str   # "when X"
    action: str      # "then Y"
    success_count: int = 0
    last_tick: float = 0.0


@dataclass
class ProceduralMemory:
    """Strategies that worked (when X then Y) learned in-run."""
    strategies: List[ProceduralEntry] = field(default_factory=list)

    def add_or_reinforce(self, condition: str, action: str, tick: float = 0.0) -> None:
        c, a = (condition or "").strip()[:200], (action or "").strip()[:200]
        if not c or not a:
            return
        for s in self.strategies:
            if s.condition == c and s.action == a:
                s.success_count += 1
                s.last_tick = tick
                return
        self.strategies.append(ProceduralEntry(condition=c, action=a, success_count=1, last_tick=tick))
        if len(self.strategies) > MAX_PROCEDURAL:
            self.strategies.sort(key=lambda x: -x.success_count)
            self.strategies.pop()

    def best_for(self, condition_hint: str, n: int = 5) -> List[ProceduralEntry]:
        hint = (condition_hint or "").lower()
        if not hint:
            return sorted(self.strategies, key=lambda x: -x.success_count)[:n]
        scored = [(s, 1.0 if hint in s.condition.lower() else 0.0) for s in self.strategies]
        scored.sort(key=lambda x: (-x[1], -x[0].success_count))
        return [s for s, _ in scored[:n]]


def experience_replay_extract(episodic: EpisodicMemory, n: int = REPLAY_BATCH) -> List[Dict[str, Any]]:
    """Periodically revisit episodes, extract patterns. Returns list of pattern dicts."""
    tail = episodic.tail(n * 2)
    if not tail:
        return []
    patterns = []
    outcomes_by_type: Dict[str, List[str]] = {}
    for ep in tail:
        outcomes_by_type.setdefault(ep.event_type, []).append(ep.outcome)
    for event_type, outcomes in outcomes_by_type.items():
        if outcomes:
            patterns.append({"event_type": event_type, "outcomes": outcomes[-5:], "count": len(outcomes)})
    return patterns


@dataclass
class MetaCognitiveState:
    """Reflect on failures/biases; adjust strategy weights."""
    failure_count: int = 0
    bias_weights: Dict[str, float] = field(default_factory=lambda: {"caution": 0.5, "exploration": 0.5})
    last_reflection_tick: float = 0.0

    def record_failure(self) -> None:
        self.failure_count += 1
        self.bias_weights["caution"] = min(0.9, self.bias_weights.get("caution", 0.5) + 0.05)
        self.bias_weights["exploration"] = max(0.1, self.bias_weights.get("exploration", 0.5) - 0.03)

    def record_success(self, exploration: bool = False) -> None:
        if exploration:
            self.bias_weights["exploration"] = min(0.9, self.bias_weights.get("exploration", 0.5) + 0.02)
        else:
            self.bias_weights["caution"] = max(0.2, self.bias_weights.get("caution", 0.5) - 0.02)


@dataclass
class RAMMemory:
    """Single aggregate: working, episodic, semantic, procedural, replay, meta-cognitive."""
    working: WorkingMemory = field(default_factory=WorkingMemory)
    episodic: EpisodicMemory = field(default_factory=EpisodicMemory)
    semantic: SemanticMemory = field(default_factory=SemanticMemory)
    procedural: ProceduralMemory = field(default_factory=ProceduralMemory)
    meta_cognitive: MetaCognitiveState = field(default_factory=MetaCognitiveState)
    _tick_count: int = 0

    def tick_and_maybe_replay(self, current_tick: float) -> List[Dict[str, Any]]:
        """Increment tick; every N ticks run experience replay and meta-cognitive update. Returns extracted patterns."""
        self._tick_count += 1
        self.working.tick = current_tick
        if self._tick_count % META_COGNITIVE_INTERVAL_TICKS != 0:
            return []
        patterns = experience_replay_extract(self.episodic, REPLAY_BATCH)
        return patterns
