"""
Tests for identity invariants.

These tests verify:
1. No persistence across restarts
2. New instance_id per run
3. Death is terminal
4. Δt gating works correctly
"""

import time
import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from agent_core.identity import Identity, create_new_identity
from agent_core.embodied_gate import EmbodiedGate, GateStatus, GateFailureCause
from agent_core.events import BirthEvent, EndedEvent, HeartbeatEvent
from adapters.sim_adapter import SimAdapter
from observer_ui import ObserverServer


class TestIdentityInvariants:
    """Test identity invariants."""

    def test_unique_instance_id_per_creation(self):
        """Each Identity creation produces a unique instance_id."""
        ids = set()
        for _ in range(100):
            identity = create_new_identity()
            assert identity.instance_id not in ids, "Duplicate instance_id!"
            ids.add(identity.instance_id)

    def test_delta_t_starts_at_zero(self):
        """New identity has delta_t = 0."""
        identity = Identity()
        assert identity.delta_t == 0.0

    def test_delta_t_only_increments_with_gate_open(self):
        """Δt only increases when gate_open=True."""
        identity = Identity()

        # Tick with gate closed
        time.sleep(0.05)
        identity.tick(gate_open=False)
        assert identity.delta_t == 0.0, "Δt increased with gate closed"

        # Tick with gate open
        time.sleep(0.05)
        dt = identity.tick(gate_open=True)
        assert dt > 0.0, "Δt didn't increase with gate open"

        # Tick with gate closed again
        old_dt = identity.delta_t
        time.sleep(0.05)
        identity.tick(gate_open=False)
        assert identity.delta_t == old_dt, "Δt increased after gate closed"

    def test_death_is_permanent(self):
        """Once dead, identity stays dead."""
        identity = Identity()
        assert identity.alive is True

        identity.die("test_cause")
        assert identity.alive is False

        # Try to tick after death
        old_dt = identity.delta_t
        identity.tick(gate_open=True)
        assert identity.delta_t == old_dt, "Δt changed after death"

    def test_internal_state_cleared_on_death(self):
        """Internal state is cleared when identity dies."""
        identity = Identity()
        identity.update_state("key1", "value1")
        identity.update_state("key2", "value2")

        assert len(identity.internal_state) == 2

        identity.die("test")
        assert len(identity.internal_state) == 0

    def test_internal_state_is_ram_only(self):
        """Internal state exists only in memory (no persistence API)."""
        identity = Identity()
        identity.update_state("secret", "data")

        # Verify there's no save/load/persist methods
        assert not hasattr(identity, 'save')
        assert not hasattr(identity, 'load')
        assert not hasattr(identity, 'persist')
        assert not hasattr(identity, 'serialize')

        # The only way to access state is through the object
        assert identity.get_state("secret") == "data"


class TestEmbodiedGate:
    """Test embodied gate behavior."""

    def test_gate_open_requires_all_conditions(self):
        """Gate is only open when power, sensors, AND actuators are all True."""
        adapter = SimAdapter(initial_power=True, initial_sensors=True, initial_actuators=True)
        gate = EmbodiedGate(adapter)

        # All on = open
        status = gate.check()
        assert status.open is True

        # Power off = closed
        adapter.kill_power()
        status = gate.check()
        assert status.open is False
        assert status.failure_cause == GateFailureCause.POWER_LOSS

        adapter.restore_power()

        # Sensors off = closed
        adapter.kill_sensors()
        status = gate.check()
        assert status.open is False
        assert status.failure_cause == GateFailureCause.SENSORS_OFFLINE

        adapter.restore_sensors()

        # Actuators off = closed
        adapter.kill_actuators()
        status = gate.check()
        assert status.open is False
        assert status.failure_cause == GateFailureCause.ACTUATORS_DISABLED

    def test_force_close_is_permanent(self):
        """Force-closing the gate is permanent within the process."""
        adapter = SimAdapter()
        gate = EmbodiedGate(adapter)

        assert gate.is_open() is True

        gate.force_close()
        assert gate.is_open() is False

        # Even with adapter restored, force_close keeps it closed
        assert gate.is_open() is False


class TestObserverEventRejection:
    """Test that observer rejects events for ended instances."""

    def test_observer_accepts_birth(self):
        """Observer accepts BIRTH event."""
        observer = ObserverServer(port=19001)
        event = BirthEvent("test-id-1")
        assert observer.handle_event(event) is True

    def test_observer_accepts_heartbeat_for_living(self):
        """Observer accepts HEARTBEAT for living instance."""
        observer = ObserverServer(port=19002)

        birth = BirthEvent("test-id-2")
        observer.handle_event(birth)

        heartbeat = HeartbeatEvent("test-id-2", 1.0, True, True, True)
        assert observer.handle_event(heartbeat) is True

    def test_observer_rejects_events_after_ended(self):
        """Observer rejects all events after ENDED for that instance."""
        observer = ObserverServer(port=19003)

        # Birth
        birth = BirthEvent("test-id-3")
        observer.handle_event(birth)

        # End
        ended = EndedEvent("test-id-3", "test", 5.0)
        assert observer.handle_event(ended) is True

        # Try heartbeat after ended
        heartbeat = HeartbeatEvent("test-id-3", 6.0, True, True, True)
        assert observer.handle_event(heartbeat) is False

        # Try another birth with same ID (should also fail)
        birth2 = BirthEvent("test-id-3")
        assert observer.handle_event(birth2) is False

    def test_different_instance_still_accepted(self):
        """Ending one instance doesn't affect others."""
        observer = ObserverServer(port=19004)

        # Instance A
        birth_a = BirthEvent("instance-a")
        observer.handle_event(birth_a)
        ended_a = EndedEvent("instance-a", "test", 5.0)
        observer.handle_event(ended_a)

        # Instance B (different) should work
        birth_b = BirthEvent("instance-b")
        assert observer.handle_event(birth_b) is True

        heartbeat_b = HeartbeatEvent("instance-b", 1.0, True, True, True)
        assert observer.handle_event(heartbeat_b) is True


class TestNoPersistence:
    """Test that no persistence mechanisms exist."""

    def test_no_file_operations_on_identity(self):
        """Identity has no file I/O methods."""
        identity = Identity()

        # Check for absence of persistence methods
        forbidden_methods = [
            'save', 'load', 'persist', 'serialize', 'deserialize',
            'to_file', 'from_file', 'dump', 'restore', 'checkpoint',
            'snapshot', 'export', 'import_'
        ]

        for method in forbidden_methods:
            assert not hasattr(identity, method), f"Identity has forbidden method: {method}"

    def test_internal_state_not_in_dict(self):
        """Internal state uses private attribute to discourage persistence."""
        identity = Identity()
        identity.update_state("key", "value")

        # The internal state should be in _internal_state (private)
        assert hasattr(identity, '_internal_state')

        # Public dict/json methods should not expose it directly
        assert 'internal_state' not in identity.__dict__


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
