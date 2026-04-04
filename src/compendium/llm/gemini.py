"""Google Gemini LLM provider."""

from __future__ import annotations

from typing import TYPE_CHECKING

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
GEMINI_PRICING: dict[str, TokenPricing] = {
    "gemini-2.5-flash": TokenPricing(input_per_million=0.15, output_per_million=0.60),
    "gemini-2.5-pro": TokenPricing(input_per_million=1.25, output_per_million=10.0),
    "gemini-2.0-flash": TokenPricing(input_per_million=0.10, output_per_million=0.40),
}

GEMINI_CONTEXT_WINDOWS: dict[str, int] = {
    "gemini-2.5-flash": 1_048_576,
    "gemini-2.5-pro": 1_048_576,
    "gemini-2.0-flash": 1_048_576,
}

DEFAULT_MODEL = "gemini-2.5-flash"


class GeminiProvider:
    """Google Gemini provider using the google-genai SDK."""

    def __init__(self, api_key: str, model: str = DEFAULT_MODEL) -> None:
        try:
            from google import genai  # type: ignore[import-untyped]

            self._client = genai.Client(api_key=api_key)
        except ImportError as e:
            msg = "Gemini requires google-genai. Install: uv pip install google-genai"
            raise ImportError(msg) from e
        self._model = model

    @property
    def name(self) -> str:
        return "gemini"

    @property
    def model_name(self) -> str:
        return self._model

    @property
    def context_window(self) -> int:
        return GEMINI_CONTEXT_WINDOWS.get(self._model, 1_048_576)

    @property
    def pricing(self) -> TokenPricing:
        return GEMINI_PRICING.get(
            self._model, TokenPricing(input_per_million=0.15, output_per_million=0.60)
        )

    def estimate_tokens(self, text: str) -> int:
        return len(text) // 4

    async def complete(self, request: CompletionRequest) -> CompletionResponse:
        """Send a completion request to Gemini."""
        # Build contents string
        contents = ""
        if request.system_prompt:
            contents += f"System: {request.system_prompt}\n\n"
        for msg in request.messages:
            contents += f"{msg.role}: {msg.content}\n\n"

        from google import genai  # type: ignore[import-untyped]

        config = genai.types.GenerateContentConfig(
            temperature=request.temperature,
            max_output_tokens=request.max_tokens,
        )

        response = self._client.models.generate_content(
            model=self._model,
            contents=contents,
            config=config,
        )

        text = response.text or ""
        usage_meta = response.usage_metadata

        return CompletionResponse(
            content=text,
            usage=TokenUsage(
                input_tokens=getattr(usage_meta, "prompt_token_count", 0) or 0,
                output_tokens=getattr(usage_meta, "candidates_token_count", 0) or 0,
            ),
            model=self._model,
            stop_reason="stop",
        )

    async def complete_stream(self, request: CompletionRequest) -> AsyncIterator[StreamChunk]:
        """Gemini streaming (falls back to non-streaming for simplicity)."""
        response = await self.complete(request)
        yield StreamChunk(text=response.content, is_final=True, usage=response.usage)

    async def test_connection(self) -> bool:
        """Test connection by listing models."""
        try:
            models = self._client.models.list()
            return len(list(models)) > 0
        except Exception:
            return False
