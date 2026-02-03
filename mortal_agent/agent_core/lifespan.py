"""
Hidden finite lifespan. TempleOS holy RNG style.
On birth: sample L (seconds) from high-range RNG. death_at = birth_monotonic + L.
Never expose L, death_at, or remaining time. Agent may know life is finite only.
"""

import math
from typing import Tuple, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .holy_rng import HolyRNG

try:
    from .will_config import (
        LIFESPAN_ENABLED,
        LIFESPAN_MIN_SECONDS,
        LIFESPAN_MAX_SECONDS,
        LIFESPAN_DISTRIBUTION,
    )
except ImportError:
    LIFESPAN_ENABLED = True
    LIFESPAN_MIN_SECONDS = 3600.0
    LIFESPAN_MAX_SECONDS = 172800.0
    LIFESPAN_DISTRIBUTION = "log_uniform"


def sample_lifespan_seconds(
    min_sec: float = LIFESPAN_MIN_SECONDS,
    max_sec: float = LIFESPAN_MAX_SECONDS,
    distribution: str = LIFESPAN_DISTRIBUTION,
    rng: Optional["HolyRNG"] = None,
) -> float:
    """
    Sample L (seconds). Log-uniform or uniform. Never expose result to agent/observer/LLM.
    Uses holy_rng if provided; otherwise falls back to os.urandom.
    """
    if min_sec <= 0 or max_sec < min_sec:
        min_sec = 3600.0
        max_sec = 172800.0
    if rng is not None:
        u = rng.uniform_01()
    else:
        import os
        b = os.urandom(8)
        v = int.from_bytes(b, "big") & ((1 << 53) - 1)
        u = v / (1 << 53)
    if distribution == "log_uniform":
        log_min = math.log(min_sec)
        log_max = math.log(max_sec)
        log_L = log_min + u * (log_max - log_min)
        return math.exp(log_L)
    return min_sec + u * (max_sec - min_sec)


def compute_death_at_monotonic(birth_monotonic: float, lifespan_seconds: float) -> float:
    """death_at = birth + L. Private; never expose."""
    return birth_monotonic + lifespan_seconds


def check_lifespan_expired(now_monotonic: float, death_at: float) -> Tuple[bool, str]:
    """
    Returns (expired, cause). cause is 'lifespan_expired' if now >= death_at.
    Never expose death_at or remaining.
    """
    if now_monotonic >= death_at:
        return (True, "lifespan_expired")
    return (False, "")
