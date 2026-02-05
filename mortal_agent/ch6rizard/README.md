# ch6rizard

**Current folder in repo for signed, immersively emergent artifacts.**

Generated code, data, and artifacts from the agent are written here via the FILE_HOST patch. Each file is prefixed with a signature line: `# signed:<hash> instance:<instance_id>` for traceability. The agent decides when to host files based on goals and context (no hard-coded triggers).

- **Local first**: artifacts land in `ch6rizard/out/` (or custom `subdir`) by default.
- **Remote**: wire GitHub (push to repo) or Pastebin in `patches/world_interaction.run_file_host` when ready.

Nothing persists after death; only artifacts written during this session exist here. Death is permanent.
