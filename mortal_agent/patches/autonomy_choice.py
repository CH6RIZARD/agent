"""
Meta-action: SELECT_AUTONOMY_ACTIONS — autonomous action that lets the agent choose
which other autonomous actions run next (e.g. NET_FETCH, WEB_SEARCH, REGISTER_API).

Pushes to selected_actions_queue; consumed by run_autonomy_tick.

Invariants (strict): no persistence, no respawn, no memory across states. Queue is
RAM-only per instance; cleared on death. Allowed: only changing what runs in this
instance; forbidden: changing persistence, respawn, or cross-state memory.
"""

from typing import Dict, Any, List


def run_select_autonomy_actions(args: Dict[str, Any], instance_id: str) -> Dict[str, Any]:
    """
    Queue autonomy actions for this instance. Next tick(s) will execute them in order.

    Args:
        actions: list of {"action": str, "args": dict}. Action can be any autonomy action
                 (NET_FETCH, WEB_SEARCH, PUBLISH_POST, REGISTER_API, GITHUB_POST, etc.).

    No persistence, no respawn, no memory across states — queue is RAM only per instance.
    """
    actions = args.get("actions") or args.get("action_list") or []
    if isinstance(actions, dict):
        actions = [actions]
    if not isinstance(actions, list):
        return {"executed": False, "error": "actions_must_be_list"}

    try:
        from ..agent_core.selected_actions_queue import push
    except ImportError:
        try:
            from mortal_agent.agent_core.selected_actions_queue import push
        except ImportError:
            from agent_core.selected_actions_queue import push
    push(instance_id, actions)
    return {"executed": True, "queued": len(actions), "note": "next_autonomy_tick_will_run_these"}
