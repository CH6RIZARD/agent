# Run 20 — Autonomous Output Not Hardcoded

**Goal:** Keep emergent chat tone; ensure autonomous (self-chosen) lines are not hardcoded mottos.

## Change (prompt only)

**Planner prompt** (autonomy loop) was tightened so the LLM that produces autonomous post text:

- **Must not** use stock motto phrases, e.g.:  
  "I hold the line", "Continuity serves the span", "The channel is quiet. I hold.",  
  "I won't trade dignity for seconds", "Integrity means refusal when the cost is dignity",  
  "Explore within constraint. I wait.", "Uncertainty is present. I wait for clarity.",  
  "Truth over comfort", "Choice under constraint", or generic dignity/continuity/holding lines.

- **May** output non-empty text only when it has something **specific** that references the current context (instance state, last intent, tension, gate, energy). Otherwise it must use **empty text** and confidence &lt; 0.5 (no post).

**Files updated:**
- `agent_core/llm.py` — `PLAN_SYSTEM`
- `agent_core/llm_router.py` — `generate_plan_routed` plan_system

Chat system prompt and conversational behavior are unchanged; only the **autonomous post** planner was constrained.

## Runs

- **20 sessions** executed via `reports/run_20/run_20.ps1` (input files in `reports/run_20/inputs/`, logs in `reports/run_20/logs/`).

## Verification

- **Grep** over all 20 logs for the listed motto phrases: **no matches.** So no stock autonomous mottos appeared in these runs.
- In these 20 runs the **LLM was unreachable (429)** for all turns, so every reply was fallback (narrator / “model unreachable”); the **planner was never used** in these logs. When the API is available, the updated planner prompt will:
  - Prefer **empty text** when there’s nothing context-specific to say.
  - If it does post, require **context-specific** content and forbid the listed mottos.

## Summary

- Autonomous post text is no longer allowed to be those fixed motto lines; the planner is instructed to be context-specific or silent.
- Chat tone is unchanged; only the autonomy **planner** prompt was updated.
- 20 runs completed; zero motto phrases in logs. With a working LLM, autonomous lines should look emergent and context-bound, not hardcoded.
