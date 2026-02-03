#!/usr/bin/env python3
"""
Energy smoke test: drain uses dt and does not instantly drop to 0.
"""

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agent_core.runtime_state import RuntimeState


def test_energy_drain_uses_dt():
    """Energy drains by rate * dt, not instant zero."""
    state = RuntimeState()
    state.energy = 1.0
    initial = state.energy
    dt = 0.1
    for _ in range(10):
        state.tick(True, dt)
    assert state.energy < initial
    assert state.energy > 0.0
    assert state.energy > 0.5
    print("energy_smoke: drain uses dt, no instant drop")


def test_energy_drain_rate_configurable():
    """Drain rate is applied per second via dt."""
    state = RuntimeState()
    state.energy = 1.0
    state.tick(True, 1.0)
    assert state.energy < 1.0
    assert state.energy > 0.0
    print("energy_smoke: rate * dt applied")


def test_energy_60s_sim_slow_drain():
    """Run 60s sim; energy decreases slowly, not instantly to 0."""
    state = RuntimeState()
    state.energy = 1.0
    dt = 0.1
    total_ticks = 600
    for _ in range(total_ticks):
        state.tick(True, dt)
    assert state.energy > 0.0, "Energy must not drop to 0 in 60s with default drain"
    assert state.energy < 1.0
    print("energy_smoke: 60s sim, energy decreases slowly, no instant drop")


if __name__ == "__main__":
    test_energy_drain_uses_dt()
    test_energy_drain_rate_configurable()
    test_energy_60s_sim_slow_drain()
    print("energy_smoke_test: done.")
