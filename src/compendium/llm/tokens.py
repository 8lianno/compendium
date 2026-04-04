"""Token usage tracking and cost estimation."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from compendium.llm.provider import Operation, TokenPricing, TokenUsage


class TokenTracker:
    """Tracks token usage and costs across operations."""

    def __init__(self, usage_dir: Path | None = None) -> None:
        self._usage_dir = usage_dir or Path.home() / ".compendium" / "usage"
        self._usage_dir.mkdir(parents=True, exist_ok=True)
        self._session_usage: list[dict] = []

    def _month_file(self) -> Path:
        month = datetime.now(UTC).strftime("%Y-%m")
        return self._usage_dir / f"{month}.json"

    def record(
        self,
        operation: Operation,
        provider: str,
        model: str,
        usage: TokenUsage,
        pricing: TokenPricing,
        project: str = "",
        step: str = "",
    ) -> float:
        """Record token usage. Returns estimated cost in USD."""
        cost = pricing.estimate_cost(usage)
        entry = {
            "timestamp": datetime.now(UTC).isoformat(),
            "operation": operation.value,
            "project": project,
            "provider": provider,
            "model": model,
            "input_tokens": usage.input_tokens,
            "output_tokens": usage.output_tokens,
            "estimated_cost_usd": round(cost, 4),
            "step": step,
        }

        # Append to session
        self._session_usage.append(entry)

        # Append to monthly file
        month_file = self._month_file()
        data: dict = {"month": month_file.stem, "operations": [], "totals": {}}
        if month_file.exists():
            data = json.loads(month_file.read_text())

        data["operations"].append(entry)

        # Update totals
        totals = data.get("totals", {})
        totals["input_tokens"] = totals.get("input_tokens", 0) + usage.input_tokens
        totals["output_tokens"] = totals.get("output_tokens", 0) + usage.output_tokens
        totals["estimated_cost_usd"] = round(totals.get("estimated_cost_usd", 0) + cost, 4)
        data["totals"] = totals

        month_file.write_text(json.dumps(data, indent=2))
        return cost

    @property
    def session_total(self) -> TokenUsage:
        """Total tokens used in current session."""
        total_in = sum(e["input_tokens"] for e in self._session_usage)
        total_out = sum(e["output_tokens"] for e in self._session_usage)
        return TokenUsage(input_tokens=total_in, output_tokens=total_out)

    @property
    def session_cost(self) -> float:
        """Total estimated cost in current session."""
        return sum(e["estimated_cost_usd"] for e in self._session_usage)

    def get_monthly_summary(self) -> dict:
        """Get current month's usage summary."""
        month_file = self._month_file()
        if not month_file.exists():
            return {"month": month_file.stem, "operations": [], "totals": {}}
        return json.loads(month_file.read_text())

    def get_operation_breakdown(self) -> list[dict]:
        """Get usage breakdown by operation+model from current month."""
        summary = self.get_monthly_summary()
        ops = summary.get("operations", [])

        breakdown: dict[str, dict] = {}
        for op in ops:
            key = f"{op.get('operation', 'unknown')}|{op.get('model', 'unknown')}"
            if key not in breakdown:
                breakdown[key] = {
                    "operation": op.get("operation", "unknown"),
                    "model": op.get("model", "unknown"),
                    "provider": op.get("provider", "unknown"),
                    "input_tokens": 0,
                    "output_tokens": 0,
                    "estimated_cost_usd": 0.0,
                    "call_count": 0,
                }
            breakdown[key]["input_tokens"] += op.get("input_tokens", 0)
            breakdown[key]["output_tokens"] += op.get("output_tokens", 0)
            breakdown[key]["estimated_cost_usd"] += op.get("estimated_cost_usd", 0.0)
            breakdown[key]["call_count"] += 1

        return sorted(breakdown.values(), key=lambda x: -x["estimated_cost_usd"])
