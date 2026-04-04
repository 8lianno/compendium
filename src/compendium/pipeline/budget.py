"""Token budget allocation and graceful degradation for compilation pipeline."""

from __future__ import annotations

from dataclasses import dataclass

# Default proportional allocation across 6 steps
DEFAULT_ALLOCATIONS = {
    "summarize": 0.25,
    "extract_concepts": 0.05,
    "generate_articles": 0.45,
    "create_backlinks": 0.08,
    "build_index": 0.07,
    "detect_conflicts": 0.10,
}


@dataclass
class BudgetState:
    """Tracks token budget consumption during compilation."""

    total_budget: int
    consumed: int = 0

    @property
    def remaining(self) -> int:
        return max(0, self.total_budget - self.consumed)

    @property
    def pct_used(self) -> float:
        if self.total_budget == 0:
            return 0.0
        return self.consumed / self.total_budget

    def consume(self, tokens: int) -> None:
        self.consumed += tokens

    def allocation_for(self, step: str) -> int:
        """Get the token allocation for a specific step."""
        pct = DEFAULT_ALLOCATIONS.get(step, 0.1)
        return int(self.total_budget * pct)

    def should_degrade(self) -> bool:
        """Check if budget is tight enough to trigger degradation."""
        return self.pct_used > 0.7

    def get_degradation_params(self) -> dict:
        """Get adjusted parameters when budget is tight."""
        if not self.should_degrade():
            return {}

        remaining_pct = 1.0 - self.pct_used
        params: dict = {}

        if remaining_pct < 0.15:
            # Severe: skip conflicts, minimal summaries
            params["skip_conflicts"] = True
            params["max_summary_tokens"] = 500
            params["article_generation_threshold"] = 4  # Need 4+ sources
        elif remaining_pct < 0.25:
            # Moderate: reduce article count, shorter summaries
            params["max_summary_tokens"] = 800
            params["article_generation_threshold"] = 3
        else:
            # Mild: just reduce summary length
            params["max_summary_tokens"] = 1200

        return params
