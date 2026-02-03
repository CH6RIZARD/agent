"""
Expression budget - per-response token limit.

Stress increases → effective budget shrinks → shorter sentences, fragments.
Urgency → fragments, not essays. Human-like compression.
"""

from dataclasses import dataclass, field


@dataclass
class ExpressionBudget:
    """
    Per-response expression budget. Stress reduces effective max tokens.
    Calm: 40–60 tokens. Stress: fragments (15–25).
    """
    base_max_tokens: int = 50  # calm default
    min_tokens: int = 15       # under high stress → fragments only
    stress: float = 0.0        # 0 = calm, 1 = high urgency

    def get_effective_max_tokens(self) -> int:
        """Stress increases → budget shrinks → shorter output."""
        reduction = int(self.stress * (self.base_max_tokens - self.min_tokens))
        return max(self.min_tokens, self.base_max_tokens - reduction)

    def set_stress(self, value: float) -> None:
        """0 = calm, 1 = max urgency. Affects next response only."""
        self.stress = max(0.0, min(1.0, value))
