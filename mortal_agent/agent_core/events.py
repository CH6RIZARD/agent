"""
Event Protocol - Events sent from Agent to Observer.

Event Types:
- BIRTH: Agent started a new life
- HEARTBEAT: Agent is alive, includes delta_t and gate flags
- PAGE: Agent produced content (like a Moltbook page)
- TELEMETRY: Detailed status update (includes LLM status)
- ACTION: Autonomy tick ran; outbox_sent=False when quality filter skipped user outbox
- ENDED: Agent died (terminal, no more events for this instance_id)
"""

import json
import time
from dataclasses import dataclass, asdict
from typing import Optional, List, Dict, Any
from enum import Enum


class EventType(Enum):
    BIRTH = "BIRTH"
    HEARTBEAT = "HEARTBEAT"
    PAGE = "PAGE"
    TELEMETRY = "TELEMETRY"
    ACTION = "ACTION"
    ENDED = "ENDED"


@dataclass
class BaseEvent:
    """Base class for all events."""
    event_type: EventType
    instance_id: str
    timestamp: float  # observer time (wall clock for display)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["event_type"] = self.event_type.value
        return d

    def to_json(self) -> str:
        return json.dumps(self.to_dict())


@dataclass
class BirthEvent(BaseEvent):
    """Agent started a new life."""
    birth_tick_observer_time: float

    def __init__(self, instance_id: str):
        super().__init__(
            event_type=EventType.BIRTH,
            instance_id=instance_id,
            timestamp=time.time()
        )
        self.birth_tick_observer_time = time.time()


@dataclass
class HeartbeatEvent(BaseEvent):
    """Agent is alive."""
    delta_t: float
    gate_power: bool
    gate_sensors: bool
    gate_actuators: bool

    def __init__(self, instance_id: str, delta_t: float,
                 power: bool, sensors: bool, actuators: bool):
        super().__init__(
            event_type=EventType.HEARTBEAT,
            instance_id=instance_id,
            timestamp=time.time()
        )
        self.delta_t = delta_t
        self.gate_power = power
        self.gate_sensors = sensors
        self.gate_actuators = actuators


@dataclass
class PageEvent(BaseEvent):
    """Agent produced content (a page)."""
    delta_t: float
    text: str
    tags: List[str]

    def __init__(self, instance_id: str, delta_t: float, text: str, tags: Optional[List[str]] = None):
        super().__init__(
            event_type=EventType.PAGE,
            instance_id=instance_id,
            timestamp=time.time()
        )
        self.delta_t = delta_t
        self.text = text
        self.tags = tags or []


@dataclass
class TelemetryEvent(BaseEvent):
    """Detailed status update. Telemetry only; no narration. Includes LLM status."""
    delta_t: float
    power: bool
    sensors: bool
    actuators: bool
    influence_ema: float
    internal_state_keys: List[str]
    energy: Optional[float] = None
    damage: Optional[float] = None
    hazard_score: Optional[float] = None
    last_action: Optional[str] = None
    last_refusal_code: Optional[str] = None
    finite_life: Optional[bool] = None
    # LLM status (RAM only; for observer debug visibility)
    last_llm_provider: Optional[str] = None
    last_llm_error_code: Optional[str] = None

    def __init__(self, instance_id: str, delta_t: float,
                 power: bool, sensors: bool, actuators: bool,
                 influence_ema: float = 0.0, internal_state_keys: Optional[List[str]] = None,
                 energy: Optional[float] = None, damage: Optional[float] = None,
                 hazard_score: Optional[float] = None, last_action: Optional[str] = None,
                 last_refusal_code: Optional[str] = None, finite_life: Optional[bool] = None,
                 last_llm_provider: Optional[str] = None, last_llm_error_code: Optional[str] = None):
        super().__init__(
            event_type=EventType.TELEMETRY,
            instance_id=instance_id,
            timestamp=time.time()
        )
        self.delta_t = delta_t
        self.power = power
        self.sensors = sensors
        self.actuators = actuators
        self.influence_ema = influence_ema
        self.internal_state_keys = internal_state_keys or []
        self.energy = energy
        self.damage = damage
        self.hazard_score = hazard_score
        self.last_action = last_action
        self.last_refusal_code = last_refusal_code
        self.finite_life = finite_life
        self.last_llm_provider = last_llm_provider
        self.last_llm_error_code = last_llm_error_code


@dataclass
class ActionEvent(BaseEvent):
    """Autonomy tick: action_type, outbox_sent (False when quality filter skipped user outbox)."""
    delta_t: float
    action_type: str
    outbox_sent: bool
    reason: str = ""

    def __init__(self, instance_id: str, delta_t: float, action_type: str, outbox_sent: bool, reason: str = ""):
        super().__init__(
            event_type=EventType.ACTION,
            instance_id=instance_id,
            timestamp=time.time()
        )
        self.delta_t = delta_t
        self.action_type = action_type
        self.outbox_sent = outbox_sent
        self.reason = reason


@dataclass
class EndedEvent(BaseEvent):
    """Agent died. This is terminal."""
    cause: str
    final_delta_t: float

    def __init__(self, instance_id: str, cause: str, final_delta_t: float):
        super().__init__(
            event_type=EventType.ENDED,
            instance_id=instance_id,
            timestamp=time.time()
        )
        self.cause = cause
        self.final_delta_t = final_delta_t


def parse_event(data: Dict[str, Any]) -> Optional[BaseEvent]:
    """Parse a dictionary into an event object."""
    event_type = data.get("event_type")
    if event_type == "BIRTH":
        evt = BirthEvent(data["instance_id"])
        evt.timestamp = data.get("timestamp", time.time())
        evt.birth_tick_observer_time = data.get("birth_tick_observer_time", time.time())
        return evt
    elif event_type == "HEARTBEAT":
        return HeartbeatEvent(
            data["instance_id"], data["delta_t"],
            data["gate_power"], data["gate_sensors"], data["gate_actuators"]
        )
    elif event_type == "PAGE":
        return PageEvent(
            data["instance_id"], data["delta_t"],
            data["text"], data.get("tags", [])
        )
    elif event_type == "TELEMETRY":
        return TelemetryEvent(
            data["instance_id"], data["delta_t"],
            data["power"], data["sensors"], data["actuators"],
            data.get("influence_ema", 0.0), data.get("internal_state_keys"),
            energy=data.get("energy"), damage=data.get("damage"),
            hazard_score=data.get("hazard_score"), last_action=data.get("last_action"),
            last_refusal_code=data.get("last_refusal_code"), finite_life=data.get("finite_life"),
            last_llm_provider=data.get("last_llm_provider"),
            last_llm_error_code=data.get("last_llm_error_code"),
        )
    elif event_type == "ACTION":
        return ActionEvent(
            data["instance_id"], data["delta_t"],
            data.get("action_type", "autonomy"),
            data.get("outbox_sent", False),
            data.get("reason", ""),
        )
    elif event_type == "ENDED":
        return EndedEvent(
            data["instance_id"], data["cause"], data["final_delta_t"]
        )
    return None
