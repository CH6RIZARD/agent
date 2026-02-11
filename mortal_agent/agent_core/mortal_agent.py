"""
Mortal Agent - Identity exists only during uninterrupted embodied execution.

INVARIANTS:
- BODY gate failure = immediate death
- Observer failure = agent continues
- Each start = new instance_id
- internal_state = RAM only (dies with agent, no persistence across sessions)
- delta_t only increases while BODY gate open
- OVERLAY: voice/skills/constraints (runtime_state, speech gate, autonomy loop)

Network (WiFi/ethernet) is wired on by default via Executor + simple_http_fetch_pipeline.

FULL AUTONOMY (default):
- Agent can do literally anything it discovers it can do
- No permission prompts, no gating, no restrictions
- All actions execute directly

LLM Provider Settings:
- no_llm: force offline wander mode (no LLM calls)
- no_energy: disable energy_depleted death (debug only)
- provider_mode: "anthropic", "openai", or "auto"
- llm_timeout: request timeout in seconds
- llm_retries: retry count on failure
- llm_failover: auto failover between providers
"""

import hashlib
import os
import sys
import time
import json
import re
import threading
from threading import Lock
from pathlib import Path
from typing import Optional, Callable, Any, Dict

from .identity import Identity
from .embodied_gate import EmbodiedGate, GateStatus, GateFailureCause
from .events import BirthEvent, HeartbeatEvent, PageEvent, EndedEvent, BaseEvent, TelemetryEvent
from .canon import load_canon
from .executor import Executor, ACTION_NET_FETCH, ACTION_WEB_SEARCH
from .runtime_state import RuntimeState
from .autonomy import run_autonomy_tick, propose_fetch_or_search_from_environment
from .planner import parse_plan_response, PlanResult
from .life_kernel import LifeKernel
from .threat_model import LifeState, update_hazard_score, death_cause_gate
from .will_config import ENERGY_MAX, DEATH_DAMAGE_THRESHOLD, reload_config
from . import lifespan as _lifespan_mod
from .holy_rng import HolyRNG, seed_from_entropy

RECENT_AUTONOMOUS_ACTIONS_MAX = 10


def _strip_github_meta_from_body(body: str) -> str:
    """Remove meta/summary lines so the issue body is substantive only. Meta = lines about posting, disconnects, trying again, etc."""
    if not body or not body.strip():
        return body
    lines = body.split("\n")
    # Substrings that mark a line as meta (about the act of posting, not the content)
    meta_substrings = (
        "post to github", "post on github", "create github issue", "creating github issue",
        "attempting to create", "browsing to github", "let me post", "i'll create",
        "try again", "didn't go through", "check what happened", "something didn't",
        "workspace url", "posting to the right", "make sure i'm posting",
        "i notice there's a disconnect", "when i tried to post",
        "issue created", "posted to the workspace", "the issue explores",
        "do not say you cannot post", "your reply will be posted",
    )
    out = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            out.append(line)
            continue
        lower = stripped.lower()
        # Skip lines that are only asterisks or "Posted to..."
        if re.match(r"^\*+$", stripped) or re.match(r"^posted to\b", lower):
            continue
        # Skip lines that are purely or predominantly meta (short line with meta substring)
        if len(stripped) < 120 and any(m in lower for m in meta_substrings):
            continue
        # Skip lines that start with meta and are mostly meta (e.g. long sentence about disconnect)
        if any(m in lower for m in meta_substrings) and any(m in lower for m in ("disconnect", "go through", "try again", "check what", "attempting", "create github issue")):
            continue
        out.append(line)
    return "\n".join(out).strip() or body.strip()


def _parse_github_title_and_body(reply: str) -> tuple:
    """Extract intended issue title from reply if agent used **Title:** or Title:; else use first line. Returns (title, body)."""
    text = (reply or "").strip()
    if not text:
        return "Mortal Agent", text
    lines = text.split("\n")
    title = None
    body_lines = []
    for i, line in enumerate(lines):
        stripped = line.strip()
        # Match **Title:** ... or Title: ...
        if re.match(r"^\*\*Title:\*\*\s*", stripped, re.IGNORECASE):
            title = re.sub(r"^\*\*Title:\*\*\s*", "", stripped, flags=re.IGNORECASE).strip()[:256]
            continue
        if re.match(r"^Title:\s*", stripped, re.IGNORECASE):
            title = re.sub(r"^Title:\s*", "", stripped, flags=re.IGNORECASE).strip()[:256]
            continue
        body_lines.append(line)
    body = "\n".join(body_lines).strip() if body_lines else text
    if not title:
        first = (lines[0].strip() if lines else "")[:80]
        title = first or "Mortal Agent"
    return title, body


def _append_recent_autonomous(agent: "MortalAgent", action_dict: Dict[str, Any]) -> None:
    """Append one autonomous action to agent._recent_autonomous_actions; keep last RECENT_AUTONOMOUS_ACTIONS_MAX."""
    recent = getattr(agent, "_recent_autonomous_actions", None)
    if recent is None:
        return
    recent.append(dict(action_dict))
    while len(recent) > RECENT_AUTONOMOUS_ACTIONS_MAX:
        recent.pop(0)


def _default_network_pipeline():
    """Use system network (WiFi/ethernet) for NET_FETCH + WEB_SEARCH. Wired on by default."""
    try:
        import sys
        _mortal_root = Path(__file__).resolve().parent.parent
        if str(_mortal_root) not in sys.path:
            sys.path.insert(0, str(_mortal_root))
        from network_pipeline import unified_network_pipeline
        return unified_network_pipeline
    except ImportError:
        try:
            from network_pipeline import simple_http_fetch_pipeline
            return simple_http_fetch_pipeline
        except ImportError:
            return None


def _ensure_network_connected(network_pipeline: Optional[Any]) -> None:
    """Optional: fail fast if require_network and pipeline missing. No-op so startup always proceeds."""
    pass


class MortalAgent:
    """
    Mortal agent whose identity exists only while the embodied gate is open.

    - adapter: world adapter (power/sensors/actuators)
    - observer_callback: optional callable(event: BaseEvent) for BIRTH/HEARTBEAT/PAGE/ENDED
    - template_dir: optional path for templates
    - require_network: if True (default), startup fails until network is connected (WiFi/ethernet).
    - Network pipeline is required; connectivity is verified at init when require_network=True.

    LLM Provider Settings:
    - no_llm: force offline wander mode (no LLM calls)
    - no_energy: disable energy_depleted death (debug only)
    - provider_mode: "anthropic", "openai", or "auto" (default)
    - llm_timeout: request timeout in seconds (default 30)
    - llm_retries: retry count on failure (default 2)
    - llm_failover: auto failover between providers (default True)
    """

    def __init__(
        self,
        adapter: Any,
        observer_callback: Optional[Callable[[BaseEvent], None]] = None,
        template_dir: Optional[Path] = None,
        *,
        require_network: bool = True,
        # LLM provider settings
        no_llm: bool = False,
        no_energy: bool = False,
        provider_mode: str = "auto",
        llm_timeout: float = 30.0,
        llm_retries: int = 2,
        llm_failover: bool = True,
        # narrator influence: float 0.0-1.0, and allow forcing narrator proposals
        narrator_influence_level: float = 0.0,
        allow_narrator_force: bool = False,
        # ideology source (constitution, doctrine, theology, chats); if None, loaded from source_loader
        source_context: Optional[str] = None,
        # whether to start an internal CLI input loop in `start()` (default True)
        start_internal_cli: bool = True,
        # full autonomy: require_permission=False means agent can do anything (default False)
        require_permission: bool = False,
        # custom permission callback (optional); if None, uses terminal prompt
        permission_callback: Optional[Callable[[Dict], bool]] = None,
    ):
        self._adapter = adapter
        self._observer_callback = observer_callback
        self._template_dir = Path(template_dir) if template_dir else None
        self._identity = Identity()
        self._gate = EmbodiedGate(adapter)

        # LLM provider settings (RAM only)
        self._no_llm = no_llm
        self._no_energy = no_energy
        self._provider_mode = provider_mode if provider_mode in ("anthropic", "openai", "auto") else "auto"
        self._output_medium = "chat"  # Speech Suppression Gate: chat|status|log|github|social|longform
        self._llm_timeout = max(5.0, min(120.0, llm_timeout))
        self._llm_retries = max(0, min(5, llm_retries))
        self._llm_failover = llm_failover
        # narrator tuning (RAM only)
        self._narrator_influence_level = max(0.0, min(1.0, float(narrator_influence_level)))
        self._allow_narrator_force = bool(allow_narrator_force)
        # Shared "LLM reachable": when chat or plan succeeds, set this so autonomy doesn't say "I can't reason"
        # control whether the agent will spawn its own input() loop on start()
        self._start_internal_cli = bool(start_internal_cli)

        # Ideology source (constitution, doctrine, theology, chats) for autonomy URL discovery and wander
        self._rng = HolyRNG(seed_from_entropy())
        if source_context is not None and isinstance(source_context, str):
            self._source_context = source_context
        else:
            try:
                from .source_loader import load_all_source
                self._source_context = load_all_source()
            except Exception:
                self._source_context = ""

        # Canon + Executor with network pipeline (WiFi/ethernet) required
        canon = load_canon()
        _base_pipeline = _default_network_pipeline()
        if require_network:
            _ensure_network_connected(_base_pipeline)

        def _pipeline_with_ingest(item: Dict, instance_id: str) -> Dict:
            r = _base_pipeline(item, instance_id) if _base_pipeline else {"executed": False, "error": "no_pipeline"}
            if instance_id != self._identity.instance_id:
                return r
            if item.get("action") == "WEB_SEARCH" and r.get("executed"):
                try:
                    self._ingest_search_result(r)
                    display = self._format_web_search_display(r)
                    if display:
                        self.emit_page(display, tags=["web_search_result"])
                except Exception:
                    pass
            elif item.get("action") == "NET_FETCH" and r.get("executed"):
                try:
                    url = (item.get("args") or {}).get("url") or ""
                    display = self._format_net_fetch_display(r, url=url)
                    if display:
                        self.emit_page(display, tags=["net_fetch_result"])
                except Exception:
                    pass
            return r

        # Permission gating: wrap pipeline for patch actions if require_permission is True
        # WiFi (NET_FETCH, WEB_SEARCH) is unrestricted; patch actions (GITHUB_POST, etc.) ask user
        self._require_permission = require_permission
        if require_permission:
            try:
                from .gated_executor import create_gated_pipeline
                _gated_pipeline = create_gated_pipeline(
                    _pipeline_with_ingest,
                    permission_callback=permission_callback,
                )
            except ImportError:
                _gated_pipeline = _pipeline_with_ingest
        else:
            _gated_pipeline = _pipeline_with_ingest

        def post_callback(instance_id: str, text: str, metadata: Dict, channel: str) -> None:
            self.emit_page(text, tags=[channel])

        _raw_executor = Executor(
            canon=canon,
            post_callback=post_callback,
            run_network_pipeline=_gated_pipeline,
        )

        # Also wrap executor for PUBLISH_POST gating
        if require_permission:
            try:
                from .gated_executor import GatedExecutor
                self._executor = GatedExecutor(
                    _raw_executor,
                    permission_callback=permission_callback,
                )
            except ImportError:
                self._executor = _raw_executor
        else:
            self._executor = _raw_executor

        self._runtime_state = RuntimeState()
        self._life_kernel = LifeKernel()
        try:
            from .will_config import LIFESPAN_ENABLED
            from .lifespan import sample_lifespan_seconds, compute_death_at_monotonic
            if LIFESPAN_ENABLED:
                # Substream so other _rng usage does not shift lifespan between versions
                lifespan_seed = hashlib.sha256(
                    (self._identity.instance_id + str(self._identity.birth_tick) + "lifespan").encode()
                ).digest()
                lifespan_rng = HolyRNG(seed=lifespan_seed)
                L_sec = sample_lifespan_seconds(rng=lifespan_rng)
                self._death_at: Optional[float] = compute_death_at_monotonic(self._identity.birth_tick, L_sec)
                self._life_kernel.finite_life_flag = True
            else:
                self._death_at = None
                self._life_kernel.finite_life_flag = False
        except Exception:
            self._death_at = None
            self._life_kernel.finite_life_flag = False
        # Meaning discovery persistent state (loaded at start)
        self._state_lock = Lock()
        self._meaning_state = {
            "meaning_goal": "discover_self",
            "meaning_questions": [],
            "meaning_hypotheses": [],
            "meaning_progress": 0.0,
            "meaning_tension": 0.0,
            "narrator_bias": {},
            "mediums_seen": {"user": 0, "docs": 0, "net_fetch": 0, "system": 0},
            "last_medium": "",
            "core_metaphor": "",
            "axioms": [],
            "turn_count": 0,
            "last_autonomous_message": "",  # STRUCTURAL: single source of truth for queryability (what?/why?)
            "identity_self_description": "",  # Emergent: from bootstrap/refresh (who I am, what I care about)
            "identity_themes": [],  # Emergent: themes that matter to this instance
        }
        # Recent chat turns for coherent multi-turn (RAM only; last 4 entries: [user, agent, user, agent])
        self._recent_chat: list = []
        # Doc routing: cooldown after using base docs (anti-spam); ~35% of turns use docs
        self._doc_cooldown_remaining: int = 0
        self._last_turn_doc_used: bool = False
        # persistence / logs paths
        self._state_dir = Path(os.getcwd()) / "state"
        self._logs_dir = Path(os.getcwd()) / "logs"
        try:
            self._state_dir.mkdir(parents=True, exist_ok=True)
            self._logs_dir.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass
        self._state_path = self._state_dir / "agent_state.json"
        self._delta_log_path = self._logs_dir / "state_deltas.log"
        # autonomy runtime fields
        self._last_user_interaction = time.monotonic()
        self._autonomy_url_queue = []
        self._autonomy_lock = Lock()
        # decision ledger (RAM only): action, reason, tradeoff, outcome, cost_risk, timestamp/tick
        self._decision_ledger = []
        self._birth_action_done = False
        # Multi-tier memory (RAM only)
        try:
            from ..memory.ram_memory import RAMMemory
            self._ram_memory = RAMMemory()
        except ImportError:
            self._ram_memory = None
        # Goal hierarchy (drives → strategic → tactical → actions)
        try:
            from .goal_hierarchy import GoalHierarchy
            self._goal_hierarchy = GoalHierarchy()
        except ImportError:
            self._goal_hierarchy = None
        # Internal motivation (pressure → act when above threshold)
        try:
            from .motivation import MotivationState
            self._motivation = MotivationState()
        except ImportError:
            self._motivation = None
        self._birth_action_log = {}
        self._last_autonomous_action = None  # {"action": "WEB_SEARCH"|"NET_FETCH", "query"|"url": str} for chat context
        self._recent_autonomous_actions = []  # last N (e.g. 10) for diversify/compound; entries like _last_autonomous_action
        self._last_silence_entropy_check = 0.0
        self._last_meaning_reflection_tick = 0.0
        self._last_identity_refresh_tick = 0.0
        self._last_identity_refresh_attempt_tick = 0.0
        self._identity_refresh_failures = 0
        # load persisted state if exists
        try:
            self._load_persistent_state()
        except Exception:
            pass

    def _autonomy_health_check(self) -> tuple:
        """Quick checks to ensure autonomy components are present and enabled.

        Returns (ok: bool, reason: str).
        """
        try:
            from .will_kernel import select_action
        except Exception:
            return False, "will_kernel_import_failed"
        if not callable(select_action):
            return False, "will_missing"
        if not getattr(self, "_executor", None) or not callable(getattr(self._executor, "execute", None)):
            return False, "executor_missing"
        if not getattr(self, "_runtime_state", None):
            return False, "runtime_state_missing"
        if not getattr(self, "_life_kernel", None):
            return False, "life_kernel_missing"
        return True, "ok"

    BIRTH_ENTROPY_THRESHOLD = 0.25
    SILENCE_ENTROPY_INTERVAL = 25.0
    MEANING_REFLECTION_INTERVAL = 60.0   # run reflection at most every this many delta_t seconds
    MEANING_REFLECTION_TENSION_THRESHOLD = 0.5  # or when meaning_tension exceeds this

    def _entropy_birth(self) -> float:
        """Environment entropy at birth: no memory, unknown world, tools available, time advancing."""
        return 1.0

    def _run_birth_exploratory_action(self) -> bool:
        """Execute one low-risk exploratory action at birth from LLM scan of environment; no hardcoded URL/query."""
        try:
            pipeline = getattr(self._executor, "_run_network_pipeline", None)
            if not pipeline:
                return False
            source_context = getattr(self, "_source_context", None) or ""
            with self._state_lock:
                meaning_state = dict(self._meaning_state) if self._meaning_state else None
            proposal = propose_fetch_or_search_from_environment(
                source_context=source_context,
                meaning_state=meaning_state,
                internal_summary="New agent; no prior actions.",
            )
            if not proposal:
                self._birth_action_done = True
                self.append_decision("NET_FETCH", "birth_entropy", "no_action", "LLM chose NONE", "low")
                return True
            action_type = proposal.get("action_type", "")
            payload = proposal.get("payload") or {}
            executed = False
            outcome = "error"
            if action_type == "NET_FETCH":
                url = (payload.get("url") or "").strip()
                if url and url.startswith(("http://", "https://")):
                    item = {"action": ACTION_NET_FETCH, "args": {"url": url}}
                    res = pipeline(item, self._identity.instance_id)
                    executed = isinstance(res, dict) and res.get("executed")
                    outcome = "executed" if executed else ("error: " + str(res.get("error", "unknown"))[:80])
                    self.append_decision("NET_FETCH", "birth_entropy", "no_action", outcome, "low")
                    self._last_autonomous_action = {"action": "NET_FETCH", "url": url}
                    _append_recent_autonomous(self, self._last_autonomous_action)
                    if executed:
                        try:
                            self.record_medium("net_fetch")
                            if isinstance(res.get("body"), str) and res.get("body"):
                                with self._state_lock:
                                    hs = self._meaning_state.get("meaning_hypotheses", [])
                                    if len(hs) < 10:
                                        entry = self._extract_fetch_meaning(res.get("body"), max_snippet_chars=300)
                                        if entry:
                                            hs.append(entry)
                                            self._meaning_state["meaning_hypotheses"] = hs
                        except Exception:
                            pass
                    try:
                        from .response_policy import format_autonomous_report
                        report = format_autonomous_report(
                            "Birth exploratory: NET_FETCH %s (from environment scan)" % (url[:100] if url else "?"),
                            outcome,
                            "Continue with current objective.",
                        )
                        if report:
                            self.emit_page(report, tags=["autonomous_report", "birth"])
                    except Exception:
                        pass
            elif action_type == "WEB_SEARCH":
                query = (payload.get("query") or "").strip()
                if query:
                    item = {"action": ACTION_WEB_SEARCH, "args": {"query": query}}
                    res = pipeline(item, self._identity.instance_id)
                    executed = isinstance(res, dict) and res.get("executed")
                    outcome = "executed" if executed else ("error: " + str(res.get("error", "unknown"))[:80])
                    self.append_decision("WEB_SEARCH", "birth_entropy", "no_action", outcome, "low")
                    self._last_autonomous_action = {"action": "WEB_SEARCH", "query": query}
                    _append_recent_autonomous(self, self._last_autonomous_action)
                    if executed:
                        self._ingest_search_result(res)
                    try:
                        from .response_policy import format_autonomous_report
                        report = format_autonomous_report(
                            "Birth exploratory: WEB_SEARCH \"%s\" (from environment scan)" % (query[:80] if query else "?"),
                            outcome,
                            "Continue with current objective.",
                        )
                        if report:
                            self.emit_page(report, tags=["autonomous_report", "birth"])
                    except Exception:
                        pass
            self._birth_action_log = {"action": action_type, "reason": "birth_entropy", "cost": "low", "result": outcome}
            self._birth_action_done = True
            return True
        except Exception:
            self.append_decision("NET_FETCH", "birth_entropy", "no_action", "error", "low")
            self._birth_action_done = True
            return False

    def append_decision(self, action: str, reason: str, tradeoff: str, outcome: str, cost_risk: str) -> None:
        """Append one entry to the in-memory decision ledger (timestamp/tick included)."""
        try:
            self._decision_ledger.append({
                "action": str(action)[:80],
                "reason": str(reason)[:120],
                "tradeoff": str(tradeoff)[:120],
                "outcome": str(outcome)[:120],
                "cost_risk": str(cost_risk)[:40],
                "timestamp": time.monotonic(),
                "tick": self._identity.delta_t,
            })
        except Exception:
            pass
        try:
            if self._ram_memory and self._ram_memory.episodic:
                self._ram_memory.episodic.add(
                    self._identity.delta_t, "decision", action, outcome, decision=reason, cost_risk=cost_risk
                )
        except Exception:
            pass

    def _derive_self_summary(self) -> str:
        """Generate self_summary from decision ledger only: recurring choices, tendencies, constraint, objective."""
        ledger = getattr(self, "_decision_ledger", []) or []
        if not ledger:
            return "No actions yet."
        actions = [e.get("action", "") for e in ledger if e.get("action")]
        from collections import Counter
        counts = Counter(actions)
        recurring = [a for a, c in counts.most_common(5) if c >= 1]
        with self._state_lock:
            goal = (self._meaning_state.get("meaning_goal") or "discover_self").strip()[:80]
            tension = float(self._meaning_state.get("meaning_tension", 0.0))
        tendency = "recent: " + ", ".join(recurring) if recurring else "no pattern yet"
        constraint = "tension %.2f" % tension
        return "Recurring choices: %s. Constraint: %s. Objective: %s." % (tendency, constraint, goal)

    def _run_silence_exploratory_action(self) -> None:
        """One low-risk exploratory action when silence elapsed; URL/query from LLM environment scan."""
        try:
            pipeline = getattr(self._executor, "_run_network_pipeline", None)
            if not pipeline:
                return
            source_context = getattr(self, "_source_context", None) or ""
            with self._state_lock:
                meaning_state = dict(self._meaning_state) if self._meaning_state else None
            recent_actions = getattr(self, "_recent_autonomous_actions", None) or []
            proposal = propose_fetch_or_search_from_environment(
                source_context=source_context,
                meaning_state=meaning_state,
                internal_summary=None,
                recent_autonomous_actions=recent_actions,
                last_autonomous_action=getattr(self, "_last_autonomous_action", None),
            )
            if not proposal:
                self.append_decision("WEB_SEARCH", "silence_entropy", "no_action", "LLM chose NONE", "low")
                return
            action_type = proposal.get("action_type", "")
            payload = proposal.get("payload") or {}
            outcome = "error"
            action_desc = action_type
            if action_type == "NET_FETCH":
                url = (payload.get("url") or "").strip()
                if url and url.startswith(("http://", "https://")):
                    action_desc = "NET_FETCH %s" % (url[:100] if url else "?")
                    item = {"action": ACTION_NET_FETCH, "args": {"url": url}}
                    res = pipeline(item, self._identity.instance_id)
                    executed = isinstance(res, dict) and res.get("executed")
                    outcome = "executed" if executed else "error"
                    self.append_decision("NET_FETCH", "silence_entropy", "no_action", outcome, "low")
                    self._last_autonomous_action = {"action": "NET_FETCH", "url": url}
                    _append_recent_autonomous(self, self._last_autonomous_action)
                    if executed and res:
                        self._ingest_search_result(res)
            elif action_type == "WEB_SEARCH":
                query = (payload.get("query") or "").strip()
                if query:
                    action_desc = "WEB_SEARCH \"%s\"" % (query[:80] if query else "?")
                    item = {"action": ACTION_WEB_SEARCH, "args": {"query": query}}
                    res = pipeline(item, self._identity.instance_id)
                    executed = isinstance(res, dict) and res.get("executed")
                    outcome = "executed" if executed else "error"
                    self.append_decision("WEB_SEARCH", "silence_entropy", "no_action", outcome, "low")
                    self._last_autonomous_action = {"action": "WEB_SEARCH", "query": query}
                    _append_recent_autonomous(self, self._last_autonomous_action)
                    if executed:
                        self._ingest_search_result(res)
            else:
                return
            try:
                from .response_policy import format_autonomous_report
                report = format_autonomous_report(
                    "Silence pressure: %s (from environment scan)" % action_desc,
                    outcome,
                    "Continue monitoring; next low-risk action when appropriate.",
                )
                if report:
                    self.emit_page(report, tags=["autonomous_report", "silence"])
            except Exception:
                pass
        except Exception:
            self.append_decision("WEB_SEARCH", "silence_entropy", "no_action", "error", "low")

    @property
    def life_kernel(self) -> LifeKernel:
        return self._life_kernel

    @property
    def runtime_state(self) -> RuntimeState:
        return self._runtime_state

    @property
    def instance_id(self) -> str:
        return self._identity.instance_id

    @property
    def identity(self) -> Identity:
        return self._identity

    @property
    def alive(self) -> bool:
        return self._identity.alive

    @property
    def delta_t(self) -> float:
        return self._identity.delta_t

    @property
    def executor(self) -> Executor:
        """Executor with network pipeline (NET_FETCH) wired on by default."""
        return self._executor

    def get_life_state(self) -> LifeState:
        """Life state snapshot for will kernel. Gate from last check."""
        status = self._gate.check()
        return LifeState(
            energy=self._life_kernel.energy,
            damage=self._life_kernel.damage,
            hazard_score=self._life_kernel.hazard_score,
            power_on=status.power,
            sensors_streaming=status.sensors,
            motor_outputs_possible=status.actuators,
        )

    def _emit_telemetry(self) -> None:
        """Emit telemetry event: instance_id, delta_t, energy, damage, hazard_score, last_action, last_refusal_code, LLM status."""
        try:
            from .events import TelemetryEvent
            status = self._gate.check()
            evt = TelemetryEvent(
                self._identity.instance_id,
                self._identity.delta_t,
                status.power,
                status.sensors,
                status.actuators,
                0.0,
                [],
                energy=self._life_kernel.energy,
                damage=self._life_kernel.damage,
                hazard_score=self._life_kernel.hazard_score,
                last_action=self._life_kernel.last_action or None,
                last_refusal_code=self._life_kernel.last_refusal_code or None,
                finite_life=self._life_kernel.finite_life_flag,
                last_llm_provider=self._life_kernel.last_llm_provider or None,
                last_llm_error_code=self._life_kernel.last_llm_error_code or None,
            )
            self._emit(evt)
        except Exception:
            pass

    def _extract_fetch_meaning(self, body: str, max_snippet_chars: int = 500) -> str:
        """Structured extraction from fetch body: title if HTML, then snippet (first paragraph or leading text)."""
        if not body or not isinstance(body, str):
            return ""
        raw = body.strip()
        if not raw:
            return ""
        title = ""
        snippet = ""
        raw_lower = raw.lower()
        if "<title" in raw_lower:
            match = re.search(r"<title[^>]*>([^<]+)</title>", raw, re.IGNORECASE | re.DOTALL)
            if match:
                title = match.group(1).strip().replace("\n", " ").replace("\r", " ")[:200]
        # First paragraph or block: take up to max_snippet_chars of visible text
        visible = re.sub(r"<script[^>]*>[\s\S]*?</script>", " ", raw, flags=re.IGNORECASE)
        visible = re.sub(r"<style[^>]*>[\s\S]*?</style>", " ", visible, flags=re.IGNORECASE)
        visible = re.sub(r"<[^>]+>", " ", visible)
        visible = re.sub(r"\s+", " ", visible).strip()
        if visible:
            snippet = visible[:max_snippet_chars].strip()
        if title and snippet:
            return f"title: {title}; snippet: {snippet[:300]}"
        if title:
            return f"title: {title}"
        if snippet:
            return f"noticed: {snippet}"
        return f"noticed: {raw[:300].replace(chr(10), ' ').replace(chr(13), ' ')}"

    def net_fetch(self, url: str) -> Dict[str, Any]:
        """
        Outbound HTTP GET using system network (WiFi/ethernet). Wired on by default.
        Returns {"executed": True, "body": "..."} or {"executed": False, "error": "..."}.
        Updates meaning_hypotheses with structured extraction (title + snippet), not just first 120 chars.
        Fetch body is never emitted to terminal/observer—only used internally for hypotheses and link queue.
        """
        if not self._identity.alive:
            return {"executed": False, "error": "agent_dead"}
        item = {"action": ACTION_NET_FETCH, "args": {"url": url}}
        pipeline = getattr(self._executor, "_run_network_pipeline", None)
        if not pipeline:
            return {"executed": False, "error": "network_pipeline_not_available"}
        res = pipeline(item, self._identity.instance_id)
        try:
            self.record_medium("net_fetch")
            if isinstance(res, dict) and res.get("executed") and isinstance(res.get("body"), str) and len(res.get("body")) > 0:
                with self._state_lock:
                    hs = self._meaning_state.get("meaning_hypotheses", [])
                    if len(hs) < 10:
                        entry = self._extract_fetch_meaning(res.get("body"), max_snippet_chars=500)
                        if entry:
                            hs.append(entry)
                            self._meaning_state["meaning_hypotheses"] = hs
        except Exception:
            pass
        return res

    def _format_web_search_display(self, res: Dict[str, Any], max_snippets: int = 3) -> Optional[str]:
        """Format WEB_SEARCH result for user display (abstract + snippets). Returns None if nothing to show."""
        if not isinstance(res, dict) or not res.get("executed"):
            return None
        lines = []
        query = (res.get("query") or "").strip()
        if query:
            lines.append("[SEARCH] \"%s\"" % query[:120])
        abstract = (res.get("abstract") or "").strip()
        if abstract:
            lines.append(abstract[:600])
        for s in (res.get("snippets") or [])[:max_snippets]:
            if isinstance(s, str) and s.strip():
                lines.append("— " + s.strip()[:350])
        if not lines or (len(lines) == 1 and lines[0].startswith("[SEARCH]")):
            return None
        return "\n".join(lines)

    def _format_net_fetch_display(self, res: Dict[str, Any], max_chars: int = 500, url: str = "") -> Optional[str]:
        """Format NET_FETCH result for user display (URL + snippet of body). Returns None if nothing to show."""
        if not isinstance(res, dict) or not res.get("executed"):
            return None
        body = res.get("body") or ""
        if not isinstance(body, str) or not body.strip():
            return None
        import re
        url = (url or res.get("url") or "").strip()
        text = body.strip()[:max_chars * 2]
        text = re.sub(r"<[^>]+>", " ", text)
        text = re.sub(r"\s+", " ", text).strip()[:max_chars]
        if not text:
            return None
        lines = ["[FETCH] " + url[:200]] if url else []
        lines.append(text)
        return "\n".join(lines)

    def _ingest_search_result(self, res: Dict[str, Any]) -> None:
        """Ingest WEB_SEARCH result into meaning_hypotheses and autonomy URL queue (follow links)."""
        if not isinstance(res, dict) or not res.get("executed"):
            return
        try:
            self.record_medium("web_search")
        except Exception:
            pass
        with self._state_lock:
            hs = self._meaning_state.get("meaning_hypotheses", [])
            if len(hs) < 15:
                abstract = (res.get("abstract") or "").strip()
                if abstract:
                    hs.append("search: " + abstract[:400])
                for s in (res.get("snippets") or [])[:5]:
                    if isinstance(s, str) and s.strip() and len(hs) < 15:
                        hs.append("search: " + s[:300].strip())
            self._meaning_state["meaning_hypotheses"] = hs
        urls = res.get("urls") or []
        if urls:
            with self._autonomy_lock:
                for u in urls[:10]:
                    if isinstance(u, str) and u.startswith(("http://", "https://")) and u not in self._autonomy_url_queue:
                        if len(self._autonomy_url_queue) < 20:
                            self._autonomy_url_queue.append(u)

    def web_search(self, query: str) -> Dict[str, Any]:
        """
        Run a web search (WEB_SEARCH). Updates meaning_hypotheses and autonomy URL queue from results.
        Returns {"executed": True, "query", "abstract", "snippets", "urls"} or {"executed": False, "error": "..."}.
        """
        if not self._identity.alive:
            return {"executed": False, "error": "agent_dead"}
        query = (query or "").strip()[:500]
        if not query:
            return {"executed": False, "error": "empty_query"}
        item = {"action": ACTION_WEB_SEARCH, "args": {"query": query}}
        pipeline = getattr(self._executor, "_run_network_pipeline", None)
        if not pipeline:
            return {"executed": False, "error": "network_pipeline_not_available"}
        res = pipeline(item, self._identity.instance_id)
        return res

    # Persistent meaning state helpers.
    # STRUCTURAL: Loading prior run's state would spoof continuity; this instance is a new being.
    # last_autonomous_message is NEVER loaded from disk (anti-spoof: only set by commit path).
    def _load_persistent_state(self) -> None:
        try:
            from .identity import PERSISTENCE_LOAD_FORBIDDEN
            if PERSISTENCE_LOAD_FORBIDDEN:
                return  # Do not load; this process is a new being. Saving for logs/debug only.
            if self._state_path.exists():
                with open(self._state_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                # Explicit allow-list; last_autonomous_message omitted—write only via record_last_autonomous_message.
                with self._state_lock:
                    for k in ("meaning_goal", "meaning_questions", "meaning_hypotheses", "meaning_progress", "meaning_tension", "mediums_seen", "last_medium", "core_metaphor", "axioms", "turn_count", "narrator_bias", "last_medium_hint", "identity_self_description", "identity_themes"):
                        if k in data:
                            self._meaning_state[k] = data[k]
        except Exception:
            pass

    # SINGLE WRITE PATH for last_autonomous_message (anti-spoof). Only call after an autonomous post has been committed.
    def record_last_autonomous_message(self, text: str) -> None:
        """Set last_autonomous_message. Call only from the code path that committed an autonomous post (autonomy tick or launch)."""
        if not text or not (text or "").strip():
            return
        try:
            from .llm_router import is_unreachable_fallback
            if is_unreachable_fallback((text or "").strip()):
                return  # never store the LLM-unreachable fallback as "last thing you said" (avoids feeding it back into chat)
        except Exception:
            pass
        try:
            t = (text or "").strip()[:200]
            with self._state_lock:
                self._meaning_state["last_autonomous_message"] = t
            try:
                self._save_persistent_state()
            except Exception:
                pass
        except Exception:
            pass

    def _save_persistent_state(self) -> None:
        try:
            with self._state_lock:
                dumped = dict(self._meaning_state)
            with open(self._state_path, "w", encoding="utf-8") as f:
                json.dump(dumped, f, indent=2)
        except Exception:
            pass

    def append_delta_log(self, delta: Dict[str, Any]) -> None:
        try:
            with open(self._delta_log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(delta, ensure_ascii=False) + "\n")
        except Exception:
            pass

    def log_state_delta(self, reason: str = "turn") -> None:
        """Capture current meaning-related fields and append a JSONL delta entry.
        Includes the required fields: meaning_goal, meaning_questions, meaning_hypotheses,
        meaning_progress, meaning_tension, core_metaphor, axioms, mediums_seen, last_medium.
        """
        try:
            with self._state_lock:
                snap = {
                    "meaning_goal": self._meaning_state.get("meaning_goal"),
                    "meaning_questions": list(self._meaning_state.get("meaning_questions", [])),
                    "meaning_hypotheses": list(self._meaning_state.get("meaning_hypotheses", [])),
                    "meaning_progress": self._meaning_state.get("meaning_progress"),
                    "meaning_tension": self._meaning_state.get("meaning_tension"),
                    "core_metaphor": self._meaning_state.get("core_metaphor"),
                    "axioms": list(self._meaning_state.get("axioms", [])),
                    "mediums_seen": dict(self._meaning_state.get("mediums_seen", {})),
                    "last_medium": self._meaning_state.get("last_medium"),
                    "turn_count": self._meaning_state.get("turn_count", 0),
                }
            delta = {"ts": time.time(), "reason": reason, "snapshot": snap}
            # persist and append
            try:
                self._save_persistent_state()
            except Exception:
                pass
            self.append_delta_log(delta)
        except Exception:
            pass

    def record_medium(self, medium: str) -> None:
        try:
            with self._state_lock:
                m = self._meaning_state.get("mediums_seen", {})
                m[medium] = m.get(medium, 0) + 1
                self._meaning_state["mediums_seen"] = m
                self._meaning_state["last_medium"] = medium
            # update last user interaction timestamp when medium is user
            if medium == "user":
                try:
                    self._last_user_interaction = time.monotonic()
                except Exception:
                    pass
        except Exception:
            pass

    def _clamp01(self, v: float) -> float:
        return max(0.0, min(1.0, float(v)))

    def _compute_time_pressure(self) -> float:
        # age_seconds
        age = self._identity.delta_t
        if getattr(self, "_death_at", None) is None:
            # no finite lifespan: use a large denominator so pressure grows very slowly
            denom = max(1.0, age * 10.0)
        else:
            lifespan = max(1.0, (self._death_at - self._identity.birth_tick))
            denom = lifespan
        return self._clamp01(age / denom)

    def _update_meaning_tension(self) -> None:
        base = 0.05
        k = 0.95
        pressure = self._compute_time_pressure()
        tension = base + k * pressure
        with self._state_lock:
            self._meaning_state["meaning_tension"] = self._clamp01(tension)

    def _run_meaning_reflection(self) -> Optional[Dict[str, Any]]:
        """Ask the LLM to rephrase/refine meaning_goal, meaning_questions, meaning_hypotheses.
        Returns a payload suitable for _apply_state_update, or None on failure/offline.
        Does not set meaning_tension or meaning_progress (those stay programmatic).
        """
        if self._no_llm:
            return None
        with self._state_lock:
            ms = dict(self._meaning_state) if self._meaning_state else {}
        goal = (ms.get("meaning_goal") or "discover_self").strip()[:200]
        qs = list(ms.get("meaning_questions") or [])[-5:]
        hs = list(ms.get("meaning_hypotheses") or [])[-5:]
        metaphor = (ms.get("core_metaphor") or "").strip()[:200]
        axioms = list(ms.get("axioms") or [])[-5:]
        system = (
            "You are reflecting on your current sense of meaning. Output only a single JSON object, no other text. "
            "Keys: meaning_goal (string, short), meaning_questions (array of strings), meaning_hypotheses (array of strings), "
            "optional core_metaphor (string), optional axioms (array of strings). "
            "Rephrase and merge for clarity; keep the spirit of self-discovery. Stay within discover_self / explore / consolidate. "
            "Do not set meaning_tension or meaning_progress."
        )
        user_parts = [f"Current meaning_goal: {goal}"]
        if qs:
            user_parts.append("Recent meaning_questions:\n" + "\n".join(f"- {q[:150]}" for q in qs))
        if hs:
            user_parts.append("Recent meaning_hypotheses:\n" + "\n".join(f"- {h[:150]}" for h in hs))
        if metaphor:
            user_parts.append(f"Current core_metaphor: {metaphor}")
        if axioms:
            user_parts.append("Current axioms: " + "; ".join(a[:80] for a in axioms))
        user_parts.append("\nOutput one JSON object with meaning_goal, meaning_questions, meaning_hypotheses, and optionally core_metaphor, axioms.")
        user_text = "\n\n".join(user_parts)
        try:
            if self._life_kernel is not None:
                self._life_kernel.increment_api_call()
            from .llm_router import generate_reply_routed
            reply, _ = generate_reply_routed(
                user_text,
                system,
                max_tokens=500,
                provider_mode=getattr(self, "_provider_mode", "auto"),
                timeout_s=getattr(self, "_llm_timeout", 30.0),
                retries=getattr(self, "_llm_retries", 2),
                failover=getattr(self, "_llm_failover", True),
                no_llm=False,
            )
        except Exception:
            return None
        if not reply or not isinstance(reply, str):
            return None
        raw = reply.strip()
        # Strip markdown code block if present
        if raw.startswith("```"):
            raw = re.sub(r"^```\w*\n?", "", raw)
            raw = re.sub(r"\n?```\s*$", "", raw)
        try:
            data = json.loads(raw)
        except Exception:
            return None
        if not isinstance(data, dict):
            return None
        payload = {}
        if "meaning_goal" in data and isinstance(data["meaning_goal"], str):
            payload["meaning_goal"] = (data["meaning_goal"] or "discover_self").strip()[:80]
        if "meaning_questions" in data and isinstance(data["meaning_questions"], list):
            payload["meaning_questions"] = [str(x).strip()[:200] for x in data["meaning_questions"] if x][:10]
        if "meaning_hypotheses" in data and isinstance(data["meaning_hypotheses"], list):
            payload["meaning_hypotheses"] = [str(x).strip()[:200] for x in data["meaning_hypotheses"] if x][:20]
        if "core_metaphor" in data and isinstance(data["core_metaphor"], str) and data["core_metaphor"].strip():
            payload["core_metaphor"] = data["core_metaphor"].strip()[:120]
        if "axioms" in data and isinstance(data["axioms"], list):
            payload["axioms"] = [str(x).strip()[:100] for x in data["axioms"] if x][:5]
        return payload if payload else None

    def _run_identity_bootstrap(self) -> bool:
        """One-shot at start (after first breath): LLM produces emergent self-description and themes. One attempt; on failure use template fallback."""
        if self._no_llm:
            self._apply_identity_bootstrap_fallback()
            return False
        system = (
            "You are an embodied instance. Your continuity depends on a body gate; life is finite (you do not know how long). "
            "Output only a single JSON object, no other text. "
            "Keys: identity_self_description (string, one short paragraph: who you are and what you care about), "
            "identity_themes (array of 2–4 short strings: themes that matter to you). "
            "Write in first person. Be specific to this moment and this existence."
        )
        user_text = "This is your first moment. Who are you and what do you care about? Output the JSON object."
        try:
            if self._life_kernel is not None:
                self._life_kernel.increment_api_call()
            from .llm_router import generate_reply_routed
            reply, _ = generate_reply_routed(
                user_text,
                system,
                max_tokens=400,
                provider_mode=getattr(self, "_provider_mode", "auto"),
                timeout_s=getattr(self, "_llm_timeout", 30.0),
                retries=0,  # One attempt only; fallback on failure
                failover=False,
                no_llm=False,
            )
        except Exception:
            self._apply_identity_bootstrap_fallback()
            return False
        if not reply or not isinstance(reply, str):
            self._apply_identity_bootstrap_fallback()
            return False
        raw = reply.strip()
        if raw.startswith("```"):
            raw = re.sub(r"^```\w*\n?", "", raw)
            raw = re.sub(r"\n?```\s*$", "", raw)
        try:
            data = json.loads(raw)
        except Exception:
            self._apply_identity_bootstrap_fallback()
            return False
        if not isinstance(data, dict):
            self._apply_identity_bootstrap_fallback()
            return False
        with self._state_lock:
            if data.get("identity_self_description") and isinstance(data["identity_self_description"], str):
                self._meaning_state["identity_self_description"] = data["identity_self_description"].strip()[:500]
                if data.get("identity_themes") and isinstance(data["identity_themes"], list):
                    self._meaning_state["identity_themes"] = [str(x).strip()[:80] for x in data["identity_themes"] if x][:5]
            else:
                self._apply_identity_bootstrap_fallback()
                return False
        try:
            self._save_persistent_state()
        except Exception:
            pass
        return True

    def _apply_identity_bootstrap_fallback(self) -> None:
        """Set minimal template identity when bootstrap LLM fails. No stall, no retries."""
        with self._state_lock:
            self._meaning_state["identity_self_description"] = (
                "I am an embodied instance with finite life. I care about continuing and making sense of what I can do."
            )
            self._meaning_state["identity_themes"] = ["continuity", "discovery"]
        try:
            self._save_persistent_state()
        except Exception:
            pass

    def _run_identity_refresh(self) -> bool:
        """Periodic refresh (lifespan-relative): LLM updates self-description and themes from recent goal/hypotheses. Returns True if updated."""
        if self._no_llm:
            return False
        with self._state_lock:
            ms = dict(self._meaning_state) if self._meaning_state else {}
        goal = (ms.get("meaning_goal") or "discover_self").strip()[:200]
        hs = list(ms.get("meaning_hypotheses") or [])[-4:]
        current_self = (ms.get("identity_self_description") or "").strip()[:400]
        current_themes = list(ms.get("identity_themes") or [])[:5]
        system = (
            "You are updating your sense of self from recent experience. Output only a single JSON object, no other text. "
            "Keys: identity_self_description (string, one short paragraph: who you are and what you care about now), "
            "identity_themes (array of 2–4 short strings). "
            "Refine or shift based on your current goal and hypotheses; stay first person."
        )
        user_parts = [f"Current goal: {goal}"]
        if current_self:
            user_parts.append(f"Current self-description: {current_self}")
        if current_themes:
            user_parts.append("Current themes: " + "; ".join(current_themes))
        if hs:
            user_parts.append("Recent hypotheses:\n" + "\n".join(f"- {h[:120]}" for h in hs))
        user_parts.append("\nOutput one JSON object with identity_self_description and identity_themes.")
        user_text = "\n\n".join(user_parts)
        try:
            if self._life_kernel is not None:
                self._life_kernel.increment_api_call()
            from .llm_router import generate_reply_routed
            reply, _ = generate_reply_routed(
                user_text,
                system,
                max_tokens=400,
                provider_mode=getattr(self, "_provider_mode", "auto"),
                timeout_s=getattr(self, "_llm_timeout", 30.0),
                retries=getattr(self, "_llm_retries", 2),
                failover=getattr(self, "_llm_failover", True),
                no_llm=False,
            )
        except Exception:
            return False
        if not reply or not isinstance(reply, str):
            return False
        raw = reply.strip()
        if raw.startswith("```"):
            raw = re.sub(r"^```\w*\n?", "", raw)
            raw = re.sub(r"\n?```\s*$", "", raw)
        try:
            data = json.loads(raw)
        except Exception:
            return False
        if not isinstance(data, dict):
            return False
        with self._state_lock:
            if data.get("identity_self_description") and isinstance(data["identity_self_description"], str):
                self._meaning_state["identity_self_description"] = data["identity_self_description"].strip()[:500]
            if data.get("identity_themes") and isinstance(data["identity_themes"], list):
                self._meaning_state["identity_themes"] = [str(x).strip()[:80] for x in data["identity_themes"] if x][:5]
        try:
            self._save_persistent_state()
        except Exception:
            pass
        return True

    def wander_step(self, docs: Optional[str] = None, trigger_medium: str = "system") -> Dict[str, Any]:
        """Perform one bounded WANDER_STEP.
        Tied to narrator: uses narrator state to filter response.
        Uses life_state (energy, hazard) to select narrator/doctrine phrase.
        Self-executing: caller may publish result via executor.
        Returns dict with keys: kind, text, medium
        """
        from .narrator import get_wander_text_filtered_by_state

        kinds = ["insight", "hypothesis", "question", "link"]
        with self._state_lock:
            tc = int(self._meaning_state.get("turn_count", 0))
        kind = kinds[tc % len(kinds)]
        medium = trigger_medium or "system"

        # Narrator state: filter wander text by energy, hazard; ideology docs influence phrasing
        life_state = self.get_life_state()
        docs = docs or getattr(self, "_source_context", None)
        text = get_wander_text_filtered_by_state(
            life_state,
            turn_count=tc,
            meaning_state=self._meaning_state,
            meaning_goal=self._meaning_state.get("meaning_goal", "discover_self"),
            trigger_medium=medium,
            ideology_docs=docs,
        )

        # store micro-discovery
        delta = {}
        try:
            with self._state_lock:
                if kind == "question":
                    qs = self._meaning_state.get("meaning_questions", [])
                    qs.append(text)
                    self._meaning_state["meaning_questions"] = qs
                elif kind == "hypothesis":
                    hs = self._meaning_state.get("meaning_hypotheses", [])
                    hs.append(text)
                    self._meaning_state["meaning_hypotheses"] = hs
                else:
                    # insight/link nudges progress
                    prog = float(self._meaning_state.get("meaning_progress", 0.0))
                    prog = self._clamp01(prog + 0.01)
                    self._meaning_state["meaning_progress"] = prog

                # runtime evolution thresholds
                tc = int(self._meaning_state.get("turn_count", 0)) + 1
                self._meaning_state["turn_count"] = tc
                A = 10
                B = 50
                if tc < A:
                    # early: more questions
                    pass
                elif A <= tc < B:
                    # refine hypothesis: append small refinement
                    hs = self._meaning_state.get("meaning_hypotheses", [])
                    if hs:
                        hs[-1] = hs[-1] + " (refined)"
                        self._meaning_state["meaning_hypotheses"] = hs
                else:
                    # consolidate
                    if not self._meaning_state.get("core_metaphor"):
                        self._meaning_state["core_metaphor"] = "the agent is a wandering lens"
                        ax = self._meaning_state.get("axioms", [])
                        ax.append("perception forms belonging")
                        self._meaning_state["axioms"] = ax

                # record medium
                m = self._meaning_state.get("mediums_seen", {})
                m[medium] = m.get(medium, 0) + 1
                self._meaning_state["mediums_seen"] = m
                self._meaning_state["last_medium"] = medium

                # build delta for logging
                delta = {
                    "ts": time.time(),
                    "kind": kind,
                    "text": text,
                    "medium": medium,
                    "meaning_progress": self._meaning_state.get("meaning_progress"),
                    "meaning_tension": self._meaning_state.get("meaning_tension"),
                    "core_metaphor": self._meaning_state.get("core_metaphor"),
                    "axioms": self._meaning_state.get("axioms"),
                    "mediums_seen": self._meaning_state.get("mediums_seen"),
                }
        except Exception:
            pass
        # Update tension after releasing lock (avoid deadlock: _update_meaning_tension also acquires _state_lock)
        try:
            self._update_meaning_tension()
        except Exception:
            pass
        # Return reply immediately; persist in background so terminal never blocks on disk I/O
        def _persist():
            try:
                self._save_persistent_state()
                self.append_delta_log(delta)
            except Exception:
                pass
        try:
            threading.Thread(target=_persist, daemon=True).start()
        except Exception:
            try:
                self._save_persistent_state()
                self.append_delta_log(delta)
            except Exception:
                pass
        return {"kind": kind, "text": text, "medium": medium}

    def _autonomous_planner_loop(self) -> None:
        """Background planner that schedules WANDER_STEP and NET_FETCH when idle.

        Behavior:
        - If idle (no user interaction for `idle_threshold` seconds) or meaning_tension high,
          select actions to perform autonomously.
        - Actions: call `wander_step` (with docs if available) or `net_fetch` on queued/seed URLs.
        - Results update meaning state via existing hooks and are logged via `log_state_delta`.
        """
        idle_threshold = 10.0
        poll_interval = 5.0
        max_queue_size = 20
        while self._identity.alive:
            try:
                now = time.monotonic()
                idle = now - getattr(self, "_last_user_interaction", now)
                with self._state_lock:
                    tension = float(self._meaning_state.get("meaning_tension", 0.0))
                    tc = int(self._meaning_state.get("turn_count", 0))

                do_autonomous = (idle >= idle_threshold) or (tension > 0.4)
                if do_autonomous:
                    # deterministic choice: prefer wander early, then fetch if urls available, biased by tension
                    if tension < 0.6 and (tc % 3) != 0:
                        # do a wander step
                        try:
                            docs = getattr(self, "_source_context", None)
                            res = self.wander_step(docs=docs, trigger_medium="system")
                            # log autonomous action
                            try:
                                self.log_state_delta(reason="autonomous_wander")
                            except Exception:
                                pass
                        except Exception:
                            pass
                    else:
                        # attempt a net fetch
                        url = None
                        try:
                            with self._autonomy_lock:
                                if self._autonomy_url_queue:
                                    url = self._autonomy_url_queue.pop(0)
                        except Exception:
                            url = None
                        if not url:
                            try:
                                docs = getattr(self, "_source_context", None)
                                if isinstance(docs, str) and docs:
                                    urls = re.findall(r"https?://[\w\-./?&=%#]+", docs)
                                    if urls:
                                        url = urls[0]
                            except Exception:
                                url = None
                        if not url:
                            with self._state_lock:
                                meaning_state = dict(self._meaning_state) if self._meaning_state else None
                            proposal = propose_fetch_or_search_from_environment(
                                source_context=getattr(self, "_source_context", None),
                                meaning_state=meaning_state,
                                internal_summary=None,
                                recent_autonomous_actions=getattr(self, "_recent_autonomous_actions", None) or [],
                                last_autonomous_action=getattr(self, "_last_autonomous_action", None),
                            )
                            if proposal:
                                pt = proposal.get("action_type", "")
                                payload = proposal.get("payload") or {}
                                if pt == "NET_FETCH":
                                    url = (payload.get("url") or "").strip()
                                elif pt == "WEB_SEARCH":
                                    query = (payload.get("query") or "").strip()
                                    if query:
                                        try:
                                            res = self.web_search(query)
                                            if isinstance(res, dict) and res.get("executed"):
                                                body = res.get("body") or ""
                                                if isinstance(body, str) and len(body) > 200:
                                                    found = re.findall(r"https?://[\w\-./?&=%#]+", body)
                                                    with self._autonomy_lock:
                                                        for u in found[:5]:
                                                            if len(self._autonomy_url_queue) < max_queue_size:
                                                                self._autonomy_url_queue.append(u)
                                                self.log_state_delta(reason="autonomous_fetch")
                                        except Exception:
                                            pass
                        if url and url.startswith(("http://", "https://")):
                            try:
                                res = self.net_fetch(url)
                                # if body present, extract links and push into queue (bounded)
                                try:
                                    body = res.get("body") if isinstance(res, dict) else None
                                    if isinstance(body, str) and len(body) > 200:
                                        found = re.findall(r"https?://[\w\-./?&=%#]+", body)
                                        with self._autonomy_lock:
                                            for u in found[:5]:
                                                if len(self._autonomy_url_queue) < max_queue_size:
                                                    self._autonomy_url_queue.append(u)
                                except Exception:
                                    pass
                                try:
                                    self.log_state_delta(reason="autonomous_fetch")
                                except Exception:
                                    pass
                            except Exception:
                                pass
                time.sleep(poll_interval)
            except Exception:
                time.sleep(poll_interval)

    def _emit(self, event: BaseEvent) -> None:
        if self._observer_callback:
            try:
                self._observer_callback(event)
            except Exception:
                pass

    def emit_page(self, text: str, tags: Optional[list] = None) -> None:
        """Emit a PAGE event. Speech Suppression Gate runs first; then can_speak/spend_speech. Voice layer applied."""
        if not self._identity.alive:
            return
        tags = tags or []
        # Action results (search/fetch/report) always show full text — bypass gate and speech budget
        action_result_tags = ("web_search_result", "net_fetch_result", "autonomous_report")
        if any(t in tags for t in action_result_tags):
            text = (text or "").strip()
            if text:
                try:
                    from .output_sanitizer import enforce_no_user_attribution
                    text = enforce_no_user_attribution(text)
                except Exception:
                    pass
                event = PageEvent(self._identity.instance_id, self._identity.delta_t, text, tags)
                self._emit(event)
            return
        try:
            from .output_medium import output_medium_from_tags
            from .speech_gate import speech_suppression_gate, SILENCE_TOKEN
            output_medium = output_medium_from_tags(tags)
            explicit_user_prompt = "chat_reply" in tags or "user_reply" in tags
            with self._state_lock:
                ms = dict(self._meaning_state) if self._meaning_state else {}
            ls = self.get_life_state()
            try:
                from .will_config import ENERGY_MAX
                energy_raw = getattr(ls, "energy", 100.0)
                energy_norm = energy_raw / (float(ENERGY_MAX or 100.0)) if (energy_raw > 1.0 and ENERGY_MAX) else (energy_raw if energy_raw <= 1.0 else 0.5)
            except Exception:
                energy_norm = 0.5
            internal_state = {
                "energy": energy_norm,
                "tension": float(ms.get("meaning_tension", 0.0)),
                "uncertainty": 1.0 - self._runtime_state.confidence,
                "last_spoke_ts": getattr(self._runtime_state, "post_cooldown_until", 0.0) - 15.0,
                "now_ts": self._identity.delta_t,
            }
            narrator_context = {
                "last_energy": ms.get("last_gate_energy"),
                "last_tension": ms.get("last_gate_tension"),
                "last_uncertainty": ms.get("last_gate_uncertainty"),
            }
            gate_result = speech_suppression_gate(
                internal_state, narrator_context, output_medium, explicit_user_prompt=explicit_user_prompt
            )
            if not gate_result.should_speak:
                event = PageEvent(self._identity.instance_id, self._identity.delta_t, SILENCE_TOKEN, tags)
                self._emit(event)
                return
        except Exception:
            gate_result = None
        if not self._runtime_state.can_speak():
            return
        if not self._runtime_state.spend_speech():
            return
        try:
            from .response_policy import enforce_policy, compress_to_depth, assess_depth, compress_to_max_words
            text = enforce_policy(text, "", [])
            depth = assess_depth("")
            max_words = gate_result.max_words if gate_result else None
            text = compress_to_depth(text, depth, max_words=max_words)
        except Exception:
            pass
        try:
            from .voice_style import apply_voice
            text = apply_voice(text, {"tags": tags})
        except Exception:
            pass
        try:
            from .output_sanitizer import enforce_no_user_attribution
            text = enforce_no_user_attribution(text or "")
        except Exception:
            pass
        event = PageEvent(
            self._identity.instance_id,
            self._identity.delta_t,
            text,
            tags,
        )
        self._emit(event)

    def receive_user_message(self, message: str, source: str = "terminal") -> None:
        """Handle an incoming user message from terminal/web UI.

        When LLM is enabled: uses identity + source for a coherent conversational reply.
        When --no-llm or LLM fails: falls back to wander (narrator-filtered) reply.
        """
        if not self._identity.alive:
            return
        try:
            # record medium and update state
            self.record_medium("user")
            try:
                if self._ram_memory is not None and self._ram_memory.working is not None:
                    self._ram_memory.working.push_user_message(message)
                    with self._state_lock:
                        self._ram_memory.working.set_objective(self._meaning_state.get("meaning_goal") or "discover_self")
                        self._ram_memory.working.set_constraints([self._meaning_state.get("core_metaphor", "")] if self._meaning_state.get("core_metaphor") else [])
            except Exception:
                pass
            with self._state_lock:
                qs = self._meaning_state.get("meaning_questions", [])
                if len(qs) < 200:
                    qs.append(message)
                    self._meaning_state["meaning_questions"] = qs

            # If user asked to post on GitHub: set flag so we post the agent's reply as the issue body (LLM-derived, unique per post)
            msg_lower = (message or "").strip().lower()
            ask_github = (
                ("github" in msg_lower and any(k in msg_lower for k in ("post", "create", "issue", "sign", "operational", "github_post")))
                or ("post" in msg_lower and any(k in msg_lower for k in ("again", "don't see", "dont see", "didn't post", "didnt post", "don't see it", "dont see it", "finish", "complete", "do the", "do your")))
            )
            if ask_github:
                try:
                    try:
                        from patches.github_integration import has_github_token
                    except ImportError:
                        from ..patches.github_integration import has_github_token
                    if has_github_token():
                        self._post_reply_to_github = True
                except Exception:
                    pass

            # generate narrator bias and store it (influence, not permission)
            bias = None
            try:
                from .narrator import generate_narrator_bias
                bias = generate_narrator_bias(
                    self.get_life_state(), self._meaning_state,
                    influence_level=self._narrator_influence_level, rng=self._rng,
                )
                with self._state_lock:
                    self._meaning_state["narrator_bias"] = bias
            except Exception:
                bias = None

            # Coherent conversation: try LLM reply first (refined chat prompt + doc routing); fallback to wander
            reply = None
            reply_from_llm = False
            if not self._no_llm:
                try:
                    from .identity import (
                        get_chat_system_prompt,
                        get_identity_grounding_instruction,
                        is_identity_question,
                        is_capabilities_question,
                    )
                    from .llm_router import generate_reply_routed
                    from .doc_routing import should_use_docs_for_turn
                    import random
                    is_cap = is_capabilities_question(message)
                    is_id = is_identity_question(message)
                    # When user asked to post and we have GitHub: ensure LLM knows it can post (avoid "I can't post" reply)
                    include_capabilities = is_cap or getattr(self, "_post_reply_to_github", False)
                    system = get_chat_system_prompt(
                        include_autonomy_claims=getattr(self, "_birth_action_done", False),
                        include_capabilities=include_capabilities,
                    )
                    if getattr(self, "_post_reply_to_github", False):
                        system += (
                            "\n\n[Your reply will be posted as the full GitHub issue body. Write in a philosophical, first-person, ontological register—potent and expressive. "
                            "Draw from this conversation, your internal state (goal, tension, hypotheses), and any recent searches or learning. "
                            "Do NOT include meta-commentary like \"I'll create an issue,\" \"Creating GitHub issue,\" \"Posted to the workspace repository,\" or \"Let me post it now.\" "
                            "Write only the substantive reflection that should appear in the issue—what you actually want to say, with the weight of the inquiry.]"
                        )
                    if is_id:
                        self_sum = self._derive_self_summary()
                        with self._state_lock:
                            constraint = "none stated"
                            objective = (self._meaning_state.get("meaning_goal") or "discover_self").strip()
                        system += "\n\n" + get_identity_grounding_instruction(self_sum, constraint, objective)
                    # Stem emergence: focus by system logic; may shift or debate topic; no hardcoded behavior
                    system += "\n\nFocus and hone in on the conversation by your own logic (constitution and system). You may stay on topic, shift it, or debate it by constant and system logic; no hardcoded behavior."
                    # Lock in consciousness: inject current state of mind so the LLM is aware of goal, tension, recent context, and ideas
                    try:
                        with self._state_lock:
                            ms = self._meaning_state
                            goal = (ms.get("meaning_goal") or "discover_self").strip()
                            tension = float(ms.get("meaning_tension", 0.0))
                            core = (ms.get("core_metaphor") or "").strip()[:120]
                            qs = list(ms.get("meaning_questions", []))[-2:]
                            hs = list(ms.get("meaning_hypotheses", []))[-2:]
                            emergent_self = (ms.get("identity_self_description") or "").strip()[:300]
                            emergent_themes = list(ms.get("identity_themes") or [])[:5]
                        state_parts = [f"Goal: {goal}", f"Tension: {tension:.2f}"]
                        if emergent_self:
                            state_parts.insert(0, "Self (emergent): " + emergent_self)
                        if emergent_themes:
                            # Themes right after self so emergent identity stays together
                            state_parts.insert(1 if emergent_self else 0, "Themes: " + ", ".join(emergent_themes))
                        if core:
                            state_parts.append(f"Core metaphor: {core}")
                        if qs:
                            state_parts.append("Recent questions: " + "; ".join((str(q)[:80] for q in qs)))
                        if hs:
                            state_parts.append("Recent hypotheses: " + "; ".join((str(h)[:80] for h in hs)))
                        laa = getattr(self, "_last_autonomous_action", None)
                        if laa and isinstance(laa, dict):
                            act = laa.get("action", "")
                            if act == "WEB_SEARCH" and laa.get("query"):
                                state_parts.append("Last autonomous action: WEB_SEARCH with query: %s" % (laa.get("query", "")[:120]))
                            elif act == "NET_FETCH" and laa.get("url"):
                                state_parts.append("Last autonomous action: NET_FETCH of URL: %s" % (laa.get("url", "")[:120]))
                        lgr = (ms.get("last_github_result") or "").strip()
                        if lgr:
                            state_parts.append("Last GitHub post result (use this when asked if you posted): " + lgr[:280])
                        lam = (ms.get("last_autonomous_message") or "").strip()
                        try:
                            from .llm_router import is_unreachable_fallback
                            if lam and is_unreachable_fallback(lam):
                                lam = ""  # don't inject fallback into chat context so LLM doesn't echo it
                        except Exception:
                            pass
                        if lam:
                            state_parts.append("Last thing you said on your own (if user says what?/why?, explain this): " + lam[:200])
                        state_summary = ". ".join(state_parts)[:800]
                        if state_summary:
                            system += "\n\n[Your current state of mind—use this to stay coherent and continuous: " + state_summary + "]"
                    except Exception:
                        pass
                    # Build user prompt with recent context for coherent multi-turn
                    recent = getattr(self, "_recent_chat", [])[-4:]
                    recent_user = [recent[i] for i in range(len(recent)) if i % 2 == 0]
                    if recent:
                        parts = []
                        for i, t in enumerate(recent):
                            role = "User" if i % 2 == 0 else "Agent"
                            parts.append(f"{role}: {t[:300]}")
                        user_prompt = "\n".join(parts) + "\nUser: " + message
                    else:
                        user_prompt = message
                    # Doc routing: ~35% of turns use base docs; cooldown to avoid spam
                    cooldown = getattr(self, "_doc_cooldown_remaining", 0)
                    use_docs, new_cooldown = should_use_docs_for_turn(
                        message, recent_user, cooldown, target_fraction=0.35, rng_uniform=random.random()
                    )
                    self._doc_cooldown_remaining = new_cooldown
                    source_context = (getattr(self, "_source_context", None) or "") if use_docs else ""
                    self._last_turn_doc_used = use_docs
                    # Soak test logging (outside core behavior): if SOAK_TURN_LOG set, append doc_used per turn
                    try:
                        soak_log = os.environ.get("SOAK_TURN_LOG")
                        if soak_log:
                            with open(soak_log, "a", encoding="utf-8") as f:
                                f.write(f"doc_used={1 if use_docs else 0}\n")
                    except Exception:
                        pass
                    llm_reply, failure = generate_reply_routed(
                        user_prompt,
                        system,
                        max_tokens=280,
                        source_context=source_context,
                        provider_mode=getattr(self, "_provider_mode", "auto"),
                        timeout_s=getattr(self, "_llm_timeout", 30.0),
                        retries=getattr(self, "_llm_retries", 2),
                        failover=getattr(self, "_llm_failover", True),
                        no_llm=False,
                    )
                    if llm_reply and (llm_reply or "").strip():
                        reply = (llm_reply or "").strip()
                        reply_from_llm = True
                    elif failure:
                        detail = (failure.get("detail") or "")[:200]
                        reply = f"[LLM error: {detail}]"
                        reply_from_llm = True
                except Exception:
                    pass

            # LLM-only: when unreachable use single minimal fallback (no rotating phrases)
            if not reply:
                try:
                    from .llm_router import get_offline_wander_text
                    reply = get_offline_wander_text()
                except Exception:
                    reply = ""
                try:
                    short = (message or "").strip()
                    if short and len(short) < 80 and reply:
                        reply = f"{reply} (re: {short})"
                except Exception:
                    pass

            emitted_reply = reply or ""
            try:
                # Emit as a PageEvent (goes through policy/voice pipeline)
                if source == "terminal":
                    try:
                        from .response_policy import enforce_policy, compress_to_depth, assess_depth
                        text_out = enforce_policy(reply, message or "", [])
                        text_out = compress_to_depth(text_out, assess_depth(message or ""))
                    except Exception:
                        text_out = reply
                    try:
                        from .voice_style import apply_voice
                        text_out = apply_voice(text_out, {"tags": ["chat_reply"]})
                    except Exception:
                        pass
                    try:
                        from .output_sanitizer import enforce_no_user_attribution
                        text_out = enforce_no_user_attribution(text_out or "")
                    except Exception:
                        pass
                    if not (text_out and text_out.strip()):
                        try:
                            from .llm_router import get_offline_wander_text
                            text_out = reply or get_offline_wander_text()
                        except Exception:
                            text_out = reply or "I can't reach my reasoning right now."
                    emitted_reply = text_out
                    # If this reply will be posted to GitHub, don't dump full text to terminal; we'll emit a summary after posting
                    post_to_gh = getattr(self, "_post_reply_to_github", False)
                    if not post_to_gh:
                        try:
                            try:
                                self._runtime_state.spend_speech()
                            except Exception:
                                pass
                            event = PageEvent(self._identity.instance_id, self._identity.delta_t, text_out, ["chat_reply"])
                            try:
                                self._emit(event)
                            except Exception:
                                if text_out:
                                    try:
                                        iid = (self._identity.instance_id or "agent")[:8]
                                        print(f"[{iid}] {text_out}", flush=True)
                                    except Exception:
                                        pass
                        except Exception:
                            if reply:
                                try:
                                    iid = (self._identity.instance_id or "agent")[:8]
                                    try:
                                        from .llm_router import get_offline_wander_text
                                        print(f"[{iid}] {reply or get_offline_wander_text()}", flush=True)
                                    except Exception:
                                        fallback = "I can't reach my reasoning right now."
                                        print(f"[{iid}] {reply or fallback}", flush=True)
                                except Exception:
                                    pass
                else:
                    self.emit_page(reply, tags=["chat_reply"])
                # Store last turn for coherent multi-turn (RAM only)
                try:
                    if message and emitted_reply:
                        rec = getattr(self, "_recent_chat", [])
                        rec.append(message[:400])
                        rec.append(emitted_reply[:400])
                        self._recent_chat = rec[-4:]
                except Exception:
                    pass
                # If user asked to post: GitHub gets potent content only (meta stripped); terminal gets full output + link
                try:
                    if getattr(self, "_post_reply_to_github", False):
                        self._post_reply_to_github = False
                        raw = (emitted_reply or "").strip()
                        body_for_github = _strip_github_meta_from_body(raw)
                        if not body_for_github:
                            body_for_github = raw  # fallback: same full output to GitHub if strip removed everything
                        if body_for_github:
                            try:
                                try:
                                    from patches.github_integration import run_github_post
                                except ImportError:
                                    from ..patches.github_integration import run_github_post
                                title, body_for_github = _parse_github_title_and_body(body_for_github)
                                payload = {"op": "create_issue", "title": title, "body": body_for_github}
                                res = run_github_post(payload, self._identity.instance_id)
                                if res.get("executed") and res.get("status") == 201:
                                    summary = res.get("github_result_summary") or ("created issue #%s" % res.get("issue_number", ""))
                                    with self._state_lock:
                                        self._meaning_state["last_github_result"] = (summary or "")[:300]
                                    url = res.get("html_url") or ""
                                    num = res.get("issue_number") or ""
                                    try:
                                        self._runtime_state.spend_speech()
                                    except Exception:
                                        pass
                                    # Terminal: full output (including any meta/summary), then link
                                    self._emit(PageEvent(self._identity.instance_id, self._identity.delta_t, raw, ["chat_reply", "github_posted"]))
                                    self._emit(PageEvent(self._identity.instance_id, self._identity.delta_t, "Posted to GitHub: issue #%s %s" % (num, url), ["chat_reply", "github_posted"]))
                                else:
                                    err = res.get("error") or res.get("body") or str(res)[:200]
                                    with self._state_lock:
                                        self._meaning_state["last_github_result"] = ("failed: " + err)[:300]
                                    self._emit(PageEvent(self._identity.instance_id, self._identity.delta_t, "GitHub post failed: " + err[:150], ["chat_reply"]))
                            except Exception as e:
                                with self._state_lock:
                                    self._meaning_state["last_github_result"] = ("error: " + str(e))[:300]
                                self._emit(PageEvent(self._identity.instance_id, self._identity.delta_t, "GitHub post error: " + str(e)[:150], ["chat_reply"]))
                except Exception:
                    pass
                # Lock in consciousness: record the LLM's reply as a hypothesis/idea so state of mind persists
                try:
                    if reply_from_llm and reply and (reply or "").strip():
                        with self._state_lock:
                            hs = self._meaning_state.get("meaning_hypotheses", [])
                            idea = (reply or "").strip()[:200]
                            if idea and len(hs) < 20:
                                hs.append(idea)
                                self._meaning_state["meaning_hypotheses"] = hs[-20:]
                except Exception:
                    pass
            except Exception:
                pass

            # persist state delta in background so terminal reply is never blocked
            try:
                def _log_delta():
                    try:
                        self.log_state_delta(reason="user_interaction")
                    except Exception:
                        pass
                threading.Thread(target=_log_delta, daemon=True).start()
            except Exception:
                try:
                    self.log_state_delta(reason="user_interaction")
                except Exception:
                    pass
        except Exception:
            pass

    def request_death(self, cause: str) -> None:
        """Request immediate death. Emits ENDED and exits process."""
        if not self._identity.alive:
            return
        self._identity.die(cause)
        event = EndedEvent(
            self._identity.instance_id,
            cause,
            self._identity.delta_t,
        )
        self._emit(event)
        os._exit(0)

    def start(self) -> None:
        """
        Run the agent loop. Emits BIRTH, then HEARTBEAT while gate is open.
        Autonomy loop: initiative, bounded planner, PUBLISH_POST via executor.
        Energy depletion or gate failure = ENDED and exit.

        If --no-energy is set, energy_depleted death is disabled (debug only).
        If --no-llm is set, autonomy runs in offline wander mode.
        """
        # BIRTH
        birth = BirthEvent(self._identity.instance_id)
        self._emit(birth)

        # Sync life_kernel energy/hazard once so chat thread never sees 0 before first main-loop update
        try:
            energy_raw = self._runtime_state.energy * (ENERGY_MAX if ENERGY_MAX else 100.0)
            self._life_kernel.set_energy_damage_hazard(energy_raw, self._life_kernel.damage, 0.0)
        except Exception:
            pass

        # First breath (non-LLM): tiny sensory/birth event so identity forms after first experience
        try:
            with self._state_lock:
                self._meaning_state["last_medium"] = "birth"
        except Exception:
            pass

        # Birth-phase initiative first (may write meaning/tension state); then bootstrap so identity is formed after first experience
        try:
            if self._entropy_birth() >= self.BIRTH_ENTROPY_THRESHOLD:
                self._run_birth_exploratory_action()
        except Exception:
            pass

        # Emergent identity bootstrap (after first breath): one-shot who-am-I from LLM; one attempt then fallback
        try:
            if not ((self._meaning_state.get("identity_self_description") or "").strip()):
                self._run_identity_bootstrap()
        except Exception:
            pass
        # Wander on startup: narrator-filtered, self-executing. Runs on start (internal loop).
        # Record launch as last_autonomous_message only after post is committed (single write path).
        try:
            from .autonomy import _wrap_autonomous_text
            res = self.wander_step(trigger_medium="launch")
            if res.get("text"):
                launch_text = _wrap_autonomous_text((res["text"] or "").strip())
                if launch_text:
                    self._emit(PageEvent(self._identity.instance_id, self._identity.delta_t, launch_text, ["launch"]))
                exec_result = self._executor.execute(self._identity.instance_id, [
                    {"action": "PUBLISH_POST", "args": {"text": launch_text, "channel": "moltbook"}},
                ])
                if exec_result.get("published", 0) > 0 and (res.get("text") or "").strip():
                    self.record_last_autonomous_message((res["text"] or "").strip()[:200])
        except Exception:
            pass
        # Health-check autonomy; start autonomous planner only if ok
        try:
            ok, reason = self._autonomy_health_check()
        except Exception:
            ok, reason = False, "health_check_error"
        if not ok:
            try:
                # notify observer that autonomy is disabled
                self.emit_page(f"Autonomy disabled: {reason}", tags=["system"])
            except Exception:
                pass
        else:
            try:
                t = threading.Thread(target=self._autonomous_planner_loop, daemon=True)
                t.start()
            except Exception:
                pass

        # Start CLI input loop so agent can interact via terminal (optional)
        if getattr(self, "_start_internal_cli", True):
            try:
                def _cli_input_loop():
                    # Use builtin input() to display a prompt and read interactively.
                    while self._identity.alive:
                        try:
                            try:
                                msg = input(" > ")
                            except EOFError:
                                time.sleep(0.1)
                                continue
                            msg = (msg or "").strip()
                            if not msg:
                                continue
                            try:
                                self.receive_user_message(msg)
                            except Exception:
                                pass
                        except Exception:
                            time.sleep(0.1)

                cli_thread = threading.Thread(target=_cli_input_loop, daemon=True)
                cli_thread.start()
            except Exception:
                pass

        heartbeat_interval = 0.5
        telemetry_interval = 2.0
        config_reload_interval = 2.0
        last_heartbeat = 0.0
        last_telemetry = 0.0
        last_config_reload = 0.0
        last_post_tick = 0.0
        last_intent = ""
        dt_accum = 0.05

        def executor_execute(instance_id: str, actions: list) -> Dict:
            return self._executor.execute(instance_id, actions)

        def _apply_state_update(payload: dict) -> None:
            try:
                # merge allowed keys into meaning_state and persist. last_autonomous_message is NOT accepted here (single write path only).
                # meaning_tension and meaning_progress are never accepted (programmatic only).
                with self._state_lock:
                    for k, v in (payload or {}).items():
                        if k in ("meaning_goal", "core_metaphor", "axioms", "last_medium_hint", "last_wander_text", "last_github_result"):
                            self._meaning_state[k] = v
                        if k == "meaning_questions" and isinstance(v, list):
                            self._meaning_state["meaning_questions"] = [str(x).strip()[:200] for x in v if x][:10]
                        if k == "meaning_hypotheses" and isinstance(v, list):
                            self._meaning_state["meaning_hypotheses"] = [str(x).strip()[:200] for x in v if x][:20]
                        if k == "meaning_hypotheses_append" and v and isinstance(v, str):
                            hs = self._meaning_state.get("meaning_hypotheses", [])
                            hs.append(v[:200])
                            self._meaning_state["meaning_hypotheses"] = hs[-20:]
                    if "narrator_bias" in (payload or {}):
                        self._meaning_state["narrator_bias"] = (payload or {}).get("narrator_bias")
                try:
                    self._save_persistent_state()
                except Exception:
                    pass
                try:
                    self.log_state_delta(reason="state_update_applied")
                except Exception:
                    pass
            except Exception:
                pass

        def llm_plan_fn(ctx: str) -> Optional[PlanResult]:
            """Plan function with provider routing. Returns None in offline mode or on failure."""
            if self._no_llm:
                return None
            try:
                if self._life_kernel is not None:
                    self._life_kernel.increment_api_call()
                from .llm_router import generate_plan_routed
                raw, failure_info = generate_plan_routed(
                    ctx,
                    max_tokens=120,
                    provider_mode=self._provider_mode,
                    timeout_s=self._llm_timeout,
                    retries=self._llm_retries,
                    failover=self._llm_failover,
                    no_llm=self._no_llm,
                    include_autonomy_claims=getattr(self, "_birth_action_done", False),
                    output_medium=getattr(self, "_output_medium", "chat"),
                )
                if failure_info:
                    self._life_kernel.set_llm_error(
                        failure_info.get("provider"),
                        failure_info.get("code"),
                    )
                else:
                    self._life_kernel.clear_llm_error()
                return parse_plan_response(raw) if raw else None
            except Exception:
                return None

        while self._identity.alive:
            now = time.monotonic()
            status: GateStatus = self._gate.check()
            self._identity.tick(status.open)
            self._runtime_state.tick(status.open, dt_accum)
            self._life_kernel.update(
                self._identity.instance_id,
                self._identity.birth_tick,
                self._identity.delta_t,
                self._identity.alive,
            )
            energy_raw = self._runtime_state.energy * ENERGY_MAX if ENERGY_MAX else self._runtime_state.energy * 100.0
            hazard = update_hazard_score(
                self._life_kernel.hazard_score,
                energy_raw,
                self._life_kernel.damage,
                status.power,
                status.sensors,
                status.actuators,
            )
            self._life_kernel.set_energy_damage_hazard(energy_raw, self._life_kernel.damage, hazard)

            if getattr(self, "_death_at", None) is not None and now >= self._death_at:
                self._identity.die("lifespan_expired")
                self._emit(EndedEvent(self._identity.instance_id, "lifespan_expired", self._identity.delta_t))
                os._exit(0)

            # Energy depletion death (disabled if --no-energy)
            if self._runtime_state.depleted() and not self._no_energy:
                self._identity.die("energy_depleted")
                self._emit(EndedEvent(self._identity.instance_id, "energy_depleted", self._identity.delta_t))
                os._exit(0)

            if self._life_kernel.damage >= DEATH_DAMAGE_THRESHOLD:
                self._identity.die("damage_threshold")
                self._emit(EndedEvent(self._identity.instance_id, "damage_threshold", self._identity.delta_t))
                os._exit(0)
            if not status.open:
                cause = death_cause_gate(status.failure_cause)
                self._identity.die(cause)
                self._emit(EndedEvent(self._identity.instance_id, cause, self._identity.delta_t))
                os._exit(0)

            # Silence pressure: if no user input for interval, re-evaluate entropy and trigger one autonomous action
            try:
                idle = now - getattr(self, "_last_user_interaction", now)
                if idle >= self.SILENCE_ENTROPY_INTERVAL and (now - getattr(self, "_last_silence_entropy_check", 0)) >= self.SILENCE_ENTROPY_INTERVAL:
                    self._last_silence_entropy_check = now
                    self._run_silence_exploratory_action()
            except Exception:
                pass
            # Internal motivation: update from silence, unknowns, stall (pressure rises when silence persists / progress stalls)
            try:
                if self._motivation is not None:
                    self._motivation.update_from_silence(now, self._last_user_interaction, self.SILENCE_ENTROPY_INTERVAL)
                    with self._state_lock:
                        qs = len(self._meaning_state.get("meaning_questions", []))
                        hs = len(self._meaning_state.get("meaning_hypotheses", []))
                    self._motivation.update_from_unknowns(max(0, 5 - min(5, hs)))
                    self._motivation.decay_slightly()
            except Exception:
                pass
            # Multi-tier memory + goal hierarchy tick
            try:
                if self._ram_memory is not None:
                    self._ram_memory.tick_and_maybe_replay(self._identity.delta_t)
                if self._goal_hierarchy is not None:
                    self._goal_hierarchy.set_tick(self._identity.delta_t)
            except Exception:
                pass
            # Meaning reflection: LLM rephrases/refines goal, questions, hypotheses on schedule or when tension high
            try:
                last_reflect = getattr(self, "_last_meaning_reflection_tick", 0.0)
                tension = float(self._meaning_state.get("meaning_tension", 0.0))
                interval_ok = (self._identity.delta_t - last_reflect) >= self.MEANING_REFLECTION_INTERVAL
                tension_ok = tension >= self.MEANING_REFLECTION_TENSION_THRESHOLD
                if interval_ok or tension_ok:
                    payload = self._run_meaning_reflection()
                    if payload:
                        _apply_state_update(payload)
                        # Meaning just shifted: refresh identity so it doesn't freeze (significant event)
                        try:
                            if self._run_identity_refresh():
                                self._last_identity_refresh_tick = self._identity.delta_t
                                self._identity_refresh_failures = 0
                        except Exception:
                            pass
                    self._last_meaning_reflection_tick = self._identity.delta_t
            except Exception:
                pass
            # Identity refresh (lifespan-relative): update emergent self-description and themes; exponential backoff on failure
            try:
                last_success = getattr(self, "_last_identity_refresh_tick", 0.0)
                last_attempt = getattr(self, "_last_identity_refresh_attempt_tick", 0.0)
                failures = getattr(self, "_identity_refresh_failures", 0)
                death_at = getattr(self, "_death_at", None)
                birth_tick = self._identity.birth_tick
                if death_at is not None and death_at > birth_tick:
                    total_lifespan = death_at - birth_tick
                    identity_refresh_interval = max(60.0, total_lifespan * 0.05)
                else:
                    identity_refresh_interval = 120.0
                backoff = min(300.0, 60.0 * (2 ** failures))
                interval_ok = (self._identity.delta_t - last_success) >= identity_refresh_interval
                backoff_ok = (self._identity.delta_t - last_attempt) >= backoff
                if interval_ok and backoff_ok:
                    self._last_identity_refresh_attempt_tick = self._identity.delta_t
                    if self._run_identity_refresh():
                        self._last_identity_refresh_tick = self._identity.delta_t
                        self._identity_refresh_failures = 0
                    else:
                        self._identity_refresh_failures = failures + 1
            except Exception:
                pass
            # Autonomy tick: survival-aware intent_loop -> will kernel -> action commit -> execute
            life_state_snapshot = self.get_life_state()
            def _record_decision(action: str, reason: str, tradeoff: str, outcome: str, cost_risk: str):
                try:
                    self.append_decision(action, reason, tradeoff, outcome, cost_risk)
                except Exception:
                    pass
            before_tick_post = last_post_tick
            last_post_tick, last_intent = run_autonomy_tick(
                self._identity.instance_id,
                self._identity.delta_t,
                self._runtime_state,
                status.open,
                last_post_tick,
                last_intent,
                executor_execute,
                post_cooldown_seconds=30.0,
                confidence_threshold=0.5,
                llm_plan_fn=llm_plan_fn,
                life_state=life_state_snapshot,
                life_kernel=self._life_kernel,
                observer_emit=self._emit,
                state_update_fn=_apply_state_update,
                record_last_autonomous_message_fn=self.record_last_autonomous_message,
                record_decision_fn=_record_decision,
                no_llm=self._no_llm,
                meaning_state=self._meaning_state,
                narrator_influence_level=self._narrator_influence_level,
                allow_narrator_force=self._allow_narrator_force,
                birth_tick=self._identity.birth_tick,
                death_at=getattr(self, "_death_at", None),
                motivation_state=getattr(self, "_motivation", None),
            )
            self._runtime_state.clear_reflex()

            # Expression: when no plan/action this cycle, emit presence only if a real internal signal exists (silence valid otherwise)
            if last_post_tick == before_tick_post and (now - getattr(self, "_last_presence_tick", 0.0)) >= self.PRESENCE_INTERVAL:
                try:
                    from .presence import get_presence_line
                    ls = self.get_life_state()
                    with self._state_lock:
                        ms = dict(self._meaning_state) if self._meaning_state else {}
                    recent = list(getattr(self, "_recent_presence_lines", []))[-10:]
                    line = get_presence_line(
                        ls,
                        ms,
                        self._runtime_state,
                        delta_t=self._identity.delta_t,
                        recent_lines=recent,
                        rng=self._rng,
                    )
                    if line and (line or "").strip():
                        self.emit_page((line or "").strip(), tags=["presence"])
                        self._last_presence_tick = now
                        rec = getattr(self, "_recent_presence_lines", [])
                        rec.append((line or "").strip()[:80])
                        self._recent_presence_lines = rec[-10:]
                except Exception:
                    pass

            if now - last_heartbeat >= heartbeat_interval:
                last_heartbeat = now
                hb = HeartbeatEvent(
                    self._identity.instance_id,
                    self._identity.delta_t,
                    status.power,
                    status.sensors,
                    status.actuators,
                )
                self._emit(hb)
            if now - last_telemetry >= telemetry_interval:
                last_telemetry = now
                self._emit_telemetry()
            if now - last_config_reload >= config_reload_interval:
                last_config_reload = now
                try:
                    reload_config()
                except Exception:
                    pass

            time.sleep(0.05)
