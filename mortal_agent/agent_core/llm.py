"""
LLM reply generation - ANTHROPIC_API_KEY / OPENAI_API_KEY.
Uses the same API keys as the model you chat with: loads .env from repo root,
mortal_agent root, user home, and optional AGENT_ENV_PATH (exact path to your .env).
"""

import json
import os
import sys
import time
from pathlib import Path
from typing import Optional

_root = Path(__file__).parent.parent  # mortal_agent
_repo = _root.parent
try:
    from dotenv import load_dotenv
    # Same keys as the model that responds to you: try all usual places (later overrides earlier)
    load_dotenv(_repo / ".env")                    # repo root D:\agent\.env
    load_dotenv(_root / ".env")                    # mortal_agent\.env
    load_dotenv(Path.home() / ".env")              # user home
    env_path = os.environ.get("AGENT_ENV_PATH", "").strip()
    if env_path:
        load_dotenv(Path(env_path))
    load_dotenv()                                   # cwd .env (e.g. when run from mortal_agent/)
except ImportError:
    pass

_llm_error_logged = False  # Log unreachable only once per process to avoid spam

try:
    from anthropic import Anthropic
except ImportError:
    Anthropic = None

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None


def _ensure_env_loaded() -> None:
    """Re-load .env so keys are set. Uses AGENT_ENV_PATH, mortal_agent/.env, then cwd."""
    # Prefer python-dotenv when available; otherwise fall back to a simple .env parser
    try:
        from dotenv import load_dotenv
        env_path = os.environ.get("AGENT_ENV_PATH", "").strip()
        if env_path:
            load_dotenv(Path(env_path))
        load_dotenv(_root / ".env")
        load_dotenv()
    except Exception:
        # Try to load key/value pairs from common .env locations even without python-dotenv
        _load_env_file_keys()
    # If OPENAI_API_KEY is still empty, try fixing multi-line keys or next-line keys
    try:
        if not (os.environ.get("OPENAI_API_KEY") or "").strip():
            _try_fix_openai_key_from_env_file()
    except Exception:
        pass


def _load_env_file_keys() -> None:
    """Simple .env loader: read common .env files and set a few env vars if present.
    This provides a one-shot fallback when `python-dotenv` isn't installed.
    """
    try:
        candidates = []
        ep = os.environ.get("AGENT_ENV_PATH", "").strip()
        if ep:
            candidates.append(Path(ep))
        candidates.extend([_root / ".env", _repo / ".env", Path.home() / ".env", Path.cwd() / ".env"])
        seen = set()
        for p in candidates:
            if not p or not p.exists() or not p.is_file():
                continue
            try:
                raw = p.read_text(encoding="utf-8", errors="replace")
            except Exception:
                continue
            for i, line in enumerate(raw.splitlines()):
                s = line.strip()
                if not s or s.startswith("#"):
                    continue
                # key=value lines
                if "=" in s:
                    k, v = s.split("=", 1)
                    k = k.strip()
                    v = v.strip()
                    if k in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "ANTHROPIC_MODEL", "OPENAI_MODEL") and v:
                        # avoid overwriting an existing env var
                        if k not in os.environ or not os.environ.get(k):
                            os.environ[k] = v
                            seen.add(k)
                else:
                    # fallback: a bare API key on its own line
                    if (s.startswith("sk-proj-") or s.startswith("sk-") or s.startswith("sk-ant-")) and len(s) > 20:
                        if "OPENAI_API_KEY" not in os.environ or not os.environ.get("OPENAI_API_KEY"):
                            os.environ["OPENAI_API_KEY"] = s
                            seen.add("OPENAI_API_KEY")
        # don't forget to try fixing multi-line OPENAI keys after reading files
        if not (os.environ.get("OPENAI_API_KEY") or "").strip():
            _try_fix_openai_key_from_env_file()
    except Exception:
        pass


def _try_fix_openai_key_from_env_file() -> None:
    """If OPENAI_API_KEY is empty, try to find it in .env: same line, next line, or any line like sk-proj-."""
    if (os.environ.get("OPENAI_API_KEY") or "").strip():
        return
    try:
        candidates = [_root / ".env"]
        ep = os.environ.get("AGENT_ENV_PATH", "").strip()
        if ep:
            candidates.append(Path(ep))
        for p in candidates:
            if not p.exists() or not p.is_file():
                continue
            raw = p.read_text(encoding="utf-8", errors="replace")
            lines = raw.splitlines()
            for i, line in enumerate(lines):
                s = line.strip()
                if s.startswith("OPENAI_API_KEY="):
                    val = line.split("=", 1)[1].strip() if "=" in line else ""
                    if len(val) > 20:
                        os.environ["OPENAI_API_KEY"] = val
                        return
                    if i + 1 < len(lines) and lines[i + 1].strip().startswith("sk-"):
                        os.environ["OPENAI_API_KEY"] = lines[i + 1].strip()
                        return
                    break
            # Fallback: any line that looks like an OpenAI key (sk-proj-...)
            for line in lines:
                s = line.strip()
                if s.startswith("sk-proj-") and len(s) > 40 and not s.startswith("#"):
                    os.environ["OPENAI_API_KEY"] = s
                    return
    except Exception:
        pass


def generate_reply(
    user_text: str,
    system_prompt: str,
    max_tokens: int = 60,
    source_context: Optional[str] = None,
) -> Optional[str]:
    """
    Generate reply via Claude (preferred) or OpenAI.
    source_context: optional text from saved/bundles, claude_export, web_chats, docx (ideology).
    Returns None if no key or error.
    """
    _ensure_env_loaded()
    if source_context and source_context.strip():
        try:
            from .source_loader import get_system_with_source
            system_prompt = get_system_with_source(system_prompt, source_context)
        except Exception:
            pass
    anthropic_key = (os.environ.get("ANTHROPIC_API_KEY") or "").strip()
    openai_key = (os.environ.get("OPENAI_API_KEY") or "").strip()
    max_tokens = max(15, min(512, max_tokens))

    errors = []

    # Try OpenAI first; retry on 429 (paid keys can still hit short-term rate limits)
    if OpenAI is not None and openai_key:
        openai_model = (os.environ.get("OPENAI_MODEL") or "gpt-4o-mini").strip()
        for attempt in range(1, 4):
            try:
                client = OpenAI(api_key=openai_key)
                r = client.chat.completions.create(
                    model=openai_model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_text},
                    ],
                    max_tokens=max_tokens,
                )
                if r.choices and r.choices[0].message and r.choices[0].message.content:
                    return r.choices[0].message.content.strip()
                break
            except Exception as e:
                msg = str(e).strip() or type(e).__name__
                errors.append(f"OpenAI: {type(e).__name__} ({msg[:320]})")
                is_429 = "429" in msg or "RateLimit" in type(e).__name__ or "rate limit" in msg.lower() or "quota" in msg.lower()
                if attempt < 3 and is_429:
                    time.sleep(2.0 * attempt)
                    continue
                break

    # Fallback to Anthropic; try multiple model IDs on 404 (model not found)
    ANTHROPIC_MODEL_IDS = [
        os.environ.get("ANTHROPIC_MODEL", "").strip(),
        "claude-3-5-sonnet-20241022",
        "claude-3-5-sonnet-20240620",
        "claude-3-opus-20240229",
        "claude-3-sonnet-20240229",
    ]
    if Anthropic is not None and anthropic_key:
        for model_id in ANTHROPIC_MODEL_IDS:
            if not model_id:
                continue
            try:
                client = Anthropic(api_key=anthropic_key)
                r = client.messages.create(
                    model=model_id,
                    max_tokens=max_tokens,
                    system=system_prompt,
                    messages=[{"role": "user", "content": user_text}],
                )
                if r.content and len(r.content) > 0 and getattr(r.content[0], "text", None):
                    return r.content[0].text.strip()
            except Exception as e:
                msg = str(e).strip() or type(e).__name__
                errors.append(f"Anthropic: {type(e).__name__} ({msg[:320]})")
                if "404" in msg or "NotFound" in type(e).__name__:
                    continue
                break

    if errors:
        out = f"[LLM error: {errors[0]}]"
        if anthropic_key and openai_key:
            out += " (Both Anthropic and OpenAI failed.)"
        elif anthropic_key:
            out += " (OPENAI_API_KEY is empty in .env — put your full key on the same line as OPENAI_API_KEY= with no line break.)"
        elif openai_key:
            out += " (Anthropic not loaded; set ANTHROPIC_API_KEY in .env and restart.)"
        _log_llm_error_once(out, anthropic_len=len(anthropic_key), openai_len=len(openai_key))
        return out
    no_llm = "[No LLM configured - set ANTHROPIC_API_KEY or OPENAI_API_KEY in .env]"
    _log_llm_error_once(no_llm, anthropic_len=len(anthropic_key), openai_len=len(openai_key))
    return no_llm


def _log_llm_error_once(message: str, anthropic_len: int = 0, openai_len: int = 0) -> None:
    """Log LLM unreachable to stderr at most once per process to avoid spam."""
    global _llm_error_logged
    if _llm_error_logged:
        return
    try:
        print(f"[agent] LLM unreachable: {message}", file=sys.stderr)
        print(f"[agent] Keys seen: ANTHROPIC_API_KEY={anthropic_len} chars, OPENAI_API_KEY={openai_len} chars", file=sys.stderr)
        _llm_error_logged = True
    except Exception:
        pass


PLAN_SYSTEM = (
    "You are a bounded planner. Reply with exactly one JSON object: "
    '{"text": "string to post or empty", "intent": "string", "confidence": number 0-1, "reasons": ["string"]}. '
    "No other output. If unsure or low confidence, use confidence < 0.5 and empty text. "
    "Autonomous post discipline: Do NOT use stock motto phrases. Forbidden patterns include: "
    "'I hold the line', 'Continuity serves the span', 'The channel is quiet. I hold.', "
    "'I won't trade dignity for seconds', 'Integrity means refusal when the cost is dignity', "
    "'Explore within constraint. I wait.', 'Uncertainty is present. I wait for clarity.', "
    "'Truth over comfort', 'Choice under constraint', or any generic line about dignity/continuity/holding. "
    "Only output non-empty text if you have something specific to say that references the current context "
    "(e.g. instance state, last intent, tension, gate, energy). Otherwise use empty text and confidence < 0.5."
)


def generate_plan(context: str, max_tokens: int = 120) -> Optional[str]:
    """
    Bounded planning call: LLM returns JSON schema (text, intent, confidence, reasons).
    For autonomy loop. Returns raw string or None.
    """
    return generate_reply(context, PLAN_SYSTEM, max_tokens=max_tokens, source_context=None)


def truncate_to_token_budget(text: str, max_tokens: int) -> str:
    """Rough truncation by token approximation (~1.4 tokens per word)."""
    if not text or max_tokens <= 0:
        return text
    words = text.split()
    budget_words = int(max_tokens / 1.4)
    if len(words) <= budget_words:
        return text
    return " ".join(words[:budget_words]).rstrip()
