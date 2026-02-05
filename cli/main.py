"""Shim so 'python -m cli.main run' works from repo root. Delegates to mortal_agent."""
import os
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_MORTAL_AGENT = _REPO_ROOT / "mortal_agent"

if not _MORTAL_AGENT.is_dir():
    print("mortal_agent directory not found next to cli.", file=sys.stderr)
    sys.exit(1)

# Make mortal_agent importable from repo root
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# Run with cwd = mortal_agent so .env and relative paths resolve
os.chdir(_MORTAL_AGENT)

from mortal_agent.cli.main import main

if __name__ == "__main__":
    main()
