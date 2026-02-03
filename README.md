# Embodied Mortal Agent

**Embodied agent whose identity exists only while it’s running. Death is terminal; restart is a new being.**

- **Identity = uninterrupted embodied execution** (Δt only while power ∧ sensors ∧ actuators)
- **Death is terminal** — process exits; no save/resume, no “see you later”
- **RAM-only state** — no internal state to disk
- **Observer optional** — disconnect the UI; the agent keeps running until the body gate fails

## Quick start

```bash
cd mortal_agent
pip install -r requirements.txt
# First run: python -m cli.main ensure-canon
python -m cli.main run --demo-pages
# Open http://127.0.0.1:8080 — CHAT panel to talk (needs ANTHROPIC_API_KEY or OPENAI_API_KEY in .env)
# In another terminal: python -m cli.main kill-gate power  # kills the agent
```

See **[mortal_agent/README.md](mortal_agent/README.md)** for full docs, commands, and spec.

## Repo layout

| Path | Purpose |
|------|--------|
| `mortal_agent/` | Core agent: CLI, life kernel, observer UI, adapters (Unity/Unreal/sim) |
| `mortal_agent/docs/` | [SPEC](mortal_agent/docs/SPEC.md), integration notes, API |
| `agent_source_data/` | Scripts and extracted context for identity/source loading |
| `scripts/` | Workspace and GitHub helpers |

## License

See [LICENSE](LICENSE) if present.
