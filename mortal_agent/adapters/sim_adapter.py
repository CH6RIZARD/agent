"""
Sim Adapter (SimBodyAdapter) - Mock world adapter for testing.

Provides fake sensors and actuators so the agent can run immediately
with embodied_gate=true. Includes switches to simulate:
- Sensor drop
- Actuator disable
- Power loss

Use these to prove death semantics work correctly.

Optional gate_file: when set, power_on/sensors_streaming/motor_outputs_possible
read from that JSON file each call (for CLI toggles from another process).
"""

import json
import time
import random
import threading
from pathlib import Path
from typing import Dict, Any, Optional

from .world_adapter import WorldAdapter


class SimAdapter(WorldAdapter):
    """
    Simulated world adapter for testing.

    Provides controllable gate signals and mock sensor data.
    Use kill switches to trigger death conditions.
    """

    def __init__(
        self,
        initial_power: bool = True,
        initial_sensors: bool = True,
        initial_actuators: bool = True,
        influence_base: float = 0.5,
        gate_file: Optional[Path] = None,
    ):
        # Gate control flags (can be toggled externally or via gate_file)
        self._power = initial_power
        self._sensors = initial_sensors
        self._actuators = initial_actuators
        self._gate_file = Path(gate_file) if gate_file else None

        # Influence simulation
        self._influence_base = influence_base
        self._influence_noise = 0.1

        # Simulated position
        self._position = {"x": 0.0, "y": 0.0, "z": 0.0}
        self._orientation = {"roll": 0.0, "pitch": 0.0, "yaw": 0.0}

        # Action history (for testing)
        self._action_history: list = []

        # Thread lock for state changes
        self._lock = threading.Lock()

        # Scheduled death (for testing)
        self._death_scheduled = False
        self._death_time: Optional[float] = None
        self._death_type: Optional[str] = None

    # ─────────────────────────────────────────────────────────────────
    # GATE SIGNALS
    # ─────────────────────────────────────────────────────────────────

    def _read_gate_file(self) -> Optional[Dict[str, bool]]:
        """Read gate state from file if set. Returns None if not used."""
        if not self._gate_file or not self._gate_file.exists():
            return None
        try:
            data = json.loads(self._gate_file.read_text(encoding="utf-8"))
            return {
                "power_on": bool(data.get("power_on", True)),
                "sensors_streaming": bool(data.get("sensors_streaming", True)),
                "motor_outputs_possible": bool(data.get("motor_outputs_possible", True)),
            }
        except Exception:
            return None

    def power_on(self) -> bool:
        self._check_scheduled_death()
        gate = self._read_gate_file()
        if gate is not None:
            return gate["power_on"]
        with self._lock:
            return self._power

    def sensors_streaming(self) -> bool:
        self._check_scheduled_death()
        gate = self._read_gate_file()
        if gate is not None:
            return gate["sensors_streaming"]
        with self._lock:
            return self._sensors

    def motor_outputs_possible(self) -> bool:
        self._check_scheduled_death()
        gate = self._read_gate_file()
        if gate is not None:
            return gate["motor_outputs_possible"]
        with self._lock:
            return self._actuators

    # ─────────────────────────────────────────────────────────────────
    # WORLD INTERACTION
    # ─────────────────────────────────────────────────────────────────

    def sense(self) -> Dict[str, Any]:
        """Return simulated sensor data."""
        with self._lock:
            if not self._sensors:
                return {"error": "sensors_offline"}

            return {
                "timestamp": time.time(),
                "position": self._position.copy(),
                "orientation": self._orientation.copy(),
                "imu": {
                    "accel_x": random.gauss(0, 0.1),
                    "accel_y": random.gauss(0, 0.1),
                    "accel_z": random.gauss(-9.8, 0.1),
                    "gyro_x": random.gauss(0, 0.01),
                    "gyro_y": random.gauss(0, 0.01),
                    "gyro_z": random.gauss(0, 0.01),
                },
                "battery": 0.95 if self._power else 0.0,
            }

    def apply(self, action: Dict[str, Any]) -> bool:
        """Apply simulated action."""
        with self._lock:
            if not self._actuators:
                return False

            self._action_history.append({
                "timestamp": time.time(),
                "action": action
            })

            # Simulate movement
            if "movement" in action:
                mov = action["movement"]
                self._position["x"] += mov.get("dx", 0)
                self._position["y"] += mov.get("dy", 0)
                self._position["z"] += mov.get("dz", 0)

            if "rotation" in action:
                rot = action["rotation"]
                self._orientation["roll"] += rot.get("droll", 0)
                self._orientation["pitch"] += rot.get("dpitch", 0)
                self._orientation["yaw"] += rot.get("dyaw", 0)

            return True

    def get_influence_feedback(self) -> float:
        """Return simulated influence score."""
        noise = random.gauss(0, self._influence_noise)
        return max(0.0, min(1.0, self._influence_base + noise))

    # ─────────────────────────────────────────────────────────────────
    # KILL SWITCHES - For testing death semantics
    # ─────────────────────────────────────────────────────────────────

    def kill_power(self) -> None:
        """Simulate power loss. Agent should die immediately."""
        with self._lock:
            self._power = False

    def kill_sensors(self) -> None:
        """Simulate sensor failure. Agent should die."""
        with self._lock:
            self._sensors = False

    def kill_actuators(self) -> None:
        """Simulate actuator failure. Agent should die."""
        with self._lock:
            self._actuators = False

    def restore_power(self) -> None:
        """Restore power (for testing, though dead agent won't recover)."""
        with self._lock:
            self._power = True

    def restore_sensors(self) -> None:
        """Restore sensors."""
        with self._lock:
            self._sensors = True

    def restore_actuators(self) -> None:
        """Restore actuators."""
        with self._lock:
            self._actuators = True

    def schedule_death(self, delay_seconds: float, death_type: str = "power") -> None:
        """
        Schedule a death event after a delay.

        Args:
            delay_seconds: Seconds until death
            death_type: "power", "sensors", or "actuators"
        """
        self._death_scheduled = True
        self._death_time = time.monotonic() + delay_seconds
        self._death_type = death_type

    def _check_scheduled_death(self) -> None:
        """Check if scheduled death time has arrived."""
        if self._death_scheduled and self._death_time is not None:
            if time.monotonic() >= self._death_time:
                self._death_scheduled = False
                if self._death_type == "power":
                    self.kill_power()
                elif self._death_type == "sensors":
                    self.kill_sensors()
                elif self._death_type == "actuators":
                    self.kill_actuators()

    # ─────────────────────────────────────────────────────────────────
    # TESTING UTILITIES
    # ─────────────────────────────────────────────────────────────────

    def get_action_history(self) -> list:
        """Get history of applied actions (for testing)."""
        with self._lock:
            return self._action_history.copy()

    def clear_action_history(self) -> None:
        """Clear action history."""
        with self._lock:
            self._action_history.clear()

    def set_position(self, x: float, y: float, z: float) -> None:
        """Set simulated position."""
        with self._lock:
            self._position = {"x": x, "y": y, "z": z}

    def set_influence_base(self, value: float) -> None:
        """Set base influence score."""
        self._influence_base = value


# Spec name alias
SimBodyAdapter = SimAdapter
