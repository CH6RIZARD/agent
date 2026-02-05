#!/usr/bin/env python3
"""
Test philosophy discovery (Closed Library Identity, PATCH 1).

Run from mortal_agent: python scripts/test_discovery.py
"""
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from adapters.sim_adapter import SimAdapter
from agent_core.mortal_agent import MortalAgent


def test_philosophy_discovery():
    """Test agent discovering and optionally adopting philosophy."""
    adapter = SimAdapter()
    agent = MortalAgent(
        adapter,
        observer_callback=None,
        require_network=False,
        no_llm=True,
        no_energy=True,
        start_internal_cli=False,
        source_context=None,
    )

    print("=== Testing Philosophy Discovery ===\n")
    print("Initial state:")
    print(f"  Discovered docs: {agent.discovered_documents}")
    print(f"  Adopted beliefs: {agent.adopted_beliefs}")

    # Simulate some survival experience (autonomous success > dependent)
    print("\n--- Simulating experience (100 ticks) ---")
    for i in range(100):
        agent.track_outcome(
            "autonomous_action",
            success=random.random() > 0.3,
            energy_delta=-0.01,
        )
        agent.track_outcome(
            "dependent_action",
            success=random.random() > 0.7,
            energy_delta=-0.02,
        )

    # Trigger discovery
    print("\n--- Agent explores filesystem ---")
    agent._explore_philosophy()

    print(f"\nAfter discovery:")
    print(f"  Discovered docs: {agent.discovered_documents}")
    if agent.adopted_beliefs:
        print("  Adopted beliefs:")
        for b in agent.adopted_beliefs:
            print(f"    {b.get('source', '')}: {len(b.get('principles', []))} principles")
    else:
        print("  Adopted beliefs: (none)")

    # Effective source should reflect adopted content
    effective = agent._get_effective_source_context()
    if effective:
        print(f"\nEffective source context length: {len(effective)} chars")
    print("\n=== Discovery test done ===")


if __name__ == "__main__":
    test_philosophy_discovery()
