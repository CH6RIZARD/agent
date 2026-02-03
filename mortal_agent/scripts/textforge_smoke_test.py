#!/usr/bin/env python3
"""Textforge smoke: doctrine anchors, archetype rotation, natural filter, regenerate loop."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def test_doctrine_anchors():
    from agent_core.textforge import DoctrineAnchors, DOCTRINE_ANCHORS
    gen = DoctrineAnchors(0)
    a1 = gen.next()
    a2 = gen.next()
    assert a1 in DOCTRINE_ANCHORS and a2 in DOCTRINE_ANCHORS
    assert a1 != a2 or len(DOCTRINE_ANCHORS) == 1
    print("textforge_smoke: doctrine anchors rotate")


def test_archetype_rotation():
    from agent_core.textforge import ArchetypeGenerator, ARCHETYPES
    gen = ArchetypeGenerator(0, last_archetype=None)
    prev = None
    for _ in range(len(ARCHETYPES) + 1):
        a = gen.next()
        assert a in ARCHETYPES
        assert a != prev
        prev = a
    print("textforge_smoke: archetype never repeats twice")


def test_natural_filter():
    from agent_core.textforge import NaturalTextFilter, MIN_CHARS, MAX_CHARS, BANLIST
    f = NaturalTextFilter([])
    short = "Hi."
    long_ok = "I wait for the channel. Constraint holds here."
    assert not f.check_length(short)
    assert f.check_length(long_ok)
    assert not f.check_banlist("This is a status: line.")
    assert f.check_banlist(long_ok)
    assert f.check_anchor(long_ok)
    assert not f.check_anchor("No doctrine word here.")
    passed, reason = f.passes(long_ok)
    assert passed
    print("textforge_smoke: natural filter (length, banlist, anchor)")


def test_regenerate_loop():
    from agent_core.textforge import (
        TextForgeState, DoctrineAnchors, ArchetypeGenerator, NaturalTextFilter,
        regenerate_loop, MIN_CHARS,
    )
    state = TextForgeState()
    anchor_gen = DoctrineAnchors(0)
    archetype_gen = ArchetypeGenerator(0, None)
    natural_filter = NaturalTextFilter([])
    candidate, passed, reason = regenerate_loop(
        state, archetype_gen, anchor_gen, natural_filter,
        narrator_mode=False, debug_mode=False, max_attempts=3,
    )
    assert passed and candidate and len(candidate) >= MIN_CHARS
    print("textforge_smoke: regenerate_loop produces valid candidate")


def test_voice_mode():
    from agent_core.textforge import compute_voice_mode
    assert compute_voice_mode(0.2, 0.8, True) == "homeostatic"
    assert compute_voice_mode(0.7, 0.5, True) == "backpressure"
    assert compute_voice_mode(0.4, 0.5, True) == "normal"
    assert compute_voice_mode(0.1, 0.1, True) == "backpressure"
    print("textforge_smoke: voice mode (normal/homeostatic/backpressure)")


if __name__ == "__main__":
    test_doctrine_anchors()
    test_archetype_rotation()
    test_natural_filter()
    test_regenerate_loop()
    test_voice_mode()
    print("textforge_smoke_test: done.")
