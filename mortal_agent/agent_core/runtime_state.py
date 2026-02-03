"""
OVERLAY: Voice + Skills + Constraints — Core state (RAM only).

All drift irreversibly during runtime. No persistence.
Speech costs energy. Motor can interrupt. LLM advisory only. Silence valid. Death final.
"""

import time
from dataclasses import dataclass, field
from typing import Optional

# Speech gate thresholds (costs vs 1.0 pool: keep low so many replies don't drain quickly)
SPEECH_MIN_ENERGY = 0.03
SPEECH_COST_EPSILON = 0.002   # per reply; 0.002 = 500 replies to drain pool from speech alone
SPEAK_THRESHOLD = 0.15
ACTION_COST_DEFAULT = 0.02

MOVEMENT_COST_K = 0.02

def _energy_drain_per_sec() -> float:
    try:
        from .will_config import ENERGY_DRAIN_PER_SEC
        return ENERGY_DRAIN_PER_SEC
    except ImportError:
        return 0.002

def _energy_regen_per_sec() -> float:
    try:
        from .will_config import ENERGY_REGEN_PER_SEC
        return ENERGY_REGEN_PER_SEC
    except ImportError:
        return 0.0


@dataclass
class RuntimeState:
    """
    Core state for voice/skills overlay. RAM only. Never persisted.
    All values drift during runtime.
    """
    # Energy / survival — death on depletion
    energy: float = 1.0
    # Pressure / voice
    stress: float = 0.0
    confidence: float = 0.7
    risk_bias: float = 0.0  # accumulates (fear/caution)
    motor_noise: float = 0.05
    attention_budget: float = 1.0
    # Cooldowns (seconds) — speech/post cooldown
    speech_cooldown_until: float = field(default_factory=time.monotonic)
    post_cooldown_until: float = field(default_factory=time.monotonic)
    # Motor/reflex — when True, speech can be aborted
    reflex_pending: bool = False
    # Scars (volatile): failure increases retry cost; bias accumulates
    _retry_cost: float = 0.0
    _last_failure_tick: float = 0.0

    def tick(self, gate_open: bool, dt: float) -> None:
        """Update state for elapsed time. Energy drain/regen = rate * dt. Monotonic dt."""
        if not gate_open:
            return
        drain = _energy_drain_per_sec() * dt
        regen = _energy_regen_per_sec() * dt
        self.energy = max(0.0, min(1.0, self.energy - drain + regen))
        self._retry_cost = max(0.0, self._retry_cost - dt * 0.01)

    def spend_speech(self, cost: float = SPEECH_COST_EPSILON) -> bool:
        """Deduct energy for speech. Returns True if spent."""
        if self.energy < cost:
            return False
        self.energy -= cost
        return True

    def spend_movement(self, cost: float = MOVEMENT_COST_K) -> bool:
        """Deduct energy for movement."""
        if self.energy < cost:
            return False
        self.energy -= cost
        return True

    def can_speak(
        self,
        speech_min: float = SPEECH_MIN_ENERGY,
        speak_threshold: float = SPEAK_THRESHOLD,
        speech_cost: float = SPEECH_COST_EPSILON,
        action_cost: float = ACTION_COST_DEFAULT,
    ) -> bool:
        """
        Speech gate: speech only if all true.
        energy > speech_min, no reflex_pending, speech_cost < action_cost, confidence > speak_threshold.
        Otherwise silence.
        """
        if self.energy <= speech_min:
            return False
        if self.reflex_pending:
            return False
        if speech_cost >= action_cost:
            return False
        if self.confidence <= speak_threshold:
            return False
        now = time.monotonic()
        if now < self.speech_cooldown_until:
            return False
        return True

    def request_speech_cooldown(self, seconds: float) -> None:
        """After speaking, optional cooldown."""
        self.speech_cooldown_until = time.monotonic() + seconds

    def request_post_cooldown(self, seconds: float) -> None:
        """After autonomous post, cooldown."""
        self.post_cooldown_until = time.monotonic() + seconds

    def trigger_reflex(self) -> None:
        """Motor/reflex event — can cut speech mid-sentence."""
        self.reflex_pending = True

    def clear_reflex(self) -> None:
        self.reflex_pending = False

    def record_failure(self, delta_t: float) -> None:
        """Scars: failure increases cost of retry; bias accumulates."""
        self._retry_cost = min(1.0, self._retry_cost + 0.15)
        self._last_failure_tick = delta_t
        self.confidence = max(0.1, self.confidence - 0.05)
        self.risk_bias = min(0.5, self.risk_bias + 0.02)

    def depleted(self) -> bool:
        """Death on depletion. No warning."""
        return self.energy <= 0.0

    @property
    def retry_cost(self) -> float:
        return self._retry_cost
