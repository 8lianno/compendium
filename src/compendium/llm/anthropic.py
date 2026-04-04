"""Anthropic Claude LLM provider."""

from __future__ import annotations

from typing import TYPE_CHECKING

import anthropic

from compendium.llm.provider import (
    CompletionRequest,
    CompletionResponse,
    StreamChunk,
    TokenPricing,
    TokenUsage,
)
from compendium.llm.retry import with_retry

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

# Pricing as of 2025 (USD per million tokens)
ANTHROPIC_PRICING: dict[str, TokenPricing] = {
    "claude-opus-4-20250514": TokenPricing(input_per_million=15.0, output_per_million=75.0),
    "claude-sonnet-4-20250514": TokenPricing(input_per_million=3.0, output_per_million=15.0),
    "claude-haiku-4-20250506": TokenPricing(input_per_million=0.80, output_per_million=4.0),
}

ANTHROPIC_CONTEXT_WINDOWS: dict[str, int] = {
    "claude-opus-4-20250514": 200_000,
    "claude-sonnet-4-20250514": 200_000,
    "claude-haiku-4-20250506": 200_000,
}

DEFAULT_MODEL = "claude-sonnet-4-20250514"


class AnthropicProvider:
    """Anthropic Claude provider using the official SDK."""

    def __init__(self, api_key: str, model: str = DEFAULT_MODEL) -> None:
        self._client = anthropic.AsyncAnthropic(api_key=api_key)
        self._model = model

    @property
    def name(self) -> str:
        return "anthropic"

    @property
    def model_name(self) -> str:
        return self._model

    @property
    def context_window(self) -> int:
        return ANTHROPIC_CONTEXT_WINDOWS.get(self._model, 200_000)

    @property
    def pricing(self) -> TokenPricing:
        return ANTHROPIC_PRICING.get(
            self._model, TokenPricing(input_per_million=3.0, output_per_million=15.0)
        )

    def estimate_tokens(self, text: str) -> int:
        """Rough estimate: ~4 chars per token for English text."""
        return len(text) // 4

    async def complete(self, request: CompletionRequest) -> CompletionResponse:
        """Send a completion request to Anthropic."""
        messages = [{"role": m.role, "content": m.content} for m in request.messages]

        kwargs: dict = {
            "model": self._model,
            "messages": messages,
            "max_tokens": request.max_tokens,
            "temperature": request.temperature,
        }
        if request.system_prompt:
            kwargs["system"] = request.system_prompt
        if request.stop_sequences:
            kwargs["stop_sequences"] = request.stop_sequences

        response = await with_retry(self._client.messages.create, **kwargs)

        content = ""
        for block in response.content:
            if block.type == "text":
                content += block.text

        return CompletionResponse(
            content=content,
            usage=TokenUsage(
                input_tokens=response.usage.input_tokens,
                output_tokens=response.usage.output_tokens,
            ),
            model=response.model,
            stop_reason=response.stop_reason or "",
        )

    async def complete_stream(self, request: CompletionRequest) -> AsyncIterator[StreamChunk]:
        """Stream a completion from Anthropic."""
        messages = [{"role": m.role, "content": m.content} for m in request.messages]

        kwargs: dict = {
            "model": self._model,
            "messages": messages,
            "max_tokens": request.max_tokens,
            "temperature": request.temperature,
        }
        if request.system_prompt:
            kwargs["system"] = request.system_prompt
        if request.stop_sequences:
            kwargs["stop_sequences"] = request.stop_sequences

        async with self._client.messages.stream(**kwargs) as stream:
            async for text in stream.text_stream:
                yield StreamChunk(text=text)

            # Final chunk with usage
            final_message = await stream.get_final_message()
            yield StreamChunk(
                is_final=True,
                usage=TokenUsage(
                    input_tokens=final_message.usage.input_tokens,
                    output_tokens=final_message.usage.output_tokens,
                ),
            )

    async def test_connection(self) -> bool:
        """Test connection by sending a minimal request."""
        try:
            response = await with_retry(
                self._client.messages.create,
                model=self._model,
                messages=[{"role": "user", "content": "ping"}],
                max_tokens=5,
            )
            return len(response.content) > 0
        except Exception:
            return False
