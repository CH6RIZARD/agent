"""
Bounded planning call. LLM optional. Strict JSON output schema.
If confidence < threshold → DO NOT POST. Cooldown + rate limits.
"""

import json
import re
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass

# Schema for planner output
PLAN_SCHEMA = {
    "text": "string",
    "intent": "string",
    "confidence": "number (0..1)",
    "reasons": ["string", ...],
}

CONFIDENCE_THRESHOLD = 0.5
CONFIDENCE_ACT_IMMEDIATE = 0.8   # act immediately without asking
CONFIDENCE_QUICK_CHECK = 0.5     # quick check then act; below this ask guidance only if high-risk
MAX_REASONS = 5


@dataclass
class PlanResult:
    text: str
    intent: str
    confidence: float
    reasons: List[str]
    valid: bool

    def should_post(self, threshold: float = CONFIDENCE_THRESHOLD) -> bool:
        return self.valid and self.confidence >= threshold and (self.text or "").strip() != ""

    def should_act_immediately(self) -> bool:
        """Confidence > 0.8: act immediately."""
        return self.valid and self.confidence >= CONFIDENCE_ACT_IMMEDIATE

    def should_quick_check_then_act(self) -> bool:
        """Confidence > 0.5: quick check then act."""
        return self.valid and CONFIDENCE_QUICK_CHECK <= self.confidence < CONFIDENCE_ACT_IMMEDIATE

    def should_ask_if_high_risk(self, is_high_risk: bool) -> bool:
        """Below 0.5: ask guidance ONLY if action is high-risk. Low-risk never ask."""
        return self.valid and self.confidence < CONFIDENCE_QUICK_CHECK and is_high_risk


def parse_plan_response(raw: str) -> PlanResult:
    """
    Parse LLM or default response into bounded schema.
    Returns PlanResult; valid=False if parse failed.
    """
    empty = PlanResult(text="", intent="", confidence=0.0, reasons=[], valid=False)
    if not raw or not isinstance(raw, str):
        return empty
    raw = raw.strip()
    # Try JSON block
    try:
        # Find {...} in response
        match = re.search(r"\{[^{}]*\}", raw, re.DOTALL)
        if match:
            data = json.loads(match.group())
        else:
            data = json.loads(raw)
    except json.JSONDecodeError:
        # Fallback: treat whole as text, low confidence
        return PlanResult(
            text=raw[:500],
            intent="unknown",
            confidence=0.3,
            reasons=[],
            valid=True,
        )
    text = str(data.get("text") or "").strip()
    intent = str(data.get("intent") or "unknown").strip()
    try:
        confidence = float(data.get("confidence", 0))
        confidence = max(0.0, min(1.0, confidence))
    except (TypeError, ValueError):
        confidence = 0.0
    reasons = data.get("reasons")
    if isinstance(reasons, list):
        reasons = [str(r) for r in reasons[:MAX_REASONS]]
    else:
        reasons = []
    return PlanResult(text=text, intent=intent, confidence=confidence, reasons=reasons, valid=True)


def default_action() -> PlanResult:
    """No LLM. Default action = silence (no post)."""
    return PlanResult(text="", intent="default", confidence=0.0, reasons=[], valid=True)
