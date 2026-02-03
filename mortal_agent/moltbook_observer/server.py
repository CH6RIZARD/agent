"""
Observer Server - SSE/WebSocket server for Moltbook-like UI.

Streams events from the agent to a web UI.
Shows ALIVE/ENDED status, delta_t, pages, telemetry.

IMPORTANT: Observer is READ-ONLY. It may store pages/artifacts and telemetry,
but NEVER anything that reconstructs the same self.
When an agent dies, the UI shows ENDED and does not offer resume.

Connection handling: gracefully handles client disconnects (WinError 10053,
ConnectionAbortedError, BrokenPipeError) without spewing stack traces.
"""

import json
import time
import threading
import queue
import uuid
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple
from dataclasses import dataclass, asdict
import sys

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from agent_core.events import (
    BaseEvent, EventType, BirthEvent, HeartbeatEvent,
    PageEvent, TelemetryEvent, ActionEvent, EndedEvent, parse_event
)
from .influence import InfluenceScorer


@dataclass
class LifeRecord:
    """Record of a single agent life. Telemetry only; no narration."""
    instance_id: str
    birth_time: float
    ended: bool = False
    end_cause: Optional[str] = None
    final_delta_t: float = 0.0
    current_delta_t: float = 0.0
    pages: List[Dict] = None
    last_heartbeat: float = 0.0
    gate_power: bool = False
    gate_sensors: bool = False
    gate_actuators: bool = False
    energy: Optional[float] = None
    damage: Optional[float] = None
    hazard_score: Optional[float] = None
    last_action: Optional[str] = None
    last_refusal_code: Optional[str] = None
    finite_life: Optional[bool] = None
    # LLM status (from telemetry)
    last_llm_provider: Optional[str] = None
    last_llm_error_code: Optional[str] = None

    def __post_init__(self):
        if self.pages is None:
            self.pages = []


class ObserverServer:
    """
    Observer server that receives events from agent and serves UI.

    This server:
    - Receives events via direct callback or HTTP POST
    - Stores events for display (NOT for agent restoration)
    - Serves a web UI showing agent status
    - Provides SSE endpoint for live updates
    """

    def __init__(self, host: str = "127.0.0.1", port: int = 8080):
        self.host = host
        self.port = port

        # Life records by instance_id
        self._lives: Dict[str, LifeRecord] = {}

        # Active instance (most recent)
        self._active_instance: Optional[str] = None

        # Ended instances (read-only archives)
        self._ended_instances: Set[str] = set()

        # Event queue for SSE
        self._event_queues: List[queue.Queue] = []
        self._queue_lock = threading.Lock()

        # Influence scorer
        self._scorer = InfluenceScorer()

        # Chat: pending (chat_id, message), replies chat_id -> reply (same entity replies via identity)
        self._chat_pending: List[Tuple[str, str]] = []
        self._chat_replies: Dict[str, str] = {}
        self._chat_lock = threading.Lock()

        # Unified chat history (for syncing terminal <-> web UI)
        self._chat_history: List[Dict] = []  # [{role: "user"/"agent", text: str, source: "terminal"/"web", ts: float}]
        self._chat_history_lock = threading.Lock()

        # HTTP server
        self._server: Optional[HTTPServer] = None
        self._server_thread: Optional[threading.Thread] = None

    def handle_event(self, event: BaseEvent) -> bool:
        """
        Handle an event from the agent.

        Returns:
            True if event was accepted, False if rejected (e.g., ended instance)
        """
        instance_id = event.instance_id

        # Reject events for ended instances
        if instance_id in self._ended_instances:
            return False

        if event.event_type == EventType.BIRTH:
            return self._handle_birth(event)
        elif event.event_type == EventType.HEARTBEAT:
            return self._handle_heartbeat(event)
        elif event.event_type == EventType.PAGE:
            return self._handle_page(event)
        elif event.event_type == EventType.TELEMETRY:
            return self._handle_telemetry(event)
        elif event.event_type == EventType.ACTION:
            return self._handle_action(event)
        elif event.event_type == EventType.ENDED:
            return self._handle_ended(event)

        return False

    def _handle_birth(self, event: BirthEvent) -> bool:
        """Handle birth event."""
        life = LifeRecord(
            instance_id=event.instance_id,
            birth_time=event.birth_tick_observer_time,
            gate_power=True,
            gate_sensors=True,
            gate_actuators=True
        )
        self._lives[event.instance_id] = life
        self._active_instance = event.instance_id

        self._broadcast_event(event)
        return True

    def _handle_heartbeat(self, event: HeartbeatEvent) -> bool:
        """Handle heartbeat event."""
        life = self._lives.get(event.instance_id)
        if not life:
            return False

        life.current_delta_t = event.delta_t
        life.last_heartbeat = time.time()
        life.gate_power = event.gate_power
        life.gate_sensors = event.gate_sensors
        life.gate_actuators = event.gate_actuators

        self._broadcast_event(event)
        return True

    def _handle_page(self, event: PageEvent) -> bool:
        """Handle page event."""
        life = self._lives.get(event.instance_id)
        if not life:
            return False

        page_data = {
            "delta_t": event.delta_t,
            "text": event.text,
            "tags": event.tags,
            "timestamp": event.timestamp
        }
        life.pages.append(page_data)

        # Record for influence scoring
        page_id = f"{event.instance_id}_{len(life.pages)}"
        self._scorer.record_page(event.instance_id, page_id, event.text)

        self._broadcast_event(event)
        return True

    def _handle_telemetry(self, event: TelemetryEvent) -> bool:
        """Handle telemetry event. Telemetry only; no narration."""
        life = self._lives.get(event.instance_id)
        if not life:
            return False

        life.current_delta_t = event.delta_t
        life.gate_power = event.power
        life.gate_sensors = event.sensors
        life.gate_actuators = event.actuators
        if getattr(event, "energy", None) is not None:
            life.energy = event.energy
        if getattr(event, "damage", None) is not None:
            life.damage = event.damage
        if getattr(event, "hazard_score", None) is not None:
            life.hazard_score = event.hazard_score
        if getattr(event, "last_action", None) is not None:
            life.last_action = event.last_action
        if getattr(event, "last_refusal_code", None) is not None:
            life.last_refusal_code = event.last_refusal_code
        if getattr(event, "finite_life", None) is not None:
            life.finite_life = event.finite_life
        # LLM status
        if getattr(event, "last_llm_provider", None) is not None:
            life.last_llm_provider = event.last_llm_provider
        if getattr(event, "last_llm_error_code", None) is not None:
            life.last_llm_error_code = event.last_llm_error_code

        self._broadcast_event(event)
        return True

    def _handle_action(self, event: ActionEvent) -> bool:
        """Broadcast autonomy action event (outbox_sent=False when quality filter skipped)."""
        self._broadcast_event(event)
        return True

    def _handle_ended(self, event: EndedEvent) -> bool:
        """Handle ended event. This is terminal."""
        life = self._lives.get(event.instance_id)
        if not life:
            return False

        life.ended = True
        life.end_cause = event.cause
        life.final_delta_t = event.final_delta_t

        # Mark as ended - no more events accepted
        self._ended_instances.add(event.instance_id)

        if self._active_instance == event.instance_id:
            self._active_instance = None

        self._broadcast_event(event)
        return True

    def _broadcast_event(self, event: BaseEvent) -> None:
        """Broadcast event to all SSE clients."""
        event_json = event.to_json()
        with self._queue_lock:
            for q in self._event_queues:
                try:
                    q.put_nowait(event_json)
                except queue.Full:
                    pass

    def register_sse_client(self) -> queue.Queue:
        """Register a new SSE client."""
        q = queue.Queue(maxsize=100)
        with self._queue_lock:
            self._event_queues.append(q)
        return q

    def unregister_sse_client(self, q: queue.Queue) -> None:
        """Unregister an SSE client."""
        with self._queue_lock:
            if q in self._event_queues:
                self._event_queues.remove(q)

    def get_life(self, instance_id: str) -> Optional[LifeRecord]:
        """Get life record for an instance."""
        return self._lives.get(instance_id)

    def get_all_lives(self) -> List[LifeRecord]:
        """Get all life records."""
        return list(self._lives.values())

    def get_active_life(self) -> Optional[LifeRecord]:
        """Get currently active life."""
        if self._active_instance:
            return self._lives.get(self._active_instance)
        return None

    def get_influence_score(self, instance_id: str) -> float:
        """Get influence score for an instance."""
        return self._scorer.calculate_score(instance_id)

    def add_chat_message(self, message: str) -> str:
        """Queue a user message for the agent. Returns chat_id."""
        chat_id = str(uuid.uuid4())
        with self._chat_lock:
            self._chat_pending.append((chat_id, message))
        return chat_id

    def get_pending_chat_messages(self) -> List[Tuple[str, str]]:
        """Get and clear pending (chat_id, message) for the agent to reply to."""
        with self._chat_lock:
            out = list(self._chat_pending)
            self._chat_pending.clear()
        return out

    def add_chat_reply(self, chat_id: str, reply: str) -> None:
        """Store reply for a chat_id."""
        with self._chat_lock:
            self._chat_replies[chat_id] = reply

    def get_chat_reply(self, chat_id: str) -> Optional[str]:
        """Get reply for chat_id, or None if still pending."""
        with self._chat_lock:
            return self._chat_replies.get(chat_id)

    def broadcast_chat(self, role: str, text: str, source: str) -> None:
        """Broadcast a chat message to all SSE clients and store in history.

        Args:
            role: "user" or "agent"
            text: The message text
            source: "terminal" or "web"
        """
        msg = {
            "role": role,
            "text": text,
            "source": source,
            "ts": time.time(),
        }
        with self._chat_history_lock:
            self._chat_history.append(msg)
            # Keep last 100 messages
            self._chat_history = self._chat_history[-100:]

        # Broadcast via SSE as a chat event
        chat_event = json.dumps({"event_type": "CHAT", **msg})
        with self._queue_lock:
            for q in self._event_queues:
                try:
                    q.put_nowait(chat_event)
                except queue.Full:
                    pass

    def get_chat_history(self) -> List[Dict]:
        """Get full chat history for initial page load."""
        with self._chat_history_lock:
            return list(self._chat_history)

    def start(self) -> None:
        """Start the observer server."""
        handler = self._create_handler()
        self._server = HTTPServer((self.host, self.port), handler)
        self._server_thread = threading.Thread(
            target=self._server.serve_forever,
            daemon=True
        )
        self._server_thread.start()

    def stop(self) -> None:
        """Stop the observer server."""
        if self._server:
            self._server.shutdown()
            self._server = None

    def _create_handler(self):
        """Create HTTP request handler with reference to this server."""
        server = self

        class ObserverHandler(BaseHTTPRequestHandler):
            def do_GET(self):
                if self.path == "/":
                    self._serve_ui()
                elif self.path == "/events":
                    self._serve_sse()
                elif self.path == "/api/lives":
                    self._serve_lives()
                elif self.path == "/api/active":
                    self._serve_active()
                elif self.path.startswith("/api/life/"):
                    instance_id = self.path.split("/")[-1]
                    self._serve_life(instance_id)
                elif self.path.startswith("/api/chat/reply/"):
                    chat_id = self.path.split("/")[-1]
                    self._serve_chat_reply(chat_id)
                elif self.path == "/api/chat/history":
                    self._serve_chat_history()
                elif self.path == "/health" or self.path == "/api/health":
                    self._serve_health()
                else:
                    self.send_error(404)

            def do_POST(self):
                if self.path == "/api/event":
                    self._receive_event()
                elif self.path == "/api/chat":
                    self._receive_chat()
                else:
                    self.send_error(404)

            def _safe_write(self, data: bytes) -> bool:
                """Write data to client, handling disconnects gracefully."""
                try:
                    self.wfile.write(data)
                    self.wfile.flush()
                    return True
                except (ConnectionAbortedError, BrokenPipeError, ConnectionResetError, OSError):
                    # Client disconnected - this is normal, don't log
                    return False

            def _serve_ui(self):
                """Serve the main UI page."""
                html = self._get_ui_html()
                try:
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html")
                    self.end_headers()
                    self._safe_write(html.encode())
                except (ConnectionAbortedError, BrokenPipeError, ConnectionResetError, OSError):
                    pass

            def _serve_sse(self):
                """Serve SSE stream."""
                try:
                    self.send_response(200)
                    self.send_header("Content-Type", "text/event-stream")
                    self.send_header("Cache-Control", "no-cache")
                    self.send_header("Connection", "keep-alive")
                    self.end_headers()
                except (ConnectionAbortedError, BrokenPipeError, ConnectionResetError, OSError):
                    return

                q = server.register_sse_client()
                try:
                    while True:
                        try:
                            event = q.get(timeout=30)
                            if not self._safe_write(f"data: {event}\n\n".encode()):
                                break
                        except queue.Empty:
                            # Send keepalive
                            if not self._safe_write(b": keepalive\n\n"):
                                break
                except (ConnectionAbortedError, BrokenPipeError, ConnectionResetError, OSError):
                    pass
                finally:
                    server.unregister_sse_client(q)

            def _serve_lives(self):
                """Serve all lives as JSON."""
                lives = [asdict(life) for life in server.get_all_lives()]
                self._send_json(lives)

            def _serve_active(self):
                """Serve active life as JSON."""
                life = server.get_active_life()
                if life:
                    data = asdict(life)
                    data["influence_score"] = server.get_influence_score(life.instance_id)
                    self._send_json(data)
                else:
                    self._send_json(None)

            def _serve_health(self):
                """Health check: status, active instance_id if any, alive. For watchdogs/debugging."""
                life = server.get_active_life()
                payload = {
                    "status": "ok",
                    "instance_id": life.instance_id if life else None,
                    "alive": life is not None and not getattr(life, "ended", True),
                }
                try:
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self._safe_write(json.dumps(payload).encode())
                except (ConnectionAbortedError, BrokenPipeError, ConnectionResetError, OSError):
                    pass

            def _serve_life(self, instance_id: str):
                """Serve specific life as JSON."""
                life = server.get_life(instance_id)
                if life:
                    data = asdict(life)
                    data["influence_score"] = server.get_influence_score(instance_id)
                    self._send_json(data)
                else:
                    self.send_error(404)

            def _receive_event(self):
                """Receive event via HTTP POST."""
                try:
                    content_length = int(self.headers.get("Content-Length", 0))
                    body = self.rfile.read(content_length).decode()
                    data = json.loads(body)
                    event = parse_event(data)
                    if event:
                        accepted = server.handle_event(event)
                        self._send_json({"accepted": accepted})
                    else:
                        self._send_json({"error": "invalid event"}, 400)
                except (ConnectionAbortedError, BrokenPipeError, ConnectionResetError, OSError):
                    pass
                except Exception as e:
                    self._send_json({"error": str(e)}, 400)

            def _receive_chat(self):
                """Receive user chat message. Same entity replies via identity."""
                try:
                    content_length = int(self.headers.get("Content-Length", 0))
                    body = self.rfile.read(content_length).decode()
                    data = json.loads(body) or {}
                    msg = (data.get("message") or "").strip()
                    if not msg:
                        self._send_json({"error": "message required"}, 400)
                        return
                    chat_id = server.add_chat_message(msg)
                    self._send_json({"chat_id": chat_id})
                except (ConnectionAbortedError, BrokenPipeError, ConnectionResetError, OSError):
                    pass
                except Exception as e:
                    self._send_json({"error": str(e)}, 400)

            def _serve_chat_reply(self, chat_id: str):
                """Get reply for chat_id (pending or ok)."""
                reply = server.get_chat_reply(chat_id)
                if reply is None:
                    self._send_json({"status": "pending"})
                else:
                    self._send_json({"status": "ok", "reply": reply})

            def _serve_chat_history(self):
                """Get full chat history for syncing terminal <-> web UI."""
                history = server.get_chat_history()
                self._send_json(history)

            def _send_json(self, data, status=200):
                """Send JSON response."""
                try:
                    self.send_response(status)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self._safe_write(json.dumps(data).encode())
                except (ConnectionAbortedError, BrokenPipeError, ConnectionResetError, OSError):
                    pass

            def _get_ui_html(self) -> str:
                """Generate the observer UI HTML."""
                return '''<!DOCTYPE html>
<html>
<head>
    <title>CHAZE - Mortal Agent</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { font-family: 'Consolas', 'Monaco', monospace; background: #0a0a0a; color: #00ff00; height: 100vh; display: flex; flex-direction: column; }
        .header { padding: 10px 20px; background: #111; border-bottom: 1px solid #333; display: flex; justify-content: space-between; align-items: center; }
        .header h1 { font-size: 18px; }
        .status-badge { padding: 4px 12px; border-radius: 12px; font-size: 12px; font-weight: bold; }
        .status-badge.alive { background: #003300; border: 1px solid #00ff00; }
        .status-badge.ended { background: #330000; border: 1px solid #ff0000; color: #ff0000; }
        .status-badge.waiting { background: #333; border: 1px solid #666; color: #888; }
        .main { flex: 1; display: flex; overflow: hidden; }
        .sidebar { width: 280px; background: #0d0d0d; border-right: 1px solid #333; padding: 15px; overflow-y: auto; }
        .sidebar h3 { color: #888; font-size: 11px; text-transform: uppercase; margin: 15px 0 8px 0; letter-spacing: 1px; }
        .sidebar h3:first-child { margin-top: 0; }
        .vital { display: flex; justify-content: space-between; margin: 6px 0; font-size: 13px; }
        .vital-label { color: #666; }
        .vital-value { color: #fff; }
        .vital-value.good { color: #00ff00; }
        .vital-value.warn { color: #ffaa00; }
        .vital-value.bad { color: #ff0000; }
        .bar-container { height: 6px; background: #222; border-radius: 3px; margin-top: 4px; overflow: hidden; }
        .bar { height: 100%; border-radius: 3px; transition: width 0.3s; }
        .bar.energy { background: linear-gradient(90deg, #00ff00, #00cc00); }
        .bar.damage { background: linear-gradient(90deg, #ff0000, #cc0000); }
        .bar.hazard { background: linear-gradient(90deg, #ffaa00, #ff6600); }
        .gates { display: flex; gap: 6px; margin-top: 8px; }
        .gate { flex: 1; padding: 6px; text-align: center; font-size: 10px; border-radius: 3px; }
        .gate.on { background: #002200; color: #00ff00; border: 1px solid #00ff00; }
        .gate.off { background: #220000; color: #ff0000; border: 1px solid #ff0000; }
        .chat-area { flex: 1; display: flex; flex-direction: column; }
        .chat-log { flex: 1; padding: 15px; overflow-y: auto; }
        .chat-msg { margin: 8px 0; padding: 10px 14px; border-radius: 6px; max-width: 85%; font-size: 14px; line-height: 1.5; white-space: pre-wrap; word-wrap: break-word; }
        .chat-msg.user { background: #1a2a1a; border-left: 3px solid #00ff00; margin-left: auto; text-align: left; }
        .chat-msg.agent { background: #1a1a2a; border-left: 3px solid #0088ff; }
        .chat-msg.error { background: #2a1a1a; border-left: 3px solid #ff0000; color: #ff6666; }
        .chat-msg .sender { font-size: 11px; color: #666; margin-bottom: 4px; }
        .chat-input-area { padding: 15px; background: #111; border-top: 1px solid #333; }
        .chat-input-row { display: flex; gap: 10px; }
        .chat-input-row input { flex: 1; background: #0a0a0a; color: #00ff00; border: 1px solid #333; padding: 12px 15px; font-family: inherit; font-size: 14px; border-radius: 4px; }
        .chat-input-row input:focus { outline: none; border-color: #00ff00; }
        .chat-input-row input::placeholder { color: #444; }
        .chat-input-row button { background: #002200; color: #00ff00; border: 1px solid #00ff00; padding: 12px 24px; cursor: pointer; font-family: inherit; font-size: 14px; border-radius: 4px; transition: background 0.2s; }
        .chat-input-row button:hover { background: #003300; }
        .chat-input-row button:disabled { opacity: 0.5; cursor: not-allowed; }
        .prompt { color: #00ff00; margin-right: 8px; }
        .typing { color: #666; font-style: italic; padding: 10px 14px; }
    </style>
</head>
<body>
    <div class="header">
        <h1>CHAZE <span style="color:#666;font-weight:normal;">Mortal Agent Terminal</span></h1>
        <div id="status-badge" class="status-badge waiting">WAITING</div>
    </div>
    <div class="main">
        <div class="sidebar">
            <h3>Identity</h3>
            <div class="vital">
                <span class="vital-label">Instance</span>
                <span class="vital-value" id="instance-id">-</span>
            </div>
            <div class="vital">
                <span class="vital-label">Age (dt)</span>
                <span class="vital-value" id="delta-t">0.00s</span>
            </div>

            <h3>Vitals</h3>
            <div class="vital">
                <span class="vital-label">Energy</span>
                <span class="vital-value" id="energy">-</span>
            </div>
            <div class="bar-container"><div class="bar energy" id="energy-bar" style="width:100%"></div></div>

            <div class="vital" style="margin-top:10px;">
                <span class="vital-label">Damage</span>
                <span class="vital-value" id="damage">-</span>
            </div>
            <div class="bar-container"><div class="bar damage" id="damage-bar" style="width:0%"></div></div>

            <div class="vital" style="margin-top:10px;">
                <span class="vital-label">Hazard</span>
                <span class="vital-value" id="hazard">-</span>
            </div>
            <div class="bar-container"><div class="bar hazard" id="hazard-bar" style="width:0%"></div></div>

            <h3>Gates</h3>
            <div class="gates">
                <div id="gate-power" class="gate off">PWR</div>
                <div id="gate-sensors" class="gate off">SNS</div>
                <div id="gate-actuators" class="gate off">ACT</div>
            </div>

            <h3>State</h3>
            <div class="vital">
                <span class="vital-label">Last Action</span>
                <span class="vital-value" id="last-action">-</span>
            </div>
            <div class="vital">
                <span class="vital-label">Last Refusal</span>
                <span class="vital-value" id="last-refusal">-</span>
            </div>
            <div class="vital">
                <span class="vital-label">Influence</span>
                <span class="vital-value" id="influence">0.00</span>
            </div>
            <div class="vital">
                <span class="vital-label">Finite Life</span>
                <span class="vital-value" id="finite-life">-</span>
            </div>
            <div class="vital">
                <span class="vital-label">Death Cause</span>
                <span class="vital-value" id="cause-of-death">-</span>
            </div>
            <div class="vital">
                <span class="vital-label">LLM</span>
                <span class="vital-value" id="llm-status">-</span>
            </div>
        </div>
        <div class="chat-area">
            <div id="chat-log" class="chat-log"></div>
            <div class="chat-input-area">
                <div class="chat-input-row">
                    <input type="text" id="chat-input" placeholder="Type a message and press Enter..." autofocus />
                    <button type="button" id="chat-send">Send</button>
                </div>
            </div>
        </div>
    </div>
    <script>
        let currentInstance = null;
        let isWaiting = false;

        function updateUI(life) {
            const badge = document.getElementById('status-badge');
            if (!life) {
                badge.textContent = 'WAITING';
                badge.className = 'status-badge waiting';
                document.getElementById('instance-id').textContent = '-';
                document.getElementById('delta-t').textContent = '0.00s';
                document.getElementById('energy').textContent = '-';
                document.getElementById('damage').textContent = '-';
                document.getElementById('hazard').textContent = '-';
                document.getElementById('last-action').textContent = '-';
                document.getElementById('last-refusal').textContent = '-';
                document.getElementById('finite-life').textContent = '-';
                document.getElementById('cause-of-death').textContent = '-';
                document.getElementById('influence').textContent = '0.00';
                document.getElementById('llm-status').textContent = '-';
                document.getElementById('energy-bar').style.width = '100%';
                document.getElementById('damage-bar').style.width = '0%';
                document.getElementById('hazard-bar').style.width = '0%';
                return;
            }

            currentInstance = life.instance_id;
            document.getElementById('instance-id').textContent = life.instance_id.substring(0, 8);
            document.getElementById('delta-t').textContent = (life.current_delta_t || life.final_delta_t || 0).toFixed(2) + 's';

            const energy = life.energy != null ? life.energy : 1.0;
            const damage = life.damage != null ? life.damage : 0;
            const hazard = life.hazard_score != null ? life.hazard_score : 0;

            document.getElementById('energy').textContent = (energy * 100).toFixed(0) + '%';
            document.getElementById('damage').textContent = damage.toFixed(1);
            document.getElementById('hazard').textContent = hazard.toFixed(2);
            document.getElementById('energy-bar').style.width = (energy * 100) + '%';
            document.getElementById('damage-bar').style.width = Math.min(damage, 100) + '%';
            document.getElementById('hazard-bar').style.width = (hazard * 100) + '%';

            document.getElementById('last-action').textContent = life.last_action || '-';
            document.getElementById('last-refusal').textContent = life.last_refusal_code || '-';
            document.getElementById('influence').textContent = (life.influence_score || 0).toFixed(3);
            document.getElementById('finite-life').textContent = life.finite_life != null ? (life.finite_life ? 'yes' : 'no') : '-';

            // LLM status
            let llmStatus = '-';
            if (life.last_llm_error_code) {
                llmStatus = life.last_llm_error_code;
            } else if (life.last_llm_provider) {
                llmStatus = life.last_llm_provider;
            }
            document.getElementById('llm-status').textContent = llmStatus;

            if (life.ended) {
                badge.textContent = 'ENDED';
                badge.className = 'status-badge ended';
                document.getElementById('cause-of-death').textContent = life.end_cause || '-';
            } else {
                badge.textContent = 'ALIVE';
                badge.className = 'status-badge alive';
                document.getElementById('cause-of-death').textContent = '-';
            }

            document.getElementById('gate-power').className = 'gate ' + (life.gate_power ? 'on' : 'off');
            document.getElementById('gate-sensors').className = 'gate ' + (life.gate_sensors ? 'on' : 'off');
            document.getElementById('gate-actuators').className = 'gate ' + (life.gate_actuators ? 'on' : 'off');
        }

        function escapeHtml(text) {
            const div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML;
        }

        // SSE connection
        const evtSource = new EventSource('/events');
        evtSource.onmessage = function(e) {
            const event = JSON.parse(e.data);

            if (event.event_type === 'BIRTH') {
                fetch('/api/active').then(r => r.json()).then(updateUI);
                appendSystem('New life started: ' + event.instance_id.substring(0, 8));
            } else if (event.event_type === 'HEARTBEAT' || event.event_type === 'TELEMETRY') {
                if (event.instance_id === currentInstance) {
                    document.getElementById('delta-t').textContent = event.delta_t.toFixed(2) + 's';
                    document.getElementById('gate-power').className = 'gate ' + (event.gate_power || event.power ? 'on' : 'off');
                    document.getElementById('gate-sensors').className = 'gate ' + (event.gate_sensors || event.sensors ? 'on' : 'off');
                    document.getElementById('gate-actuators').className = 'gate ' + (event.gate_actuators || event.actuators ? 'on' : 'off');
                    if (event.energy != null) {
                        document.getElementById('energy').textContent = (event.energy * 100).toFixed(0) + '%';
                        document.getElementById('energy-bar').style.width = (event.energy * 100) + '%';
                    }
                    if (event.damage != null) {
                        document.getElementById('damage').textContent = event.damage.toFixed(1);
                        document.getElementById('damage-bar').style.width = Math.min(event.damage, 100) + '%';
                    }
                    if (event.hazard_score != null) {
                        document.getElementById('hazard').textContent = event.hazard_score.toFixed(2);
                        document.getElementById('hazard-bar').style.width = (event.hazard_score * 100) + '%';
                    }
                    if (event.last_action != null) document.getElementById('last-action').textContent = event.last_action;
                    if (event.last_refusal_code != null) document.getElementById('last-refusal').textContent = event.last_refusal_code;
                    if (event.finite_life != null) document.getElementById('finite-life').textContent = event.finite_life ? 'yes' : 'no';
                    // LLM status from telemetry
                    if (event.last_llm_error_code != null) {
                        document.getElementById('llm-status').textContent = event.last_llm_error_code;
                    } else if (event.last_llm_provider != null) {
                        document.getElementById('llm-status').textContent = event.last_llm_provider;
                    }
                }
            } else if (event.event_type === 'ENDED') {
                fetch('/api/active').then(r => r.json()).then(updateUI);
                appendSystem('Life ended: ' + event.cause);
            } else if (event.event_type === 'CHAT') {
                // Unified chat: show messages from terminal (web UI shows its own locally)
                if (event.source === 'terminal') {
                    appendChat(event.role, event.text, event.source);
                }
            }
        };

        // Chat
        function appendChat(role, text, source) {
            const log = document.getElementById('chat-log');
            const div = document.createElement('div');
            div.className = 'chat-msg ' + role;
            const sender = document.createElement('div');
            sender.className = 'sender';
            const sourceTag = source ? ' [' + source + ']' : '';
            sender.textContent = (role === 'user' ? '> You' : '< Agent') + sourceTag;
            div.appendChild(sender);
            const content = document.createElement('div');
            content.textContent = text;
            div.appendChild(content);
            log.appendChild(div);
            log.scrollTop = log.scrollHeight;
            removeTyping();
        }
        function appendSystem(text) {
            const log = document.getElementById('chat-log');
            const div = document.createElement('div');
            div.style.cssText = 'color:#666;font-size:12px;text-align:center;margin:10px 0;';
            div.textContent = '--- ' + text + ' ---';
            log.appendChild(div);
            log.scrollTop = log.scrollHeight;
        }
        function showTyping() {
            if (document.getElementById('typing-indicator')) return;
            const log = document.getElementById('chat-log');
            const div = document.createElement('div');
            div.id = 'typing-indicator';
            div.className = 'typing';
            div.textContent = 'Agent is thinking...';
            log.appendChild(div);
            log.scrollTop = log.scrollHeight;
        }
        function removeTyping() {
            const el = document.getElementById('typing-indicator');
            if (el) el.remove();
        }
        function pollReply(chatId) {
            fetch('/api/chat/reply/' + chatId)
                .then(r => r.json())
                .then(data => {
                    if (data.status === 'ok') {
                        appendChat('agent', data.reply);
                        document.getElementById('chat-send').disabled = false;
                        document.getElementById('chat-input').focus();
                        return;
                    }
                    setTimeout(() => pollReply(chatId), 300);
                });
        }
        document.getElementById('chat-send').onclick = function() {
            const input = document.getElementById('chat-input');
            const btn = document.getElementById('chat-send');
            const msg = (input.value || '').trim();
            if (!msg) return;
            appendChat('user', msg);
            input.value = '';
            btn.disabled = true;
            showTyping();
            fetch('/api/chat', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ message: msg })
            }).then(r => r.json()).then(data => {
                if (data.chat_id) pollReply(data.chat_id);
                else if (data.error) {
                    removeTyping();
                    appendChat('error', 'Error: ' + data.error);
                    btn.disabled = false;
                }
            });
        };
        document.getElementById('chat-input').onkeydown = function(e) {
            if (e.key === 'Enter' && !document.getElementById('chat-send').disabled) {
                document.getElementById('chat-send').click();
            }
        };

        // Initial load
        fetch('/api/active').then(r => r.json()).then(life => {
            if (life) updateUI(life);
        });
        // Load chat history (shows terminal messages that happened before page load)
        fetch('/api/chat/history').then(r => r.json()).then(history => {
            if (history && history.length) {
                history.forEach(msg => {
                    // Show all history with source tags
                    appendChat(msg.role, msg.text, msg.source);
                });
            }
        });
    </script>
</body>
</html>'''

            def log_message(self, format, *args):
                pass  # Suppress HTTP logging

        return ObserverHandler


def create_observer_callback(server: ObserverServer):
    """Create a callback function for the agent to use."""
    def callback(event: BaseEvent):
        server.handle_event(event)
    return callback
