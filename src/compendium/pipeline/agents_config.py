"""AGENTS.md configuration parser for pipeline prompt/model overrides."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import frontmatter

if TYPE_CHECKING:
    from pathlib import Path


def load_agents_config(project_root: Path) -> dict[str, Any]:
    """Load AGENTS.md from project root and return per-step overrides.

    AGENTS.md uses YAML frontmatter for step configuration:

    ```
    ---
    steps:
      summarize:
        temperature: 0.2
        max_output_tokens: 800
      generate_articles:
        temperature: 0.3
        min_words: 200
        max_words: 3000
    ---
    Optional markdown body (ignored by parser).
    ```

    Returns dict of step_name -> config overrides. Empty dict if no AGENTS.md.
    """
    agents_path = project_root / "AGENTS.md"
    if not agents_path.exists():
        return {}

    try:
        post = frontmatter.load(str(agents_path))
        return post.metadata.get("steps", {})
    except Exception:
        return {}


def get_step_config(
    agents: dict[str, Any], step_name: str, default: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Get configuration for a specific pipeline step.

    Merges AGENTS.md overrides with defaults.
    """
    base = dict(default or {})
    overrides = agents.get(step_name, {})
    base.update(overrides)
    return base
