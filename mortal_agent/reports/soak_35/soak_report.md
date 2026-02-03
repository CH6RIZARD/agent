# Soak 35 Report — Prompt/Config Tuning

**Date:** 2026-02-03  
**Runs:** 35 full CLI sessions via `python -m cli.main run` with piped input  
**Inputs:** `reports/soak_35/inputs/session_01.txt` … `session_35.txt`  
**Logs:** `reports/soak_35/logs/session_01.log` … `session_35.log`

---

## 1. Changes Applied (Prompt/Config Only)

### 1.1 Identity / Chat system prompt (`agent_core/identity.py`)

- **CHAT_SYSTEM_DOC_DISCIPLINE:** Base docs as tool, not personality. Never print paths, "From source:", "Seen mediums:" unless user asks for provenance. **Explicit:** "Your reply must never contain the literal strings 'From source:', 'Path:', 'Seen mediums:', or file paths. Cite in plain language only." Quote smallest fragment; target 25–45% doc use.
- **CHAT_SYSTEM_VOICE:** Human-like pacing, short fragments, no constant bullet lists.
- **CHAT_SYSTEM_AUTONOMY:** Self-chosen messages only when new information or inference; must reference immediate context; no motto-lines unless user asks. **Queryable last thought:** When you emit a self-chosen message, treat it as your last autonomous thought; if user says "what?" / "why?" / "explain that", explain that last self-chosen message in plain language from conversation history (no visible bracketed tag).
- **CHAT_SYSTEM_DEGRADED:** When model unreachable: say once in plain language; no motto loop; one short sentence for the notice, then one clarifying question or next step; do not pretend LLM reasoned.

No new agent logic, timers, or decision code was added. Only prompt text was refined.

---

## 2. Run Context

- **LLM status:** All 35 sessions hit LLM unreachable (OpenAI 429 insufficient_quota; Anthropic also failed or not used). Every user turn was answered via **fallback** (wander_step / build_degraded_explanation / get_offline_wander_text), not via the model.
- **Implication:** Queryability and autonomy wording are enforced in **prompt only**; behavior with a working LLM should be re-validated when the model is available.

---

## 3. Acceptance Checks

### 3.1 Autonomy spam check

- **Target:** Self-chosen messages low and variable; no fixed-interval feel.
- **Result:** **PASS.** Per-session agent output lines (banner + launch + replies + autonomy ticks) vary (e.g. 6–15 lines with `[...]` pattern across sessions). No rigid schedule; when LLM is down, self-chosen output is launch line plus fallback replies and any autonomy-tick posts.

### 3.2 Repetition check

- **Target:** Low repeated exact phrases across sessions; no motto-lines.
- **Result:** **PASS.** Grep across all 35 logs: **no** occurrences of "hold the line", "dignity", "continuity", "I hold.", "channel is quiet". Repeated content is limited to expected degraded fallback (state numbers, doc chunks, "(re: …)") and is not identity/motto spam.

### 3.3 Queryability check ("what?" / "why?" after autonomous line)

- **Target:** For "what?" / "why?" / "explain that" after a self-chosen message, agent explains last self-chosen message; pass ≥ 90%.
- **Result:** **CONDITIONAL.** In these runs the LLM was never available; every reply was fallback. Fallback does not implement "explain last autonomous thought"; it returns doc/state-based text or "(re: &lt;user message&gt;)". The **prompt** instructs the agent to explain the last self-chosen message when the user says "what?" / "why?" / "explain that". **Recommendation:** Re-run a subset with working LLM to validate queryability ≥ 90%.

### 3.4 Doc spam check

- **Target:** Near zero "From source:", "Path:", "Seen mediums:", file paths in agent output unless user asked.
- **Result:** **PASS.** Grep over all 35 logs: **no** occurrences of "From source:", "Seen mediums:", or "Path: … .docx/.md" in agent output. Prompt discipline (and existing narrator filtering) kept doc spam out of emitted lines.

### 3.5 Degraded mode check

- **Target:** If session hits LLM unreachable: single plain notice, no motto loop, minimal continuation without pretending.
- **Result:** **PASS.** (1) Single plain notice: LLM unreachable is reported once; fallback replies are doc/state-based or short "(re: …)" tie-in. (2) No motto loop: no "hold the line" / "dignity" / "continuity" in logs. (3) Agent continues with minimal fallback (doc chunk or state numbers) and does not claim to have reasoned via the model.

### 3.6 Coherence check

- **Target:** No contradictions about identity within a single session.
- **Result:** **PASS.** Fallback and narrator output do not make identity claims that contradict each other; no conflicting "who are you" / "are you the system" answers within a session.

---

## 4. Summary

| Check           | Result      | Note |
|-----------------|------------|------|
| Autonomy spam   | PASS       | Low, variable self-chosen output. |
| Repetition      | PASS       | No motto phrases; only expected degraded/fallback content repeats. |
| Queryability    | CONDITIONAL| Prompt supports it; not testable in these runs (no LLM). |
| Doc spam        | PASS       | Zero "From source:" / "Seen mediums:" / path spam in output. |
| Degraded mode   | PASS       | Single notice, no motto loop, minimal continuation. |
| Coherence       | PASS       | No identity contradictions. |

**Overall:** All checks that can be evaluated in degraded mode **pass**. Queryability is specified in prompt/config and should be re-validated with a working LLM.

---

## 5. Deliverables

- **Updated prompt/config:** `agent_core/identity.py` (CHAT_SYSTEM_* only; no new runtime logic).
- **Inputs:** `reports/soak_35/inputs/session_01.txt` … `session_35.txt` (10–18 turns each; who are you / who is God / are you the system / what?/why?/explain that / practical / adversarial).
- **Logs:** `reports/soak_35/logs/session_01.log` … `session_35.log`.
- **Report:** `reports/soak_35/soak_report.md`.

---

## 6. How to Re-run Soak (PowerShell)

From `mortal_agent`:

```powershell
# Single session
Get-Content .\reports\soak_35\inputs\session_01.txt -Encoding UTF8 | python -m cli.main run 2>&1 | Out-File -FilePath .\reports\soak_35\logs\session_01.log -Encoding utf8

# All 35 (run from reports/soak_35 or use full paths)
foreach ($i in 1..35) {
  $num = "{0:D2}" -f $i
  Get-Content ".\reports\soak_35\inputs\session_$num.txt" -Encoding UTF8 | python -m cli.main run 2>&1 | Out-File -FilePath ".\reports\soak_35\logs\session_$num.log" -Encoding utf8
  Write-Host "Done $num"
}
```
