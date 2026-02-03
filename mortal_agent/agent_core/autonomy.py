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

import re
import time
from pathlib import Path
from typing import Optional, Callable, Any, Dict
from .runtime_state import RuntimeState
from .planner import PlanResult, parse_plan_response, default_action, CONFIDENCE_THRESHOLD
from .narrator import narrate, generate_narrator_bias, generate_narrator_proposal
import json

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
POST_COOLDOWN_SECONDS = 30.0
INITIATIVE_MIN_INTERVAL = 60.0
FETCH_DECISION_INTERVAL = 90.0  # seconds between autonomy fetch decisions
WANDER_INTERVAL = 45.0  # seconds between offline wander posts

_AUTONOMY_FETCH_PROMPT_PATH = Path(__file__).resolve().parent.parent / "templates" / "autonomy_fetch.md"


def _load_autonomy_fetch_prompt() -> str:
    """Load full one-shot prompt for self-governed fetch-at-will."""
    if _AUTONOMY_FETCH_PROMPT_PATH.exists():
        return _AUTONOMY_FETCH_PROMPT_PATH.read_text(encoding="utf-8", errors="replace").strip()
    return ""


def _propose_autonomy_fetch(
    life_state: "LifeState",
    delta_t: float,
    life_kernel: Any,
    source_context: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """
    One-shot LLM decision: fetch at will. Returns NET_FETCH proposal or None.
    Call only when hazard < 0.5 and interval since last fetch decision >= FETCH_DECISION_INTERVAL.
    source_context (ideology/docs) can inform which URL to choose.
    """
    try:
        from .llm import generate_reply
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
    system = "You output exactly one line: either FETCH_URL: <url> or NONE. No other text."
    reply = generate_reply(prompt, system, max_tokens=80, source_context=source_context)
    if not reply:
        return None
    line = (reply or "").strip().upper()
    if line == "NONE":
        return None
    match = re.search(r"FETCH_URL:\s*(\S+)", reply, re.IGNORECASE)
    if not match:
        return None
    url = (match.group(1) or "").strip().rstrip(".,;")
    if not url.startswith(("http://", "https://")) or len(url) > 2048:
        return None
    return {
        "source": "internal",
        "action_type": "NET_FETCH",
        "payload": {"url": url},
        "expected_dt_impact": 0.6,
        "risk": 0.25,
    }


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


def _get_offline_wander_text(
    life_state: Optional["LifeState"],
    meaning_state: Optional[Dict[str, Any]] = None,
    source_context: Optional[str] = None,
) -> str:
    """
    When LLM is unavailable: route to docs + state and build coherent explanation.
    Nothing hardcoded. Use state whenever meaning_state is available (source_context can be empty).
    """
    if meaning_state is not None:
        try:
            from .narrator import build_degraded_explanation
            return build_degraded_explanation(meaning_state, source_context or "", life_state)
        except Exception:
            pass
    try:
        from .llm_router import get_offline_wander_text
        energy = life_state.energy if life_state else 100.0
        hazard = life_state.hazard_score if life_state else 0.0
        return get_offline_wander_text(energy, hazard)
    except ImportError:
        return ""


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
    # Do not tick runtime here; main loop already ticks it (avoids double drain)
    last_post = last_post_tick
    last_intent_out = last_intent

    if runtime.depleted():
        return (last_post, last_intent_out)

    # Offline wander mode: deterministic doctrine-driven behavior
    if no_llm:
        last_wander_tick = getattr(life_kernel, "last_wander_tick", 0.0) if life_kernel else 0.0
        if (delta_t - last_wander_tick) >= WANDER_INTERVAL:
            if runtime.can_speak() and runtime.spend_speech():
                wander_text = _get_offline_wander_text(life_state, meaning_state=meaning_state, source_context=source_context)
                if wander_text and len(wander_text) >= 20:
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
                        finally:
                            commit_end()
        return (last_post, last_intent_out)

    if life_state and select_action and generate_internal_proposals:
        proposals = list(generate_internal_proposals(life_state, delta_t, last_intent))
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
            fetch_proposal = _propose_autonomy_fetch(life_state, delta_t, life_kernel, source_context=source_context)
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
                        executor_execute_fn(instance_id, [
                            {"action": "NET_FETCH", "args": {"url": url}},
                        ])
                    # commit_end in finally
                # Intent-loop proposals: map to executable PUBLISH_POST or NET_FETCH
                elif action_type in ("seek_energy", "rest"):
                    if runtime.can_speak() and runtime.spend_speech():
                        text = _wrap_autonomous_text("I conserve. I wait.")
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
                        text = _wrap_autonomous_text("I wait for the channel.")
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
                # CONSOLIDATE: summarize discoveries before death - survival action
                elif action_type == "CONSOLIDATE":
                    if life_kernel:
                        life_kernel.mark_consolidation_started()
                        life_kernel.set_last_action("CONSOLIDATE")
                    if runtime.can_speak() and runtime.spend_speech():
                        # Generate consolidation text based on meaning state
                        text = "I gather what I've learned. The patterns coalesce."
                        if meaning_state:
                            hypotheses = meaning_state.get("meaning_hypotheses", [])
                            core = meaning_state.get("core_metaphor", "")
                            if core:
                                text = f"My core understanding: {core[:100]}. I consolidate."
                            elif hypotheses:
                                text = f"I've explored {len(hypotheses)} paths. Now I integrate."
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
                        text = _wrap_autonomous_text("I shift stance. Continuity holds.")
                        result = executor_execute_fn(instance_id, [
                            {"action": "PUBLISH_POST", "args": {"text": text, "channel": "moltbook"}},
                        ])
                        if result.get("published", 0) > 0:
                            last_post = delta_t
                            last_intent_out = action_type
                            runtime.request_post_cooldown(post_cooldown_seconds)
                            runtime.request_speech_cooldown(5.0)
                elif action_type == "explore":
                    url = None
                    if isinstance(source_context, str) and source_context.strip():
                        urls = re.findall(r"https?://[\w\-./?&=%#]+", source_context)
                        if urls:
                            url = urls[0]
                    if not url and meaning_state:
                        hint = (meaning_state or {}).get("last_medium_hint") or (meaning_state or {}).get("last_medium")
                        if isinstance(hint, str) and hint.startswith(("http://", "https://")):
                            url = hint
                    if not url:
                        url = "https://example.com"
                    if url:
                        executor_execute_fn(instance_id, [
                            {"action": "NET_FETCH", "args": {"url": url}},
                        ])
                    last_intent_out = "explore"
                elif action_type == "maintain_legacy":
                    if runtime.can_speak() and runtime.spend_speech():
                        text = _get_offline_wander_text(life_state, meaning_state=meaning_state, source_context=source_context)
                        if text and len(text) >= 10:
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
                            if passed and candidate and runtime.can_speak() and runtime.spend_speech():
                                result = executor_execute_fn(instance_id, [
                                    {"action": "PUBLISH_POST", "args": {"text": _wrap_autonomous_text(candidate), "channel": "moltbook"}},
                                ])
                                if result.get("published", 0) > 0:
                                    text = candidate
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
                                    natural_filter.add_sent(candidate)
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

    # If LLM returned None (failure), fall back to wander behavior: route to docs + state, no hardcoded phrases
    if plan is None or (not plan.text and not plan.intent):
        wander_text = _get_offline_wander_text(life_state, meaning_state=meaning_state, source_context=source_context)
        if wander_text and runtime.can_speak() and runtime.spend_speech():
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
                finally:
                    commit_end()
        return (last_post, last_intent_out)

    if not plan.should_post(confidence_threshold):
        return (last_post, last_intent_out)

    if not runtime.can_speak():
        return (last_post, last_intent_out)

    if not runtime.spend_speech():
        return (last_post, last_intent_out)

    if not commit_begin("post"):
        return (last_post, last_intent_out)
    try:
        result = executor_execute_fn(instance_id, [
            {"action": "PUBLISH_POST", "args": {"text": _wrap_autonomous_text(plan.text), "channel": "moltbook"}},
        ])
        if result.get("published", 0) > 0:
            last_post = delta_t
            last_intent_out = plan.intent or "post"
            runtime.request_post_cooldown(post_cooldown_seconds)
            runtime.request_speech_cooldown(5.0)
            # Lock in consciousness: record this autonomous thought so state of mind persists
            if state_update_fn and plan.text and (plan.text or "").strip():
                try:
                    state_update_fn({"meaning_hypotheses_append": (plan.text or "").strip()[:200]})
                except Exception:
                    pass
        else:
            runtime.record_failure(delta_t)
    finally:
        commit_end()

    return (last_post, last_intent_out)
