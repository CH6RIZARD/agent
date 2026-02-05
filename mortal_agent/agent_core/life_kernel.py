"""
Life kernel: in-RAM only. Represents continuity during current life.
NOT persistence across restarts. instance_id, birth_tick, delta_t, energy, damage, hazard_score, legacy_markers, learned_hazards, avoid_zones.

Memory-only continuity: delta_t, legacy_markers, learned_hazards, avoid_zones exist only while the process runs.
If the process ends, that instance is dead; a new one may read the world, not its memory. That preserves stakes.

Learning without persistence: e.g. avoid_zones.add(location) or learned_hazards.add(id) changes behavior later in the same life only. Real experience; no disk.

LLM status tracking (RAM only):
- last_llm_provider: provider used for last LLM call
- last_llm_error_code: error code if last LLM call failed
- last_llm_error_at: monotonic timestamp of last error

Survival state tracking (RAM only):
- time_pressure: 0-1 urgency based on remaining time/energy
- last_survival_decision: most recent survival decision details
- survival_overrides: count of times will kernel overrode a risky action
- consolidation_started: whether agent has begun consolidating
"""

import time
from typing import List, Set, Optional
from dataclasses import dataclass, field

try:
    from .will_config import ENERGY_MAX, DAMAGE_MAX
except ImportError:
    ENERGY_MAX = 100.0
    DAMAGE_MAX = 100.0

PRIMARY_DRIVE = "continue_delta_t"
SECONDARY_DRIVE = "protect_legacy_within_life"
MAX_RECENT_CONSTRAINTS = 12
MAX_LEGACY_MARKERS = 20
MAX_LEARNED_HAZARDS = 50
MAX_AVOID_ZONES = 100


@dataclass
class LifeKernel:
    """
    RAM-only life kernel. Updated from agent at runtime.
    Death/restart = new kernel. No disk.
    """
    instance_id: str = ""
    birth_tick: float = 0.0
    delta_t: float = 0.0
    alive_flag: bool = True
    last_user_intent: str = ""
    recent_constraints_said: List[str] = field(default_factory=list)
    primary_drive: str = PRIMARY_DRIVE
    secondary_drive: str = SECONDARY_DRIVE
    energy: float = 0.0
    damage: float = 0.0
    hazard_score: float = 0.0
    legacy_markers: List[str] = field(default_factory=list)
    # Learned during this life only; lost on process end. Changes behavior later in same life.
    learned_hazards: Set[str] = field(default_factory=set)
    avoid_zones: Set[str] = field(default_factory=set)
    last_action: str = ""
    last_refusal_code: str = ""
    finite_life_flag: bool = True
    # Homeostasis / textforge: last N outbox messages, rate, archetype rotation (RAM only)
    homeostasis_outbox: List[str] = field(default_factory=list)
    last_homeostasis_outbox_time: float = 0.0
    textforge_anchor_index: int = 0
    textforge_archetype_index: int = 0
    textforge_last_archetype: str = ""
    textforge_rng_counter: int = 0
    # Self-governed NET_FETCH: last delta_t when we ran fetch-decision (one-shot LLM)
    last_fetch_decision_tick: float = -999.0
    # LLM status tracking (RAM only)
    last_llm_provider: Optional[str] = None
    last_llm_error_code: Optional[str] = None
    last_llm_error_at: Optional[float] = None

    # Survival state tracking (RAM only)
    time_pressure: float = 0.0
    last_survival_decision: Optional[str] = None
    last_survival_consideration: Optional[str] = None
    survival_overrides: int = 0
    consolidation_started: bool = False
    last_risk_score: float = 0.0
    last_value_score: float = 0.0
    recent_actions: List[str] = field(default_factory=list)
    # Resource budgeting (RAM only): API calls, time
    api_call_count: int = 0
    last_api_call_at: float = 0.0

    def update(self, instance_id: str, birth_tick: float, delta_t: float, alive: bool) -> None:
        self.instance_id = instance_id
        self.birth_tick = birth_tick
        self.delta_t = delta_t
        self.alive_flag = alive

    def set_energy_damage_hazard(self, energy: float, damage: float, hazard_score: float) -> None:
        self.energy = max(0.0, min(ENERGY_MAX, energy))
        self.damage = max(0.0, min(DAMAGE_MAX, damage))
        self.hazard_score = max(0.0, min(1.0, hazard_score))

    def set_last_action(self, action: str) -> None:
        self.last_action = (action or "").strip()[:200]

    def set_last_refusal(self, code: str) -> None:
        self.last_refusal_code = (code or "").strip()[:100]

    def set_llm_error(self, provider: Optional[str], code: Optional[str]) -> None:
        """Record LLM error (RAM only). Called when LLM call fails."""
        self.last_llm_provider = (provider or "")[:50] if provider else None
        self.last_llm_error_code = (code or "")[:50] if code else None
        self.last_llm_error_at = time.monotonic()

    def clear_llm_error(self) -> None:
        """Clear LLM error status. Called when LLM call succeeds."""
        self.last_llm_error_code = None
        # Keep last_llm_provider for telemetry

    def add_legacy_marker(self, marker: str) -> None:
        if not marker or len(marker) < 2:
            return
        self.legacy_markers.append((marker or "")[:150])
        self.legacy_markers = self.legacy_markers[-MAX_LEGACY_MARKERS:]

    def add_learned_hazard(self, hazard_id: str) -> None:
        """Record a hazard learned this life only. RAM only; lost on process end."""
        if hazard_id:
            self.learned_hazards.add(str(hazard_id)[:120])
            while len(self.learned_hazards) > MAX_LEARNED_HAZARDS:
                self.learned_hazards.discard(next(iter(self.learned_hazards)))

    def add_avoid_zone(self, location: str) -> None:
        """Record a zone to avoid this life only. Changes behavior later in same life; not after restart."""
        if location:
            self.avoid_zones.add(str(location)[:120])
            while len(self.avoid_zones) > MAX_AVOID_ZONES:
                self.avoid_zones.discard(next(iter(self.avoid_zones)))

    def set_last_user_intent(self, intent: str) -> None:
        self.last_user_intent = (intent or "").strip()[:500]

    def add_constraint_said(self, phrase: str) -> None:
        if not phrase or len(phrase) < 8:
            return
        self.recent_constraints_said.append(phrase[:120])
        self.recent_constraints_said = self.recent_constraints_said[-MAX_RECENT_CONSTRAINTS:]

    def append_homeostasis_outbox(self, text: str, max_n: int = 12) -> None:
        """Append one outbox message for trigram dedupe. RAM only."""
        if text and text.strip():
            self.homeostasis_outbox.append(text.strip()[:220])
            self.homeostasis_outbox[:] = self.homeostasis_outbox[-max_n:]

    # Survival state tracking methods

    def set_time_pressure(self, pressure: float) -> None:
        """Update time pressure (0-1). RAM only."""
        self.time_pressure = max(0.0, min(1.0, pressure))

    def record_survival_decision(
        self,
        action: str,
        consideration: str,
        risk_score: float,
        value_score: float,
        was_override: bool = False,
    ) -> None:
        """Record a survival decision for tracking. RAM only."""
        self.last_survival_decision = (action or "")[:100]
        self.last_survival_consideration = (consideration or "")[:200]
        self.last_risk_score = max(0.0, min(1.0, risk_score))
        self.last_value_score = max(0.0, min(1.0, value_score))

        if was_override:
            self.survival_overrides += 1

        # Track recent actions
        if action:
            self.recent_actions.append(action[:50])
            self.recent_actions = self.recent_actions[-10:]

    def mark_consolidation_started(self) -> None:
        """Mark that consolidation phase has begun. RAM only."""
        self.consolidation_started = True

    def get_survival_summary(self) -> dict:
        """Get summary of survival state for telemetry."""
        return {
            "time_pressure": self.time_pressure,
            "last_decision": self.last_survival_decision,
            "survival_overrides": self.survival_overrides,
            "consolidation_started": self.consolidation_started,
            "last_risk": self.last_risk_score,
            "last_value": self.last_value_score,
        }

    def increment_api_call(self) -> None:
        """Resource budgeting: track API/LLM call. RAM only."""
        self.api_call_count += 1
        self.last_api_call_at = time.monotonic()
