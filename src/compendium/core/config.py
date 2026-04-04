"""Configuration loader for compendium.toml."""

from __future__ import annotations

import tomllib
from pathlib import Path

from pydantic import BaseModel, Field


class ModelConfig(BaseModel):
    """Configuration for a specific LLM model."""

    provider: str = "anthropic"
    model: str = "claude-sonnet-4-20250514"
    endpoint: str | None = None  # For Ollama or custom endpoints


class ModelsConfig(BaseModel):
    """Per-operation model assignment."""

    default_provider: str = "anthropic"
    compilation: ModelConfig = Field(default_factory=ModelConfig)
    qa: ModelConfig = Field(default_factory=ModelConfig)
    lint: ModelConfig = Field(default_factory=lambda: ModelConfig(provider="anthropic"))


class CompilationConfig(BaseModel):
    """Compilation pipeline settings."""

    token_budget: int = 500_000
    min_article_words: int = 200
    max_article_words: int = 3000
    batch_size: int = 5
    max_parallel: int = 10
    category_depth: int = 2


class ServerConfig(BaseModel):
    """Local server settings."""

    port: int = 17394
    host: str = "127.0.0.1"


class ProjectConfig(BaseModel):
    """Top-level project configuration."""

    name: str = "My Knowledge Wiki"


class CompendiumConfig(BaseModel):
    """Root configuration from compendium.toml."""

    project: ProjectConfig = Field(default_factory=ProjectConfig)
    models: ModelsConfig = Field(default_factory=ModelsConfig)
    compilation: CompilationConfig = Field(default_factory=CompilationConfig)
    server: ServerConfig = Field(default_factory=ServerConfig)

    @classmethod
    def load(cls, path: Path) -> CompendiumConfig:
        """Load config from a compendium.toml file."""
        if not path.exists():
            return cls()
        with open(path, "rb") as f:
            data = tomllib.load(f)
        return cls.model_validate(data)

    @classmethod
    def find_and_load(cls, start_dir: Path | None = None) -> CompendiumConfig:
        """Walk up from start_dir to find compendium.toml and load it."""
        search = start_dir or Path.cwd()
        for parent in [search, *search.parents]:
            config_path = parent / "compendium.toml"
            if config_path.exists():
                return cls.load(config_path)
        return cls()

    def save(self, path: Path) -> None:
        """Save config to a compendium.toml file."""
        import tomli_w  # type: ignore[import-untyped]

        data = self.model_dump(mode="json")
        with open(path, "wb") as f:
            tomli_w.dump(data, f)
