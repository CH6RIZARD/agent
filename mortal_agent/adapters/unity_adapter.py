"""
Unity Adapter - Skeleton for connecting to Unity 3D engine.

STATUS: SKELETON - Not yet implemented.

This adapter will connect to Unity via UDP or WebSocket.
The world (Unity) persists. The agent is mortal.

Message Contract:
- Agent -> Unity: ActionPacket (JSON over UDP/WebSocket)
- Unity -> Agent: ObservationPacket (JSON over UDP/WebSocket)
- Unity -> Agent: GateStatus (power, sensors, actuators flags)

To implement:
1. Configure Unity to send/receive on specified port
2. Implement the sense/apply methods
3. Implement gate signal reception from Unity

See docs/3d_integration.md for full details.
"""

import time
import socket
import json
from typing import Dict, Any, Optional

from .world_adapter import WorldAdapter


class UnityAdapter(WorldAdapter):
    """
    Skeleton Unity adapter. NOT YET FUNCTIONAL.

    Connect to Unity 3D engine via UDP.
    """

    def __init__(
        self,
        host: str = "127.0.0.1",
        send_port: int = 5005,
        recv_port: int = 5006,
        timeout: float = 1.0
    ):
        self._host = host
        self._send_port = send_port
        self._recv_port = recv_port
        self._timeout = timeout

        # Sockets (created on connect)
        self._send_socket: Optional[socket.socket] = None
        self._recv_socket: Optional[socket.socket] = None

        # Cached gate status
        self._power = False
        self._sensors = False
        self._actuators = False

        # Last observation
        self._last_obs: Dict[str, Any] = {}

    def connect(self) -> bool:
        """Connect to Unity."""
        try:
            # Send socket (UDP)
            self._send_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

            # Receive socket (UDP, bound to recv_port)
            self._recv_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self._recv_socket.bind(("0.0.0.0", self._recv_port))
            self._recv_socket.settimeout(self._timeout)

            return True
        except Exception as e:
            print(f"[UnityAdapter] Connect failed: {e}")
            return False

    def disconnect(self) -> None:
        """Disconnect from Unity."""
        if self._send_socket:
            self._send_socket.close()
            self._send_socket = None
        if self._recv_socket:
            self._recv_socket.close()
            self._recv_socket = None

    def _receive_update(self) -> bool:
        """Receive update from Unity."""
        if not self._recv_socket:
            return False

        try:
            data, addr = self._recv_socket.recvfrom(65535)
            msg = json.loads(data.decode("utf-8"))

            # Update gate status
            if "gate" in msg:
                self._power = msg["gate"].get("power", False)
                self._sensors = msg["gate"].get("sensors", False)
                self._actuators = msg["gate"].get("actuators", False)

            # Update observation
            if "observation" in msg:
                self._last_obs = msg["observation"]

            return True
        except socket.timeout:
            return False
        except Exception as e:
            print(f"[UnityAdapter] Receive error: {e}")
            return False

    def power_on(self) -> bool:
        self._receive_update()
        return self._power

    def sensors_streaming(self) -> bool:
        return self._sensors

    def motor_outputs_possible(self) -> bool:
        return self._actuators

    def sense(self) -> Dict[str, Any]:
        """Get observation from Unity."""
        self._receive_update()
        return self._last_obs

    def apply(self, action: Dict[str, Any]) -> bool:
        """Send action to Unity."""
        if not self._send_socket:
            return False

        try:
            msg = {
                "type": "action",
                "timestamp": time.time(),
                "action": action
            }
            data = json.dumps(msg).encode("utf-8")
            self._send_socket.sendto(data, (self._host, self._send_port))
            return True
        except Exception as e:
            print(f"[UnityAdapter] Send error: {e}")
            return False

    def get_influence_feedback(self) -> float:
        """Get influence from Unity (if provided)."""
        return self._last_obs.get("influence", 0.0)
