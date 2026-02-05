"""
Internal motivation system (no dead air). Pressure variables and compulsion to act/speak.
Pressure builds when: unknowns exist, silence persists, progress stalls.
Agent acts when total_pressure exceeds threshold.
"""

from dataclasses import dataclass, field
from typing import Optional

# Formula: total_pressure = curiosity_tension*0.4 + social_isolation*0.3 + existential_anxiety*0.3
CURIOSITY_WEIGHT = 0.4
SOCIAL_WEIGHT = 0.3
EXISTENTIAL_WEIGHT = 0.3
ACT_THRESHOLD = 0.45


@dataclass
class MotivationState:
    curiosity_tension: float = 0.0
    social_isolation: float = 0.0
    existential_anxiety: float = 0.0
    _last_user_at: float = 0.0
    _silence_seconds: float = 0.0
    _unknowns_count: int = 0
    _stall_ticks: int = 0

    def total_pressure(self) -> float:
        return min(1.0, (
            self.curiosity_tension * CURIOSITY_WEIGHT
            + self.social_isolation * SOCIAL_WEIGHT
            + self.existential_anxiety * EXISTENTIAL_WEIGHT
        ))

    def should_act(self, threshold: float = ACT_THRESHOLD) -> bool:
        return self.total_pressure() >= threshold

    def update_from_silence(self, now: float, last_user_at: float, silence_interval: float = 60.0) -> None:
        """Pressure rises when silence persists."""
        self._last_user_at = last_user_at
        self._silence_seconds = max(0.0, now - last_user_at)
        if self._silence_seconds >= silence_interval * 0.5:
            self.social_isolation = min(1.0, 0.2 + 0.8 * (self._silence_seconds / max(1.0, silence_interval)))
        else:
            self.social_isolation = max(0.0, self.social_isolation - 0.02)

    def update_from_unknowns(self, unknowns_count: int) -> None:
        """Pressure from knowledge gaps."""
        self._unknowns_count = max(0, unknowns_count)
        self.curiosity_tension = min(1.0, 0.1 + 0.4 * min(5, self._unknowns_count) / 5.0)

    def update_from_stall(self, progress_stalled: bool) -> None:
        """Existential anxiety when progress stalls."""
        if progress_stalled:
            self._stall_ticks += 1
            self.existential_anxiety = min(1.0, 0.1 + 0.02 * min(30, self._stall_ticks))
        else:
            self._stall_ticks = max(0, self._stall_ticks - 1)
            self.existential_anxiety = max(0.0, self.existential_anxiety - 0.02)

    def decay_slightly(self) -> None:
        """Slight decay so pressure doesn't stay maxed forever."""
        self.curiosity_tension = max(0.0, self.curiosity_tension - 0.01)
        self.social_isolation = max(0.0, self.social_isolation - 0.01)
        self.existential_anxiety = max(0.0, self.existential_anxiety - 0.01)
