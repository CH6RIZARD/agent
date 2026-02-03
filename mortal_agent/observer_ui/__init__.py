# Observer UI - Moltbook-like UI (non-critical, best-effort)
# Server implementation in moltbook_observer; observer_ui is the canonical API.
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from moltbook_observer import ObserverServer, create_observer_callback
from .observer_client import ObserverClient

__all__ = ["ObserverServer", "create_observer_callback", "ObserverClient"]
