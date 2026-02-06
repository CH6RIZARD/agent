"""
Queue of autonomy actions chosen by the agent via SELECT_AUTONOMY_ACTIONS (meta-action).
Per instance_id; consumed by run_autonomy_tick. RAM only; no persistence across runs.
"""

from typing import Dict, List, Any, Optional
from threading import Lock

_QUEUE: Dict[str, List[Dict[str, Any]]] = {}
_LOCK = Lock()
_MAX_PER_INSTANCE = 20


def push(instance_id: str, actions: List[Dict[str, Any]]) -> None:
    """Append chosen actions for this instance. Each item: {"action": str, "args": dict}."""
    if not instance_id or not actions:
        return
    with _LOCK:
        q = _QUEUE.setdefault(instance_id, [])
        for a in actions[: _MAX_PER_INSTANCE - len(q)]:
            if isinstance(a, dict) and a.get("action"):
                q.append({"action": str(a["action"]).strip(), "args": a.get("args") or {}})


def pop(instance_id: str) -> Optional[Dict[str, Any]]:
    """Pop one chosen action for this instance. Returns {"action_type": str, "payload": dict} or None."""
    with _LOCK:
        q = _QUEUE.get(instance_id)
        if not q:
            return None
        item = q.pop(0)
        return {"action_type": item["action"], "payload": item.get("args") or {}}


def peek_count(instance_id: str) -> int:
    """Number of queued actions for this instance."""
    with _LOCK:
        return len(_QUEUE.get(instance_id) or [])
