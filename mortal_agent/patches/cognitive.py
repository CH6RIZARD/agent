"""
Cognitive architecture patches.
- Multi-tier memory: working (current context), episodic (timestamped events), semantic (facts/concepts), procedural (skills)
- Internal dialogue / reasoning loop: chain-of-thought, self-questioning for complex decisions
- Goal hierarchy: top-level drives → strategic goals → tactical objectives → immediate actions
- Attention / salience filter: what deserves processing based on importance/novelty
"""

import time
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field

# In-RAM only; one session only—no persistence across process restarts (death is permanent)
WORKING_MAX = 20
EPISODIC_MAX = 100
SEMANTIC_MAX = 200
PROCEDURAL_MAX = 50


@dataclass
class WorkingMemory:
    """Current context: last N items (turns, fetches, salient facts)."""
    items: List[Dict[str, Any]] = field(default_factory=list)
    updated_at: float = 0.0

    def push(self, item: Dict[str, Any]) -> None:
        self.items = (self.items + [item])[-WORKING_MAX:]
        self.updated_at = time.monotonic()

    def snapshot(self) -> List[Dict[str, Any]]:
        return list(self.items)


@dataclass
class EpisodicMemory:
    """Experiences, timestamped events (delta_t or monotonic)."""
    events: List[Dict[str, Any]] = field(default_factory=list)
    updated_at: float = 0.0

    def record(self, event: Dict[str, Any], delta_t: float = 0.0) -> None:
        event = dict(event)
        event["_t"] = time.monotonic()
        event["_delta_t"] = delta_t
        self.events = (self.events + [event])[-EPISODIC_MAX:]
        self.updated_at = time.monotonic()

    def recent(self, n: int = 20) -> List[Dict[str, Any]]:
        return list(self.events[-n:])


@dataclass
class SemanticMemory:
    """Learned facts, concepts, relationships (no timestamps)."""
    facts: List[Dict[str, Any]] = field(default_factory=list)
    updated_at: float = 0.0

    def add(self, fact: Dict[str, Any]) -> None:
        self.facts = (self.facts + [fact])[-SEMANTIC_MAX:]
        self.updated_at = time.monotonic()

    def snapshot(self) -> List[Dict[str, Any]]:
        return list(self.facts)


@dataclass
class ProceduralMemory:
    """Skills, strategies that worked (action_type -> outcome summary)."""
    skills: List[Dict[str, Any]] = field(default_factory=list)
    updated_at: float = 0.0

    def record_success(self, action_type: str, summary: str) -> None:
        self.skills = (self.skills + [{"action": action_type, "summary": summary[:200]}])[-PROCEDURAL_MAX:]
        self.updated_at = time.monotonic()

    def snapshot(self) -> List[Dict[str, Any]]:
        return list(self.skills)


# Module-level singletons (RAM only; one per process)
_working = WorkingMemory()
_episodic = EpisodicMemory()
_semantic = SemanticMemory()
_procedural = ProceduralMemory()


def working_memory() -> WorkingMemory:
    return _working


def episodic_memory() -> EpisodicMemory:
    return _episodic


def semantic_memory() -> SemanticMemory:
    return _semantic


def procedural_memory() -> ProceduralMemory:
    return _procedural


def get_goal_hierarchy(meaning_state: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Top-level drives → strategic goals → tactical objectives → immediate actions.
    Used by autonomy controller for goal selection.
    """
    drives = ["continue_delta_t", "protect_legacy_within_life", "discover_meaning"]
    goals: List[str] = []
    objectives: List[str] = []
    if meaning_state:
        g = (meaning_state.get("meaning_goal") or "discover_self").strip()
        if g:
            goals.append(g)
        objectives = list(meaning_state.get("meaning_questions", []) or [])[:5]
    return {
        "drives": drives,
        "goals": goals or ["explore", "consolidate"],
        "objectives": objectives,
        "immediate": [],  # Filled by autonomy tick
    }


def get_attention_salience(context: Dict[str, Any]) -> Dict[str, Any]:
    """
    Determine what deserves processing time based on importance/novelty.
    Returns salient (high priority) and defer (low priority).
    """
    salient: List[str] = []
    defer: List[str] = []
    hazard = float(context.get("hazard_score", 0.0))
    energy = float(context.get("energy_norm", 0.5))
    recent = context.get("recent_actions") or []
    if hazard > 0.5:
        salient.append("reduce_hazard")
    if energy < 0.2:
        salient.append("conserve_energy")
    if "CONSOLIDATE" in (context.get("last_intent") or ""):
        salient.append("consolidate_legacy")
    # Novelty: if we just did fetch/search, processing that is salient
    if any(a in recent for a in ("NET_FETCH", "WEB_SEARCH", "WEB_SCRAPE", "ACADEMIC_FETCH")):
        salient.append("process_recent_research")
    defer = [x for x in ["explore", "reposition", "web_browse"] if x not in salient]
    return {"salient": salient, "defer": defer[:5]}


def internal_dialogue_prompt(question: str, context: Dict[str, Any]) -> str:
    """
    Build a prompt for chain-of-thought / self-questioning (used by LLM when needed).
    Caller uses this with generate_reply_routed or equivalent.
    """
    parts = [f"Internal dialogue: {question}"]
    if context.get("options"):
        parts.append("Options: " + "; ".join(str(o) for o in context["options"][:8]))
    if context.get("constraints"):
        parts.append("Constraints: " + (context["constraints"][:300] if isinstance(context["constraints"], str) else str(context["constraints"])[:300])
    return "\n".join(parts)
