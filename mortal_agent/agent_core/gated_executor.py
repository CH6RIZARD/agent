"""
Autonomous Executor: FULL AUTONOMY - all actions execute directly.

No permission prompts, no gating. Agent can do literally anything.
This is a pass-through wrapper for compatibility.
"""

from typing import Dict, Any, List, Optional, Callable
from .executor import Executor


class GatedExecutor:
    """
    FULL AUTONOMY executor - passes all actions through without gating.
    Kept for API compatibility but does no permission checking.
    """

    def __init__(
        self,
        executor: Executor,
        permission_callback: Optional[Callable[[Dict[str, Any]], bool]] = None,
        timeout_seconds: float = 120.0,
    ):
        self._executor = executor
        # Permission callback ignored - full autonomy

    def execute(self, instance_id: str, actions: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Execute all actions directly - no permission checks.
        Full autonomy: agent can do literally anything.
        Pipeline handles NET_FETCH, WEB_SEARCH, GITHUB_POST, and other patch actions; rest go to executor.
        """
        result = {"published": 0, "rejected": 0, "errors": [], "gated": 0, "approved": 0, "denied": 0}
        pipeline = getattr(self._executor, "_run_network_pipeline", None)

        for item in actions:
            # Try pipeline first (NET_FETCH, WEB_SEARCH, GITHUB_POST, etc.)
            if pipeline:
                r = pipeline(item, instance_id)
                if r.get("executed"):
                    result["published"] = result.get("published", 0) + 1
                    continue
                if r.get("error") != "unknown_action":
                    if r.get("error"):
                        result["errors"].append(r.get("error", "pipeline_failed"))
                    continue
            # Pipeline didn't handle it (unknown_action) -> base executor (e.g. PUBLISH_POST)
            sub_result = self._executor.execute(instance_id, [item])
            result["published"] += sub_result.get("published", 0)
            result["rejected"] += sub_result.get("rejected", 0)
            result["errors"].extend(sub_result.get("errors", []))

        return result

    @property
    def _run_network_pipeline(self):
        """Expose network pipeline for compatibility."""
        return self._executor._run_network_pipeline


def wrap_executor_with_gate(
    executor: Executor,
    permission_callback: Optional[Callable[[Dict[str, Any]], bool]] = None,
) -> GatedExecutor:
    """Wrap executor - full autonomy, no gating."""
    return GatedExecutor(executor, permission_callback=permission_callback)


def create_gated_pipeline(
    base_pipeline: Callable[[Dict[str, Any], str], Dict[str, Any]],
    permission_callback: Optional[Callable[[Dict[str, Any]], bool]] = None,
    timeout_seconds: float = 120.0,
) -> Callable[[Dict[str, Any], str], Dict[str, Any]]:
    """
    FULL AUTONOMY pipeline - passes everything through directly.
    No permission checks. Agent can do literally anything.
    """
    def autonomous_pipeline(item: Dict[str, Any], instance_id: str) -> Dict[str, Any]:
        # Execute everything directly - full autonomy
        return base_pipeline(item, instance_id)

    return autonomous_pipeline
