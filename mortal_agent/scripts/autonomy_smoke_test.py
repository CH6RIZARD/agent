#!/usr/bin/env python3
"""Autonomy smoke: will kernel, command gate, intent loop, action commit."""

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agent_core.threat_model import LifeState, would_die
from agent_core.will_kernel import select_action
from agent_core.action_commit import commit_begin, commit_end, in_commit_window, block_reversal
from agent_core.intent_loop import generate_internal_proposals
from agent_core.will_config import WILL_RISK_THRESHOLD


def test_low_risk_accepted():
    state = LifeState(energy=80.0, damage=10.0, hazard_score=0.2, power_on=True, sensors_streaming=True, motor_outputs_possible=True)
    proposals = [{"action_type": "reply", "payload": {}, "expected_dt_impact": 0.85, "risk": 0.1}]
    result = select_action(proposals, state, risk_threshold=WILL_RISK_THRESHOLD)
    assert result.outcome == "accepted"
    assert result.proposal is not None


def test_high_risk_refused():
    state = LifeState(energy=80.0, damage=10.0, hazard_score=0.2, power_on=True, sensors_streaming=True, motor_outputs_possible=True)
    proposals = [{"action_type": "danger", "payload": {}, "expected_dt_impact": 0.2, "risk": 0.9}]
    result = select_action(proposals, state, risk_threshold=WILL_RISK_THRESHOLD)
    assert result.outcome in ("refused", "modified")


def test_no_input_self_act():
    state = LifeState(energy=80.0, damage=5.0, hazard_score=0.2, power_on=True, sensors_streaming=True, motor_outputs_possible=True)
    proposals = generate_internal_proposals(state, delta_t=10.0, last_action="")
    assert len(proposals) >= 1
    result = select_action(proposals, state, risk_threshold=WILL_RISK_THRESHOLD)
    assert result.outcome in ("accepted", "modified", "refused")


def test_mid_commit_blocked():
    commit_end()
    assert not in_commit_window()
    ok = commit_begin("test")
    assert ok is True
    assert block_reversal() is True
    time.sleep(0.6)
    commit_end()
    assert not in_commit_window()


def test_would_die():
    assert would_die(LifeState(energy=0.0, damage=0.0, hazard_score=0.0, power_on=True, sensors_streaming=True, motor_outputs_possible=True)) is True


if __name__ == "__main__":
    test_low_risk_accepted()
    test_high_risk_refused()
    test_no_input_self_act()
    test_mid_commit_blocked()
    test_would_die()
    print("autonomy_smoke_test: all passed.")
