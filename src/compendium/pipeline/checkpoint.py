"""Checkpoint models for pipeline resume support."""

from __future__ import annotations

import json
from enum import StrEnum
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from pathlib import Path


class StepStatus(StrEnum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    PARTIAL = "partial"
    FAILED = "failed"


class TokenUsage(BaseModel):
    input_tokens: int = 0
    output_tokens: int = 0


class StepCheckpoint(BaseModel):
    """Checkpoint data for a single pipeline step."""

    status: StepStatus = StepStatus.PENDING
    started_at: str | None = None
    completed_at: str | None = None
    outputs: list[str] = Field(default_factory=list)
    completed_items: list[str] = Field(default_factory=list)
    failed_items: list[dict[str, str]] = Field(default_factory=list)
    pending_items: list[str] = Field(default_factory=list)
    tokens_used: TokenUsage = Field(default_factory=TokenUsage)
    cost_usd: float = 0.0


class CompilationCheckpoint(BaseModel):
    """Full compilation checkpoint stored at wiki/.staging/.checkpoint.json."""

    compilation_id: str = ""
    started_at: str = ""
    checkpoint_at: str = ""
    mode: str = "full"  # full | incremental
    source_manifest: dict[str, str] = Field(default_factory=dict)
    steps: dict[str, StepCheckpoint] = Field(default_factory=dict)
    total_tokens_used: TokenUsage = Field(default_factory=TokenUsage)
    total_cost_usd: float = 0.0

    @classmethod
    def load(cls, path: Path) -> CompilationCheckpoint | None:
        """Load checkpoint from file, or return None if not found."""
        if not path.exists():
            return None
        data = json.loads(path.read_text())
        return cls.model_validate(data)

    def save(self, path: Path) -> None:
        """Save checkpoint to file."""
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.model_dump_json(indent=2))
