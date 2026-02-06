"""
LLM reply generation - ANTHROPIC_API_KEY / OPENAI_API_KEY.
Uses the same API keys as the model you chat with: loads .env from repo root,
mortal_agent root, user home, and optional AGENT_ENV_PATH (exact path to your .env).
All calls go through agent_core.llm_router. Primary: Claude (Anthropic); fallback: OpenRouter, OpenAI.
"""

import os
import sys
from pathlib import Path
from typing import Optional

_root = Path(__file__).resolve().parent.parent
_repo = _root.parent
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

_llm_error_logged = False


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
                    if k in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "CLAUDE_API_KEY", "OPENROUTER_API_KEY", "ANTHROPIC_MODEL", "OPENAI_MODEL") and v:
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
    try:
        from .llm_router import generate_reply_routed
    except ImportError:
        _log_llm_error_once("[No LLM router - install agent_core.llm_router]", 0, 0)
        return "[No LLM configured - set ANTHROPIC_API_KEY or OPENAI_API_KEY in .env]"
    reply, failure = generate_reply_routed(
        user_text,
        system_prompt,
        max_tokens=max(15, min(512, max_tokens)),
        source_context=source_context,
        provider_mode="auto",
        failover=True,
        no_llm=False,
    )
    if reply:
        return reply
    if failure:
        detail = (failure.get("detail") or "no response")[:200]
        _log_llm_error_once(detail, 0, 0)
        return f"[LLM error: {detail}]"
    return "[LLM error: no response]"


def _log_llm_error_once(message: str, anthropic_len: int = 0, openai_len: int = 0) -> None:
    """Log LLM unreachable to stderr at most once per process to avoid spam."""
    global _llm_error_logged
    if _llm_error_logged:
        return
    try:
        print(f"[agent] LLM unreachable: {message}", file=sys.stderr)
        print(f"[agent] Keys: ANTHROPIC={anthropic_len} chars, OPENAI={openai_len} chars", file=sys.stderr)
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
