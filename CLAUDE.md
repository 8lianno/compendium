# Compendium — Development Guide

## What is this?
LLM-native knowledge compiler. Raw research sources -> compiled markdown wiki -> Q&A -> feedback loop. Local-first, file-first, BYOM (Bring Your Own Model). Designed as an Obsidian-native vault.

## Quick Commands
```bash
uv run compendium --help            # CLI reference
uv run compendium init [path]       # Create new project (open in Obsidian)
uv run compendium status --dir .    # Show project status
uv run compendium clip <url>        # Clip web pages with images into raw/
uv run compendium apple-books       # Export Apple Books highlights into raw/
uv run compendium watch             # Auto-ingest new files in raw/
uv run compendium download-media    # Download remote images for offline access
uv run compendium daemon start      # Start background daemon (watcher + auto-compile)
uv run compendium daemon start --menubar  # Start with macOS menu bar UI
uv run compendium daemon install    # Install as macOS LaunchAgent
uv run pytest tests/ -v             # Run tests (196 tests)
uv run ruff check src/ tests/       # Lint
```

## Architecture
- **Python 3.12+**, managed with `uv`
- **CLI**: Typer (src/compendium/cli.py) - 16 commands
- **Core**: src/compendium/core/ - config, frontmatter, WikiFileSystem, wikilinks
- **LLM**: src/compendium/llm/ - provider protocol, Anthropic/OpenAI/Ollama, router, token tracker
- **Pipeline**: src/compendium/pipeline/ - 6-step compilation, dependency graph, checkpoint/resume
- **Q&A**: src/compendium/qa/ - engine, sessions, output (reports/slides/charts), feedback filing
- **Ingestion**: src/compendium/ingest/ - file drop, PDF/OCR, web clip, Apple Books, dedup, watcher, media download
- **Daemon**: src/compendium/daemon/ - batching engine, launchd service, macOS menu bar app
- **Lint**: src/compendium/lint/ - broken links, orphans, staleness, coverage gaps
- **Prompts**: prompts/*.md - version-controlled templates with {{variable}} interpolation

## Key Patterns
- All data models use **pydantic v2** (BaseModel)
- Enums use **StrEnum** (not str, Enum)
- Use `from __future__ import annotations` in all files
- Type-only imports go in `if TYPE_CHECKING:` blocks
- WikiFileSystem handles all file I/O with atomic staging -> promotion -> rollback
- LLM providers implement the `LlmProvider` protocol (src/compendium/llm/provider.py)
- Obsidian-native: valid YAML frontmatter (Dataview compatible), standard `[[wikilinks]]` (Graph View compatible)
- Canonical retrieval entrypoint: `wiki/index.md` (legacy `wiki/INDEX.md` is read as fallback)

## Testing
- `tests/test_core.py` - frontmatter, config, WikiFileSystem, wikilinks
- `tests/test_llm.py` - providers, router, token tracker, prompt loader, factory
- `tests/test_ingestion.py` - file drop, web clip, PDF, CSV, dedup, batch
- `tests/test_pipeline.py` - dep graph, checkpoint, steps, full pipeline, incremental
- `tests/test_qa.py` - Q&A engine, sessions, output, feedback filing
- `tests/test_lint.py` - broken links, orphans, staleness, coverage gaps, structure
- `tests/test_watch.py` - file watcher, debounce, filtering, auto-ingest
- `tests/test_media.py` - remote image scanning, download, URL localization
- `tests/test_clip.py` - web page clipping, duplicate handling, image download
- `tests/test_apple_books.py` - Apple Books extraction, export, roundtrip
- `tests/test_daemon.py` - daemon engine, batching, cloud-only, plist, sync cache
- `tests/test_gaps.py` - index verification, template operations
