"""Prompt template loader with variable interpolation."""

from __future__ import annotations

import re
from pathlib import Path

# Default prompts directory (shipped with package)
_PACKAGE_PROMPTS_DIR = Path(__file__).parent.parent.parent.parent / "prompts"


class PromptTemplate:
    """A prompt template loaded from a .md file with {{variable}} interpolation."""

    def __init__(self, name: str, template: str) -> None:
        self.name = name
        self.template = template

    def render(self, **kwargs: str) -> str:
        """Render the template by replacing {{variable}} placeholders."""
        result = self.template
        for key, value in kwargs.items():
            result = result.replace(f"{{{{{key}}}}}", value)
        # Warn about unreplaced variables (but don't fail)
        remaining = re.findall(r"\{\{(\w+)\}\}", result)
        if remaining:
            pass  # Could log a warning in the future
        return result


class PromptLoader:
    """Loads prompt templates from the prompts/ directory."""

    def __init__(self, project_prompts_dir: Path | None = None) -> None:
        self._project_dir = project_prompts_dir
        self._cache: dict[str, PromptTemplate] = {}

    def load(self, name: str) -> PromptTemplate:
        """Load a prompt template by name (without .md extension).

        Looks in project prompts dir first (user overrides), then package defaults.
        """
        if name in self._cache:
            return self._cache[name]

        # Try project-level override first
        if self._project_dir:
            project_file = self._project_dir / f"{name}.md"
            if project_file.exists():
                template = PromptTemplate(name, project_file.read_text())
                self._cache[name] = template
                return template

        # Fall back to package defaults
        default_file = _PACKAGE_PROMPTS_DIR / f"{name}.md"
        if default_file.exists():
            template = PromptTemplate(name, default_file.read_text())
            self._cache[name] = template
            return template

        msg = f"Prompt template not found: {name}"
        raise FileNotFoundError(msg)

    def clear_cache(self) -> None:
        self._cache.clear()
