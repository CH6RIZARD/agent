"""
Threat model: hazard_score from sensors/events. Death conditions.
RAM only. No persistence.
"""

from typing import Optional
from dataclasses import dataclass

try:
    from .will_config import HAZARD_DECAY, ENERGY_MAX, DAMAGE_MAX
except ImportError:
    HAZARD_DECAY = 0.98
    ENERGY_MAX = 100.0
    DAMAGE_MAX = 100.0


@dataclass
class LifeState:
    """Snapshot for threat evaluation."""
    energy: float = 0.0
    damage: float = 0.0
    hazard_score: float = 0.0
    power_on: bool = True
    sensors_streaming: bool = True
    motor_outputs_possible: bool = True


def update_hazard_score(
    current_hazard: float,
    energy: float,
    damage: float,
    power_on: bool,
    sensors: bool,
    actuators: bool,
    decay: float = HAZARD_DECAY,
) -> float:
    """
    Update hazard_score (0..1). Decay toward 0; rise on threat signals.
    High when energy low, damage high, or gate false.
    """
    raw = current_hazard * decay
    if not power_on or not sensors or not actuators:
        raw = min(1.0, raw + 0.4)
    if energy is not None and ENERGY_MAX > 0:
        if energy <= 0:
            raw = 1.0
        elif energy < ENERGY_MAX * 0.2:
            raw = min(1.0, raw + 0.3)
        elif energy < ENERGY_MAX * 0.5:
            raw = min(1.0, raw + 0.1)
    if damage is not None and DAMAGE_MAX > 0:
        if damage >= DAMAGE_MAX:
            raw = 1.0
        elif damage >= DAMAGE_MAX * 0.7:
            raw = min(1.0, raw + 0.35)
        elif damage >= DAMAGE_MAX * 0.4:
            raw = min(1.0, raw + 0.15)
    return min(1.0, max(0.0, raw))


def would_die(state: LifeState) -> bool:
    """Death if: energy<=0 OR damage>=DAMAGE_MAX OR motor_outputs_possible=false OR sensors_streaming=false while power_on."""
    if state.energy <= 0:
        return True
    if state.damage >= DAMAGE_MAX:
        return True
    if state.power_on and not state.sensors_streaming:
        return True
    if state.power_on and not state.motor_outputs_possible:
        return True
    return False


def death_cause_gate(failure_cause) -> str:
    """Map gate failure to cause code. Never expose lifespan/remaining."""
    if failure_cause is None:
        return "gate_failure"
    v = getattr(failure_cause, "value", str(failure_cause))
    if "sensor" in v.lower():
        return "sensors_lost"
    if "actuator" in v.lower() or "motor" in v.lower():
        return "motor_unavailable"
    return "gate_failure"
