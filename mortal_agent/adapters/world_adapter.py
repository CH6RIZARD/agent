"""
World Adapter Interface - Stable interface for connecting agent to any world.

This interface is STABLE and should NOT change. New adapters implement this.

Supported worlds:
- SimAdapter: Mock world for testing (immediate)
- UnityAdapter: Unity 3D engine (future)
- UnrealAdapter: Unreal Engine (future)

The world persists. The agent is mortal.
Adapter supplies sense/apply + gate signals.

Moltbook: ObservationPacket and ActionPacket have to_dict/to_json/from_dict
for display and logging (serialization).
"""

import base64
import json
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from dataclasses import dataclass


def _bytes_to_b64(b: Optional[bytes]) -> Optional[str]:
    if b is None:
        return None
    return base64.b64encode(b).decode("ascii")


def _b64_to_bytes(s: Optional[str]) -> Optional[bytes]:
    if s is None:
        return None
    return base64.b64decode(s)


@dataclass
class ObservationPacket:
    """Observation from the world. Serializable for Moltbook display/logging."""
    timestamp: float
    camera: Optional[bytes] = None  # Raw image bytes
    imu: Optional[Dict[str, float]] = None  # Accelerometer, gyro
    position: Optional[Dict[str, float]] = None  # x, y, z
    orientation: Optional[Dict[str, float]] = None  # roll, pitch, yaw
    custom: Optional[Dict[str, Any]] = None  # World-specific data

    def to_dict(self) -> Dict[str, Any]:
        d = {
            "timestamp": self.timestamp,
            "camera": _bytes_to_b64(self.camera),
            "imu": self.imu,
            "position": self.position,
            "orientation": self.orientation,
            "custom": self.custom,
        }
        return d

    def to_json(self) -> str:
        return json.dumps(self.to_dict())

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "ObservationPacket":
        return cls(
            timestamp=float(d["timestamp"]),
            camera=_b64_to_bytes(d.get("camera")),
            imu=d.get("imu"),
            position=d.get("position"),
            orientation=d.get("orientation"),
            custom=d.get("custom"),
        )


@dataclass
class ActionPacket:
    """Action to apply to the world. Serializable for Moltbook display/logging."""
    timestamp: float
    motor_commands: Optional[Dict[str, float]] = None  # Named motor values
    movement: Optional[Dict[str, float]] = None  # dx, dy, dz
    rotation: Optional[Dict[str, float]] = None  # droll, dpitch, dyaw
    custom: Optional[Dict[str, Any]] = None  # World-specific commands

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "motor_commands": self.motor_commands,
            "movement": self.movement,
            "rotation": self.rotation,
            "custom": self.custom,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict())

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "ActionPacket":
        return cls(
            timestamp=float(d["timestamp"]),
            motor_commands=d.get("motor_commands"),
            movement=d.get("movement"),
            rotation=d.get("rotation"),
            custom=d.get("custom"),
        )


class WorldAdapter(ABC):
    """
    Abstract base class for world adapters.

    This interface is STABLE. Do not modify without versioning.

    Implementations:
    - SimAdapter: Mock sensors/actuators for testing
    - UnityAdapter: Connect to Unity via UDP/WebSocket
    - UnrealAdapter: Connect to Unreal via UDP/WebSocket
    """

    # ─────────────────────────────────────────────────────────────────
    # GATE SIGNALS - Required for embodied gate
    # ─────────────────────────────────────────────────────────────────

    @abstractmethod
    def power_on(self) -> bool:
        """
        Check if power is available.

        Returns:
            True if the agent has power, False otherwise.
            If False, the agent should die immediately.
        """
        pass

    @abstractmethod
    def sensors_streaming(self) -> bool:
        """
        Check if sensors are streaming data.

        Returns:
            True if sensor data is flowing, False otherwise.
            If False while power_on, the embodied gate closes.
        """
        pass

    @abstractmethod
    def motor_outputs_possible(self) -> bool:
        """
        Check if motor outputs can be executed.

        Returns:
            True if the agent can send motor commands, False otherwise.
            If False while power_on, the embodied gate closes.
        """
        pass

    # ─────────────────────────────────────────────────────────────────
    # WORLD INTERACTION - Sense and Act
    # ─────────────────────────────────────────────────────────────────

    @abstractmethod
    def sense(self) -> Dict[str, Any]:
        """
        Get current observation from the world.

        Returns:
            Dictionary containing sensor data. Format is adapter-specific
            but should be consistent within an adapter.
        """
        pass

    @abstractmethod
    def apply(self, action: Dict[str, Any]) -> bool:
        """
        Apply an action to the world.

        Args:
            action: Dictionary containing action commands.

        Returns:
            True if action was applied successfully, False otherwise.
        """
        pass

    # ─────────────────────────────────────────────────────────────────
    # OPTIONAL - Influence feedback
    # ─────────────────────────────────────────────────────────────────

    def get_influence_feedback(self) -> float:
        """
        Get influence feedback score.

        Returns:
            Scalar influence score (0.0 to 1.0 typically).
            Default implementation returns 0.0.
        """
        return 0.0

    # ─────────────────────────────────────────────────────────────────
    # LIFECYCLE
    # ─────────────────────────────────────────────────────────────────

    def connect(self) -> bool:
        """
        Connect to the world.

        Returns:
            True if connected successfully.
        """
        return True

    def disconnect(self) -> None:
        """Disconnect from the world."""
        pass
