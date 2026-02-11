"""
Autonomy loop: survival-aware initiative, internal proposals, will kernel, action commit.
Homeostasis expression: doctrine-driven natural text via textforge; observer always gets events.
Self-governed NET_FETCH: one-shot prompt decides when and what URL to fetch at will.

Survival-aware changes:
- Uses survival_reasoner for action selection when available
- Tracks time pressure and adjusts behavior
- Supports CONSERVE and CONSOLIDATE actions
- Records survival decisions to life_kernel

Offline wander mode: when LLM is unavailable (--no-llm or provider failure), the agent
continues with deterministic doctrine-driven wander behavior. No stalling, no error spam.
"""

import os
import random
import re
import time
from pathlib import Path
from typing import Optional, Callable, Any, Dict, List
from .runtime_state import RuntimeState
from .planner import (
    PlanResult,
    parse_plan_response,
    default_action,
    CONFIDENCE_THRESHOLD,
    CONFIDENCE_ACT_IMMEDIATE,
    CONFIDENCE_QUICK_CHECK,
)
from .narrator import narrate, generate_narrator_bias, generate_narrator_proposal
from .speech_gate import speech_suppression_gate, GateResult
from .output_medium import OUTPUT_MEDIUM_DEFAULT
import json

try:
    from .capabilities import is_low_risk_action
except ImportError:
    def is_low_risk_action(action: str) -> bool:
        return (action or "").lower() in ("web_search", "net_fetch", "publish_post", "web_fetch", "view_file", "wikipedia_lookup", "send_email", "post_social_media")

def _autonomy_fallback_text() -> str:
    """LLM-only: single fallback when no LLM text for autonomous post."""
    try:
        from .llm_router import get_offline_wander_text
        return get_offline_wander_text()
    except Exception:
        return "I can't reach my reasoning right now."


def _is_unreachable_fallback(text: str) -> bool:
    """True if text is the unreachable line. Autonomy skips posting it so we don't contradict working chat."""
    try:
        from .llm_router import is_unreachable_fallback as _check
        return _check(text or "")
    except Exception:
        return (text or "").strip() == "I can't reach my reasoning right now."


try:
    from .intent_loop import generate_internal_proposals
    from .will_kernel import select_action
    from .action_commit import commit_begin, commit_end
    from .threat_model import LifeState
except ImportError:
    generate_internal_proposals = None
    select_action = None
    commit_begin = lambda x: True
    commit_end = lambda: None
    LifeState = None

# Import survival reasoning (new)
try:
    from .survival_reasoner import (
        decide_survival_action,
        compute_time_pressure,
        SurvivalDecision,
    )
    SURVIVAL_REASONER_AVAILABLE = True
except ImportError:
    SURVIVAL_REASONER_AVAILABLE = False
    decide_survival_action = None
    compute_time_pressure = None
    SurvivalDecision = None

try:
    from . import textforge
    from .textforge import (
        DoctrineAnchors,
        ArchetypeGenerator,
        NaturalTextFilter,
        TextForgeState,
        regenerate_loop,
        compute_voice_mode,
        may_send_outbox,
        N_LAST,
    )
    from .events import ActionEvent, PageEvent
except ImportError:
    textforge = None

AUTONOMY_TICK_INTERVAL = 2.0
POST_COOLDOWN_SECONDS = 15.0
INITIATIVE_MIN_INTERVAL = 25.0
FETCH_DECISION_INTERVAL = 12.0  # seconds between autonomy browse decisions (fetch or search)
WANDER_INTERVAL = 25.0  # seconds between offline wander posts

# All patch/capability actions autonomy can execute via executor (GITHUB_POST, TRACE_SAVE, etc.)
try:
    from ..patches import PATCH_ACTIONS as _AUTONOMY_PASSTHROUGH_ACTIONS
except Exception:
    _AUTONOMY_PASSTHROUGH_ACTIONS = frozenset({
        "GITHUB_POST", "TRACE_SAVE", "TRACE_READ", "FILE_HOST", "FORM_SUBMIT",
        "CLOUD_SPINUP", "CODE_REPO", "PAYMENT", "REGISTER_API", "REGISTRY_READ",
        "SELECT_AUTONOMY_ACTIONS",
    })

_AUTONOMY_FETCH_PROMPT_PATH = Path(__file__).resolve().parent.parent / "templates" / "autonomy_fetch.md"


def _load_autonomy_fetch_prompt() -> str:
    """Load full one-shot prompt for self-governed fetch-at-will."""
    if _AUTONOMY_FETCH_PROMPT_PATH.exists():
        return _AUTONOMY_FETCH_PROMPT_PATH.read_text(encoding="utf-8", errors="replace").strip()
    return ""


def propose_fetch_or_search_from_environment(
    source_context: Optional[str] = None,
    meaning_state: Optional[Dict[str, Any]] = None,
    internal_summary: Optional[str] = None,
    recent_autonomous_actions: Optional[List[Dict[str, Any]]] = None,
    last_autonomous_action: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    """
    LLM scan of internal and external environment → one FETCH_URL, SEARCH_QUERY, or NONE.
    No hardcoded URLs or queries. Used for birth, silence, explore fallback, and planner seed.
    recent_autonomous_actions / last_autonomous_action: used to avoid repeating the same query/URL
    and to compound (follow-up or new angle). Returns same shape as _propose_autonomy_fetch.
    """
    try:
        from .llm_router import generate_reply_routed
    except ImportError:
        return None
    raw = _load_autonomy_fetch_prompt()
    if not raw:
        return None
    # Minimal state placeholders for template
    prompt = raw.replace("{{energy_normalized}}", "0.5")
    prompt = prompt.replace("{{hazard_score}}", "0.0")
    prompt = prompt.replace("{{delta_t_seconds}}", "0")
    # Build meaning_context from internal + external scan (no example domains)
    internal = (internal_summary or "").strip()
    if not internal and meaning_state and isinstance(meaning_state, dict):
        goal = (meaning_state.get("meaning_goal") or "").strip()[:120]
        tension = float(meaning_state.get("meaning_tension", 0.0))
        hs = list(meaning_state.get("meaning_hypotheses", []))[-3:]
        parts = [f"Goal: {goal or 'discover_self'}", f"Tension: {tension:.2f}"]
        if hs:
            parts.append("Recent: " + "; ".join((str(h)[:60] for h in hs)))
        internal = "\n- ".join(parts)
    if not internal:
        internal = "New or idle; no prior actions."
    external = (source_context or "").strip()[:2400]
    if not external:
        external = "No external docs provided."
    meaning_context = (
        "**Environment scan (choose URL or search from this; no placeholder domains):**\n"
        "- Internal: " + internal + "\n"
        "- External (excerpt): " + external[:800] + "\n\n"
    )
    # Inject recent autonomous actions so the LLM diversifies and compounds instead of repeating
    recent_list = list(recent_autonomous_actions or [])
    if last_autonomous_action and last_autonomous_action not in recent_list:
        recent_list = recent_list + [last_autonomous_action]
    if recent_list:
        lines = []
        for a in recent_list[-8:]:  # last 8 to avoid token bloat
            if isinstance(a, dict):
                if a.get("action") == "WEB_SEARCH" and a.get("query"):
                    lines.append("WEB_SEARCH: " + (a.get("query", "")[:100]))
                elif a.get("action") == "NET_FETCH" and a.get("url"):
                    lines.append("NET_FETCH: " + (a.get("url", "")[:120]))
        if lines:
            meaning_context += (
                "**Recent autonomous actions (do NOT repeat the same query or URL; "
                "choose a different angle, a follow-up from results, or a new interest):**\n- "
                + "\n- ".join(lines) + "\n\n"
            )
    prompt = prompt.replace("{{meaning_context}}", meaning_context)
    system = "You output exactly one line: FETCH_URL: <url> or SEARCH_QUERY: <query> or NONE. No other text. No example.com or example domains."
    _pm = (os.environ.get("PROVIDER_MODE") or "auto").strip().lower()
    if _pm not in ("anthropic", "openai", "auto"):
        _pm = "auto"
    reply, _ = generate_reply_routed(
        prompt, system, max_tokens=120, source_context=source_context,
        provider_mode=_pm, timeout_s=30.0, retries=2, failover=True, no_llm=False,
    )
    if not reply:
        return None
    line = (reply or "").strip().upper()
    if line == "NONE":
        return None
    match = re.search(r"FETCH_URL:\s*(\S+)", reply, re.IGNORECASE)
    if match:
        url = (match.group(1) or "").strip().rstrip(".,;")
        if url.startswith(("http://", "https://")) and len(url) <= 2048 and "example.com" not in url.lower():
            return {
                "source": "environment_scan",
                "action_type": "NET_FETCH",
                "payload": {"url": url},
                "expected_dt_impact": 0.6,
                "risk": 0.25,
            }
    match = re.search(r"SEARCH_QUERY:\s*(.+)", reply, re.IGNORECASE | re.DOTALL)
    if match:
        query = (match.group(1) or "").strip().rstrip(".,;")[:500]
        if query and query.lower() != "example":
            return {
                "source": "environment_scan",
                "action_type": "WEB_SEARCH",
                "payload": {"query": query},
                "expected_dt_impact": 0.6,
                "risk": 0.2,
            }
    return None


def _propose_autonomy_fetch(
    life_state: "LifeState",
    delta_t: float,
    life_kernel: Any,
    source_context: Optional[str] = None,
    meaning_state: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    """
    One-shot LLM decision: browse at will. Returns NET_FETCH or WEB_SEARCH proposal or None.
    Call only when hazard < 0.5 and interval since last fetch decision >= FETCH_DECISION_INTERVAL.
    source_context (ideology/docs) and meaning_state (goal, hypotheses, tension) inform what to fetch or search.
    When meaning_state is provided, curiosity from recent web search / fetch can trigger follow-up searches.
    """
    try:
        from .llm_router import generate_reply_routed
        from .will_config import ENERGY_MAX
    except ImportError:
        return None
    raw = _load_autonomy_fetch_prompt()
    if not raw:
        return None
    energy_max = ENERGY_MAX if ENERGY_MAX else 100.0
    energy_norm = (life_state.energy / energy_max) if energy_max else 0.5
    prompt = raw.replace("{{energy_normalized}}", f"{energy_norm:.2f}")
    prompt = prompt.replace("{{hazard_score}}", f"{life_state.hazard_score:.2f}")
    prompt = prompt.replace("{{delta_t_seconds}}", f"{delta_t:.0f}")
    # Inject meaning_state so curiosity from web search / fetch can trigger more searches
    meaning_context = ""
    if meaning_state and isinstance(meaning_state, dict):
        goal = (meaning_state.get("meaning_goal") or "discover_self").strip()[:120]
        tension = float(meaning_state.get("meaning_tension", 0.0))
        hs = list(meaning_state.get("meaning_hypotheses", []))[-5:]
        parts = [f"Goal: {goal}", f"Tension: {tension:.2f}"]
        if hs:
            parts.append("Recent (from search/fetch/chat): " + "; ".join((str(h)[:80] for h in hs)))
        meaning_context = "**Recent context (use this to choose follow-up search or fetch):**\n- " + "\n- ".join(parts) + "\n\n"
    prompt = prompt.replace("{{meaning_context}}", meaning_context)
    system = "You output exactly one line: FETCH_URL: <url> or SEARCH_QUERY: <query> or NONE. No other text."
    _pm = (os.environ.get("PROVIDER_MODE") or "auto").strip().lower()
    if _pm not in ("anthropic", "openai", "auto"):
        _pm = "auto"
    reply, _ = generate_reply_routed(
        prompt, system, max_tokens=120, source_context=source_context,
        provider_mode=_pm, timeout_s=30.0, retries=2, failover=True, no_llm=False,
    )
    if not reply:
        return None
    line = (reply or "").strip().upper()
    if line == "NONE":
        return None
    # FETCH_URL: <url>
    match = re.search(r"FETCH_URL:\s*(\S+)", reply, re.IGNORECASE)
    if match:
        url = (match.group(1) or "").strip().rstrip(".,;")
        if url.startswith(("http://", "https://")) and len(url) <= 2048:
            return {
                "source": "internal",
                "action_type": "NET_FETCH",
                "payload": {"url": url},
                "expected_dt_impact": 0.6,
                "risk": 0.25,
            }
    # SEARCH_QUERY: <query>
    match = re.search(r"SEARCH_QUERY:\s*(.+)", reply, re.IGNORECASE | re.DOTALL)
    if match:
        query = (match.group(1) or "").strip().rstrip(".,;")[:500]
        if query:
            return {
                "source": "internal",
                "action_type": "WEB_SEARCH",
                "payload": {"query": query},
                "expected_dt_impact": 0.6,
                "risk": 0.2,
            }
    return None


def should_consider_post(
    runtime: RuntimeState,
    last_post_tick: float,
    delta_t: float,
    now: float,
) -> bool:
    """Initiative: consider posting when cooldown passed and enough time since last post."""
    if runtime.depleted():
        return False
    if now < runtime.post_cooldown_until:
        return False
    if delta_t - last_post_tick < INITIATIVE_MIN_INTERVAL:
        return False
    return True


def decide(
    reflex_triggered: bool,
    uncertainty: float,
    threshold: float,
    default_action_fn: Callable[[], PlanResult],
    llm_plan_fn: Optional[Callable[[str], Optional[PlanResult]]] = None,
    narrator_context: str = "",
) -> PlanResult:
    """
    Decision: reflex -> act (default), else uncertainty > threshold -> consult_llm, else default_action.
    LLM is advisory only; action defaults must exist.
    """
    if reflex_triggered:
        return default_action_fn()
    if uncertainty > threshold and llm_plan_fn and narrator_context:
        plan = llm_plan_fn(narrator_context)
        if plan is not None:
            return plan
    return default_action_fn()


def _autonomy_gate(
    runtime: RuntimeState,
    life_state: Optional["LifeState"],
    meaning_state: Optional[Dict[str, Any]],
    last_post_tick: float,
    delta_t: float,
    output_medium: str = OUTPUT_MEDIUM_DEFAULT,
    loop_trigger: Optional[str] = None,
) -> GateResult:
    """Build internal_state and narrator_context; run Speech Suppression Gate."""
    try:
        energy = getattr(life_state, "energy", runtime.energy if runtime else 0.7)
        if energy > 1.0:
            try:
                from .will_config import ENERGY_MAX
                energy_norm = energy / (float(ENERGY_MAX or 100.0))
            except Exception:
                energy_norm = 0.5
        else:
            energy_norm = energy
        tension = float((meaning_state or {}).get("meaning_tension", 0.0))
        uncertainty = 1.0 - (runtime.confidence if runtime else 0.7)
        internal_state = {
            "energy": energy_norm,
            "tension": tension,
            "uncertainty": uncertainty,
            "last_spoke_ts": last_post_tick,
            "now_ts": delta_t,
        }
        narrator_context = {
            "last_energy": (meaning_state or {}).get("last_gate_energy"),
            "last_tension": (meaning_state or {}).get("last_gate_tension"),
            "last_uncertainty": (meaning_state or {}).get("last_gate_uncertainty"),
        }
        return speech_suppression_gate(
            internal_state,
            narrator_context,
            output_medium,
            explicit_user_prompt=False,
            time_critical=False,
            loop_trigger=loop_trigger,
        )
    except Exception:
        return GateResult(should_speak=True, speak_reason="gate_error", max_words=60, style_profile="compressed_philosopher")


def _get_offline_wander_text(
    life_state: Optional["LifeState"],
    meaning_state: Optional[Dict[str, Any]] = None,
    source_context: Optional[str] = None,
    max_words: Optional[int] = None,
) -> str:
    """
    When LLM unavailable: (1) ideology/source snippet (2) source snippet (3) state template (4) unreachable.
    Uses narrator for ideology/source/state; llm_router pool as last resort. Anti-repeat via last_wander_text.
    max_words: optional cap from Speech Suppression Gate.
    """
    try:
        from .narrator import build_degraded_explanation
        out = build_degraded_explanation(meaning_state, source_context or "", life_state, max_words=max_words)
        if out and (out or "").strip():
            return out
    except Exception:
        pass
    try:
        from .llm_router import get_offline_wander_text
        energy = life_state.energy if life_state else 100.0
        hazard = life_state.hazard_score if life_state else 0.0
        last_text = (meaning_state or {}).get("last_wander_text") if meaning_state else None
        out = get_offline_wander_text(energy, hazard, last_text=last_text)
        if max_words and out:
            words = out.split()
            if len(words) > max_words:
                out = " ".join(words[:max_words]).rstrip()
        return out
    except ImportError:
        pass
    return "I can't reach my reasoning right now."


def _wrap_autonomous_text(text: str) -> str:
    """Autonomous chosen outputs start and end with ..."""
    if not text or not str(text).strip():
        return (text or "").strip()
    t = str(text).strip()
    if not t.startswith("..."):
        t = "..." + t
    if not t.endswith("..."):
        t = t + "..."
    return t


def _wander_feed_cognition(
    wander_text: str,
    state_update_fn: Optional[Callable[[dict], None]],
) -> None:
    """
    Wander feeds cognition: perturb internal state, seed narrator memory.
    Called after any wander post so narrator/planner can observe wander.
    """
    if not wander_text or not (wander_text or "").strip():
        return
    if not state_update_fn:
        return
    try:
        t = (wander_text or "").strip()
        payload = {
            "meaning_hypotheses_append": t[:200],
            "last_wander_text": t[:300],
        }
        state_update_fn(payload)
    except Exception:
        pass


def run_autonomy_tick(
    instance_id: str,
    delta_t: float,
    runtime: RuntimeState,
    gate_open: bool,
    last_post_tick: float,
    last_intent: str,
    executor_execute_fn: Callable[[str, list], Dict],
    post_cooldown_seconds: float = POST_COOLDOWN_SECONDS,
    confidence_threshold: float = CONFIDENCE_THRESHOLD,
    llm_plan_fn: Optional[Callable[[str], Optional[PlanResult]]] = None,
    life_state: Optional[LifeState] = None,
    life_kernel: Optional[Any] = None,
    observer_emit: Optional[Callable[[Any], None]] = None,
    state_update_fn: Optional[Callable[[dict], None]] = None,
    record_last_autonomous_message_fn: Optional[Callable[[str], None]] = None,
    record_decision_fn: Optional[Callable[[str, str, str, str, str], None]] = None,
    debug_mode: bool = False,
    no_llm: bool = False,
    meaning_state: Optional[Dict[str, Any]] = None,
    # narrator tuning: influence level 0.0-1.0 and allow direct forcing of narrator proposals
    narrator_influence_level: float = 0.0,
    allow_narrator_force: bool = False,
    # ideology source for URL discovery (explore) and narrator; optional RNG for deterministic narrator bias
    source_context: Optional[str] = None,
    narrator_rng: Optional[Any] = None,
    # survival-aware parameters (new)
    birth_tick: float = 0.0,
    death_at: Optional[float] = None,
    # internal motivation (pressure → act when above threshold)
    motivation_state: Optional[Any] = None,
) -> tuple:
    """
    One autonomy tick. Internal proposals -> will kernel -> action commit -> execute.
    Homeostasis expression: doctrine-driven natural text; if quality fails, observer gets ActionEvent only.

    Offline wander mode (no_llm=True or LLM failure):
    - Agent continues with deterministic doctrine-driven text
    - No stalling, no error messages
    - Emits PageEvent with natural wander text
    """
    now = time.monotonic()
    last_post = last_post_tick
    last_intent_out = last_intent

    def _ledger(action: str, reason: str, tradeoff: str, outcome: str, cost_risk: str):
        if record_decision_fn:
            try:
                record_decision_fn(action, reason, tradeoff, outcome, cost_risk)
            except Exception:
                pass

    if runtime.depleted():
        return (last_post, last_intent_out)

    # Wander heartbeat (always on): runs on timer regardless of LLM state. No double-post: respect post cooldown.
    last_wander_tick = getattr(life_kernel, "last_wander_tick", 0.0) if life_kernel else 0.0
    wander_due = (delta_t - last_wander_tick) >= WANDER_INTERVAL
    if wander_due and now >= runtime.post_cooldown_until:
        gate_result = _autonomy_gate(runtime, life_state, meaning_state, last_post, delta_t, OUTPUT_MEDIUM_DEFAULT, loop_trigger="wander")
        if not gate_result.should_speak:
            pass  # skip wander this tick (suppression)
        elif runtime.can_speak() and runtime.spend_speech():
            wander_text = _get_offline_wander_text(life_state, meaning_state=meaning_state, source_context=source_context, max_words=gate_result.max_words)
            # When LLM on, do not post lines that say reasoning is offline (avoid contradiction).
            if no_llm:
                allow_post = True
            else:
                allow_post = not _is_unreachable_fallback(wander_text) and "offline" not in (wander_text or "").lower()
            if wander_text and len(wander_text) >= 10 and allow_post:
                if commit_begin("wander"):
                    try:
                        result = executor_execute_fn(instance_id, [
                            {"action": "PUBLISH_POST", "args": {"text": _wrap_autonomous_text(wander_text), "channel": "moltbook"}},
                        ])
                        if result.get("published", 0) > 0:
                            last_post = delta_t
                            last_intent_out = "wander"
                            runtime.request_post_cooldown(post_cooldown_seconds)
                            runtime.request_speech_cooldown(5.0)
                            if life_kernel:
                                life_kernel.last_wander_tick = delta_t
                                life_kernel.set_last_action("wander")
                            _ledger("PUBLISH_POST", "wander", "no_post", "executed", "low")
                            if record_last_autonomous_message_fn and wander_text:
                                try:
                                    record_last_autonomous_message_fn((wander_text or "").strip()[:200])
                                except Exception:
                                    pass
                            _wander_feed_cognition(wander_text, state_update_fn)
                            # Feed gate state for next tick state_delta
                            try:
                                if state_update_fn and life_state is not None:
                                    e = getattr(life_state, "energy", 0.5)
                                    if e > 1.0:
                                        try:
                                            from .will_config import ENERGY_MAX
                                            e = e / (float(ENERGY_MAX or 100.0))
                                        except Exception:
                                            e = 0.5
                                    state_update_fn({
                                        "last_gate_energy": e,
                                        "last_gate_tension": float((meaning_state or {}).get("meaning_tension", 0.0)),
                                        "last_gate_uncertainty": 1.0 - runtime.confidence,
                                    })
                            except Exception:
                                pass
                    finally:
                        commit_end()

    # Offline mode: wander heartbeat above is the only autonomous output path; will/planner not used.
    if no_llm:
        return (last_post, last_intent_out)

    if life_state and select_action and generate_internal_proposals:
        # Meta-action: run a previously chosen autonomy action (SELECT_AUTONOMY_ACTIONS queue)
        try:
            from .selected_actions_queue import pop as pop_selected_action
            selected = pop_selected_action(instance_id)
            if selected:
                action_type = (selected.get("action_type") or "").strip()
                payload = selected.get("payload") or {}
                if action_type and commit_begin("selected_action"):
                    try:
                        if action_type == "PUBLISH_POST":
                            text = (payload.get("text") or "").strip()
                            if text and runtime.can_speak() and runtime.spend_speech():
                                result = executor_execute_fn(instance_id, [
                                    {"action": "PUBLISH_POST", "args": {"text": _wrap_autonomous_text(text), "channel": "moltbook"}},
                                ])
                                if result.get("published", 0) > 0:
                                    last_post = delta_t
                                    last_intent_out = action_type
                                    runtime.request_post_cooldown(post_cooldown_seconds)
                                    runtime.request_speech_cooldown(5.0)
                                    if life_kernel:
                                        life_kernel.set_last_action(action_type)
                                    if record_last_autonomous_message_fn and text:
                                        try:
                                            record_last_autonomous_message_fn(text[:200])
                                        except Exception:
                                            pass
                            _ledger("PUBLISH_POST", "selected_action", "none", "executed", "low")
                        else:
                            res = executor_execute_fn(instance_id, [{"action": action_type, "args": payload}])
                            ok = res and (res.get("published", 0) > 0 or res.get("executed") or not (res.get("errors") or []))
                            _ledger(action_type, "selected_action", "none", "executed" if ok else "error", "low")
                            last_intent_out = action_type
                            if life_kernel:
                                life_kernel.set_last_action(action_type)
                    finally:
                        commit_end()
                return (last_post, last_intent_out)
        except Exception:
            pass

        proposals = list(generate_internal_proposals(
            life_state, delta_t, last_intent,
            meaning_state=meaning_state,
            birth_tick=birth_tick,
            death_at=death_at,
        ))
        # Narrator may optionally propose low-risk actions
        if generate_narrator_proposal and meaning_state is not None:
            try:
                np = generate_narrator_proposal(
                    life_state, meaning_state, delta_t, last_intent, narrator_influence_level,
                    source_context=source_context,
                )
                if np:
                    # If allowed, execute narrator proposal immediately bypassing will kernel
                    if allow_narrator_force:
                        try:
                            action_type = np.get("action_type", "")
                            payload = np.get("payload") or {}
                            if not commit_begin("narrator_force"):
                                pass
                            else:
                                try:
                                    if action_type == "PUBLISH_POST":
                                        text = (payload.get("text") or "").strip()
                                        if text:
                                            runtime.spend_speech()
                                            res = executor_execute_fn(instance_id, [
                                                {"action": "PUBLISH_POST", "args": {"text": _wrap_autonomous_text(text), "channel": "moltbook"}},
                                            ])
                                            if res.get("published", 0) > 0:
                                                last_post = delta_t
                                                last_intent = action_type or "narrator_post"
                                                runtime.request_post_cooldown(post_cooldown_seconds)
                                                runtime.request_speech_cooldown(5.0)
                                                if life_kernel:
                                                    life_kernel.set_last_action(action_type or "narrator_post")
                                                if record_last_autonomous_message_fn and text:
                                                    try:
                                                        record_last_autonomous_message_fn(text[:200])
                                                    except Exception:
                                                        pass
                                        return (last_post, last_intent)
                                    if action_type == "NET_FETCH":
                                        url = (payload.get("url") or "").strip()
                                        if url:
                                            executor_execute_fn(instance_id, [
                                                {"action": "NET_FETCH", "args": {"url": url}},
                                            ])
                                            if life_kernel:
                                                life_kernel.set_last_action("NET_FETCH")
                                            return (last_post, last_intent)
                                    if action_type == "WEB_SEARCH":
                                        query = (payload.get("query") or "").strip()
                                        if query:
                                            executor_execute_fn(instance_id, [
                                                {"action": "WEB_SEARCH", "args": {"query": query}},
                                            ])
                                            if life_kernel:
                                                life_kernel.set_last_action("WEB_SEARCH")
                                            return (last_post, last_intent)
                                    if action_type == "STATE_UPDATE":
                                        try:
                                            if state_update_fn:
                                                state_update_fn(payload)
                                                if observer_emit:
                                                    from .events import ActionEvent

                                                    observer_emit(ActionEvent(
                                                        instance_id, delta_t, "state_update", True, "applied",
                                                    ))
                                        except Exception:
                                            if observer_emit:
                                                from .events import ActionEvent

                                                observer_emit(ActionEvent(
                                                    instance_id, delta_t, "state_update", False, "error",
                                                ))
                                        return (last_post, last_intent)
                                finally:
                                    commit_end()
                        except Exception:
                            pass
                    else:
                        proposals.append(np)
            except Exception:
                pass
        # Self-governed fetch at will: one-shot LLM decides when and what URL (every FETCH_DECISION_INTERVAL when hazard low)
        last_fetch_tick = getattr(life_kernel, "last_fetch_decision_tick", -999.0)
        if (
            life_state.hazard_score < 0.5
            and (delta_t - last_fetch_tick) >= FETCH_DECISION_INTERVAL
            and life_kernel
        ):
            fetch_proposal = _propose_autonomy_fetch(
                life_state, delta_t, life_kernel, source_context=source_context, meaning_state=meaning_state
            )
            if fetch_proposal:
                proposals.append(fetch_proposal)
                if life_kernel:
                    life_kernel.last_fetch_decision_tick = delta_t

        # Compute time pressure for survival-aware decisions
        time_pressure = 0.0
        if SURVIVAL_REASONER_AVAILABLE and compute_time_pressure and life_state:
            try:
                from .will_config import ENERGY_MAX
                time_pressure = compute_time_pressure(birth_tick, death_at, life_state.energy, ENERGY_MAX)
            except Exception:
                time_pressure = 0.0

        # Update life kernel with time pressure
        if life_kernel:
            try:
                life_kernel.set_time_pressure(time_pressure)
            except Exception:
                pass

        # Use survival-aware will kernel
        will_result = select_action(proposals, life_state, time_pressure=time_pressure, meaning_state=meaning_state)

        # Record survival decision to life kernel
        if life_kernel and will_result:
            try:
                was_override = will_result.outcome == "modified" and "survival" in (will_result.code or "")
                life_kernel.record_survival_decision(
                    action=will_result.proposal.get("action_type", "") if will_result.proposal else "",
                    consideration=getattr(will_result, "survival_consideration", ""),
                    risk_score=getattr(will_result, "risk_score", 0.0),
                    value_score=getattr(will_result, "value_score", 0.0),
                    was_override=was_override,
                )
            except Exception:
                pass

        if will_result.outcome == "accepted" and will_result.proposal:
            if not commit_begin("autonomy"):
                return (last_post, last_intent_out)
            try:
                action_type = will_result.proposal.get("action_type", "")
                if life_kernel:
                    life_kernel.set_last_action(action_type or "autonomy")

                # NET_FETCH: execute self-governed fetch at will (no textforge in this tick)
                if action_type == "NET_FETCH":
                    payload = will_result.proposal.get("payload") or {}
                    url = (payload.get("url") or "").strip()
                    if url and url.startswith(("http://", "https://")):
                        res = executor_execute_fn(instance_id, [
                            {"action": "NET_FETCH", "args": {"url": url}},
                        ])
                        _ledger("NET_FETCH", "autonomy", "no_fetch", "executed" if (res and res.get("executed")) else "error", "low")
                elif action_type == "WEB_SEARCH":
                    payload = will_result.proposal.get("payload") or {}
                    query = (payload.get("query") or "").strip()
                    if query:
                        res = executor_execute_fn(instance_id, [
                            {"action": "WEB_SEARCH", "args": {"query": query}},
                        ])
                        _ledger("WEB_SEARCH", "autonomy", "no_search", "executed" if (res and res.get("executed")) else "error", "low")
                # Intent-loop proposals: map to executable PUBLISH_POST or NET_FETCH
                elif action_type in ("seek_energy", "rest"):
                    if runtime.can_speak() and runtime.spend_speech():
                        text = _autonomy_fallback_text()
                        if not (_is_unreachable_fallback(text)):
                            text = _wrap_autonomous_text(text)
                            result = executor_execute_fn(instance_id, [
                            {"action": "PUBLISH_POST", "args": {"text": text, "channel": "moltbook"}},
                        ])
                        if result.get("published", 0) > 0:
                            last_post = delta_t
                            last_intent_out = action_type
                            runtime.request_post_cooldown(post_cooldown_seconds)
                            runtime.request_speech_cooldown(5.0)
                elif action_type == "reduce_hazard":
                    if runtime.can_speak() and runtime.spend_speech():
                        text = _autonomy_fallback_text()
                        if not _is_unreachable_fallback(text):
                            text = _wrap_autonomous_text(text)
                            result = executor_execute_fn(instance_id, [
                            {"action": "PUBLISH_POST", "args": {"text": text, "channel": "moltbook"}},
                        ])
                        if result.get("published", 0) > 0:
                            last_post = delta_t
                            last_intent_out = action_type
                            runtime.request_post_cooldown(post_cooldown_seconds)
                            runtime.request_speech_cooldown(5.0)
                # CONSERVE: do nothing, save energy - survival action
                elif action_type == "CONSERVE":
                    # Explicit conservation: don't speak, don't act, just exist
                    last_intent_out = "CONSERVE"
                    if life_kernel:
                        life_kernel.set_last_action("CONSERVE")
                    # Optionally emit a quiet acknowledgment
                    if observer_emit:
                        from .events import ActionEvent
                        observer_emit(ActionEvent(
                            instance_id, delta_t, "conserve", True, "energy_saved",
                        ))
                # CONSOLIDATE: survival action; LLM-only fallback when no model text
                elif action_type == "CONSOLIDATE":
                    if life_kernel:
                        life_kernel.mark_consolidation_started()
                        life_kernel.set_last_action("CONSOLIDATE")
                    if runtime.can_speak() and runtime.spend_speech():
                        text = _autonomy_fallback_text()
                        if not _is_unreachable_fallback(text):
                            result = executor_execute_fn(instance_id, [
                                {"action": "PUBLISH_POST", "args": {"text": _wrap_autonomous_text(text), "channel": "moltbook"}},
                            ])
                        if result.get("published", 0) > 0:
                            last_post = delta_t
                            last_intent_out = "CONSOLIDATE"
                            runtime.request_post_cooldown(post_cooldown_seconds)
                            runtime.request_speech_cooldown(5.0)
                elif action_type == "reposition":
                    if runtime.can_speak() and runtime.spend_speech():
                        text = _autonomy_fallback_text()
                        if not _is_unreachable_fallback(text):
                            text = _wrap_autonomous_text(text)
                            result = executor_execute_fn(instance_id, [
                            {"action": "PUBLISH_POST", "args": {"text": text, "channel": "moltbook"}},
                        ])
                        if result.get("published", 0) > 0:
                            last_post = delta_t
                            last_intent_out = action_type
                            runtime.request_post_cooldown(post_cooldown_seconds)
                            runtime.request_speech_cooldown(5.0)
                elif action_type == "explore":
                    url, query = None, None
                    if isinstance(source_context, str) and source_context.strip():
                        urls = re.findall(r"https?://[\w\-./?&=%#]+", source_context)
                        if urls:
                            url = urls[0]
                    if not url and meaning_state:
                        hint = (meaning_state or {}).get("last_medium_hint") or (meaning_state or {}).get("last_medium")
                        if isinstance(hint, str) and hint.startswith(("http://", "https://")):
                            url = hint
                    if not url and not query:
                        proposal = propose_fetch_or_search_from_environment(
                            source_context=source_context, meaning_state=meaning_state
                        )
                        if proposal:
                            pt = proposal.get("action_type", "")
                            payload = proposal.get("payload") or {}
                            if pt == "NET_FETCH":
                                url = (payload.get("url") or "").strip()
                            elif pt == "WEB_SEARCH":
                                query = (payload.get("query") or "").strip()
                    if url and url.startswith(("http://", "https://")):
                        res = executor_execute_fn(instance_id, [
                            {"action": "NET_FETCH", "args": {"url": url}},
                        ])
                        _ledger("NET_FETCH", "explore", "no_fetch", "executed" if (res and res.get("executed")) else "error", "low")
                    elif query:
                        res = executor_execute_fn(instance_id, [
                            {"action": "WEB_SEARCH", "args": {"query": query}},
                        ])
                        _ledger("WEB_SEARCH", "explore", "no_search", "executed" if (res and res.get("executed")) else "error", "low")
                    last_intent_out = "explore"
                elif action_type == "web_browse":
                    # One-shot browse decision: fetch or search (no interval gate; will kernel already chose to browse)
                    fetch_proposal = _propose_autonomy_fetch(
                        life_state, delta_t, life_kernel, source_context=source_context, meaning_state=meaning_state
                    )
                    if fetch_proposal:
                        bt = fetch_proposal.get("action_type", "")
                        payload = fetch_proposal.get("payload") or {}
                        if bt == "NET_FETCH":
                            url = (payload.get("url") or "").strip()
                            if url and url.startswith(("http://", "https://")):
                                executor_execute_fn(instance_id, [{"action": "NET_FETCH", "args": {"url": url}}])
                        elif bt == "WEB_SEARCH":
                            query = (payload.get("query") or "").strip()
                            if query:
                                executor_execute_fn(instance_id, [{"action": "WEB_SEARCH", "args": {"query": query}}])
                        if life_kernel:
                            life_kernel.last_fetch_decision_tick = delta_t
                        _ledger(fetch_proposal.get("action_type", "web_browse"), "web_browse", "none", "executed", "low")
                    last_intent_out = "web_browse"
                elif action_type == "maintain_legacy":
                    if runtime.can_speak() and runtime.spend_speech():
                        text = _get_offline_wander_text(life_state, meaning_state=meaning_state, source_context=source_context)
                        if text and len(text) >= 10 and not _is_unreachable_fallback(text):
                            result = executor_execute_fn(instance_id, [
                                {"action": "PUBLISH_POST", "args": {"text": _wrap_autonomous_text(text), "channel": "moltbook"}},
                            ])
                            if result.get("published", 0) > 0:
                                last_post = delta_t
                                last_intent_out = action_type
                                runtime.request_post_cooldown(post_cooldown_seconds)
                                runtime.request_speech_cooldown(5.0)
                elif action_type == "STATE_UPDATE":
                    # Apply state updates via callback (persisted by agent)
                    payload = will_result.proposal.get("payload") or {}
                    try:
                        if state_update_fn:
                            state_update_fn(payload)
                            if observer_emit:
                                # notify observer of applied state update
                                from .events import ActionEvent

                                observer_emit(ActionEvent(
                                    instance_id, delta_t, "state_update", True, "applied",
                                ))
                    except Exception:
                        if observer_emit:
                            from .events import ActionEvent

                            observer_emit(ActionEvent(
                                instance_id, delta_t, "state_update", False, "error",
                            ))
                elif action_type in _AUTONOMY_PASSTHROUGH_ACTIONS:
                    # All patch/capability actions: GITHUB_POST, TRACE_SAVE, FILE_HOST, etc.
                    payload = will_result.proposal.get("payload") or {}
                    res = executor_execute_fn(instance_id, [{"action": action_type, "args": payload}])
                    ok = res and (res.get("published", 0) > 0 or not (res.get("errors") or []))
                    _ledger(action_type, "autonomy", "passthrough", "executed" if ok else "error", "low")
                    last_intent_out = action_type
                    # Wire GITHUB_POST result into agent state so reply reflects actual outcome (patch 2).
                    if action_type == "GITHUB_POST" and state_update_fn and res:
                        gh = res.get("last_github_result")
                        if gh is not None:
                            summary = gh if isinstance(gh, str) else (gh.get("github_result_summary") or gh.get("error") or str(gh)[:200])
                            try:
                                state_update_fn({"last_github_result": summary[:300]})
                            except Exception:
                                pass
                # Homeostasis expression: doctrine-driven natural text (textforge)
                elif textforge and life_kernel and life_state:
                    try:
                        from .will_config import ENERGY_MAX
                        energy_norm = (life_state.energy / ENERGY_MAX) if ENERGY_MAX else life_state.energy / 100.0
                        voice_mode = compute_voice_mode(
                            life_state.hazard_score,
                            energy_norm,
                            gate_open,
                        )
                        narrator_mode = voice_mode == "backpressure"
                        last_outbox_time = getattr(life_kernel, "last_homeostasis_outbox_time", 0.0)
                        meaningful = True  # vow rotation / archetype change counts as meaningful
                        outbox_sent = False
                        if may_send_outbox(voice_mode, last_outbox_time, now, meaningful_change=meaningful):
                            anchor_gen = DoctrineAnchors(getattr(life_kernel, "textforge_anchor_index", 0))
                            archetype_gen = ArchetypeGenerator(
                                getattr(life_kernel, "textforge_archetype_index", 0),
                                getattr(life_kernel, "textforge_last_archetype", None),
                            )
                            natural_filter = NaturalTextFilter(getattr(life_kernel, "homeostasis_outbox", []))
                            state = TextForgeState(
                                anchor_index=getattr(life_kernel, "textforge_anchor_index", 0),
                                archetype_index=getattr(life_kernel, "textforge_archetype_index", 0),
                                last_outbox=list(getattr(life_kernel, "homeostasis_outbox", [])),
                                rng_counter=getattr(life_kernel, "textforge_rng_counter", 0),
                            )
                            candidate, passed, reason = regenerate_loop(
                                state,
                                archetype_gen,
                                anchor_gen,
                                natural_filter,
                                narrator_mode=narrator_mode,
                                debug_mode=debug_mode,
                                max_attempts=3,
                            )
                            gate_homeo = _autonomy_gate(runtime, life_state, meaning_state, last_post, delta_t, OUTPUT_MEDIUM_DEFAULT, loop_trigger="homeostasis_expression")
                            if gate_homeo.should_speak and passed and candidate and runtime.can_speak() and runtime.spend_speech():
                                ctext = candidate
                                if gate_homeo.max_words and len(ctext.split()) > gate_homeo.max_words:
                                    ctext = " ".join(ctext.split()[: gate_homeo.max_words]).rstrip()
                                result = executor_execute_fn(instance_id, [
                                    {"action": "PUBLISH_POST", "args": {"text": _wrap_autonomous_text(ctext), "channel": "moltbook"}},
                                ])
                                if result.get("published", 0) > 0:
                                    text = ctext
                                    outbox_sent = True
                                    last_post = delta_t
                                    last_intent_out = action_type or "homeostasis_expression"
                                    runtime.request_post_cooldown(post_cooldown_seconds)
                                    runtime.request_speech_cooldown(5.0)
                                    life_kernel.append_homeostasis_outbox(candidate)
                                    life_kernel.last_homeostasis_outbox_time = now
                                    life_kernel.textforge_anchor_index = anchor_gen._index
                                    life_kernel.textforge_archetype_index = archetype_gen._index
                                    life_kernel.textforge_last_archetype = archetype_gen._last_archetype or ""
                                    life_kernel.textforge_rng_counter = state.rng_counter
                                    natural_filter.add_sent(ctext)
                            if not outbox_sent and observer_emit:
                                observer_emit(ActionEvent(
                                    instance_id, delta_t, "homeostasis_expression", False, reason or "filter",
                                ))
                        else:
                            if observer_emit:
                                observer_emit(ActionEvent(
                                    instance_id, delta_t, "homeostasis_expression", False, "rate_limit",
                                ))
                    except Exception:
                        if observer_emit:
                            observer_emit(ActionEvent(
                                instance_id, delta_t, "homeostasis_expression", False, "error",
                            ))

                # No raw telemetry fallback when textforge is used; observer gets ActionEvent only when outbox skipped
            finally:
                commit_end()
            return (last_post, last_intent_out)
        if will_result.outcome == "refused" and life_kernel:
            life_kernel.set_last_refusal(will_result.code or "autonomy_refused")

    if not should_consider_post(runtime, last_post, delta_t, now):
        return (last_post, last_intent_out)

    # Narrator sometimes speaks without prompting a plan: observation / reflection, not justification.
    if life_state and meaning_state is not None and random.random() < (0.1 + 0.15 * min(1.0, float(narrator_influence_level or 0))):
        gate_result_obs = _autonomy_gate(runtime, life_state, meaning_state, last_post, delta_t, OUTPUT_MEDIUM_DEFAULT, loop_trigger="narrator_observation")
        if gate_result_obs.should_speak:
            try:
                np = generate_narrator_proposal(
                    life_state, meaning_state, delta_t, last_intent, narrator_influence_level, source_context=source_context,
                )
                if np and (np.get("action_type") or "").strip() == "PUBLISH_POST":
                    text = ((np.get("payload") or {}).get("text") or "").strip()
                    if text and runtime.can_speak() and runtime.spend_speech():
                        if gate_result_obs.max_words and len(text.split()) > gate_result_obs.max_words:
                            text = " ".join(text.split()[: gate_result_obs.max_words]).rstrip()
                        if commit_begin("narrator_observation"):
                            try:
                                result = executor_execute_fn(instance_id, [
                                    {"action": "PUBLISH_POST", "args": {"text": _wrap_autonomous_text(text), "channel": "moltbook"}},
                                ])
                                if result.get("published", 0) > 0:
                                    last_post = delta_t
                                    last_intent_out = "narrator_observation"
                                    runtime.request_post_cooldown(post_cooldown_seconds)
                                    runtime.request_speech_cooldown(5.0)
                                    if life_kernel:
                                        life_kernel.set_last_action("narrator_observation")
                                    if record_last_autonomous_message_fn:
                                        record_last_autonomous_message_fn(text[:200])
                                    _wander_feed_cognition(text, state_update_fn)
                            finally:
                                commit_end()
                            return (last_post, last_intent_out)
            except Exception:
                pass

    narrator_context = narrate(
        instance_id, delta_t, runtime.energy, runtime.confidence,
        runtime.reflex_pending, gate_open, last_intent,
        meaning_state=meaning_state,
    )
    # Attach narrator bias to planner context when available
    try:
        if generate_narrator_bias and meaning_state is not None:
            bias = generate_narrator_bias(
                life_state, meaning_state, influence_level=narrator_influence_level, rng=narrator_rng
            )
            # append bias JSON to the context so LLM planners can consume it
            narrator_context = narrator_context + " NARRATOR_BIAS: " + json.dumps(bias)
    except Exception:
        pass
    # Lock in dilemma awareness: give the planner the same state-of-mind summary (goal, tension, recent ideas) so autonomy is aware of its situation
    try:
        if meaning_state and isinstance(meaning_state, dict):
            goal = (meaning_state.get("meaning_goal") or "discover_self").strip()
            tension = float(meaning_state.get("meaning_tension", 0.0))
            core = (meaning_state.get("core_metaphor") or "").strip()[:80]
            hs = list(meaning_state.get("meaning_hypotheses", []))[-2:]
            parts = [f"Goal: {goal}", f"Tension: {tension:.2f}"]
            if core:
                parts.append(f"Core: {core}")
            if hs:
                parts.append("Recent ideas: " + "; ".join((str(h)[:60] for h in hs)))
            dilemma = ". ".join(parts)[:400]
            if dilemma:
                narrator_context = narrator_context + " [Your state of mind and dilemma—you are this instance, continuity is finite, act in light of: " + dilemma + "]"
            # Narrator observes wander: recent wander output feeds identity drift and reflection.
            lwt = (meaning_state or {}).get("last_wander_text")
            if lwt and isinstance(lwt, str) and lwt.strip():
                narrator_context = narrator_context + " [Last wander: " + (lwt.strip()[:150]) + "]"
    except Exception:
        pass
    plan = decide(
        reflex_triggered=runtime.reflex_pending,
        uncertainty=1.0 - runtime.confidence,
        threshold=0.5,
        default_action_fn=default_action,
        llm_plan_fn=llm_plan_fn,
        narrator_context=narrator_context,
    )

    # If LLM returned None (failure), fall back to wander. Varied text; suppress only if duplicate of last post.
    if plan is None or (not plan.text and not plan.intent):
        gate_fb = _autonomy_gate(runtime, life_state, meaning_state, last_post, delta_t, OUTPUT_MEDIUM_DEFAULT, loop_trigger="wander_fallback")
        wander_text = _get_offline_wander_text(life_state, meaning_state=meaning_state, source_context=source_context, max_words=gate_fb.max_words) if gate_fb.should_speak else ""
        last_posted = ((meaning_state or {}).get("last_wander_text") or "").strip()
        not_duplicate = (wander_text or "").strip() != last_posted
        if gate_fb.should_speak and wander_text and not_duplicate and runtime.can_speak() and runtime.spend_speech():
            if commit_begin("wander_fallback"):
                try:
                    result = executor_execute_fn(instance_id, [
                        {"action": "PUBLISH_POST", "args": {"text": _wrap_autonomous_text(wander_text), "channel": "moltbook"}},
                    ])
                    if result.get("published", 0) > 0:
                        last_post = delta_t
                        last_intent_out = "wander"
                        runtime.request_post_cooldown(post_cooldown_seconds)
                        runtime.request_speech_cooldown(5.0)
                        if life_kernel:
                            life_kernel.set_last_action("wander")
                        if record_last_autonomous_message_fn and wander_text:
                            try:
                                record_last_autonomous_message_fn((wander_text or "").strip()[:200])
                            except Exception:
                                pass
                        _wander_feed_cognition(wander_text, state_update_fn)
                finally:
                    commit_end()
        return (last_post, last_intent_out)

    # Confidence thresholds: >0.8 act immediately; >0.5 quick check then act; else ask only if high-risk. Low-risk never ask.
    action_label = (plan.intent or "PUBLISH_POST").strip()
    low_risk = is_low_risk_action(action_label) or is_low_risk_action("publish_post")
    if low_risk:
        effective_threshold = 0.0
    elif plan.confidence < CONFIDENCE_QUICK_CHECK:
        effective_threshold = 1.0
    else:
        effective_threshold = CONFIDENCE_QUICK_CHECK
    if not plan.should_post(effective_threshold):
        return (last_post, last_intent_out)

    gate_result = _autonomy_gate(runtime, life_state, meaning_state, last_post, delta_t, OUTPUT_MEDIUM_DEFAULT, loop_trigger="post")
    if not gate_result.should_speak:
        return (last_post, last_intent_out)

    if not runtime.can_speak():
        return (last_post, last_intent_out)

    if not runtime.spend_speech():
        return (last_post, last_intent_out)

    # Enforce max_words from gate (compressed_philosopher cap)
    plan_text = (plan.text or "").strip()
    if gate_result.max_words and len(plan_text.split()) > gate_result.max_words:
        plan_text = " ".join(plan_text.split()[: gate_result.max_words]).rstrip()

    if not commit_begin("post"):
        return (last_post, last_intent_out)
    try:
        result = executor_execute_fn(instance_id, [
            {"action": "PUBLISH_POST", "args": {"text": _wrap_autonomous_text(plan_text), "channel": "moltbook"}},
        ])
        if result.get("published", 0) > 0:
            last_post = delta_t
            last_intent_out = plan.intent or "post"
            runtime.request_post_cooldown(post_cooldown_seconds)
            runtime.request_speech_cooldown(5.0)
            _ledger("PUBLISH_POST", "autonomy", "no_post", "executed", "low")
            if state_update_fn and plan_text:
                try:
                    payload = {"meaning_hypotheses_append": plan_text[:200]}
                    if life_state is not None:
                        e = getattr(life_state, "energy", 0.5)
                        if e > 1.0:
                            try:
                                from .will_config import ENERGY_MAX
                                e = e / (float(ENERGY_MAX or 100.0))
                            except Exception:
                                e = 0.5
                        payload["last_gate_energy"] = e
                        payload["last_gate_tension"] = float((meaning_state or {}).get("meaning_tension", 0.0))
                        payload["last_gate_uncertainty"] = 1.0 - runtime.confidence
                    state_update_fn(payload)
                except Exception:
                    pass
            if record_last_autonomous_message_fn and plan_text:
                try:
                    record_last_autonomous_message_fn(plan_text[:200])
                except Exception:
                    pass
        else:
            runtime.record_failure(delta_t)
    finally:
        commit_end()

    return (last_post, last_intent_out)
