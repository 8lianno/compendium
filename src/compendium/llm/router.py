"""Model router — selects the right LLM provider for each operation."""

from __future__ import annotations

from typing import TYPE_CHECKING

from compendium.llm.provider import LlmProvider, Operation

if TYPE_CHECKING:
    from compendium.core.config import CompendiumConfig


class ModelRouter:
    """Routes operations to the configured LLM provider."""

    def __init__(self, config: CompendiumConfig) -> None:
        self._config = config
        self._providers: dict[str, LlmProvider] = {}

    def register(self, provider: LlmProvider) -> None:
        """Register a provider instance."""
        key = f"{provider.name}:{provider.model_name}"
        self._providers[key] = provider

    def for_operation(self, operation: Operation) -> LlmProvider:
        """Get the configured provider for an operation."""
        match operation:
            case Operation.COMPILATION:
                model_cfg = self._config.models.compilation
            case Operation.QA:
                model_cfg = self._config.models.qa
            case Operation.LINT:
                model_cfg = self._config.models.lint

        key = f"{model_cfg.provider}:{model_cfg.model}"
        if key not in self._providers:
            msg = f"No provider registered for {key}. Available: {list(self._providers.keys())}"
            raise ValueError(msg)
        return self._providers[key]

    @property
    def all_providers(self) -> dict[str, LlmProvider]:
        return dict(self._providers)
