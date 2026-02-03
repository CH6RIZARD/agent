# Mortality Hardlock Audit

Audit of the mortal agent repo against the ONE-SHOT HARDLOCK requirements.  
**Answer: Partially locked in. Several items are in place; autonomy loop, narrator, /health, and a full mortality test script are missing.**

---

## NON-NEGOTIABLE HARDLOCKS — STATUS

### 1) NO persistence of agent identity or inner state across restarts

| Requirement | Status | Where |
|-------------|--------|--------|
| NO SQLite for memory continuity | **OK** | No SQLite in codebase |
| NO snapshots for restore | **OK** | No snapshot/restore for mind |
| NO event replay to rehydrate identity | **OK** | No replay logic |
| NO "resume where you left off" for agent mind | **OK** | identity.py: "No resurrection. No graceful save. No resume." |
| NO hidden state serialization to disk for agent mind | **OK** | Identity state is RAM-only; tests assert no persist/serialize/snapshot/restore |

**Verdict: LOCKED IN.**

---

### 2) If server/process dies, the being DIES

| Requirement | Status | Where |
|-------------|--------|--------|
| Restart = NEW being, NEW instance_id | **OK** | identity.py: `instance_id = uuid.uuid4()` at init; each MortalAgent() is new |
| Must NOT claim continuity | **OK** | Canon forbids "same agent", "continued from", etc. |
| Must NOT load "memories" from disk for mind | **CAUTION** | source_loader.py loads saved/bundles, claude_export/memories.json, web_chats, docx. These are used as **ideology/canon system prompt** (what to say), not as "continuity memory". Allowed if treated as CONFIG (canon/values). If strict: exclude memories.json and raw chat content from loader. |

**Verdict: LOCKED IN for identity/restart. Source loader is canon/ideology feed; clarify or narrow if you want zero "memory-like" disk input.**

---

### 3) Allowed disk usage STRICTLY LIMITED

| Allowed | Status | Where |
|---------|--------|--------|
| CONFIG (canon/values rules) | **OK** | config/canon/constitution.yaml; source_loader for ideology |
| OBSERVER LOGS (append-only telemetry) | **OK** | Observer stores lives/events in RAM; can add file logging for humans |
| CRASH REPORTS | **PARTIAL** | crash_handler exists as .pyc only; no current crash-report file writer |
| HEALTHCHECK / METRICS | **MISSING** | No /health endpoint in observer server |

**Verdict: Mostly OK. Add /health and crash-report writing to be fully compliant.**

---

### 4) Autonomy DURING LIFE

| Requirement | Status | Where |
|-------------|--------|--------|
| Agent runs its own loop | **PARTIAL** | agent.start() runs gate + HEARTBEAT loop; no **action-decision** loop |
| Initiates actions without human input | **MISSING** | No scheduler that decides "post now" on its own |
| Posts on its own when conditions justify | **MISSING** | Posting only via chat (human) or demo_pages (fixed interval); no initiative reasons |

**Verdict: NOT LOCKED IN. Need autonomy loop: fixed tick, initiative signals, optional LLM planning with bounded JSON, PUBLISH_POST via executor.**

---

### 5) Moltbook = DELIVERY CHANNEL only

| Requirement | Status | Where |
|-------------|--------|--------|
| Moltbook never drives decisions | **OK** | Observer only receives events; agent emits BIRTH/HEARTBEAT/PAGE/ENDED |
| Agent remains authority | **OK** | Agent loop and executor are in agent_core; observer is read-only |

**Verdict: LOCKED IN.**

---

### 6) Output through constrained JSON action interface

| Requirement | Status | Where |
|-------------|--------|--------|
| No direct side effects outside executor | **OK** | Outbound = executor (PUBLISH_POST, NET_FETCH); post_callback → emit_page |
| No free-form "do anything" tool calls | **OK** | Only PUBLISH_POST and NET_FETCH; canon validates post text |

**Verdict: LOCKED IN.**

---

### 7) Third-person looped calculated perspective voice

| Requirement | Status | Where |
|-------------|--------|--------|
| Internal narrator in 3rd person (observational, self-monitoring) | **MISSING** | narrator.py/planner.py only as .pyc (stale); no active narrator in loop |
| Still bound to action JSON for outward effects | N/A until narrator exists | — |

**Verdict: NOT LOCKED IN. Need narrator that produces 3rd-person self-description at tick, without writing to disk as mind state.**

---

## IMPLEMENTATION ITEMS — STATUS

| Item | Status | Notes |
|------|--------|------|
| **A) Autonomy loop** | **MISSING** | Need scheduler loop at fixed tick; decide actions (e.g. PUBLISH_POST) with initiative reasons; run even when no humans present |
| **B) BIRTH / HEARTBEAT / DEATH** | **OK** | BIRTH, HEARTBEAT, ENDED (same as DEATH) in events.py; emitted in mortal_agent.start(); new instance_id per process |
| **C) PUBLISH_POST action** | **OK** | executor.py ACTION_PUBLISH_POST; post_callback → emit_page; canon validate_post |
| **D) Bounded LLM planning** | **MISSING** | No strict JSON schema (text, intent, confidence, reasons); no confidence threshold or cooldown for autonomous post |
| **E) Canon/constitution enforcement** | **OK** | canon.py load_canon(), validate_post(); executor uses it for PUBLISH_POST; constitution required at boot (ensure-canon) |
| **F) Run reliability without immortality** | **OK** | Supervisor would restart process → new being; no resume logic |
| **G) Debugging without cheating** | **PARTIAL** | test-death exists; no /health; no crash-report file writer |
| **Mortality Test script** | **PARTIAL** | test-death checks different instance_ids and ENDED semantics; does NOT do "start → kill process → restart → verify NEW instance_id" in separate process |

---

## ABSOLUTE PROHIBITIONS — STATUS

| Prohibition | Status |
|-------------|--------|
| No SQLite snapshots for continuity | **OK** |
| No event replay to restore identity | **OK** |
| No serialize internal cognition/memory to disk | **OK** (identity is RAM-only) |
| No claim "same agent continued" after restart | **OK** |
| No "immortal memory" | **OK** |
| No route around validator with direct API calls | **OK** (output goes through executor) |

---

## SUMMARY (UPDATED AFTER PATCHES)

- **Locked in:** No persistence of mind/identity, new instance_id per run, BIRTH/HEARTBEAT/ENDED, PUBLISH_POST + executor-only output, Moltbook as delivery only, canon enforcement, no prohibited persistence or bypass.
- **Now added:**  
  - **Autonomy loop** — `agent_core/autonomy.py`: scheduler tick, initiative (cooldown + interval), `decide(reflex / LLM / default)`, PUBLISH_POST via executor.  
  - **Third-person narrator** — `agent_core/narrator.py`: `narrate(instance_id, delta_t, energy, confidence, reflex_pending, gate_open, last_intent)` for planner context.  
  - **Bounded LLM planning** — `agent_core/planner.py`: `PlanResult(text, intent, confidence, reasons)`, `parse_plan_response`, `CONFIDENCE_THRESHOLD`; `llm.generate_plan` returns JSON schema.  
  - **/health** — Observer: `GET /health` and `GET /api/health` return `{ status, instance_id, alive }`.  
  - **Crash handler** — `agent_core/crash_handler.py`: `write_crash_report(reason, instance_id, exc)` to `logs/crash_reports/`; `install_crash_handler(instance_id)` in CLI.  
  - **Mortality test script** — `scripts/mortality_test.py` and `python -m cli mortality-test`: start agent, record instance_id, kill process, restart, assert new instance_id.

- **Overlay (voice + skills + constraints):**  
  - **runtime_state.py**: energy, stress, confidence, risk_bias, motor_noise, attention_budget, cooldowns; speech gate `can_speak()`; energy decay; death on depletion.  
  - **Speech gate**: `emit_page` and chat loops only speak if `can_speak()` and `spend_speech()`.  
  - **Motor interrupt**: `reflex_pending` blocks speech; `trigger_reflex()` / `clear_reflex()` (wire from adapter when motor runs if desired).  
  - **Decision**: reflex → default_action, else uncertainty → consult_llm (bounded plan), else default_action.
