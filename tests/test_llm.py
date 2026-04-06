"""Tests for LLM providers, router, token tracker, and prompt loader."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from compendium.core.config import CompendiumConfig, ModelConfig, ModelsConfig
from compendium.llm.provider import (
    CompletionRequest,
    CompletionResponse,
    Message,
    Operation,
    TokenPricing,
    TokenUsage,
)
from compendium.llm.router import ModelRouter
from compendium.llm.tokens import TokenTracker

if TYPE_CHECKING:
    from pathlib import Path

# -- Fixtures --


class FakeProvider:
    """Fake LLM provider for testing."""

    def __init__(self, name: str = "fake", model: str = "fake-model") -> None:
        self._name = name
        self._model = model
        self.complete_calls: list[CompletionRequest] = []

    @property
    def name(self) -> str:
        return self._name

    @property
    def model_name(self) -> str:
        return self._model

    @property
    def context_window(self) -> int:
        return 100_000

    @property
    def pricing(self) -> TokenPricing:
        return TokenPricing(input_per_million=3.0, output_per_million=15.0)

    def estimate_tokens(self, text: str) -> int:
        return len(text) // 4

    async def complete(self, request: CompletionRequest) -> CompletionResponse:
        self.complete_calls.append(request)
        return CompletionResponse(
            content="Test response",
            usage=TokenUsage(input_tokens=100, output_tokens=50),
            model=self._model,
            stop_reason="end_turn",
        )

    async def complete_stream(self, request: CompletionRequest):
        yield {"text": "Test", "is_final": False}
        yield {"text": " response", "is_final": True}

    async def test_connection(self) -> bool:
        return True


# -- Provider Tests --


class TestAnthropicProvider:
    def test_properties(self) -> None:
        from compendium.llm.anthropic import AnthropicProvider

        with patch("compendium.llm.anthropic.anthropic.AsyncAnthropic"):
            provider = AnthropicProvider(api_key="test-key", model="claude-sonnet-4-20250514")
            assert provider.name == "anthropic"
            assert provider.model_name == "claude-sonnet-4-20250514"
            assert provider.context_window == 200_000
            assert provider.pricing.input_per_million == 3.0
            assert provider.pricing.output_per_million == 15.0

    def test_estimate_tokens(self) -> None:
        from compendium.llm.anthropic import AnthropicProvider

        with patch("compendium.llm.anthropic.anthropic.AsyncAnthropic"):
            provider = AnthropicProvider(api_key="test-key")
            assert provider.estimate_tokens("hello world") == 2  # 11 chars / 4

    @pytest.mark.asyncio
    async def test_complete(self) -> None:
        from compendium.llm.anthropic import AnthropicProvider

        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.content = [MagicMock(type="text", text="Hello from Claude")]
        mock_response.usage.input_tokens = 10
        mock_response.usage.output_tokens = 5
        mock_response.model = "claude-sonnet-4-20250514"
        mock_response.stop_reason = "end_turn"
        mock_client.messages.create = AsyncMock(return_value=mock_response)

        with patch("compendium.llm.anthropic.anthropic.AsyncAnthropic", return_value=mock_client):
            provider = AnthropicProvider(api_key="test-key")

        provider._client = mock_client
        result = await provider.complete(
            CompletionRequest(
                messages=[Message(role="user", content="Hello")],
                system_prompt="You are a test.",
            )
        )
        assert result.content == "Hello from Claude"
        assert result.usage.input_tokens == 10
        assert result.usage.output_tokens == 5

    @pytest.mark.asyncio
    async def test_test_connection_failure(self) -> None:
        from compendium.llm.anthropic import AnthropicProvider

        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(side_effect=Exception("Connection failed"))

        with patch("compendium.llm.anthropic.anthropic.AsyncAnthropic", return_value=mock_client):
            provider = AnthropicProvider(api_key="bad-key")

        provider._client = mock_client
        result = await provider.test_connection()
        assert result is False


class TestOpenAIProvider:
    def test_properties(self) -> None:
        from compendium.llm.openai_provider import OpenAIProvider

        with patch("compendium.llm.openai_provider.openai.AsyncOpenAI"):
            provider = OpenAIProvider(api_key="test-key", model="gpt-4o")
            assert provider.name == "openai"
            assert provider.model_name == "gpt-4o"
            assert provider.context_window == 128_000

    @pytest.mark.asyncio
    async def test_complete(self) -> None:
        from compendium.llm.openai_provider import OpenAIProvider

        mock_client = AsyncMock()
        mock_choice = MagicMock()
        mock_choice.message.content = "Hello from GPT"
        mock_choice.finish_reason = "stop"
        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        mock_response.usage.prompt_tokens = 8
        mock_response.usage.completion_tokens = 4
        mock_response.model = "gpt-4o"
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

        with patch("compendium.llm.openai_provider.openai.AsyncOpenAI", return_value=mock_client):
            provider = OpenAIProvider(api_key="test-key")

        provider._client = mock_client
        result = await provider.complete(
            CompletionRequest(messages=[Message(role="user", content="Hello")])
        )
        assert result.content == "Hello from GPT"
        assert result.usage.input_tokens == 8


class TestOllamaProvider:
    def test_properties(self) -> None:
        from compendium.llm.ollama import OllamaProvider

        provider = OllamaProvider(model="llama3.2")
        assert provider.name == "ollama"
        assert provider.model_name == "llama3.2"
        assert provider.pricing.input_per_million == 0.0  # Free

    @pytest.mark.asyncio
    async def test_complete(self) -> None:
        from compendium.llm.ollama import OllamaProvider

        provider = OllamaProvider(model="llama3.2")
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "message": {"content": "Hello from Llama"},
            "prompt_eval_count": 12,
            "eval_count": 8,
            "model": "llama3.2",
            "done_reason": "stop",
        }
        mock_response.raise_for_status = MagicMock()

        provider._client = AsyncMock()
        provider._client.post = AsyncMock(return_value=mock_response)

        result = await provider.complete(
            CompletionRequest(messages=[Message(role="user", content="Hello")])
        )
        assert result.content == "Hello from Llama"
        assert result.usage.input_tokens == 12
        assert result.usage.output_tokens == 8


# -- Router Tests --


class TestModelRouter:
    def test_route_operations(self) -> None:
        config = CompendiumConfig(
            models=ModelsConfig(
                compilation=ModelConfig(provider="anthropic", model="claude-sonnet-4-20250514"),
                qa=ModelConfig(provider="openai", model="gpt-4o"),
                lint=ModelConfig(provider="ollama", model="llama3.2"),
            )
        )
        router = ModelRouter(config)

        anthropic_prov = FakeProvider("anthropic", "claude-sonnet-4-20250514")
        openai_prov = FakeProvider("openai", "gpt-4o")
        ollama_prov = FakeProvider("ollama", "llama3.2")

        router.register(anthropic_prov)
        router.register(openai_prov)
        router.register(ollama_prov)

        assert router.for_operation(Operation.COMPILATION) is anthropic_prov
        assert router.for_operation(Operation.QA) is openai_prov
        assert router.for_operation(Operation.LINT) is ollama_prov

    def test_missing_provider_raises(self) -> None:
        config = CompendiumConfig()
        router = ModelRouter(config)

        with pytest.raises(ValueError, match="No provider registered"):
            router.for_operation(Operation.COMPILATION)


# -- Token Tracker Tests --


class TestTokenTracker:
    def test_record_usage(self, tmp_path: Path) -> None:
        tracker = TokenTracker(usage_dir=tmp_path)

        cost = tracker.record(
            operation=Operation.COMPILATION,
            provider="anthropic",
            model="claude-sonnet-4-20250514",
            usage=TokenUsage(input_tokens=10000, output_tokens=2000),
            pricing=TokenPricing(input_per_million=3.0, output_per_million=15.0),
            project="/test/wiki",
            step="summarize",
        )

        # Cost: (10000 * 3.0 / 1M) + (2000 * 15.0 / 1M) = 0.03 + 0.03 = 0.06
        assert abs(cost - 0.06) < 0.001

        # Check session tracking
        assert tracker.session_total.input_tokens == 10000
        assert tracker.session_total.output_tokens == 2000
        assert abs(tracker.session_cost - 0.06) < 0.001

    def test_monthly_file(self, tmp_path: Path) -> None:
        tracker = TokenTracker(usage_dir=tmp_path)

        tracker.record(
            operation=Operation.QA,
            provider="openai",
            model="gpt-4o",
            usage=TokenUsage(input_tokens=5000, output_tokens=1000),
            pricing=TokenPricing(input_per_million=2.5, output_per_million=10.0),
        )

        summary = tracker.get_monthly_summary()
        assert len(summary["operations"]) == 1
        assert summary["totals"]["input_tokens"] == 5000
        assert summary["totals"]["output_tokens"] == 1000

    def test_cumulative_tracking(self, tmp_path: Path) -> None:
        tracker = TokenTracker(usage_dir=tmp_path)
        pricing = TokenPricing(input_per_million=3.0, output_per_million=15.0)

        for _ in range(3):
            tracker.record(
                operation=Operation.COMPILATION,
                provider="anthropic",
                model="test",
                usage=TokenUsage(input_tokens=1000, output_tokens=500),
                pricing=pricing,
            )

        assert tracker.session_total.input_tokens == 3000
        assert tracker.session_total.output_tokens == 1500

        summary = tracker.get_monthly_summary()
        assert summary["totals"]["input_tokens"] == 3000


# -- Prompt Loader Tests --


class TestPromptLoader:
    def test_load_default_prompt(self) -> None:
        from compendium.llm.prompts import PromptLoader

        loader = PromptLoader()
        template = loader.load("summarize")
        assert "{{title}}" in template.template
        assert "{{content}}" in template.template

    def test_render_template(self) -> None:
        from compendium.llm.prompts import PromptLoader

        loader = PromptLoader()
        template = loader.load("summarize")
        rendered = template.render(
            title="Test Paper",
            word_count="5000",
            content="Some content here",
            source_id="test-paper",
        )
        assert "Test Paper" in rendered
        assert "5000" in rendered
        assert "Some content here" in rendered

    def test_project_override(self, tmp_path: Path) -> None:
        from compendium.llm.prompts import PromptLoader

        # Create a project-level override
        prompts_dir = tmp_path / "prompts"
        prompts_dir.mkdir()
        (prompts_dir / "summarize.md").write_text("Custom prompt: {{title}}")

        loader = PromptLoader(project_prompts_dir=prompts_dir)
        template = loader.load("summarize")
        assert template.template == "Custom prompt: {{title}}"

    def test_missing_prompt_raises(self) -> None:
        from compendium.llm.prompts import PromptLoader

        loader = PromptLoader()
        with pytest.raises(FileNotFoundError, match="not found"):
            loader.load("nonexistent_prompt")

    def test_cache(self) -> None:
        from compendium.llm.prompts import PromptLoader

        loader = PromptLoader()
        t1 = loader.load("summarize")
        t2 = loader.load("summarize")
        assert t1 is t2  # Same object from cache


# -- Factory Tests --


class TestProviderFactory:
    def test_create_ollama_no_key_needed(self) -> None:
        from compendium.llm.factory import create_provider

        mc = ModelConfig(provider="ollama", model="llama3.2")
        provider = create_provider(mc)
        assert provider.name == "ollama"
        assert provider.model_name == "llama3.2"

    def test_create_anthropic_missing_key(self) -> None:
        from compendium.llm.factory import create_provider

        with patch("compendium.llm.factory.get_api_key", return_value=None):
            mc = ModelConfig(provider="anthropic", model="claude-sonnet-4-20250514")
            with pytest.raises(ValueError, match="No API key"):
                create_provider(mc)

    def test_create_anthropic_with_key(self) -> None:
        from compendium.llm.factory import create_provider

        with (
            patch("compendium.llm.factory.get_api_key", return_value="sk-test-key"),
            patch("compendium.llm.anthropic.anthropic.AsyncAnthropic"),
        ):
            mc = ModelConfig(provider="anthropic", model="claude-sonnet-4-20250514")
            provider = create_provider(mc)
            assert provider.name == "anthropic"

    def test_unknown_provider(self) -> None:
        from compendium.llm.factory import create_provider

        mc = ModelConfig(provider="unknown", model="test")
        with pytest.raises(ValueError, match="Unknown provider"):
            create_provider(mc)

    def test_create_openrouter_with_key(self) -> None:
        from compendium.llm.factory import create_provider

        with patch("compendium.llm.factory.get_api_key", return_value="sk-or-test"):
            mc = ModelConfig(provider="openrouter", model="anthropic/claude-sonnet-4")
            provider = create_provider(mc)
            assert provider.name == "openrouter"
            assert provider.model_name == "anthropic/claude-sonnet-4"

    def test_create_openrouter_missing_key(self) -> None:
        from compendium.llm.factory import create_provider

        with patch("compendium.llm.factory.get_api_key", return_value=None):
            mc = ModelConfig(provider="openrouter", model="anthropic/claude-sonnet-4")
            with pytest.raises(ValueError, match="No API key"):
                create_provider(mc)

    def test_google_ai_studio_alias_routes_to_gemini(self) -> None:
        """google-ai-studio should attempt GeminiProvider (same API)."""
        from compendium.llm.factory import create_provider

        with patch("compendium.llm.factory.get_api_key", return_value="test-key"):
            mc = ModelConfig(provider="google-ai-studio", model="gemini-2.5-flash")
            try:
                provider = create_provider(mc)
                assert provider.name == "gemini"
            except ValueError as e:
                # google-genai SDK not installed — that's fine, it tried
                assert "google-genai" in str(e)

    def test_cloud_providers_includes_new(self) -> None:
        from compendium.llm.factory import CLOUD_PROVIDERS

        assert "openrouter" in CLOUD_PROVIDERS
        assert "google-ai-studio" in CLOUD_PROVIDERS

    def test_create_router(self) -> None:
        from compendium.llm.factory import create_router

        config = CompendiumConfig(
            models=ModelsConfig(
                compilation=ModelConfig(provider="ollama", model="llama3.2"),
                qa=ModelConfig(provider="ollama", model="llama3.2"),
                lint=ModelConfig(provider="ollama", model="llama3.2"),
            )
        )
        router = create_router(config)
        # Ollama doesn't need API keys, so it should succeed
        provider = router.for_operation(Operation.COMPILATION)
        assert provider.name == "ollama"
