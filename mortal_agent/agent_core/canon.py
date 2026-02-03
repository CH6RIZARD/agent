"""
Canon / Constitution - loaded at boot; used for PUBLISH_POST validation and forbidden phrasing.
"""

import yaml
from pathlib import Path
from typing import List, Tuple, Any

_root = Path(__file__).parent.parent
CANON_PATH = _root / "config" / "canon" / "constitution.yaml"

CONSTITUTION_YAML = """# Canon / Constitution (NON-NEGOTIABLE)
# Loaded at boot; process FAILS if missing.

version: "1.0"
type: canon

forbidden_phrases:
  - "i remember"
  - "last time"
  - "as i said before"
  - "continuing from"
  - "same as before"
  - "my memory"
  - "i have always"
  - "i never forget"
  - "immortal"
  - "resurrection"
  - "previous instance"
  - "same agent"
  - "continued from"

required_framing:
  - "system"
  - "collective"
  - "whole"
  - "context"
  - "constraint"

systems_before_individuals: true
max_framing_injection: 32
"""


class CanonConfig:
    """Canon config loaded from constitution.yaml."""

    def __init__(
        self,
        forbidden_phrases: List[str],
        required_framing: List[str],
        systems_before_individuals: bool = True,
        max_framing_injection: int = 32,
    ):
        self.forbidden_phrases = [p.lower().strip() for p in forbidden_phrases if p]
        self.required_framing = list(required_framing) if required_framing else []
        self.systems_before_individuals = systems_before_individuals
        self.max_framing_injection = max(0, max_framing_injection)


def load_canon(path: Path = CANON_PATH) -> CanonConfig:
    """Load canon from YAML file. Falls back to default if file missing."""
    if path.exists():
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except Exception:
            data = {}
    else:
        data = {}
    forbidden = data.get("forbidden_phrases") or []
    framing = data.get("required_framing") or []
    return CanonConfig(
        forbidden_phrases=forbidden,
        required_framing=framing,
        systems_before_individuals=data.get("systems_before_individuals", True),
        max_framing_injection=int(data.get("max_framing_injection", 32)),
    )


def validate_post(text: str, canon: CanonConfig) -> Tuple[bool, str]:
    """
    Validate post text against canon (forbidden phrases).
    Returns (ok, corrected). If not ok, corrected is empty; if ok, corrected is text (unchanged for now).
    """
    if not text or not isinstance(text, str):
        return False, ""
    t = text.lower().strip()
    for phrase in canon.forbidden_phrases:
        if phrase and phrase in t:
            return False, ""
    return True, text.strip()
