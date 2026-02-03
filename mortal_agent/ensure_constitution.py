"""
Create config/canon/constitution.yaml if missing. Same canon on C: or D: — same entity.
Run from mortal_agent:  python ensure_constitution.py
Or:  python -m cli.main ensure-canon
"""
from pathlib import Path

def ensure_constitution() -> Path:
    """Write constitution.yaml next to this package (works on C: or D:). Returns path."""
    from agent_core.canon import CONSTITUTION_YAML
    base = Path(__file__).resolve().parent
    canon_dir = base / "config" / "canon"
    canon_dir.mkdir(parents=True, exist_ok=True)
    path = canon_dir / "constitution.yaml"
    path.write_text(CONSTITUTION_YAML, encoding="utf-8")
    return path


if __name__ == "__main__":
    p = ensure_constitution()
    print(f"Constitution ready: {p}")
    print("Run: python -m cli.main run")
