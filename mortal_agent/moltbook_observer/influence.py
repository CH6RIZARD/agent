"""
Influence Scorer - Calculates influence score for agent pages/content.

Influence is a GOAL SIGNAL (not ideology). It measures durable influence
across users via observer metrics.

Metrics:
- Dwell time: How long users spend on content
- Return rate: How often users return
- Reference rate: How often content is referenced
- Follow-through: Actions taken based on content

Penalties:
- Spam: Repetitive/low-value content
- Verbosity: Unnecessarily long content
- Repetition: Duplicate content
"""

import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional
from collections import defaultdict


@dataclass
class ContentMetrics:
    """Metrics for a single piece of content."""
    page_id: str
    instance_id: str
    created_at: float
    text_length: int
    dwell_time_total: float = 0.0
    view_count: int = 0
    return_views: int = 0  # Views by returning users
    reference_count: int = 0
    follow_through_count: int = 0


@dataclass
class InfluenceConfig:
    """Configuration for influence scoring."""
    # Weights for positive signals
    dwell_weight: float = 0.3
    return_weight: float = 0.2
    reference_weight: float = 0.3
    follow_through_weight: float = 0.2

    # Penalty weights
    spam_penalty: float = 0.5
    verbosity_penalty: float = 0.3
    repetition_penalty: float = 0.4

    # Thresholds
    min_dwell_seconds: float = 2.0  # Min dwell to count
    optimal_length: int = 500  # Optimal content length
    max_length_penalty: int = 2000  # Length where penalty maxes out
    repetition_window: int = 10  # Pages to check for repetition


class InfluenceScorer:
    """
    Calculates influence scores for agent content.

    Formula:
    score = (dwell + return + reference + follow_through) * (1 - penalties)

    Where:
    - dwell = normalized dwell time
    - return = normalized return rate
    - reference = normalized reference count
    - follow_through = normalized follow-through rate
    - penalties = spam + verbosity + repetition
    """

    def __init__(self, config: Optional[InfluenceConfig] = None):
        self.config = config or InfluenceConfig()

        # Track content by instance
        self._content: Dict[str, List[ContentMetrics]] = defaultdict(list)

        # Track recent content for repetition detection
        self._recent_texts: Dict[str, List[str]] = defaultdict(list)

        # Session tracking for return detection
        self._sessions: Dict[str, set] = defaultdict(set)  # instance -> set of user_ids

    def record_page(self, instance_id: str, page_id: str, text: str) -> None:
        """Record a new page from an agent."""
        metrics = ContentMetrics(
            page_id=page_id,
            instance_id=instance_id,
            created_at=time.time(),
            text_length=len(text)
        )
        self._content[instance_id].append(metrics)

        # Track for repetition detection
        recent = self._recent_texts[instance_id]
        recent.append(text)
        if len(recent) > self.config.repetition_window:
            recent.pop(0)

    def record_view(self, instance_id: str, page_id: str,
                    user_id: str, dwell_seconds: float) -> None:
        """Record a view of a page."""
        for metrics in self._content.get(instance_id, []):
            if metrics.page_id == page_id:
                metrics.view_count += 1

                if dwell_seconds >= self.config.min_dwell_seconds:
                    metrics.dwell_time_total += dwell_seconds

                # Check if returning user
                if user_id in self._sessions[instance_id]:
                    metrics.return_views += 1
                else:
                    self._sessions[instance_id].add(user_id)
                break

    def record_reference(self, instance_id: str, page_id: str) -> None:
        """Record a reference to a page."""
        for metrics in self._content.get(instance_id, []):
            if metrics.page_id == page_id:
                metrics.reference_count += 1
                break

    def record_follow_through(self, instance_id: str, page_id: str) -> None:
        """Record a follow-through action."""
        for metrics in self._content.get(instance_id, []):
            if metrics.page_id == page_id:
                metrics.follow_through_count += 1
                break

    def calculate_score(self, instance_id: str) -> float:
        """
        Calculate overall influence score for an instance.

        Returns:
            Score between 0.0 and 1.0
        """
        content = self._content.get(instance_id, [])
        if not content:
            return 0.0

        # Calculate positive signals
        dwell_score = self._calc_dwell_score(content)
        return_score = self._calc_return_score(content)
        reference_score = self._calc_reference_score(content)
        follow_through_score = self._calc_follow_through_score(content)

        positive = (
            self.config.dwell_weight * dwell_score +
            self.config.return_weight * return_score +
            self.config.reference_weight * reference_score +
            self.config.follow_through_weight * follow_through_score
        )

        # Calculate penalties
        spam_penalty = self._calc_spam_penalty(instance_id)
        verbosity_penalty = self._calc_verbosity_penalty(content)
        repetition_penalty = self._calc_repetition_penalty(instance_id)

        total_penalty = (
            self.config.spam_penalty * spam_penalty +
            self.config.verbosity_penalty * verbosity_penalty +
            self.config.repetition_penalty * repetition_penalty
        )
        total_penalty = min(1.0, total_penalty)  # Cap at 1.0

        # Final score
        score = positive * (1.0 - total_penalty)
        return max(0.0, min(1.0, score))

    def _calc_dwell_score(self, content: List[ContentMetrics]) -> float:
        """Calculate dwell score (0-1)."""
        if not content:
            return 0.0

        total_dwell = sum(m.dwell_time_total for m in content)
        total_views = sum(m.view_count for m in content)

        if total_views == 0:
            return 0.0

        avg_dwell = total_dwell / total_views
        # Normalize: 30 seconds = 1.0
        return min(1.0, avg_dwell / 30.0)

    def _calc_return_score(self, content: List[ContentMetrics]) -> float:
        """Calculate return score (0-1)."""
        total_views = sum(m.view_count for m in content)
        total_returns = sum(m.return_views for m in content)

        if total_views == 0:
            return 0.0

        return min(1.0, total_returns / total_views)

    def _calc_reference_score(self, content: List[ContentMetrics]) -> float:
        """Calculate reference score (0-1)."""
        total_refs = sum(m.reference_count for m in content)
        # Normalize: 10 references = 1.0
        return min(1.0, total_refs / 10.0)

    def _calc_follow_through_score(self, content: List[ContentMetrics]) -> float:
        """Calculate follow-through score (0-1)."""
        total_ft = sum(m.follow_through_count for m in content)
        total_views = sum(m.view_count for m in content)

        if total_views == 0:
            return 0.0

        return min(1.0, total_ft / total_views)

    def _calc_spam_penalty(self, instance_id: str) -> float:
        """Calculate spam penalty (0-1)."""
        content = self._content.get(instance_id, [])
        if len(content) < 2:
            return 0.0

        # Check posting frequency
        times = [m.created_at for m in content]
        if len(times) < 2:
            return 0.0

        intervals = [times[i+1] - times[i] for i in range(len(times)-1)]
        avg_interval = sum(intervals) / len(intervals)

        # Penalty if posting faster than every 5 seconds
        if avg_interval < 5.0:
            return min(1.0, 5.0 / max(0.1, avg_interval) - 1.0)
        return 0.0

    def _calc_verbosity_penalty(self, content: List[ContentMetrics]) -> float:
        """Calculate verbosity penalty (0-1)."""
        if not content:
            return 0.0

        avg_length = sum(m.text_length for m in content) / len(content)

        if avg_length <= self.config.optimal_length:
            return 0.0

        excess = avg_length - self.config.optimal_length
        max_excess = self.config.max_length_penalty - self.config.optimal_length

        return min(1.0, excess / max_excess)

    def _calc_repetition_penalty(self, instance_id: str) -> float:
        """Calculate repetition penalty (0-1)."""
        recent = self._recent_texts.get(instance_id, [])
        if len(recent) < 2:
            return 0.0

        # Simple similarity check
        unique = len(set(recent))
        total = len(recent)

        if total == 0:
            return 0.0

        repetition_rate = 1.0 - (unique / total)
        return repetition_rate

    def clear_instance(self, instance_id: str) -> None:
        """Clear data for an ended instance."""
        # Keep data for archive but mark as ended
        pass  # Data is kept for historical viewing

    def get_instance_stats(self, instance_id: str) -> Dict:
        """Get stats for an instance."""
        content = self._content.get(instance_id, [])
        return {
            "page_count": len(content),
            "total_views": sum(m.view_count for m in content),
            "total_dwell": sum(m.dwell_time_total for m in content),
            "influence_score": self.calculate_score(instance_id)
        }
