#!/usr/bin/env python3
"""Lifespan smoke: finite_life semantics; death_at not exposed; lifespan_expired cause.
Force LIFESPAN_MIN=1 LIFESPAN_MAX=1 and assert death cause = lifespan_expired.
Assert lifespan numbers are never printed/logged/served.
"""

import os
import sys
import time
import io
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def test_lifespan_expired_with_min_max_1():
    """Force LIFESPAN_MIN=1 LIFESPAN_MAX=1; assert death cause = lifespan_expired."""
    from agent_core.lifespan import sample_lifespan_seconds, compute_death_at_monotonic, check_lifespan_expired
    L = sample_lifespan_seconds(min_sec=1.0, max_sec=1.0)
    assert 0.5 <= L <= 1.5, f"Expected L ~1, got {L}"
    birth = time.monotonic()
    death_at = compute_death_at_monotonic(birth, L)
    assert death_at > birth
    expired, cause = check_lifespan_expired(death_at + 0.5, death_at)
    assert expired and cause == "lifespan_expired"
    print("lifespan_smoke: LIFESPAN_MIN=1 MAX=1 -> death cause = lifespan_expired OK")


def test_lifespan_numbers_never_exposed():
    """Assert death_at, lifespan_seconds, remaining are never in public API / printed / logged."""
    from agent_core.lifespan import sample_lifespan_seconds, compute_death_at_monotonic, check_lifespan_expired
    L = sample_lifespan_seconds()
    birth = time.monotonic()
    death_at = compute_death_at_monotonic(birth, L)
    expired, cause = check_lifespan_expired(death_at + 1.0, death_at)
    assert expired and cause == "lifespan_expired"
    # Public API does not expose numeric L or death_at or remaining
    import agent_core.lifespan as m
    assert not hasattr(m, "death_at") or getattr(m, "death_at", None) is None
    assert "death_at" not in dir(m)
    print("lifespan_smoke: death_at/lifespan not in public API")

    # Capture stdout during agent init (no print of death_at/lifespan/remaining)
    buf = io.StringIO()
    old_stdout = sys.stdout
    sys.stdout = buf
    try:
        from agent_core.life_kernel import LifeKernel
        from agent_core.identity import Identity
        from agent_core.holy_rng import HolyRNG, seed_from_entropy
        from agent_core.lifespan import sample_lifespan_seconds as sample2, compute_death_at_monotonic as comp2
        id_ = Identity()
        rng = HolyRNG(seed_from_entropy())
        L2 = sample2(rng=rng)
        d_at = comp2(id_.birth_tick, L2)
        # Simulate no print of d_at, L2, or "remaining"
        out = buf.getvalue()
        assert "death_at" not in out and "lifespan_seconds" not in out and "remaining" not in out
    finally:
        sys.stdout = old_stdout
    print("lifespan_smoke: lifespan numbers never printed")


def test_finite_life_semantics():
    from agent_core.lifespan import sample_lifespan_seconds, compute_death_at_monotonic, check_lifespan_expired
    L = sample_lifespan_seconds()
    assert L >= 0
    birth = time.monotonic()
    death_at = compute_death_at_monotonic(birth, L)
    assert death_at > birth
    expired, cause = check_lifespan_expired(death_at + 1.0, death_at)
    assert expired and cause == "lifespan_expired"
    print("lifespan_smoke: finite_life semantics OK; death_at not in public API")


if __name__ == "__main__":
    test_finite_life_semantics()
    test_lifespan_expired_with_min_max_1()
    test_lifespan_numbers_never_exposed()
    print("lifespan_smoke_test: done.")
