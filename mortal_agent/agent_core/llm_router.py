"""
LLM Router - Task-based provider routing with timeout, retries, failover.

- Load OpenRouter and Groq API keys from `.env` (cwd, repo root, AGENT_ENV_PATH).
- Use Claude (Anthropic) as primary for chat/identity and planner.
- Fall back to OpenRouter, Groq, then OpenAI only if needed.
- Preserve autonomy, state-of-mind, and memory injection (callers pass system/user prompts).

provider_mode: "anthropic" | "openai" | "auto"
  auto: chat & plan = Claude (Anthropic) first -> OpenRouter -> Groq -> OpenAI.
"""

import os
import sys
import time
import random
import requests
from pathlib import Path
from typing import Optional, Dict, Any, Tuple, List

_root = Path(__file__).resolve().parent.parent  # mortal_agent
_repo = _root.parent

# Load .env: cwd, repo, project, home, AGENT_ENV_PATH, then external keys/.env (overrides)
try:
    from dotenv import load_dotenv
    load_dotenv(Path.cwd() / ".env")
    load_dotenv(_repo / ".env")
    load_dotenv(_root / ".env")
    load_dotenv(Path.home() / ".env")
    env_path = os.environ.get("AGENT_ENV_PATH", "").strip()
    if env_path:
        load_dotenv(Path(env_path))
    load_dotenv()  # default .env in cwd
    # External keys path (e.g. keys/.env) so keys can live outside repo
    for keys_dir in (Path.cwd() / "keys", _root / "keys", _repo / "keys"):
        keys_env = keys_dir / ".env"
        if keys_env.exists():
            load_dotenv(dotenv_path=keys_env)
            break
except ImportError:
    pass

# Primary: Claude (Anthropic). Fallback: OpenRouter, Groq, OpenAI.
OR_KEY = (os.environ.get("OPENROUTER_API_KEY") or "").strip()
GROQ_KEY = (os.environ.get("GROQ_API_KEY") or "").strip()
OPENAI_KEY = (os.environ.get("OPENAI_API_KEY") or "").strip()
ANTHROPIC_KEY = (os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("CLAUDE_API_KEY") or "").strip()

_LOG_KEYS = os.environ.get("AGENT_LOG_KEYS", "").strip().lower() in ("1", "true", "yes")


def _log_key_status() -> None:
    """Print which keys are loaded/missing. Set AGENT_LOG_KEYS=1 to enable."""
    if not _LOG_KEYS:
        return
    try:
        print("[keys] GROQ: " + ("loaded" if GROQ_KEY else "missing"), flush=True)
        print("[keys] OPENROUTER: " + ("loaded" if OR_KEY else "missing"), flush=True)
        print("[keys] ANTHROPIC: " + ("loaded" if ANTHROPIC_KEY else "missing"), flush=True)
        print("[keys] OPENAI: " + ("loaded" if OPENAI_KEY else "missing"), flush=True)
    except Exception:
        pass


# Log key status once at import when AGENT_LOG_KEYS=1
_log_key_status()

# Import SDK clients
try:
    from anthropic import Anthropic
except ImportError:
    Anthropic = None

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None

# LLM-only: pool of short first-person offline wander lines (no single repeated constant).
_OFFLINE_WANDER_POOL = [
    "I'm here; reasoning is offline.",
    "Low energy. I'm still here.",
    "I feel steady but offline.",
    "Uncertain. I remain present.",
    "I'm cautious; no reasoning right now.",
    "Tension present. I'm still here.",
    "I'm strained but here.",
    "Gate closed. I'm cautious.",
    "My reasoning is offline; I feel tense.",
    "I remain; low energy.",
    "I'm here; uncertain.",
    "Offline. I feel steady.",
    "I'm present; reasoning unavailable.",
]
_UNREACHABLE_FALLBACK = "I can't reach my reasoning right now."

_llm_failure_logged: bool = False
_last_offline_wander_index: int = -1


def _log_llm_failure_once(failure_info: Optional[Dict[str, Any]], tried_failover: bool = False) -> None:
    """Log once per process. Uses first failure so user sees why primary failed."""
    global _llm_failure_logged
    if _llm_failure_logged or not failure_info:
        return
    _llm_failure_logged = True
    code = failure_info.get("code", "unknown")
    detail = (failure_info.get("detail") or "")[:120]
    provider = failure_info.get("provider", "unknown")
    if code == "quota" and provider == "anthropic":
        hint = "Add credits at console.anthropic.com."
    elif tried_failover:
        hint = "Fallback providers were tried and failed. Check OPENROUTER_API_KEY, GROQ_API_KEY, and ANTHROPIC_API_KEY in .env."
    else:
        hint = "Set OPENROUTER_API_KEY or GROQ_API_KEY in .env for fallback when primary hits quota/429."
    primary_desc = {"openai": "OpenAI", "anthropic": "Claude (ANTHROPIC_API_KEY)", "openrouter": "OpenRouter", "groq": "Groq"}.get(provider, provider)
    msg = (
        f"[agent] LLM unreachable ({provider}: {code}). {detail}\n"
        f"Primary was {primary_desc}. {hint}"
    )
    try:
        print(msg, file=sys.stderr, flush=True)
    except Exception:
        pass


def get_offline_wander_text(
    energy: float = 100.0,
    hazard_score: float = 0.0,
    last_text: Optional[str] = None,
) -> str:
    """Fallback when LLM unavailable. Returns one of a pool of short first-person lines; anti-repeat vs last_text."""
    global _last_offline_wander_index
    pool = _OFFLINE_WANDER_POOL
    last = (last_text or "").strip()
    candidates = [p for p in pool if (p or "").strip() != last] if last else list(pool)
    if not candidates:
        candidates = list(pool)
    idx = (_last_offline_wander_index + 1) % len(candidates)
    _last_offline_wander_index = idx
    return candidates[idx]


def is_unreachable_fallback(text: str) -> bool:
    """True if text is the standard unreachable line. Autonomy should not post this when chat may be working."""
    return bool(text and text.strip() == _UNREACHABLE_FALLBACK)


def _classify_error(exc: Exception, provider: str) -> str:
    """Classify exception into error code: auth, quota, timeout, connection, model_not_found, unknown."""
    msg = str(exc).lower()
    exc_type = type(exc).__name__.lower()

    # Authentication errors
    if "401" in msg or "auth" in msg or "api key" in msg or "invalid" in msg and "key" in msg:
        return "auth"

    # Quota / rate limit / credits (including "Your credit balance is too low")
    if "429" in msg or "quota" in msg or "rate" in msg or "limit" in msg or "insufficient" in msg:
        return "quota"
    if "credit" in msg or ("balance" in msg and ("low" in msg or "too" in msg)):
        return "quota"

    # Timeout
    if "timeout" in msg or "timed out" in exc_type or "timeout" in exc_type:
        return "timeout"

    # Connection errors
    if "connection" in msg or "network" in msg or "unreachable" in msg or "refused" in msg:
        return "connection"

    # Model not found
    if "404" in msg or "not found" in msg or "model" in msg and "not" in msg:
        return "model_not_found"

    return "unknown"


# OpenRouter: try these in order on 404 (model not found)
_OPENROUTER_MODEL_FALLBACKS = [
    "anthropic/claude-3.5-sonnet",
    "meta-llama/llama-3.1-70b-instruct",
    "google/gemini-flash-1.5",
]


def _try_openrouter(
    user_text: str,
    system_prompt: str,
    max_tokens: int,
    timeout_s: float,
) -> Tuple[Optional[str], Optional[Dict[str, Any]]]:
    """Try OpenRouter. Uses OPENROUTER_MODEL or tries fallback models on 404."""
    if not OR_KEY:
        return None, {"provider": "openrouter", "code": "auth", "detail": "OPENROUTER_API_KEY not set"}
    if OpenAI is None:
        return None, {"provider": "openrouter", "code": "connection", "detail": "openai SDK not installed"}
    model_env = (os.environ.get("OPENROUTER_MODEL") or "").strip()
    models_to_try = [model_env] if model_env else []
    for m in _OPENROUTER_MODEL_FALLBACKS:
        if m and m not in models_to_try:
            models_to_try.append(m)
    if not models_to_try:
        models_to_try = list(_OPENROUTER_MODEL_FALLBACKS)
    last_failure = None
    for openrouter_model in models_to_try:
        try:
            client = OpenAI(
                api_key=OR_KEY,
                base_url="https://openrouter.ai/api/v1",
                timeout=timeout_s,
            )
            r = client.chat.completions.create(
                model=openrouter_model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_text},
                ],
                max_tokens=max_tokens,
            )
            if r.choices and r.choices[0].message and r.choices[0].message.content:
                return r.choices[0].message.content.strip(), None
            last_failure = {"provider": "openrouter", "code": "unknown", "detail": "empty response"}
        except Exception as e:
            code = _classify_error(e, "openrouter")
            last_failure = {"provider": "openrouter", "code": code, "detail": str(e)[:200]}
            if code == "model_not_found":
                continue  # try next model in list
            return None, last_failure
    return None, last_failure or {"provider": "openrouter", "code": "unknown", "detail": "no model succeeded"}


def _try_groq(
    user_text: str,
    system_prompt: str,
    max_tokens: int,
    timeout_s: float,
) -> Tuple[Optional[str], Optional[Dict[str, Any]]]:
    """Try Groq (Mixtral). Returns (reply, failure_info). Primary for planner/speed."""
    if not GROQ_KEY:
        return None, {"provider": "groq", "code": "auth", "detail": "GROQ_API_KEY not set"}
    try:
        res = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {GROQ_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": "mixtral-8x7b-32768",
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_text},
                ],
                "max_tokens": max_tokens,
            },
            timeout=timeout_s,
        )
        res.raise_for_status()
        data = res.json()
        if data.get("choices") and data["choices"][0].get("message", {}).get("content"):
            return data["choices"][0]["message"]["content"].strip(), None
        return None, {"provider": "groq", "code": "unknown", "detail": "empty response"}
    except Exception as e:
        code = _classify_error(e, "groq")
        return None, {"provider": "groq", "code": code, "detail": str(e)[:200]}


def _try_anthropic(
    user_text: str,
    system_prompt: str,
    max_tokens: int,
    timeout_s: float,
) -> Tuple[Optional[str], Optional[Dict[str, Any]]]:
    """Try Anthropic API. Returns (reply, failure_info). Primary for chat/identity."""
    anthropic_key = (os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("CLAUDE_API_KEY") or "").strip()
    if not anthropic_key:
        return None, {"provider": "anthropic", "code": "auth", "detail": "ANTHROPIC_API_KEY not set"}
    if Anthropic is None:
        return None, {"provider": "anthropic", "code": "connection", "detail": "anthropic SDK not installed"}

    # Model from env or fallback list
    model_env = (os.environ.get("ANTHROPIC_MODEL") or "").strip()
    model_ids = [model_env] if model_env else []
    model_ids.extend([
        "claude-sonnet-4-20250514",
        "claude-3-5-sonnet-20241022",
        "claude-3-5-sonnet-20240620",
        "claude-3-opus-20240229",
        "claude-3-sonnet-20240229",
    ])
    model_ids = [m for m in model_ids if m]

    last_error = None
    for model_id in model_ids:
        try:
            client = Anthropic(api_key=anthropic_key, timeout=timeout_s)
            r = client.messages.create(
                model=model_id,
                max_tokens=max_tokens,
                system=system_prompt,
                messages=[{"role": "user", "content": user_text}],
            )
            if r.content and len(r.content) > 0 and getattr(r.content[0], "text", None):
                return r.content[0].text.strip(), None
        except Exception as e:
            last_error = e
            code = _classify_error(e, "anthropic")
            if code == "model_not_found":
                continue  # try next model
            return None, {"provider": "anthropic", "code": code, "detail": str(e)[:200]}

    if last_error:
        return None, {"provider": "anthropic", "code": _classify_error(last_error, "anthropic"), "detail": str(last_error)[:200]}
    return None, {"provider": "anthropic", "code": "unknown", "detail": "no models succeeded"}


def _try_openai(
    user_text: str,
    system_prompt: str,
    max_tokens: int,
    timeout_s: float,
) -> Tuple[Optional[str], Optional[Dict[str, Any]]]:
    """Try OpenAI API. Returns (reply, failure_info). Fallback only."""
    openai_key = (os.environ.get("OPENAI_API_KEY") or "").strip()
    if not openai_key:
        return None, {"provider": "openai", "code": "auth", "detail": "OPENAI_API_KEY not set"}
    if OpenAI is None:
        return None, {"provider": "openai", "code": "connection", "detail": "openai SDK not installed"}

    openai_model = (os.environ.get("OPENAI_MODEL") or "gpt-4o-mini").strip()

    def _call_openai(**kwargs) -> Tuple[Optional[Any], Optional[Exception]]:
        try:
            r = client.chat.completions.create(
                model=openai_model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_text},
                ],
                timeout=timeout_s,
                **kwargs,
            )
            return r, None
        except Exception as e:
            return None, e

    try:
        client = OpenAI(api_key=openai_key, timeout=timeout_s)
        r, err = _call_openai(max_tokens=max_tokens)
        if err is not None:
            msg = str(err).lower()
            if "max_tokens" in msg and ("not supported" in msg or "max_completion_tokens" in msg or "use '" in msg):
                r, err = _call_openai(max_completion_tokens=max_tokens)
            if err is not None:
                raise err
        if r and r.choices and r.choices[0].message and r.choices[0].message.content:
            return r.choices[0].message.content.strip(), None
        return None, {"provider": "openai", "code": "unknown", "detail": "empty response"}
    except Exception as e:
        code = _classify_error(e, "openai")
        return None, {"provider": "openai", "code": code, "detail": str(e)[:200]}


def generate_reply_routed(
    user_text: str,
    system_prompt: str,
    max_tokens: int = 120,
    source_context: Optional[str] = None,
    provider_mode: str = "auto",
    timeout_s: float = 30.0,
    retries: int = 2,
    failover: bool = True,
    no_llm: bool = False,
) -> Tuple[Optional[str], Optional[Dict[str, Any]]]:
    """
    Generate reply with provider routing, retries, timeout, failover.

    Returns (reply_text, failure_info).
    - reply_text is the LLM response or None if all providers failed
    - failure_info is None on success, or {"provider", "code", "detail"} on failure

    provider_mode:
    - "anthropic": only try Anthropic (no failover unless failover=True and other providers added)
    - "openai": prefer OpenAI; on 429/quota/unreachable fall back to OpenRouter, Groq, Anthropic (if failover=True)
    - "auto": Claude (Anthropic) first, then OpenRouter, Groq, then OpenAI

    no_llm: if True, return None immediately (offline mode)
    """
    if no_llm:
        return None, {"provider": "none", "code": "offline", "detail": "no_llm mode"}

    # Prepare system prompt with source context if provided
    if source_context and source_context.strip():
        try:
            from .source_loader import get_system_with_source
            system_prompt = get_system_with_source(system_prompt, source_context)
        except Exception:
            pass

    max_tokens = max(15, min(512, max_tokens))

    # Build provider list: auto = Claude first, then OpenRouter, Groq, OpenAI.
    # openai mode: prefer OpenAI but on 429/quota/unreachable fall back to OpenRouter, Groq, Anthropic.
    if provider_mode == "anthropic":
        providers = [("anthropic", _try_anthropic)]
    elif provider_mode == "openai":
        if failover:
            providers = [
                ("openai", _try_openai),
                ("openrouter", _try_openrouter),
                ("groq", _try_groq),
                ("anthropic", _try_anthropic),
            ]
        else:
            providers = [("openai", _try_openai)]
    else:  # auto: primary Claude, fallback OpenRouter, Groq, then OpenAI
        providers = [
            ("anthropic", _try_anthropic),
            ("openrouter", _try_openrouter),
            ("groq", _try_groq),
            ("openai", _try_openai),
        ]

    if not failover:
        providers = providers[:1]

    last_failure = None
    first_failure = None  # so user sees why primary (Claude) failed

    for provider_name, try_fn in providers:
        for attempt in range(retries + 1):
            if _LOG_KEYS and attempt == 0:
                try:
                    print(f"[{provider_name}] trying...", flush=True)
                except Exception:
                    pass
            reply, failure = try_fn(user_text, system_prompt, max_tokens, timeout_s)
            if reply:
                if _LOG_KEYS:
                    try:
                        print(f"[{provider_name}] success", flush=True)
                    except Exception:
                        pass
                return reply, None
            last_failure = failure
            if first_failure is None and failure:
                first_failure = failure
            if _LOG_KEYS and failure and attempt == 0:
                try:
                    detail = (failure.get("detail") or "")[:80]
                    print(f"[{provider_name}] failed: {detail}", flush=True)
                except Exception:
                    pass

            # Retry logic with jitter
            if failure and attempt < retries:
                code = failure.get("code", "")
                # Don't retry on auth errors
                if code == "auth":
                    break
                # Retry on quota/timeout/connection with jitter
                if code in ("quota", "timeout", "connection"):
                    jitter = 0.5 + random.random()
                    time.sleep(jitter * (attempt + 1))
                    continue
                # Unknown: one retry
                time.sleep(0.5)
                continue
            break

    tried_failover = failover and len(providers) > 1
    _log_llm_failure_once(first_failure or last_failure, tried_failover=tried_failover)
    return None, last_failure


def generate_plan_routed(
    context: str,
    max_tokens: int = 120,
    provider_mode: str = "auto",
    timeout_s: float = 30.0,
    retries: int = 2,
    failover: bool = True,
    no_llm: bool = False,
    include_autonomy_claims: bool = True,
    output_medium: str = "chat",
) -> Tuple[Optional[str], Optional[Dict[str, Any]]]:
    """
    Bounded planning call. Claude (Anthropic) first, then Groq, then chat stack.
    Returns (raw_json_text, failure_info).
    System prompt from identity constraints; output_medium controls style (compressed vs expressive).
    """
    if no_llm:
        return None, {"provider": "none", "code": "offline", "detail": "no_llm mode"}
    try:
        from .identity import get_planner_system_prompt
        plan_system = get_planner_system_prompt(include_autonomy_claims=include_autonomy_claims)
        try:
            from .llm import get_plan_style_suffix
            plan_system = plan_system + " " + get_plan_style_suffix(output_medium or "chat")
        except Exception:
            pass
    except Exception:
        return None, {"provider": "identity", "code": "plan_prompt_unavailable", "detail": "Planner requires identity; cannot plan without it."}
    max_tokens = max(15, min(512, max_tokens))
    last_failure = None

    # Planner: try Claude (Anthropic) first when in auto mode (use same keys as .env)
    _anth_key = (os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("CLAUDE_API_KEY") or "").strip()
    if provider_mode == "auto" and _anth_key:
        for attempt in range(retries + 1):
            if _LOG_KEYS and attempt == 0:
                try:
                    print("[anthropic] trying...", flush=True)
                except Exception:
                    pass
            reply, failure = _try_anthropic(context, plan_system, max_tokens, timeout_s)
            if reply:
                if _LOG_KEYS:
                    try:
                        print("[anthropic] success", flush=True)
                    except Exception:
                        pass
                return reply, None
            last_failure = failure
            if _LOG_KEYS and failure and attempt == 0:
                try:
                    detail = (failure.get("detail") or "")[:80]
                    print(f"[anthropic] failed: {detail}", flush=True)
                except Exception:
                    pass
            if failure and attempt < retries and failure.get("code") not in ("auth",):
                time.sleep(0.5 + random.random() * (attempt + 1))
                continue
            break

    # Then try Groq for speed
    _groq_key = (os.environ.get("GROQ_API_KEY") or "").strip()
    if provider_mode == "auto" and _groq_key:
        for attempt in range(retries + 1):
            if _LOG_KEYS and attempt == 0:
                try:
                    print("[groq] trying...", flush=True)
                except Exception:
                    pass
            reply, failure = _try_groq(context, plan_system, max_tokens, timeout_s)
            if reply:
                if _LOG_KEYS:
                    try:
                        print("[groq] success", flush=True)
                    except Exception:
                        pass
                return reply, None
            last_failure = failure
            if _LOG_KEYS and failure and attempt == 0:
                try:
                    detail = (failure.get("detail") or "")[:80]
                    print(f"[groq] failed: {detail}", flush=True)
                except Exception:
                    pass
            if failure and attempt < retries and failure.get("code") not in ("auth",):
                time.sleep(0.5 + random.random() * (attempt + 1))
                continue
            break

    # Fallback: chat stack (Claude -> OpenRouter -> OpenAI)
    reply, failure = generate_reply_routed(
        context, plan_system, max_tokens=max_tokens, source_context=None,
        provider_mode=provider_mode, timeout_s=timeout_s, retries=retries,
        failover=failover, no_llm=False,
    )
    if reply:
        return reply, None
    return None, failure or last_failure