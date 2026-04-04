"""Ollama LLM provider (local, OpenAI-compatible API)."""

from __future__ import annotations

from typing import TYPE_CHECKING

import httpx

from compendium.llm.provider import (
    CompletionRequest,
    CompletionResponse,
    StreamChunk,
    TokenPricing,
    TokenUsage,
)

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

DEFAULT_ENDPOINT = "http://localhost:11434"
DEFAULT_MODEL = "llama3.2"


class OllamaProvider:
    """Ollama provider using the OpenAI-compatible API."""

    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        endpoint: str = DEFAULT_ENDPOINT,
    ) -> None:
        self._model = model
        self._endpoint = endpoint.rstrip("/")
        self._client = httpx.AsyncClient(base_url=self._endpoint, timeout=120.0)

    @property
    def name(self) -> str:
        return "ollama"

    @property
    def model_name(self) -> str:
        return self._model

    @property
    def context_window(self) -> int:
        return 128_000  # Varies by model; 128K is a safe default for modern models

    @property
    def pricing(self) -> TokenPricing:
        return TokenPricing(input_per_million=0.0, output_per_million=0.0)  # Local = free

    def estimate_tokens(self, text: str) -> int:
        return len(text) // 4

    async def complete(self, request: CompletionRequest) -> CompletionResponse:
        messages: list[dict] = []
        if request.system_prompt:
            messages.append({"role": "system", "content": request.system_prompt})
        messages.extend({"role": m.role, "content": m.content} for m in request.messages)

        payload = {
            "model": self._model,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": request.temperature,
                "num_predict": request.max_tokens,
            },
        }

        response = await self._client.post("/api/chat", json=payload)
        response.raise_for_status()
        data = response.json()

        return CompletionResponse(
            content=data.get("message", {}).get("content", ""),
            usage=TokenUsage(
                input_tokens=data.get("prompt_eval_count", 0),
                output_tokens=data.get("eval_count", 0),
            ),
            model=data.get("model", self._model),
            stop_reason=data.get("done_reason", ""),
        )

    async def complete_stream(self, request: CompletionRequest) -> AsyncIterator[StreamChunk]:
        messages: list[dict] = []
        if request.system_prompt:
            messages.append({"role": "system", "content": request.system_prompt})
        messages.extend({"role": m.role, "content": m.content} for m in request.messages)

        payload = {
            "model": self._model,
            "messages": messages,
            "stream": True,
            "options": {
                "temperature": request.temperature,
                "num_predict": request.max_tokens,
            },
        }

        async with self._client.stream("POST", "/api/chat", json=payload) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if not line:
                    continue
                import json

                data = json.loads(line)
                if data.get("done"):
                    yield StreamChunk(
                        is_final=True,
                        usage=TokenUsage(
                            input_tokens=data.get("prompt_eval_count", 0),
                            output_tokens=data.get("eval_count", 0),
                        ),
                    )
                else:
                    content = data.get("message", {}).get("content", "")
                    if content:
                        yield StreamChunk(text=content)

    async def test_connection(self) -> bool:
        """Test by listing available models."""
        try:
            response = await self._client.get("/api/tags")
            response.raise_for_status()
            return True
        except Exception:
            return False

    async def list_models(self) -> list[str]:
        """List available Ollama models."""
        try:
            response = await self._client.get("/api/tags")
            response.raise_for_status()
            data = response.json()
            return [m["name"] for m in data.get("models", [])]
        except Exception:
            return []
