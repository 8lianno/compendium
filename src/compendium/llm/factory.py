"""Provider factory — creates LLM provider instances from config + keyring."""

from __future__ import annotations

import contextlib
from typing import TYPE_CHECKING

import keyring

from compendium.llm.anthropic import AnthropicProvider
from compendium.llm.ollama import OllamaProvider
from compendium.llm.openai_provider import OpenAIProvider
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


def create_provider(model_config: ModelConfig) -> LlmProvider:
    """Create a single LLM provider from a ModelConfig."""
    provider_name = model_config.provider.lower()

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

    if provider_name == "gemini":
        api_key = get_api_key("gemini")
        if not api_key:
            msg = "No API key found for Gemini. Run: compendium config set-key gemini"
            raise ValueError(msg)
        try:
            from compendium.llm.gemini import GeminiProvider

            return GeminiProvider(api_key=api_key, model=model_config.model)
        except ImportError:
            pass
        msg = "Gemini requires google-genai SDK. Install with: uv pip install google-genai"
        raise ValueError(msg)

    msg = f"Unknown provider: {provider_name}. Supported: anthropic, openai, ollama, gemini"
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
