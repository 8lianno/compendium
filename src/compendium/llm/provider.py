"""Abstract LLM provider protocol and shared types."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from collections.abc import AsyncIterator


class Operation(StrEnum):
    """Operations that can be assigned to different models."""

    COMPILATION = "compilation"
    QA = "qa"
    LINT = "lint"


@dataclass
class Message:
    role: str  # "user" | "assistant" | "system"
    content: str


@dataclass
class CompletionRequest:
    messages: list[Message]
    system_prompt: str | None = None
    max_tokens: int = 4096
    temperature: float = 0.3
    stop_sequences: list[str] = field(default_factory=list)


@dataclass
class TokenUsage:
    input_tokens: int = 0
    output_tokens: int = 0


@dataclass
class CompletionResponse:
    content: str
    usage: TokenUsage
    model: str = ""
    stop_reason: str = ""


@dataclass
class StreamChunk:
    text: str = ""
    is_final: bool = False
    usage: TokenUsage | None = None


@dataclass
class TokenPricing:
    """USD per million tokens."""

    input_per_million: float = 0.0
    output_per_million: float = 0.0

    def estimate_cost(self, usage: TokenUsage) -> float:
        return (
            usage.input_tokens * self.input_per_million / 1_000_000
            + usage.output_tokens * self.output_per_million / 1_000_000
        )


@runtime_checkable
class LlmProvider(Protocol):
    """Protocol that all LLM providers must implement."""

    @property
    def name(self) -> str:
        """Provider name (anthropic, openai, gemini, ollama)."""
        ...

    @property
    def model_name(self) -> str:
        """Model identifier."""
        ...

    @property
    def context_window(self) -> int:
        """Context window size in tokens."""
        ...

    async def complete(self, request: CompletionRequest) -> CompletionResponse:
        """Send a chat completion request."""
        ...

    async def complete_stream(self, request: CompletionRequest) -> AsyncIterator[StreamChunk]:
        """Send a streaming chat completion request."""
        ...

    def estimate_tokens(self, text: str) -> int:
        """Estimate token count for text."""
        ...

    async def test_connection(self) -> bool:
        """Test connection and validate API key. Returns True on success."""
        ...

    @property
    def pricing(self) -> TokenPricing:
        """Pricing info for cost estimation."""
        ...
