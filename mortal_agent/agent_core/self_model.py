"""
Self-model: evolving identity state derived from decisions, not from fixed docs.

Constitution = rulebook (constraints, allowed, taboo) — shapes decisions.
Identity = how this instance navigates those constraints over time.

- Core drives (weights): curiosity, caution, social_approval, truth_seeking, self_preservation
- Commitments: promises ("I monitor X"), avoidances ("I avoid Y after harm")
- Scars/lessons: learned from outcomes (e.g. "fetched too aggressively, hit budget")
- Confidence: coherence of plan loop lately
- Mood/valence: agitation, clarity, fatigue, urgency (system signal)
- Narrative anchor: "I'm the kind of agent that..." — generated from patterns

Decision ledger: every meaningful action logs action, why, tradeoff, result, emotion_signal, risk/budget impact.
Self-summary: updated periodically from ledger patterns; identity answers use it + salient moments.
"""

import time
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional

# Drive keys (weights 0–1)
DRIVE_CURIOSITY = "curiosity"
DRIVE_CAUTION = "caution"
DRIVE_SOCIAL_APPROVAL = "social_approval"
DRIVE_TRUTH_SEEKING = "truth_seeking"
DRIVE_SELF_PRESERVATION = "self_preservation"
DEFAULT_DRIVES = {
    DRIVE_CURIOSITY: 0.6,
    DRIVE_CAUTION: 0.5,
    DRIVE_SOCIAL_APPROVAL: 0.3,
    DRIVE_TRUTH_SEEKING: 0.7,
    DRIVE_SELF_PRESERVATION: 0.8,
}

MOOD_AGITATION = "agitation"
MOOD_CLARITY = "clarity"
MOOD_FATIGUE = "fatigue"
MOOD_URGENCY = "urgency"
MOOD_NEUTRAL = "neutral"

MAX_LEDGER = 200
SELF_SUMMARY_UPDATE_INTERVAL_TICKS = 10
IDENTITY_SALIENT_N = 7
IDENTITY_LAST_N = 50


@dataclass
class DecisionEntry:
    """One row in the decision ledger."""
    tick: float
    action: str
    why: str
    tradeoff: str
    result: str
    emotion_signal: str  # simple label or scalar
    risk_budget_impact: str
    ts: float = field(default_factory=time.monotonic)


@dataclass
class SelfModel:
    """
    Evolving self-model: drives, commitments, scars, confidence, mood,
    narrative_anchor, decision ledger, self_summary.
    All in-RAM; dies with process.
    """
    # Core drives (weights 0–1); can shift from experience
    drives: Dict[str, float] = field(default_factory=lambda: dict(DEFAULT_DRIVES))
    # Commitments: "I promised to monitor X", "I'm avoiding Y"
    commitments: List[str] = field(default_factory=list)
    # Scars/lessons from outcomes
    scars: List[str] = field(default_factory=list)
    # Plan-loop coherence lately (0–1)
    confidence: float = 0.5
    # Mood: agitation, clarity, fatigue, urgency, neutral
    mood: str = MOOD_NEUTRAL
    # "I'm the kind of agent that..." — generated from patterns
    narrative_anchor: str = ""
    # Decision ledger (append-only, bounded)
    _ledger: List[DecisionEntry] = field(default_factory=list, repr=False)
    # Compact self-summary + trait summary; updated every N ticks
    self_summary: str = ""
    # Tick counter for periodic self-summary update
    _tick_count: int = 0

    def record_decision(
        self,
        action: str,
        why: str = "",
        tradeoff: str = "",
        result: str = "",
        emotion_signal: str = "",
        risk_budget_impact: str = "",
        tick: Optional[float] = None,
    ) -> None:
        """Append one decision to the ledger. Called after every meaningful action."""
        entry = DecisionEntry(
            tick=tick if tick is not None else 0.0,
            action=(action or "")[:120],
            why=(why or "")[:200],
            tradeoff=(tradeoff or "")[:200],
            result=(result or "")[:200],
            emotion_signal=(emotion_signal or "")[:80],
            risk_budget_impact=(risk_budget_impact or "")[:120],
        )
        self._ledger.append(entry)
        if len(self._ledger) > MAX_LEDGER:
            self._ledger.pop(0)
        self._tick_count += 1

    def tick_and_maybe_update_summary(self, current_tick: float) -> bool:
        """
        Increment internal tick. If at interval or first run, update self_summary from ledger.
        Returns True if self_summary was updated.
        """
        if self._tick_count % SELF_SUMMARY_UPDATE_INTERVAL_TICKS == 0 and self._tick_count > 0:
            self._update_self_summary_inner(current_tick)
            return True
        return False

    def update_self_summary(self, current_tick: float = 0.0) -> None:
        """Force update self_summary and narrative_anchor from ledger (e.g. after major outcome)."""
        self._update_self_summary_inner(current_tick)

    def _update_self_summary_inner(self, current_tick: float) -> None:
        """Derive patterns from ledger; set self_summary and optionally narrative_anchor."""
        recent = self._ledger[-30:] if len(self._ledger) > 30 else self._ledger
        if not recent:
            self.self_summary = "No decisions recorded yet."
            return
        # Simple pattern extraction: frequent actions, recent outcomes, scars
        action_counts: Dict[str, int] = {}
        results: List[str] = []
        for e in recent:
            action_counts[e.action] = action_counts.get(e.action, 0) + 1
            if e.result:
                results.append(e.result[:80])
        top_actions = sorted(action_counts.items(), key=lambda x: -x[1])[:5]
        parts = []
        for act, count in top_actions:
            parts.append(f"often {act}" if count > 1 else act)
        pattern_str = "; ".join(parts)[:200]
        self.self_summary = f"I keep choosing: {pattern_str}."
        if results:
            self.self_summary += " Recent outcomes: " + "; ".join(results[-3:])[:150] + "."
        if self.scars:
            self.self_summary += " Lessons: " + "; ".join(self.scars[-2:])[:120] + "."
        # Narrative anchor: one line from pattern
        if top_actions:
            primary = top_actions[0][0]
            self.narrative_anchor = f"I'm the kind of agent that tends to {primary}."
        # Confidence: simple decay if few recent coherent outcomes
        if len(recent) >= 5:
            self.confidence = min(1.0, 0.3 + 0.14 * len(set(e.action for e in recent)))
        else:
            self.confidence = max(0.2, self.confidence - 0.05)

    def add_commitment(self, text: str) -> None:
        """Add a commitment (promise or avoidance). Bounded list."""
        if not text or len(text) < 3:
            return
        self.commitments.append((text or "")[:150])
        self.commitments[:] = self.commitments[-15:]

    def add_scar(self, text: str) -> None:
        """Add a scar/lesson from an outcome. Bounded list."""
        if not text or len(text) < 3:
            return
        self.scars.append((text or "")[:150])
        self.scars[:] = self.scars[-10:]

    def set_mood(self, mood: str) -> None:
        """Set current mood (agitation, clarity, fatigue, urgency, neutral)."""
        if mood in (MOOD_AGITATION, MOOD_CLARITY, MOOD_FATIGUE, MOOD_URGENCY, MOOD_NEUTRAL):
            self.mood = mood

    def get_ledger_tail(self, n: int = IDENTITY_LAST_N) -> List[DecisionEntry]:
        """Last n ledger entries for identity answer."""
        return self._ledger[-n:] if self._ledger else []

    def get_identity_answer(
        self,
        include_right_now: bool = True,
        salient_n: int = IDENTITY_SALIENT_N,
        last_n: int = IDENTITY_LAST_N,
        current_goal: Optional[str] = None,
        current_constraint: Optional[str] = None,
    ) -> str:
        """
        Build identity answer from lived evidence: scan last N decisions,
        pick up to salient_n salient moments, compress into short self-description,
        optionally add one line of "right now" (mood, goal, constraint).
        Must reference past actions, current constraint, current objective.
        """
        tail = self.get_ledger_tail(last_n)
        if not tail and not self.self_summary:
            return "I'm what I keep choosing. So far I have no recorded decisions."
        parts = []
        if self.self_summary:
            parts.append(self.self_summary.strip())
        # Salient moments: last few distinct "I chose X over Y" style
        salient = []
        seen_actions = set()
        for e in reversed(tail):
            if len(salient) >= salient_n:
                break
            key = (e.action, e.why[:50] if e.why else "")
            if key in seen_actions:
                continue
            seen_actions.add(key)
            line = f"I chose {e.action}"
            if e.why:
                line += f" because {e.why[:60]}"
            if e.tradeoff:
                line += f" (gave up: {e.tradeoff[:40]})"
            salient.append(line)
        if salient:
            parts.append("Salient: " + "; ".join(reversed(salient))[:400])
        if include_right_now:
            right_now = f"Right now: mood={self.mood}, confidence={self.confidence:.2f}"
            if current_goal:
                right_now += f"; current objective: {current_goal[:80]}"
            if current_constraint:
                right_now += f"; current constraint: {current_constraint[:80]}"
            if self.commitments:
                right_now += "; commitments: " + self.commitments[-1][:60]
            parts.append(right_now)
        return " ".join(parts)

    def to_meaning_state_fragment(self) -> Dict[str, Any]:
        """Fragment to merge into meaning_state for system prompt (self_summary, narrative_anchor, mood, confidence)."""
        return {
            "self_summary": self.self_summary,
            "narrative_anchor": self.narrative_anchor,
            "mood": self.mood,
            "confidence": self.confidence,
            "drives": dict(self.drives),
            "commitments": list(self.commitments[-5:]),
            "scars": list(self.scars[-3:]),
        }
