"""OpenAI LLM provider."""

from __future__ import annotations

from typing import TYPE_CHECKING

import openai

from compendium.llm.provider import (
    CompletionRequest,
    CompletionResponse,
    StreamChunk,
    TokenPricing,
    TokenUsage,
)

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

# Pricing as of 2025 (USD per million tokens)
OPENAI_PRICING: dict[str, TokenPricing] = {
    "gpt-4o": TokenPricing(input_per_million=2.50, output_per_million=10.0),
    "gpt-4o-mini": TokenPricing(input_per_million=0.15, output_per_million=0.60),
    "gpt-4.1": TokenPricing(input_per_million=2.0, output_per_million=8.0),
    "gpt-4.1-mini": TokenPricing(input_per_million=0.40, output_per_million=1.60),
    "gpt-4.1-nano": TokenPricing(input_per_million=0.10, output_per_million=0.40),
    "o3-mini": TokenPricing(input_per_million=1.10, output_per_million=4.40),
}

OPENAI_CONTEXT_WINDOWS: dict[str, int] = {
    "gpt-4o": 128_000,
    "gpt-4o-mini": 128_000,
    "gpt-4.1": 1_047_576,
    "gpt-4.1-mini": 1_047_576,
    "gpt-4.1-nano": 1_047_576,
    "o3-mini": 200_000,
}

DEFAULT_MODEL = "gpt-4o"


class OpenAIProvider:
    """OpenAI provider using the official SDK."""

    def __init__(
        self,
        api_key: str,
        model: str = DEFAULT_MODEL,
        base_url: str | None = None,
    ) -> None:
        kwargs: dict = {"api_key": api_key}
        if base_url:
            kwargs["base_url"] = base_url
        self._client = openai.AsyncOpenAI(**kwargs)
        self._model = model

    @property
    def name(self) -> str:
        return "openai"

    @property
    def model_name(self) -> str:
        return self._model

    @property
    def context_window(self) -> int:
        return OPENAI_CONTEXT_WINDOWS.get(self._model, 128_000)

    @property
    def pricing(self) -> TokenPricing:
        return OPENAI_PRICING.get(
            self._model, TokenPricing(input_per_million=2.50, output_per_million=10.0)
        )

    def estimate_tokens(self, text: str) -> int:
        return len(text) // 4

    async def complete(self, request: CompletionRequest) -> CompletionResponse:
        messages: list[dict] = []
        if request.system_prompt:
            messages.append({"role": "system", "content": request.system_prompt})
        messages.extend({"role": m.role, "content": m.content} for m in request.messages)

        kwargs: dict = {
            "model": self._model,
            "messages": messages,
            "max_tokens": request.max_tokens,
            "temperature": request.temperature,
        }
        if request.stop_sequences:
            kwargs["stop"] = request.stop_sequences

        response = await self._client.chat.completions.create(**kwargs)
        choice = response.choices[0]
        usage = response.usage

        return CompletionResponse(
            content=choice.message.content or "",
            usage=TokenUsage(
                input_tokens=usage.prompt_tokens if usage else 0,
                output_tokens=usage.completion_tokens if usage else 0,
            ),
            model=response.model,
            stop_reason=choice.finish_reason or "",
        )

    async def complete_stream(self, request: CompletionRequest) -> AsyncIterator[StreamChunk]:
        messages: list[dict] = []
        if request.system_prompt:
            messages.append({"role": "system", "content": request.system_prompt})
        messages.extend({"role": m.role, "content": m.content} for m in request.messages)

        kwargs: dict = {
            "model": self._model,
            "messages": messages,
            "max_tokens": request.max_tokens,
            "temperature": request.temperature,
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        if request.stop_sequences:
            kwargs["stop"] = request.stop_sequences

        stream = await self._client.chat.completions.create(**kwargs)
        async for chunk in stream:
            if chunk.choices and chunk.choices[0].delta.content:
                yield StreamChunk(text=chunk.choices[0].delta.content)
            if chunk.usage:
                yield StreamChunk(
                    is_final=True,
                    usage=TokenUsage(
                        input_tokens=chunk.usage.prompt_tokens,
                        output_tokens=chunk.usage.completion_tokens,
                    ),
                )

    async def test_connection(self) -> bool:
        try:
            response = await self._client.chat.completions.create(
                model=self._model,
                messages=[{"role": "user", "content": "ping"}],
                max_tokens=5,
            )
            return len(response.choices) > 0
        except Exception:
            return False
