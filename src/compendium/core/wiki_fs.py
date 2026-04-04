"""WikiFileSystem — manages the project directory structure and atomic operations."""

from __future__ import annotations

import hashlib
import shutil
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import frontmatter

from compendium.core.frontmatter import RawSourceFrontmatter

if TYPE_CHECKING:
    from pathlib import Path


class WikiFileSystem:
    """Manages the Compendium project directory structure.

    Project layout:
        project_root/
            compendium.toml
            raw/                    # User's raw source documents
                images/             # Downloaded images
                originals/          # Preserved original files (PDFs, etc.)
            wiki/                   # Compiled wiki articles
                INDEX.md
                CONCEPTS.md
                CONFLICTS.md
                CHANGELOG.md
                .deps.json          # Dependency graph
                .staging/           # In-progress compilation
                .backup/            # Pre-update snapshots
                .compilation-log/   # Prompt audit trail
            output/                 # Q&A outputs
                reports/
                slides/
                charts/
    """

    def __init__(self, project_root: Path) -> None:
        self.root = project_root.resolve()

    # -- Directory accessors --

    @property
    def raw_dir(self) -> Path:
        return self.root / "raw"

    @property
    def raw_images_dir(self) -> Path:
        return self.root / "raw" / "images"

    @property
    def raw_originals_dir(self) -> Path:
        return self.root / "raw" / "originals"

    @property
    def wiki_dir(self) -> Path:
        return self.root / "wiki"

    @property
    def staging_dir(self) -> Path:
        return self.root / "wiki" / ".staging"

    @property
    def backup_dir(self) -> Path:
        return self.root / "wiki" / ".backup"

    @property
    def compilation_log_dir(self) -> Path:
        return self.root / "wiki" / ".compilation-log"

    @property
    def output_dir(self) -> Path:
        return self.root / "output"

    @property
    def reports_dir(self) -> Path:
        return self.root / "output" / "reports"

    @property
    def slides_dir(self) -> Path:
        return self.root / "output" / "slides"

    @property
    def charts_dir(self) -> Path:
        return self.root / "output" / "charts"

    @property
    def deps_path(self) -> Path:
        return self.root / "wiki" / ".deps.json"

    @property
    def checkpoint_path(self) -> Path:
        return self.staging_dir / ".checkpoint.json"

    @property
    def config_path(self) -> Path:
        return self.root / "compendium.toml"

    # -- Initialization --

    def init_project(self, name: str = "My Knowledge Wiki") -> None:
        """Create the full project directory structure."""
        dirs = [
            self.raw_dir,
            self.raw_images_dir,
            self.raw_originals_dir,
            self.wiki_dir,
            self.staging_dir,
            self.backup_dir,
            self.compilation_log_dir,
            self.output_dir,
            self.reports_dir,
            self.slides_dir,
            self.charts_dir,
        ]
        for d in dirs:
            d.mkdir(parents=True, exist_ok=True)

        # Create default compendium.toml if it doesn't exist
        if not self.config_path.exists():
            self.config_path.write_text(
                f'[project]\nname = "{name}"\n\n'
                "[models]\n"
                'default_provider = "anthropic"\n\n'
                "[models.compilation]\n"
                'provider = "anthropic"\n'
                'model = "claude-sonnet-4-20250514"\n\n'
                "[models.qa]\n"
                'provider = "anthropic"\n'
                'model = "claude-sonnet-4-20250514"\n\n'
                "[compilation]\n"
                "token_budget = 500_000\n"
                "min_article_words = 200\n"
                "max_article_words = 3000\n\n"
                "[server]\n"
                "port = 17394\n"
            )

        # Create .gitkeep files for empty dirs
        for d in [self.raw_images_dir, self.raw_originals_dir, self.staging_dir, self.backup_dir]:
            gitkeep = d / ".gitkeep"
            if not gitkeep.exists():
                gitkeep.touch()

        # Create project-level CLAUDE.md (wiki schema for LLM agents)
        claude_md = self.root / "CLAUDE.md"
        if not claude_md.exists():
            claude_md.write_text(self._generate_project_claude_md(name))

        # Initialize git repo
        git_dir = self.root / ".git"
        if not git_dir.exists():
            import subprocess

            try:
                subprocess.run(
                    ["git", "init"],
                    cwd=str(self.root),
                    capture_output=True,
                    check=False,
                )
                # Create .gitignore
                gitignore = self.root / ".gitignore"
                if not gitignore.exists():
                    gitignore.write_text(
                        "# Compendium internals\n"
                        "wiki/.staging/\nwiki/.backup/\n"
                        "wiki/.compilation-log/\nwiki/.search-index/\n"
                        ".sessions/\n"
                    )
            except FileNotFoundError:
                pass  # git not installed — skip silently

    @staticmethod
    def _generate_project_claude_md(name: str) -> str:
        """Generate CLAUDE.md that teaches LLM agents how to maintain this wiki."""
        return f"""# {name}

## Project Structure

This is a Compendium knowledge wiki. The LLM writes and maintains all wiki content.

```
raw/        Source documents (immutable, never modified by LLM)
wiki/       LLM-generated wiki articles (LLM owns this entirely)
output/     Q&A reports, slides, charts
```

## Wiki Conventions

- **Wikilinks:** Use `[[article-slug]]` or `[[slug|Display Text]]` to link articles
- **Frontmatter:** Every wiki article has YAML frontmatter with title, category, sources, tags
- **Sources:** Every claim must reference its raw source: `[[raw/source-name.md]]`
- **INDEX.md:** Master index table — updated after every compilation
- **CONCEPTS.md:** Hierarchical concept taxonomy
- **CONFLICTS.md:** Detected contradictions between sources
- **log.md:** Append-only chronological record of all operations

## How to Maintain This Wiki

### Adding Sources
1. Drop files into `raw/` (PDF, markdown, CSV, images)
2. Run `compendium ingest <file>` to preprocess
3. Run `compendium update --all-new` to integrate into the wiki

### Querying
- `compendium ask "question"` — answers grounded in wiki with citations
- `compendium ask "question" --output report --file` — save and file back to wiki

### Maintenance
- `compendium lint` — check for broken links, orphans, gaps
- `compendium verify-index` — ensure INDEX.md is in sync
- `compendium rebuild-index` — regenerate index from scratch

## Schema (co-evolve this section as the wiki grows)

Customize this section to document domain-specific conventions:
- What categories exist and what belongs in each
- How entities vs concepts vs methods are distinguished
- What level of detail each article should have
- Which sources are authoritative vs supplementary
"""

    # -- Raw source operations --

    def list_raw_sources(self) -> list[Path]:
        """List all markdown files in raw/."""
        if not self.raw_dir.exists():
            return []
        return sorted(p for p in self.raw_dir.iterdir() if p.suffix == ".md" and p.is_file())

    def read_raw_source(self, path: Path) -> tuple[RawSourceFrontmatter, str]:
        """Read a raw source file and return its frontmatter and content."""
        post = frontmatter.load(str(path))
        fm = RawSourceFrontmatter.model_validate(post.metadata)
        return fm, post.content

    def content_hash(self, path: Path) -> str:
        """Compute SHA-256 hash of file contents."""
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
        return f"sha256:{h.hexdigest()}"

    # -- Wiki article operations --

    def list_wiki_articles(self) -> list[Path]:
        """List all markdown files in wiki/ (recursive, excluding dot-dirs)."""
        if not self.wiki_dir.exists():
            return []
        return sorted(
            p
            for p in self.wiki_dir.rglob("*.md")
            if not any(part.startswith(".") for part in p.relative_to(self.wiki_dir).parts)
        )

    # -- Staging / atomic promotion --

    def clear_staging(self) -> None:
        """Remove all contents of the staging directory."""
        if self.staging_dir.exists():
            for item in self.staging_dir.iterdir():
                if item.name == ".gitkeep":
                    continue
                if item.is_dir():
                    shutil.rmtree(item)
                else:
                    item.unlink()

    def create_backup(self) -> str:
        """Create a backup of the current wiki state. Returns backup ID (timestamp)."""
        backup_id = datetime.now(UTC).strftime("%Y-%m-%dT%H-%M-%SZ")
        backup_path = self.backup_dir / backup_id
        backup_path.mkdir(parents=True, exist_ok=True)

        # Copy all wiki files (excluding dot-dirs)
        for item in self.wiki_dir.iterdir():
            if item.name.startswith("."):
                continue
            dest = backup_path / item.name
            if item.is_dir():
                shutil.copytree(item, dest)
            else:
                shutil.copy2(item, dest)

        # Prune old backups (keep last 5)
        backups = sorted(
            (d for d in self.backup_dir.iterdir() if d.is_dir() and d.name != ".gitkeep"),
            key=lambda d: d.name,
        )
        while len(backups) > 5:
            shutil.rmtree(backups.pop(0))

        return backup_id

    def list_backups(self) -> list[str]:
        """List available backup IDs (timestamps), newest first."""
        if not self.backup_dir.exists():
            return []
        return sorted(
            (d.name for d in self.backup_dir.iterdir() if d.is_dir() and d.name != ".gitkeep"),
            reverse=True,
        )

    def promote_staging(self) -> None:
        """Promote staged files to wiki/. Atomic per-file copy."""
        if not self.staging_dir.exists():
            return

        for item in self.staging_dir.iterdir():
            if item.name.startswith("."):
                continue
            dest = self.wiki_dir / item.name
            if item.is_dir():
                if dest.exists():
                    shutil.rmtree(dest)
                shutil.copytree(item, dest)
            else:
                shutil.copy2(item, dest)

        self.clear_staging()

    def rollback(self, backup_id: str) -> None:
        """Restore wiki from a backup."""
        backup_path = self.backup_dir / backup_id
        if not backup_path.exists():
            msg = f"Backup not found: {backup_id}"
            raise FileNotFoundError(msg)

        # Remove current wiki content (excluding dot-dirs)
        for item in self.wiki_dir.iterdir():
            if item.name.startswith("."):
                continue
            if item.is_dir():
                shutil.rmtree(item)
            else:
                item.unlink()

        # Restore from backup
        for item in backup_path.iterdir():
            dest = self.wiki_dir / item.name
            if item.is_dir():
                shutil.copytree(item, dest)
            else:
                shutil.copy2(item, dest)
