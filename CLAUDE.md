# Compendium — Development Guide

## What is this?
LLM-native knowledge compiler. Raw research sources -> compiled markdown wiki -> Q&A -> feedback loop. Local-first, BYOM (Bring Your Own Model).

## Quick Commands
```bash
uv run compendium --help          # CLI reference
uv run compendium init [path]     # Create new project
uv run compendium status --dir .  # Show project status
uv run compendium serve           # Start web server on :17394
uv run pytest tests/ -v           # Run tests (121 tests)
uv run ruff check src/ tests/     # Lint
cd frontend && pnpm build         # Build web UI
```

## Architecture
- **Python 3.12+**, managed with `uv`
- **CLI**: Typer (src/compendium/cli.py) - 12 commands
- **Server**: FastAPI (src/compendium/server.py) - REST API + WebSocket + serves Svelte SPA
- **Frontend**: Svelte 5 + Vite (frontend/) - builds to src/compendium/web/static/
- **Extension**: Chrome/Firefox Manifest V3 (extension/) - web clipper
- **Core**: src/compendium/core/ - config, frontmatter, WikiFileSystem, wikilinks
- **LLM**: src/compendium/llm/ - provider protocol, Anthropic/OpenAI/Ollama, router, token tracker
- **Pipeline**: src/compendium/pipeline/ - 6-step compilation, dependency graph, checkpoint/resume
- **Q&A**: src/compendium/qa/ - engine, sessions, output (reports/slides/charts), feedback filing
- **Search**: src/compendium/search/ - Whoosh BM25 full-text search
- **Lint**: src/compendium/lint/ - broken links, orphans, staleness, coverage gaps
- **Prompts**: prompts/*.md - version-controlled templates with {{variable}} interpolation

## Key Patterns
- All data models use **pydantic v2** (BaseModel)
- Enums use **StrEnum** (not str, Enum)
- Use `from __future__ import annotations` in all files
- Type-only imports go in `if TYPE_CHECKING:` blocks
- WikiFileSystem handles all file I/O with atomic staging -> promotion -> rollback
- LLM providers implement the `LlmProvider` protocol (src/compendium/llm/provider.py)

## Testing
- `tests/test_core.py` - frontmatter, config, WikiFileSystem, wikilinks (20 tests)
- `tests/test_llm.py` - providers, router, token tracker, prompt loader, factory (23 tests)
- `tests/test_ingestion.py` - file drop, web clip, PDF, CSV, dedup, batch (22 tests)
- `tests/test_pipeline.py` - dep graph, checkpoint, steps, full pipeline, incremental (19 tests)
- `tests/test_qa.py` - Q&A engine, sessions, output, feedback filing (17 tests)
- `tests/test_search.py` - BM25 index, search ranking, snippets, update/remove (12 tests)
- `tests/test_lint.py` - broken links, orphans, staleness, coverage gaps, structure (13 tests)

## All Phases Complete
Phase 0 (Foundation) -> Phase 1 (BYOM) -> Phase 2 (Ingestion) -> Phase 3 (Compilation) -> Phase 4 (Q&A) -> Phase 5 (Search/Lint) -> Frontend + Extension + Beta
