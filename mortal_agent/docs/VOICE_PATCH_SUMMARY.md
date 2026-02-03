# Voice Patch Summary

## 1) Repo file tree (changed/added)

```
mortal_agent/
├── agent_core/
│   └── voice_style.py          # NEW — voice style module
├── cli/
│   └── main.py                 # CHANGED — apply_voice at terminal + observer reply
├── tests/
│   └── voice_smoke_test.py     # NEW — smoke test + unit checks
├── .env.example                # CHANGED — VOICE_MODE comment
└── docs/
    └── VOICE_PATCH_SUMMARY.md  # NEW — this file
```

Also changed:
- `agent_core/mortal_agent.py` — apply_voice in emit_page before PageEvent

---

## 2) Exact commands to run the smoke test

From repo root (D:\agent):

```powershell
cd D:\agent\mortal_agent
python tests/voice_smoke_test.py
```

Or with pytest (if installed):

```powershell
cd D:\agent\mortal_agent
python -m pytest tests/voice_smoke_test.py -v -s
```

Bypass voice (clean mode) at runtime:

```powershell
$env:VOICE_MODE = "clean"
python -m cli run
```

---

## 3) Three before/after examples (voice effect)

**Example 1 — Corporate → human**

BEFORE:
```
As an AI I would say that we should leverage a robust approach. Let me delve into the details. The solution is seamless and will scale.
```

AFTER:
```
I would say that we should use a solid approach. Let me go into the details. The solution is smooth and will scale.
```

**Example 2 — Instruction steps (run-on)**

BEFORE:
```
Step 1: Open the config file. Step 2: Set the environment variable. Step 3: Restart the service. You're done.
```

AFTER:
```
Step 1: Open the config file. Step 2: Set the environment variable. Step 3: Restart the service and You're done.
```

**Example 3 — Formal assist → direct**

BEFORE:
```
I'd be happy to assist. Please feel free to reach out if you have any further questions. We leverage best practices to ensure a seamless experience.
```

AFTER:
```
I'll assist. Please you can reach out if you have any further questions. We use best practices to ensure a smooth experience.
```

---

## 4) Integration points (no behavior change)

- **emit_page** (agent_core/mortal_agent.py): text passed through `apply_voice(text)` before creating PageEvent.
- **Terminal chat** (cli/main.py): reply passed through `apply_voice(reply)` before print.
- **Observer chat** (cli/main.py): reply passed through `apply_voice(reply)` before `add_chat_reply`.

Config: `VOICE_MODE=human_raw` (default) or `VOICE_MODE=clean` (bypass). No new deps. Deterministic (hash of text).
