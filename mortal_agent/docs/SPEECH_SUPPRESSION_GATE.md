# Speech Suppression Gate & Output Medium

## High-level design

- **output_medium** (string enum): `chat` (default), `status`, `log`, `github`, `social`, `longform`. Single control signal for where speech is going.
- **Speech Suppression Gate** runs **before** any text is produced. Inputs: `internal_state`, `narrator_context`, `output_medium`. Outputs: `should_speak`, `speak_reason`, `max_words`, `style_profile`.
- **chat/status/log**: Suppressed, compressed. Target 6–35 words, hard cap 60. One idea per utterance. No multi-paragraph. Style: `compressed_philosopher`. If gate says `should_speak=false`, output silence token `…` (or skip emit in autonomy).
- **github/social/longform**: Expressive allowed. Target 150–800 (github/longform), 80–250 (social). Style: `expressive_structured`. Headings/bullets/narrative ok; no repetition.
- **Grounding**: Observation lines and presence grounded in narrator context (energy, tension, uncertainty, constraints).
- **Minimal intrusion**: New modules `output_medium.py`, `speech_gate.py`; wiring in narrator, llm, autonomy, mortal_agent; config/prompt layer (plan system style suffix, max_words) rather than autonomy logic refactor.
- **State delta**: Gate uses `last_gate_energy`, `last_gate_tension`, `last_gate_uncertainty` in `meaning_state` to decide if there is a meaningful state change; otherwise (with cooldowns) can suppress in chat/status/log.
- **Explicit user prompt**: When `explicit_user_prompt=True` (e.g. chat reply), gate always allows speak; max_words still by medium.
- **Medium unset**: Defaults to `chat` (suppressed behavior).

## Files changed

| File | Change |
|------|--------|
| `agent_core/output_medium.py` | **New**. Enum values, `normalize_output_medium`, `output_medium_from_tags`, `is_suppressed_medium`, `is_expressive_medium`. |
| `agent_core/speech_gate.py` | **New**. `speech_suppression_gate()`, `GateResult`, `SILENCE_TOKEN`, `gate_result_for_reply()`. |
| `agent_core/narrator.py` | `build_degraded_explanation(..., max_words=...)`, `get_wander_text_filtered_by_state(..., max_words=...)`. |
| `agent_core/llm.py` | `PLAN_SYSTEM_COMPRESSED`, `PLAN_SYSTEM_EXPRESSIVE`, `get_plan_system_for_medium()`, `get_plan_style_suffix()`, `generate_plan(..., output_medium=...)`. |
| `agent_core/llm_router.py` | `generate_plan_routed(..., output_medium="chat")`, append style suffix from `get_plan_style_suffix()`. |
| `agent_core/response_policy.py` | `compress_to_max_words()`, `compress_to_depth(..., max_words=...)`. |
| `agent_core/autonomy.py` | `_autonomy_gate()`, `_get_offline_wander_text(..., max_words=...)`. Gate before: wander heartbeat, wander fallback, plan post, narrator_observation, textforge homeostasis. Update `last_gate_*` in meaning_state after successful posts. |
| `agent_core/mortal_agent.py` | `_output_medium` in __init__; `emit_page()` runs gate (resolve medium from tags), emits `SILENCE_TOKEN` when `should_speak=false`, applies `max_words` in compress_to_depth; `generate_plan_routed(..., output_medium=self._output_medium)`. |

## Test plan (6 cases)

1. **LLM off: chat wander short + varied**  
   Run with `--no-llm`. Trigger autonomy wander (wait WANDER_INTERVAL). Assert each wander line is ≤60 words and varies (no single repeated phrase). Assert lines are state-grounded (from degraded templates or ideology snippet).

2. **LLM on: chat still suppressed**  
   Run with LLM on. Let autonomy produce a plan post or wander. Assert output is ≤60 words and style is compressed (one idea, no multi-paragraph). Optionally assert presence lines ≤25 words.

3. **github medium: longform allowed**  
   Set `output_medium="github"` (or trigger a GITHUB_POST path that uses expressive style). Generate a plan or post targeting github. Assert max_words ≥ 250 and style allows headings/bullets; no hard 60-word cap.

4. **should_speak=false: silence behavior**  
   Force gate to return `should_speak=False` (e.g. no state delta, no heartbeat interval, suppressed medium). Assert autonomy does not post (or emits only `…`). Assert no spend_speech when gate suppresses.

5. **Regression: no spam loop**  
   Run autonomy for N ticks (e.g. 20). Assert we do not get a burst of many posts in a short time; cooldowns and gate suppression limit frequency. Assert no repeated identical lines in sequence.

6. **Medium unset defaults to chat**  
   Call `normalize_output_medium(None)`, `normalize_output_medium("")`, `output_medium_from_tags([])`. Assert all return `"chat"`. Assert plan system gets compressed style when medium is default.
