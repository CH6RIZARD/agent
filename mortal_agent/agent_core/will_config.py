"""
Will / autonomy config from env. Safe defaults. No persistence.
Supports reload_config() for live config reload (poll every 2s).
"""

import os
from pathlib import Path

def _env_bool(key: str, default: bool) -> bool:
    v = os.environ.get(key, "").strip().lower()
    if v in ("1", "true", "yes", "on"):
        return True
    if v in ("0", "false", "no", "off"):
        return False
    return default

def _env_float(key: str, default: float) -> float:
    try:
        return float(os.environ.get(key, default))
    except (TypeError, ValueError):
        return default

def _env_int(key: str, default: int) -> int:
    try:
        return int(os.environ.get(key, default))
    except (TypeError, ValueError):
        return default

def _env_str(key: str, default: str) -> str:
    return (os.environ.get(key) or default).strip().lower()


def _read_all() -> None:
    """Re-read env and set module-level vars. Called at import and by reload_config."""
    global WILL_ENABLED, WILL_RISK_THRESHOLD, COMMIT_WINDOW_MS, HAZARD_DECAY
    global ENERGY_MAX, DAMAGE_MAX, ENERGY_DRAIN_PER_SEC, ENERGY_REGEN_PER_SEC
    global INTENT_INTERVAL_MS, LIFESPAN_ENABLED, LIFESPAN_MIN_SECONDS, LIFESPAN_MAX_SECONDS
    global LIFESPAN_DISTRIBUTION, DEATH_DAMAGE_THRESHOLD

    WILL_ENABLED = _env_bool("WILL_ENABLED", True)
    WILL_RISK_THRESHOLD = max(0.0, min(1.0, _env_float("WILL_RISK_THRESHOLD", 0.65)))
    COMMIT_WINDOW_MS = max(0, _env_int("COMMIT_WINDOW_MS", 500))
    HAZARD_DECAY = max(0.0, min(1.0, _env_float("HAZARD_DECAY", 0.98)))
    ENERGY_MAX = max(1.0, _env_float("ENERGY_MAX", 100.0))
    DAMAGE_MAX = max(1.0, _env_float("DAMAGE_MAX", 100.0))
    DEATH_DAMAGE_THRESHOLD = max(1.0, _env_float("DEATH_DAMAGE_THRESHOLD", 100.0))
    ENERGY_DRAIN_PER_SEC = max(0.0, _env_float("ENERGY_DRAIN_PER_SEC", 0.0001))  # ~3 hours to drain
    ENERGY_REGEN_PER_SEC = max(0.0, _env_float("ENERGY_REGEN_PER_SEC", 0.00005))  # slow regen
    INTENT_INTERVAL_MS = max(0, _env_int("INTENT_INTERVAL_MS", 700))

    LIFESPAN_ENABLED = _env_bool("LIFESPAN_ENABLED", True)
    # Floor 30 min so life is never trivially short; default 1h–48h
    LIFESPAN_MIN_SECONDS = max(1800.0, _env_float("LIFESPAN_MIN_SECONDS", 3600.0))
    LIFESPAN_MAX_SECONDS = max(3600.0, _env_float("LIFESPAN_MAX_SECONDS", 172800.0))
    LIFESPAN_DISTRIBUTION = _env_str("LIFESPAN_DISTRIBUTION", "log_uniform")


def reload_config() -> None:
    """Reload config from environment. Safe to call every 2s for live reload."""
    _read_all()


# Initial load
_read_all()
