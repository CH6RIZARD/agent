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
