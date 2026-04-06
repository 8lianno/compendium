"""Provider factory — creates LLM provider instances from config + keyring."""

from __future__ import annotations

import contextlib
from typing import TYPE_CHECKING

import keyring

from compendium.llm.anthropic import AnthropicProvider
from compendium.llm.ollama import OllamaProvider
from compendium.llm.openai_provider import OpenAIProvider
from compendium.llm.openrouter import OpenRouterProvider
from compendium.llm.router import ModelRouter

if TYPE_CHECKING:
    from compendium.core.config import CompendiumConfig, ModelConfig
    from compendium.llm.provider import LlmProvider

KEYRING_SERVICE = "compendium"


def get_api_key(provider: str) -> str | None:
    """Retrieve API key from OS keychain."""
    return keyring.get_password(KEYRING_SERVICE, provider)


def set_api_key(provider: str, key: str) -> None:
    """Store API key in OS keychain."""
    keyring.set_password(KEYRING_SERVICE, provider, key)


def delete_api_key(provider: str) -> None:
    """Remove API key from OS keychain."""
    with contextlib.suppress(keyring.errors.PasswordDeleteError):
        keyring.delete_password(KEYRING_SERVICE, provider)


CLOUD_PROVIDERS = {"anthropic", "openai", "gemini", "openrouter", "google-ai-studio"}


def create_provider(
    model_config: ModelConfig, *, cloud_only: bool = False
) -> LlmProvider:
    """Create a single LLM provider from a ModelConfig.

    If cloud_only is True, raises ValueError for local providers (e.g. Ollama).
    """
    provider_name = model_config.provider.lower()

    if cloud_only and provider_name not in CLOUD_PROVIDERS:
        msg = (
            f"Provider '{provider_name}' is not a cloud API. "
            f"Daemon requires cloud-only providers: {', '.join(sorted(CLOUD_PROVIDERS))}"
        )
        raise ValueError(msg)

    if provider_name == "anthropic":
        api_key = get_api_key("anthropic")
        if not api_key:
            msg = "No API key found for Anthropic. Run: compendium config set-key anthropic"
            raise ValueError(msg)
        return AnthropicProvider(api_key=api_key, model=model_config.model)

    if provider_name == "openai":
        api_key = get_api_key("openai")
        if not api_key:
            msg = "No API key found for OpenAI. Run: compendium config set-key openai"
            raise ValueError(msg)
        return OpenAIProvider(
            api_key=api_key,
            model=model_config.model,
            base_url=model_config.endpoint,
        )

    if provider_name == "ollama":
        endpoint = model_config.endpoint or "http://localhost:11434"
        return OllamaProvider(model=model_config.model, endpoint=endpoint)

    if provider_name == "gemini" or provider_name == "google-ai-studio":
        key_name = "gemini" if provider_name == "gemini" else "google-ai-studio"
        api_key = get_api_key(key_name)
        # Fall back: google-ai-studio and gemini share the same API
        if not api_key:
            api_key = get_api_key("gemini" if key_name != "gemini" else "google-ai-studio")
        if not api_key:
            msg = f"No API key found. Run: compendium config set-key {key_name}"
            raise ValueError(msg)
        try:
            from compendium.llm.gemini import GeminiProvider

            return GeminiProvider(api_key=api_key, model=model_config.model)
        except ImportError:
            pass
        msg = "Gemini requires google-genai SDK. Install with: uv pip install google-genai"
        raise ValueError(msg)

    if provider_name == "openrouter":
        api_key = get_api_key("openrouter")
        if not api_key:
            msg = "No API key found for OpenRouter. Run: compendium config set-key openrouter"
            raise ValueError(msg)
        return OpenRouterProvider(api_key=api_key, model=model_config.model)

    supported = "anthropic, openai, ollama, gemini, openrouter, google-ai-studio"
    msg = f"Unknown provider: {provider_name}. Supported: {supported}"
    raise ValueError(msg)


def create_router(config: CompendiumConfig) -> ModelRouter:
    """Create a fully wired ModelRouter from config.

    Registers providers for each unique (provider, model) pair
    referenced in the config's model assignments.
    """
    router = ModelRouter(config)

    # Collect unique model configs to avoid duplicate provider instances
    seen: set[str] = set()
    model_configs = [
        config.models.compilation,
        config.models.qa,
        config.models.lint,
    ]

    for mc in model_configs:
        key = f"{mc.provider}:{mc.model}"
        if key in seen:
            continue
        seen.add(key)
        try:
            provider = create_provider(mc)
            router.register(provider)
        except ValueError:
            # Skip providers that can't be created (missing keys, etc.)
            # They'll raise when actually used via router.for_operation()
            pass

    return router
