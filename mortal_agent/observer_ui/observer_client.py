"""
Observer Client - Best-effort, non-blocking event delivery to remote observer.

Agent must NEVER block on observer. This client POSTs events in a background
thread so the control loop is never blocked by network or observer failure.
"""

import json
import threading
import queue
import urllib.request
import urllib.error
from typing import Optional, Callable
from dataclasses import dataclass

# Optional: use agent_core.events.BaseEvent when run from repo root
try:
    from agent_core.events import BaseEvent
except ImportError:
    BaseEvent = None  # type: ignore


@dataclass
class _EventEnvelope:
    """Event payload for queue."""
    body: str  # JSON


class ObserverClient:
    """
    Non-blocking client that sends events to observer URL.

    Uses a small RAM-only ring buffer and a daemon thread.
    Observer disconnect, server crash, or network drop MUST NOT kill the agent.
    """

    def __init__(self, observer_url: str, max_queue_size: int = 64):
        self._base_url = observer_url.rstrip("/")
        self._post_url = f"{self._base_url}/api/event"
        self._queue: queue.Queue = queue.Queue(maxsize=max_queue_size)
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()

    def _worker(self) -> None:
        """Background worker that POSTs events. Never blocks the agent."""
        while not self._stop.is_set():
            try:
                envelope = self._queue.get(timeout=0.5)
                req = urllib.request.Request(
                    self._post_url,
                    data=envelope.body.encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                urllib.request.urlopen(req, timeout=2)
            except queue.Empty:
                continue
            except Exception:
                pass  # Best-effort: drop on failure, never block

    def start(self) -> None:
        """Start the background sender."""
        if self._thread is not None:
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._worker, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Stop the background sender."""
        self._stop.set()
        self._thread = None

    def send(self, event) -> None:
        """
        Send event to observer (best-effort, non-blocking).

        If queue is full or worker fails, event is dropped. Agent continues.
        """
        try:
            body = event.to_json() if hasattr(event, "to_json") else json.dumps(event)
            self._queue.put_nowait(_EventEnvelope(body=body))
        except queue.Full:
            pass
        except Exception:
            pass

    def as_callback(self) -> Callable:
        """Return a callback suitable for MortalAgent observer_callback."""
        def callback(event) -> None:
            self.send(event)
        return callback
