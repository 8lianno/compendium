"""OpenRouter LLM provider (multi-model API gateway, OpenAI-compatible)."""

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
from compendium.llm.retry import with_retry

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
DEFAULT_MODEL = "anthropic/claude-sonnet-4"


class OpenRouterProvider:
    """OpenRouter provider — routes to 200+ models via a single API key."""

    def __init__(self, api_key: str, model: str = DEFAULT_MODEL) -> None:
        self._client = openai.AsyncOpenAI(
            api_key=api_key,
            base_url=OPENROUTER_BASE_URL,
            default_headers={
                "HTTP-Referer": "https://github.com/8lianno/compendium",
                "X-Title": "Compendium",
            },
        )
        self._model = model

    @property
    def name(self) -> str:
        return "openrouter"

    @property
    def model_name(self) -> str:
        return self._model

    @property
    def context_window(self) -> int:
        return 128_000  # Varies by model; safe default

    @property
    def pricing(self) -> TokenPricing:
        # Pricing depends on the underlying model; OpenRouter bills per-model.
        return TokenPricing(input_per_million=0.0, output_per_million=0.0)

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

        response = await with_retry(self._client.chat.completions.create, **kwargs)
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
            response = await with_retry(
                self._client.chat.completions.create,
                model=self._model,
                messages=[{"role": "user", "content": "ping"}],
                max_tokens=5,
            )
            return len(response.choices) > 0
        except Exception:
            return False
