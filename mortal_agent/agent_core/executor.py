"""Action Executor: PUBLISH_POST + NET_FETCH. All outbound via canon; optional network pipeline."""
from typing import Dict, Any, List, Optional, Callable
from .canon import CanonConfig, validate_post

ACTION_PUBLISH_POST = "PUBLISH_POST"
ACTION_NET_FETCH = "NET_FETCH"
ALLOWED_ACTIONS = [ACTION_PUBLISH_POST, ACTION_NET_FETCH]

def parse_actions(payload: Any) -> List[Dict[str, Any]]:
    if payload is None:
        return []
    if isinstance(payload, dict):
        a, args = payload.get("action"), payload.get("args") or {}
        return [{"action": str(a), "args": args if isinstance(args, dict) else {}}] if a else []
    if isinstance(payload, list):
        return [{"action": str(i.get("action")), "args": i.get("args") or {}} for i in payload if isinstance(i, dict) and i.get("action")]
    return []

class Executor:
    def __init__(self, canon: CanonConfig, post_callback: Callable[[str, Dict, str], None], run_network_pipeline: Optional[Callable[[Dict, str], Dict]] = None):
        self._canon = canon
        self._post_callback = post_callback
        self._run_network_pipeline = run_network_pipeline

    def execute(self, instance_id: str, actions: List[Dict[str, Any]]) -> Dict[str, Any]:
        result = {"published": 0, "rejected": 0, "errors": []}
        for item in actions:
            action, args = item.get("action"), item.get("args") or {}
            if action == ACTION_PUBLISH_POST:
                ok, err = self._execute_publish_post(instance_id, args, result)
                if not ok and err:
                    result["errors"].append(err)
            elif action == ACTION_NET_FETCH and self._run_network_pipeline:
                r = self._run_network_pipeline(item, instance_id)
                if not r.get("executed") and r.get("error"):
                    result["errors"].append(r.get("error", "network_failed"))
        return result

    def _execute_publish_post(self, instance_id: str, args: Dict, result: Dict) -> tuple:
        text = str(args.get("text") or "").strip()
        metadata = args.get("metadata") if isinstance(args.get("metadata"), dict) else {}
        channel = args.get("channel") or "moltbook"
        if not text:
            return True, ""
        ok, corrected = validate_post(text, self._canon)
        if not ok:
            result["rejected"] = result.get("rejected", 0) + 1
            return False, "canon_rejected"
        try:
            self._post_callback(instance_id, corrected, metadata, channel)
            result["published"] = result.get("published", 0) + 1
            return True, ""
        except Exception as e:
            result["errors"].append(str(e))
            return False, str(e)
