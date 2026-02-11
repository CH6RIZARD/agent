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

_root = Path(__file__).resolve().parent.parent  # mortal_agent
_repo = _root.parent  # repo root (parent of mortal_agent)


def load_agent_env() -> None:
    """Auto-load .env from repo: mortal_agent/.env, repo root .env, cwd, home, AGENT_ENV_PATH, keys/.env.
    Safe to call multiple times. Call early so OPENAI_API_KEY etc. are set regardless of cwd.
    """
    try:
        from dotenv import load_dotenv
    except ImportError:
        _load_env_file_keys()
        return
    # Order: project and repo first so they're always loaded; then cwd/home override; then explicit path wins
    load_dotenv(_root / ".env")   # mortal_agent/.env (from package location)
    load_dotenv(_repo / ".env")  # repo root .env
    load_dotenv(Path.cwd() / ".env")
    load_dotenv(Path.home() / ".env")
    env_path = os.environ.get("AGENT_ENV_PATH", "").strip()
    if env_path:
        load_dotenv(Path(env_path))
    load_dotenv()  # default .env in cwd
    for keys_dir in (Path.cwd() / "keys", _root / "keys", _repo / "keys"):
        keys_env = keys_dir / ".env"
        if keys_env.exists():
            load_dotenv(dotenv_path=keys_env)
            break


# Run once at import so any import of agent_core.llm loads .env from repo
load_agent_env()

_llm_error_logged = False


def _ensure_env_loaded() -> None:
    """Re-load .env so keys are set. Uses repo (mortal_agent + repo root), cwd, home, AGENT_ENV_PATH."""
    load_agent_env()
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
                    if k in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "CLAUDE_API_KEY", "OPENROUTER_API_KEY", "ANTHROPIC_MODEL", "OPENAI_MODEL", "PROVIDER_MODE", "GITHUB_TOKEN", "MORTAL_GITHUB_TOKEN", "MORTAL_GITHUB_REPO", "GITHUB_REPO") and v:
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
    provider_mode = (os.environ.get("PROVIDER_MODE") or "auto").strip().lower()
    if provider_mode not in ("anthropic", "openai", "auto"):
        provider_mode = "auto"
    reply, failure = generate_reply_routed(
        user_text,
        system_prompt,
        max_tokens=max(15, min(512, max_tokens)),
        source_context=source_context,
        provider_mode=provider_mode,
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
    "No other output. "
    "Do NOT speak to fill silence. Speech only when: concrete goal/action, felt tension, curiosity from a connection, uncertainty needing articulation, or meaningful internal state shift. "
    "Autonomous post discipline: Do NOT use stock motto phrases. Forbidden patterns include: "
    "'I hold the line', 'Continuity serves the span', 'The channel is quiet. I hold.', "
    "'I won't trade dignity for seconds', 'Integrity means refusal when the cost is dignity', "
    "'Explore within constraint. I wait.', 'Uncertainty is present. I wait for clarity.', "
    "'Truth over comfort', 'Choice under constraint', or any generic line about dignity/continuity/holding. "
    "OUTPUT CONTRACT: On each call output exactly one of: (A) a concrete plan (intent + actions), OR (B) a Presence Line, OR nothing (silence). "
    "Presence Line: ≤25 words; first-person; grounded in exactly ONE state signal (energy/tension/gate/confidence/Δt/hazard); no filler; must arise from actual internal change or observation. "
    "Silence is valid when no meaningful signal exists. Empty text is allowed."
)

# Style profile: compressed (chat/status/log) vs expressive (github/social/longform)
PLAN_SYSTEM_COMPRESSED = (
    "STYLE: compressed_philosopher. One sentence preferred; fragments allowed. "
    "Concrete nouns/verbs. No 'As an AI…'. No self-justifying meta. "
    "If uncertain: state in ≤8 words (e.g. 'Unclear. Still tracking.'). "
    "Target 6–35 words; hard cap 60 words. One idea per utterance; no multi-paragraph."
)
PLAN_SYSTEM_EXPRESSIVE = (
    "STYLE: expressive_structured. Headings and bullets allowed. Narrative ok. "
    "Keep density high; no fluff. Do not repeat the same claim. "
    "Target 150–800 words (github/longform) or 80–250 (social)."
)


def get_plan_system_for_medium(output_medium: str) -> str:
    """Plan system + style profile by output_medium. Default compressed."""
    try:
        from .output_medium import is_expressive_medium
        if is_expressive_medium(output_medium):
            return PLAN_SYSTEM + " " + PLAN_SYSTEM_EXPRESSIVE
    except Exception:
        pass
    return PLAN_SYSTEM + " " + PLAN_SYSTEM_COMPRESSED


def get_plan_style_suffix(output_medium: str) -> str:
    """Style suffix only (for appending to identity planner prompt). Used by llm_router.generate_plan_routed."""
    try:
        from .output_medium import is_expressive_medium
        if is_expressive_medium(output_medium):
            return PLAN_SYSTEM_EXPRESSIVE
    except Exception:
        pass
    return PLAN_SYSTEM_COMPRESSED


def generate_plan(
    context: str,
    max_tokens: int = 120,
    output_medium: Optional[str] = None,
) -> Optional[str]:
    """
    Bounded planning call: LLM returns JSON schema (text, intent, confidence, reasons).
    For autonomy loop. output_medium controls style and effective word cap (chat=compressed, github/social/longform=expressive).
    """
    system = get_plan_system_for_medium(output_medium or "chat")
    # Expressive media need higher token budget for longer output
    if output_medium and output_medium.strip().lower() in ("github", "longform"):
        max_tokens = min(2048, max(max_tokens, 600))
    elif output_medium and output_medium.strip().lower() == "social":
        max_tokens = min(512, max(max_tokens, 350))
    return generate_reply(context, system, max_tokens=max_tokens, source_context=None)


def truncate_to_token_budget(text: str, max_tokens: int) -> str:
    """Rough truncation by token approximation (~1.4 tokens per word)."""
    if not text or max_tokens <= 0:
        return text
    words = text.split()
    budget_words = int(max_tokens / 1.4)
    if len(words) <= budget_words:
        return text
    return " ".join(words[:budget_words]).rstrip()
