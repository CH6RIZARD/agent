"""
LLM Router - Provider routing with timeout, retries, failover.

Supports:
- provider_mode: "anthropic", "openai", "auto"
- Timeout enforcement
- Retries with jitter
- Failover between providers
- Diagnosable error codes (auth, quota, timeout, connection, model_not_found, unknown)

Offline wander: doctrine-driven fallback text when LLM is unavailable.
"""

import os
import sys
import time
import random
from pathlib import Path
from typing import Optional, Dict, Any, Tuple, List

_root = Path(__file__).parent.parent  # mortal_agent
_repo = _root.parent

# Load .env files
try:
    from dotenv import load_dotenv
    load_dotenv(_repo / ".env")
    load_dotenv(_root / ".env")
    load_dotenv(Path.home() / ".env")
    env_path = os.environ.get("AGENT_ENV_PATH", "").strip()
    if env_path:
        load_dotenv(Path(env_path))
    load_dotenv()
except ImportError:
    pass

# Import SDK clients
try:
    from anthropic import Anthropic
except ImportError:
    Anthropic = None

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None

# When LLM unreachable and no docs/state context: minimal fallback only. No hardcoded wander phrases.
# Prefer autonomy/narrator.build_degraded_explanation(meaning_state, source_context, life_state) when available.


def get_offline_wander_text(energy: float = 100.0, hazard_score: float = 0.0) -> str:
    """
    Fallback when LLM unavailable and no meaning_state/source_context passed. One coherent line for conversation.
    """
    return "The model isn't reachable right now. What would you like to do?"


def _classify_error(exc: Exception, provider: str) -> str:
    """Classify exception into error code: auth, quota, timeout, connection, model_not_found, unknown."""
    msg = str(exc).lower()
    exc_type = type(exc).__name__.lower()

    # Authentication errors
    if "401" in msg or "auth" in msg or "api key" in msg or "invalid" in msg and "key" in msg:
        return "auth"

    # Quota / rate limit
    if "429" in msg or "quota" in msg or "rate" in msg or "limit" in msg or "insufficient" in msg:
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


def _try_anthropic(
    user_text: str,
    system_prompt: str,
    max_tokens: int,
    timeout_s: float,
) -> Tuple[Optional[str], Optional[Dict[str, Any]]]:
    """Try Anthropic API. Returns (reply, failure_info)."""
    anthropic_key = (os.environ.get("ANTHROPIC_API_KEY") or "").strip()
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
    """Try OpenAI API. Returns (reply, failure_info)."""
    openai_key = (os.environ.get("OPENAI_API_KEY") or "").strip()
    if not openai_key:
        return None, {"provider": "openai", "code": "auth", "detail": "OPENAI_API_KEY not set"}
    if OpenAI is None:
        return None, {"provider": "openai", "code": "connection", "detail": "openai SDK not installed"}

    openai_model = (os.environ.get("OPENAI_MODEL") or "gpt-4o-mini").strip()

    try:
        client = OpenAI(api_key=openai_key, timeout=timeout_s)
        r = client.chat.completions.create(
            model=openai_model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_text},
            ],
            max_tokens=max_tokens,
        )
        if r.choices and r.choices[0].message and r.choices[0].message.content:
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
    - "anthropic": only try Anthropic
    - "openai": only try OpenAI
    - "auto": try Anthropic first, failover to OpenAI if enabled

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

    # Build provider list based on mode
    if provider_mode == "anthropic":
        providers = [("anthropic", _try_anthropic)]
    elif provider_mode == "openai":
        providers = [("openai", _try_openai)]
    else:  # auto
        providers = [("anthropic", _try_anthropic), ("openai", _try_openai)]

    if not failover:
        providers = providers[:1]

    last_failure = None

    for provider_name, try_fn in providers:
        for attempt in range(retries + 1):
            reply, failure = try_fn(user_text, system_prompt, max_tokens, timeout_s)
            if reply:
                return reply, None
            last_failure = failure

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

    return None, last_failure


def generate_plan_routed(
    context: str,
    max_tokens: int = 120,
    provider_mode: str = "auto",
    timeout_s: float = 30.0,
    retries: int = 2,
    failover: bool = True,
    no_llm: bool = False,
) -> Tuple[Optional[str], Optional[Dict[str, Any]]]:
    """
    Bounded planning call with provider routing.
    Returns (raw_json_text, failure_info).
    System prompt comes from identity constraints only; dilemma and discipline emerge from those, no hardcoded responses.
    """
    try:
        from .identity import get_planner_system_prompt
        plan_system = get_planner_system_prompt()
    except Exception:
        plan_system = (
            "Output exactly one JSON: "
            '{"text": "string or empty", "intent": "string", "confidence": number 0-1, "reasons": ["string"]}. '
            "If nothing to say from context, confidence < 0.5 and empty text."
        )
    return generate_reply_routed(
        context, plan_system, max_tokens=max_tokens, source_context=None,
        provider_mode=provider_mode, timeout_s=timeout_s, retries=retries,
        failover=failover, no_llm=no_llm,
    )
