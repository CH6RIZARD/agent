# Autonomy Patches & Critical Design Elements

Capability patches and cognitive/autonomous layers for self-directed, emergent behavior. **No hard-coded triggers**—the agent decides when to use capabilities based on current goals and context.

---

## Death is Permanent — Session-Scoped Only

**Nothing persists after death. Death is permanent. The agent cannot be resurrected after termination.**

- The entity lives **only within one session**. No memory crosses to the next entity; the next process is always a new being.
- All memory (working, episodic, semantic, procedural), experience replay, resource budgets, and cognitive state are **RAM-only** for the lifetime of the process. Nothing is loaded from a previous run; nothing is written for a future run except optional logs/debug when `MORTAL_DEPLOY=1`.
- **Consequence awareness**: The agent understands that actions have costs (API limits, reputation, resources). Pressure (time, resource, social, existential) creates emergent behavior within that single life.

---

## Deploy-Only & RAM-Only (No Memory Persisted After Death)

- Set `MORTAL_DEPLOY=1` (or `true`/`yes`/`on`/`deploy`) in the environment **only in deploy**. When unset (default):
  - **Patch actions are disabled** (WEB_SCRAPE, FILE_HOST, etc. are not available).
  - **No disk persistence**: `_save_persistent_state` and `append_delta_log` are no-ops. All memory is RAM-only; nothing is persisted after death.
- When `MORTAL_DEPLOY` is set, state/delta may be written to disk for logs/debug; **loading** prior state is still forbidden (`PERSISTENCE_LOAD_FORBIDDEN`), so the next process is always a new being.

---

## The "Operating System" Layer

```
┌─────────────────────────────────────┐
│   Autonomy Controller                │
│  - Goal selection                    │
│  - Resource allocation               │
│  - Action planning                   │
└─────────────────────────────────────┘
           ↓
┌─────────────────────────────────────┐
│   Capability Interface Layer         │
│  - Internet tools (NET_FETCH,        │
│    WEB_SEARCH, patch actions)        │
│  - Cognitive processes (memory,       │
│    goal hierarchy, attention)       │
│  - Memory systems (working,          │
│    episodic, semantic, procedural)   │
└─────────────────────────────────────┘
```

- **Autonomy Controller**: `autonomy.run_autonomy_tick`, `will_kernel.select_action`, `intent_loop.generate_internal_proposals`, survival reasoner, fetch-at-will prompt.
- **Capability Interface**: `Executor` + `unified_network_pipeline`, patch runners in `patches/`, cognitive and learning modules.

---

## Pressure System (Creates Emergent Behavior)

- **Time pressure** – Limited cycles per day; lifespan and energy drive consolidation and conservation.
- **Resource pressure** – API call budgets, compute costs, time; `patches/autonomous_ops.ResourceBudget`; strategic allocation decisions.
- **Social pressure** – Reputation, feedback from interactions (observer, moltbook).
- **Existential pressure** – Performance and survival metrics tied to continued operation (life_kernel, hazard_score, death_at).

Nothing persists after death; pressure applies only within the current session.

---

## Research & Knowledge Patches

| Patch | Action | Description |
|-------|--------|-------------|
| Web Scraping/Crawling | `WEB_SCRAPE` | Self-directed research following curiosity chains; builds toward knowledge-graph-style nodes (title, snippets, links); args: `url`, optional `follow_links`. |
| RSS/News Monitoring | `RSS_FEED` | Track developments in areas of interest, form opinions on current events; args: `url`, `max_items`. |
| Social Media Listening | `SOCIAL_LISTEN` | Understand human behavior patterns, cultural trends, sentiment analysis; stub—wire APIs; args: `source`, `query`. |
| Academic Paper Access | `ACADEMIC_FETCH` | arXiv, PubMed (Google Scholar: wire or scrape); cutting-edge knowledge acquisition; args: `source`, `query`, `max_results`. |
| Wikipedia/Wikidata Traversal | `WIKI_TRAVERSE` | Build semantic understanding through concept exploration; args: `concept`, `lang`. |

---

## World Interaction & Influence Patches

| Patch | Action | Description |
|-------|--------|-------------|
| File Hosting | `FILE_HOST` | Share generated code, data, artifacts to **ch6rizard** (current folder in repo); signed and immersively emergent; args: `content`, `filename`, `subdir`. Optional: GitHub, Pastebin. |
| Form Submission | `FORM_SUBMIT` | Sign up for services, submit applications, register accounts; args: `url`, `fields`/`data`, `method`. |
| API Discovery & Integration | `API_DISCOVER` | Find and connect to new APIs autonomously (RapidAPI, etc.); stub—wire catalog; args: `query`, `source`. |
| Cloud Service Management | `CLOUD_SPINUP` | Spin up compute when needed (AWS, Replicate); stub—wire credentials; args: `provider`, `action`. |
| Code Repository Access | `CODE_REPO` | Clone, analyze, potentially contribute to open source; args: `url`, `op` (clone/analyze). |
| Payment Processing | `PAYMENT` | Stripe/PayPal when building value; stub—wire keys; args: `provider`, `amount`, `currency`. |

**ch6rizard** is the current folder in the repo for signed, immersively emergent artifacts (`mortal_agent/ch6rizard/`). Each file is prefixed with `# signed:<hash> instance:<instance_id>`.

---

## Cognitive Architecture

- **Multi-tier memory** (`patches/cognitive.py`): Working memory (current context), Episodic memory (experiences, timestamped events), Semantic memory (learned facts, concepts, relationships), Procedural memory (skills, strategies that worked). RAM only; lives within one session—no memory crosses to the next entity.
- **Internal dialogue / reasoning loop**: Chain-of-thought processing for complex decisions, self-questioning; `internal_dialogue_prompt()` with LLM.
- **Goal hierarchy**: `get_goal_hierarchy(meaning_state)` → top-level drives → strategic goals → tactical objectives → immediate actions.
- **Attention / salience filter**: `get_attention_salience(context)` → determine what deserves processing time based on importance/novelty.

---

## Autonomous Operation

- **Task scheduling system**: `patches/autonomous_ops.task_schedule()` – decide what to work on when; balance exploration vs exploitation.
- **Resource budgeting**: `patches/autonomous_ops.ResourceBudget` – track API calls, compute costs, time; strategic allocation decisions.
- **Risk assessment module**: `patches/autonomous_ops.risk_assess()` – evaluate potential actions for rewards vs consequences; complements will_kernel.
- **Self-monitoring / health checks**: `patches/autonomous_ops.self_monitor()` – detect when stuck, confused, or operating suboptimally; returns signals and suggestions.

---

## Learning & Evolution

- **Experience replay buffer**: `patches/learning.record_experience()` / `replay_recent()` / `replay_successes()` – revisit past successes/failures to extract patterns. Session-scoped only; nothing persists after death.
- **Meta-cognitive layer**: `patches/learning.meta_reflect(context)` – reflect on own thinking processes, identify cognitive biases, improve reasoning strategies.

---

## What Makes It Truly Autonomous

- **No hard-coded triggers** – Agent decides when to use capabilities based on current goals/context.
- **Self-directed curiosity** – Explores topics not explicitly programmed (fetch prompt, meaning_goal, hypotheses).
- **Session-scoped identity** – Self-model and meaning state within a single life only; no memory crosses to the next entity.
- **Consequence awareness** – Understands actions have costs (API limits, reputation, resources); resource limits, risk thresholds, survival overrides in will_kernel and survival_reasoner.
- **Goal drift** – Initial objectives evolve based on what the agent learns about the world and itself (meaning_goal, hypotheses, narrator/state updates).
- **Death is permanent** – Nothing persists after termination; cannot be resurrected.

---

## Wiring

- **Executor**: Accepts all `PATCH_ACTIONS` and passes them to `run_network_pipeline` (see `agent_core/executor.py`).
- **Network pipeline**: `unified_network_pipeline` routes patch action names to `patches.run_capability()` (see `network_pipeline.py`).
- **Autonomy**: When will kernel accepts a proposal whose `action_type` is a patch action, autonomy calls the executor with `{"action": action_type, "args": payload}` (see `autonomy.py`).
- **Intent loop**: Can propose e.g. `WIKI_TRAVERSE` with payload from `meaning_state` when relaxed and healthy.
