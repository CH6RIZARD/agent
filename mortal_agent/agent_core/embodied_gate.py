"""
Embodied Gate - Controls when the agent is considered "alive" in the embodied sense.

The gate is open (True) ONLY when ALL conditions are met:
1. power_on = True
2. sensors_streaming = True
3. motor_outputs_possible = True

If ANY condition fails, the gate closes and delta_t stops accumulating.
If the gate fails critically, the agent MUST die immediately.
"""

from dataclasses import dataclass
from typing import Protocol, Optional
from enum import Enum


class GateFailureCause(Enum):
    """Reasons the embodied gate can fail."""
    POWER_LOSS = "power_loss"
    SENSORS_OFFLINE = "sensors_offline"
    ACTUATORS_DISABLED = "actuators_disabled"
    ADAPTER_DISCONNECTED = "adapter_disconnected"
    MANUAL_KILL = "manual_kill"
    UNKNOWN = "unknown"


class WorldAdapterProtocol(Protocol):
    """Protocol that world adapters must implement."""

    def power_on(self) -> bool:
        """Check if power is available."""
        ...

    def sensors_streaming(self) -> bool:
        """Check if sensors are streaming data."""
        ...

    def motor_outputs_possible(self) -> bool:
        """Check if motor outputs can be executed."""
        ...


@dataclass
class GateStatus:
    """Current status of the embodied gate."""
    power: bool
    sensors: bool
    actuators: bool

    @property
    def open(self) -> bool:
        """Gate is open only if ALL conditions are met."""
        return self.power and self.sensors and self.actuators

    @property
    def failure_cause(self) -> Optional[GateFailureCause]:
        """Return the cause of gate failure, if any."""
        if self.open:
            return None
        if not self.power:
            return GateFailureCause.POWER_LOSS
        if not self.sensors:
            return GateFailureCause.SENSORS_OFFLINE
        if not self.actuators:
            return GateFailureCause.ACTUATORS_DISABLED
        return GateFailureCause.UNKNOWN


class EmbodiedGate:
    """
    The embodied gate determines when the agent is truly "alive."

    Identity (Δt) accumulates ONLY while this gate is open.
    When the gate fails critically, the agent must die immediately.
    """

    def __init__(self, adapter: WorldAdapterProtocol):
        self._adapter = adapter
        self._force_closed = False
        self._last_status: Optional[GateStatus] = None

    def check(self) -> GateStatus:
        """
        Check current gate status by querying the world adapter.

        Returns:
            GateStatus with current conditions
        """
        if self._force_closed:
            return GateStatus(power=False, sensors=False, actuators=False)

        try:
            status = GateStatus(
                power=self._adapter.power_on(),
                sensors=self._adapter.sensors_streaming(),
                actuators=self._adapter.motor_outputs_possible()
            )
        except Exception:
            # Adapter failure = gate failure
            status = GateStatus(power=False, sensors=False, actuators=False)

        self._last_status = status
        return status

    def is_open(self) -> bool:
        """Quick check if gate is open."""
        return self.check().open

    def force_close(self, cause: GateFailureCause = GateFailureCause.MANUAL_KILL) -> None:
        """
        Force the gate closed. Used for manual kills or critical failures.

        Once force-closed, the gate cannot be reopened in this process.
        """
        self._force_closed = True

    @property
    def last_status(self) -> Optional[GateStatus]:
        """Get last checked status without re-querying."""
        return self._last_status
