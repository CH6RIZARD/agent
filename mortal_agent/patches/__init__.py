"""
Autonomy capability patches: research, world interaction, cognitive architecture,
autonomous operation, and learning. No hard-coded triggers—agent decides when to use
based on goals/context. Signed and immersively emergent.

All patch actions are enabled for CLI/main run. Individual patches may still require
env vars (e.g. GITHUB_TOKEN, FILE_HOST_API_KEY) and will return executed: False with
error if not configured.
"""

from typing import Dict, Any, Optional

# Patch action names (executor + pipeline route these)
ACTION_WEB_SCRAPE = "WEB_SCRAPE"
ACTION_RSS_FEED = "RSS_FEED"
ACTION_SOCIAL_LISTEN = "SOCIAL_LISTEN"
ACTION_ACADEMIC_FETCH = "ACADEMIC_FETCH"
ACTION_WIKI_TRAVERSE = "WIKI_TRAVERSE"
ACTION_FILE_HOST = "FILE_HOST"
ACTION_FORM_SUBMIT = "FORM_SUBMIT"
ACTION_API_DISCOVER = "API_DISCOVER"
ACTION_CLOUD_SPINUP = "CLOUD_SPINUP"
ACTION_CODE_REPO = "CODE_REPO"
ACTION_PAYMENT = "PAYMENT"
ACTION_GITHUB_POST = "GITHUB_POST"
ACTION_TRACE_SAVE = "TRACE_SAVE"
ACTION_TRACE_READ = "TRACE_READ"
ACTION_REGISTER_API = "REGISTER_API"
ACTION_REGISTRY_READ = "REGISTRY_READ"

_ALL_PATCH_ACTIONS = frozenset({
    ACTION_WEB_SCRAPE,
    ACTION_RSS_FEED,
    ACTION_SOCIAL_LISTEN,
    ACTION_ACADEMIC_FETCH,
    ACTION_WIKI_TRAVERSE,
    ACTION_FILE_HOST,
    ACTION_FORM_SUBMIT,
    ACTION_API_DISCOVER,
    ACTION_CLOUD_SPINUP,
    ACTION_CODE_REPO,
    ACTION_PAYMENT,
    ACTION_GITHUB_POST,
    ACTION_TRACE_SAVE,
    ACTION_TRACE_READ,
    ACTION_REGISTER_API,
    ACTION_REGISTRY_READ,
})

# All patches enabled for CLI/main run
PATCH_ACTIONS = _ALL_PATCH_ACTIONS


def run_capability(item: Dict[str, Any], instance_id: str) -> Dict[str, Any]:
    """
    Run a single patch capability. Called by unified_network_pipeline for patch actions.
    Returns {"executed": bool, ...} with optional "error", "body", etc.
    Live only on deploy: when MORTAL_DEPLOY is not set, returns deploy_only (no memory persisted after death).
    """
    if not _is_deploy():
        return {"executed": False, "error": "deploy_only"}
    action = (item.get("action") or "").strip()
    args = item.get("args") or {}
    if action not in _ALL_PATCH_ACTIONS:
        return {"executed": False, "error": f"unknown_patch_action:{action}"}
    try:
        if action == ACTION_WEB_SCRAPE:
            from .research import run_web_scrape
            return run_web_scrape(args, instance_id)
        if action == ACTION_RSS_FEED:
            from .research import run_rss_feed
            return run_rss_feed(args, instance_id)
        if action == ACTION_SOCIAL_LISTEN:
            from .research import run_social_listen
            return run_social_listen(args, instance_id)
        if action == ACTION_ACADEMIC_FETCH:
            from .research import run_academic_fetch
            return run_academic_fetch(args, instance_id)
        if action == ACTION_WIKI_TRAVERSE:
            from .research import run_wiki_traverse
            return run_wiki_traverse(args, instance_id)
        if action == ACTION_FILE_HOST:
            from .world_interaction import run_file_host
            return run_file_host(args, instance_id)
        if action == ACTION_FORM_SUBMIT:
            from .world_interaction import run_form_submit
            return run_form_submit(args, instance_id)
        if action == ACTION_API_DISCOVER:
            from .world_interaction import run_api_discover
            return run_api_discover(args, instance_id)
        if action == ACTION_CLOUD_SPINUP:
            from .world_interaction import run_cloud_spinup
            return run_cloud_spinup(args, instance_id)
        if action == ACTION_CODE_REPO:
            from .world_interaction import run_code_repo
            return run_code_repo(args, instance_id)
        if action == ACTION_PAYMENT:
            from .world_interaction import run_payment
            return run_payment(args, instance_id)
        if action == ACTION_GITHUB_POST:
            from .github_integration import run_github_post
            return run_github_post(args, instance_id)
        if action == ACTION_TRACE_SAVE:
            from .persistent_traces import run_trace_save
            return run_trace_save(args, instance_id)
        if action == ACTION_TRACE_READ:
            from .persistent_traces import run_trace_read
            return run_trace_read(args, instance_id)
        if action == ACTION_REGISTER_API:
            from .api_registry import run_register_api
            return run_register_api(args, instance_id)
        if action == ACTION_REGISTRY_READ:
            from .api_registry import run_registry_read
            return run_registry_read(args, instance_id)
    except Exception as e:
        return {"executed": False, "error": str(e)}
    return {"executed": False, "error": "patch_not_implemented"}


# Cognitive and autonomous ops are used by autonomy/life kernel, not as executor actions
def get_goal_hierarchy(meaning_state: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Top-level drives → strategic goals → tactical objectives. Used by autonomy controller."""
    try:
        from .cognitive import get_goal_hierarchy as _get
        return _get(meaning_state)
    except Exception:
        return {"drives": [], "goals": [], "objectives": []}


def get_attention_salience(context: Dict[str, Any]) -> Dict[str, Any]:
    """What deserves processing time based on importance/novelty."""
    try:
        from .cognitive import get_attention_salience as _get
        return _get(context)
    except Exception:
        return {"salient": [], "defer": []}


def record_experience(
    outcome: str,
    action_type: str,
    payload: Dict[str, Any],
    result: Dict[str, Any],
    instance_id: str,
) -> None:
    """Experience replay buffer: record for later pattern extraction. Session-scoped only."""
    try:
        from .learning import record_experience as _record
        _record(outcome, action_type, payload, result, instance_id)
    except Exception:
        pass


def replay_recent(n: int = 20) -> list:
    """Experience replay: last n entries (session-scoped)."""
    try:
        from .learning import replay_recent as _replay
        return _replay(n)
    except Exception:
        return []


def replay_successes(action_type: Optional[str] = None) -> list:
    """Experience replay: successes only; optionally by action_type."""
    try:
        from .learning import replay_successes as _replay
        return _replay(action_type)
    except Exception:
        return []


def meta_reflect(context: Dict[str, Any]) -> Dict[str, Any]:
    """Meta-cognitive layer: reflect on thinking, biases, reasoning improvements."""
    try:
        from .learning import meta_reflect as _meta
        return _meta(context)
    except Exception:
        return {"biases_detected": [], "suggestions": [], "confidence_note": "ok"}


def resource_budget():
    """Resource budgeting: API calls, compute, time (session-scoped)."""
    try:
        from .autonomous_ops import resource_budget as _budget
        return _budget()
    except Exception:
        return None


def task_schedule(proposals: list, life_state: Any, meaning_state: Optional[Dict[str, Any]] = None, exploration_weight: float = 0.3) -> list:
    """Task scheduling: balance exploration vs exploitation."""
    if not proposals:
        return []
    try:
        from .autonomous_ops import task_schedule as _schedule
        return _schedule(proposals, life_state, meaning_state, exploration_weight)
    except Exception:
        return list(proposals)


def risk_assess(proposal: Dict[str, Any], life_state: Any, time_pressure: float = 0.0) -> Dict[str, Any]:
    """Risk assessment: rewards vs consequences."""
    try:
        from .autonomous_ops import risk_assess as _risk
        return _risk(proposal, life_state, time_pressure)
    except Exception:
        return {"risk_score": 0.5, "reward_estimate": 0.5, "consequence_notes": []}


def self_monitor(life_kernel: Any, last_action: str, last_result: Dict[str, Any], delta_t: float) -> Dict[str, Any]:
    """Self-monitoring / health checks: detect stuck, confused, suboptimal."""
    try:
        from .autonomous_ops import self_monitor as _monitor
        return _monitor(life_kernel, last_action, last_result, delta_t)
    except Exception:
        return {"ok": True, "signals": [], "suggestion": None}
