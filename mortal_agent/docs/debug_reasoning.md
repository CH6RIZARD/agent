# Debugging "I can't reach my reasoning right now"

## What "reasoning" is

In this codebase, **"reasoning" is the LLM** (the language model used for chat and planning). The agent does not have a separate "reasoning service"—when it says it can't reach its reasoning, it means **every configured LLM provider failed** for that request.

- **Chat**: `generate_reply_routed()` in `agent_core/llm_router.py` tries, in order:
  1. **Anthropic** (Claude) — `ANTHROPIC_API_KEY` or `CLAUDE_API_KEY`
  2. **OpenRouter** — `OPENROUTER_API_KEY`
  3. **OpenAI** — `OPENAI_API_KEY`
- **Planning**: Tries Anthropic, then Groq, then the same chat stack.

When all attempts fail (auth, quota, timeout, network, or `--no-llm`), the agent returns the single fallback line: *"I can't reach my reasoning right now."*

**Why you might see that phrase even when chat works:** The agent injects `last_autonomous_message` (the last thing it "said" on its own, from autonomy) into the chat system prompt. If that value was ever set to the fallback (e.g. from a previous run with `--no-llm` or from an autonomy path that posted the fallback), the **chat LLM is told** "Last thing you said on your own: I can't reach my reasoning right now." and then echoes or elaborates on it in its reply. So the chat call can succeed while the reply still contains the phrase. The code now avoids storing and injecting the fallback as `last_autonomous_message`, so the LLM is no longer prompted to repeat it.

## Why it might be unreachable

| Cause | What to check |
|-------|----------------|
| **No key** | `.env` in `mortal_agent/` (or repo root). Need at least one of: `ANTHROPIC_API_KEY`, `OPENROUTER_API_KEY`, `OPENAI_API_KEY`. |
| **Invalid/revoked key** | Re-create the key in the provider console; no line break after `=` in `.env`. |
| **Quota / rate limit** | Anthropic: add credits at console.anthropic.com. OpenRouter/OpenAI: check provider dashboard. |
| **Timeout** | Default 30s; slow networks or heavy load can cause timeouts. Increase via env if your code supports it. |
| **Network** | Proxy, firewall, or no internet. Run from a terminal and check stderr. |
| **Offline mode** | Agent started with `--no-llm`; no LLM is called. |
| **Exception in chat path** | Any exception before/after `generate_reply_routed` is swallowed and results in no reply, then the same fallback. |

## How to debug

1. **See which keys are loaded**  
   From the `mortal_agent` directory (or where `.env` is loaded):
   ```bash
   set AGENT_LOG_KEYS=1
   python -c "from agent_core.llm_router import OR_KEY, ANTHROPIC_KEY, OPENAI_KEY; print('OR:', bool(OR_KEY), 'Anth:', bool(ANTHROPIC_KEY), 'OpenAI:', bool(OPENAI_KEY))"
   ```
   Or run your usual entry point (e.g. observer or CLI) with `AGENT_LOG_KEYS=1` and watch the first lines.

2. **See why the LLM failed**  
   On the **first** failure per process, the router logs one line to **stderr**, e.g.:
   ```text
   [agent] LLM unreachable (anthropic: quota). Your credit balance is too low...
   Primary is Claude (ANTHROPIC_API_KEY). Add credits at console.anthropic.com.
   ```
   So run the agent from a terminal (or ensure stderr is visible) and trigger a chat turn.

3. **See failure reason in the reply (debug)**  
   Set `AGENT_DEBUG_LLM=1` before starting the agent. When the LLM is unreachable, the agent will append a short reason to the fallback message so you can see it in the UI (e.g. observer) without reading stderr.

## Code references

- Fallback text: `agent_core/llm_router.py` — `_UNREACHABLE_FALLBACK`, `get_offline_wander_text()`.
- One-time stderr log: `_log_llm_failure_once()` in `llm_router.py`, called from `generate_reply_routed()` when all providers fail.
- Chat path that uses it: `agent_core/mortal_agent.py` (around line 787) — calls `generate_reply_routed()`; if it returns `(None, failure_info)`, the agent uses `get_offline_wander_text()` and optionally surfaces `failure_info` when `AGENT_DEBUG_LLM=1`.
