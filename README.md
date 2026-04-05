# Compendium

Compendium is a local-first knowledge tool that turns a pile of source material into a living
markdown wiki. It runs as a standalone macOS app in your menu bar — no terminal required.

In simple terms:

- You drop files, web clips, and book highlights into `raw/`
- Compendium reads them and writes structured notes into `wiki/`
- You ask questions against the wiki instead of against the raw files
- You can save useful answers back into the wiki so the knowledge base keeps improving

The project is built for people who want their research, notes, and generated outputs to stay on
disk in plain files instead of being trapped inside a hosted app.

## Install & Run

### Option A: Standalone macOS App (recommended)

```bash
./scripts/build_app.sh
cp -r dist/Compendium.app /Applications/
open /Applications/Compendium.app
```

On first launch, the app walks you through:

1. **Choose your vault folder** — where raw/, wiki/, and output/ will live
2. **Pick your AI engine** — Cloud API (Anthropic/OpenAI/Gemini) or Local (Ollama with auto-detected models)
3. **Start at login** — optional auto-start on boot

After setup, the app lives in your menu bar and Dock. No terminal needed.

### Option B: CLI

```bash
uv sync --group dev
uv run compendium init demo-wiki --template research
cd demo-wiki
uv run compendium config set-key anthropic
uv run compendium ingest ~/Downloads/paper.pdf
uv run compendium compile --mode batch
```

## The Idea

Most research workflows are messy:

- PDFs live in one folder
- clipped articles live somewhere else
- notes are manual and inconsistent
- AI outputs are useful for five minutes and then disappear

Compendium fixes that by creating one loop:

1. Ingest source material (files, web clips, Apple Books highlights)
2. Compile it into a clean wiki with an LLM
3. Ask questions against that wiki
4. Turn useful answers into permanent pages
5. Rebuild indexes and backlinks automatically

The end result is not just "chat with files". It is a small knowledge system that keeps getting
better as you use it.

## What It Does

- **Ingestion** — files, PDFs (with OCR), web clips, Apple Books highlights
- **Compilation** — 6-step LLM pipeline: summarize, extract concepts, generate articles, backlinks, index, conflict detection
- **Q&A** — question answering with citations, reports, slides, HTML, and chart outputs
- **Filing** — save useful answers back into the wiki as permanent pages
- **Linting** — broken links, orphans, staleness, coverage gaps, contradictions
- **Deduplication** — SHA-256 content hashing on ingestion
- **Archive/Restore** — non-destructive soft-delete with dependency cascade (no re-compilation needed on restore)
- **Obsidian-native** — valid YAML frontmatter (Dataview), standard `[[wikilinks]]` (Graph View)

## Menu Bar App

The macOS menu bar app provides:

- **Status icon** — idle (watching), processing (compiling), paused, error
- **Pause / Resume** — control when background processing runs
- **Sync Now** — bypass the debounce timer and process immediately
- **Manage Apple Books** — submenu listing all annotated books with checkmark toggles. Tick a book to sync it, untick to archive it. Books default to unticked (opt-in).
- **View Recent Activity** — parsed from wiki/log.md
- **Settings** — API key input (macOS Keychain), Ollama model auto-discovery
- **Quit** — graceful shutdown

## Background Daemon

The daemon watches `raw/` for new files, batches them (60-second debounce), auto-runs
the compilation pipeline, and periodically polls Apple Books for new highlights.

```bash
# Headless (for launchd or terminal)
uv run compendium daemon start

# With menu bar UI
uv run compendium daemon start --menubar

# Install as macOS LaunchAgent (auto-starts on boot)
uv run compendium daemon install
```

Configuration in `compendium.toml`:

```toml
[daemon]
debounce_seconds = 60
apple_books_poll_minutes = 5
cloud_only = true
auto_compile = true
```

## Apple Books Integration

Compendium reads the macOS Apple Books SQLite database to extract highlights and annotations.

- **Selective sync** — choose which books to sync via the menu bar submenu
- **Incremental polling** — only new highlights since last sync are extracted
- **Archive/Restore** — unticking a book archives its source and dependent wiki articles to `archive/`. Ticking it back restores everything without re-compilation.
- **Metadata** — YAML frontmatter with title, author, format, book_title, book_author, genre

```bash
# CLI: list all annotated books
uv run compendium apple-books --list

# CLI: export a specific book
uv run compendium apple-books --book "Deep Work"
```

## Repository Layout

```text
src/compendium/         Python CLI, pipeline, ingestion, Q&A, lint, daemon
prompts/                Prompt templates for the LLM pipeline
scripts/                Build scripts (build_app.sh)
tests/                  Tests (227 tests)
compendium.spec         PyInstaller config for building the .app
README.md               This file
pyproject.toml          Python package and dependency config
```

## Code Overview

### Entry points

- `src/compendium/cli.py` — Typer CLI with 16+ commands
- `src/compendium/daemon/menubar_entry.py` — standalone macOS app entry point
- `src/compendium/daemon/menubar.py` — rumps menu bar UI
- `src/compendium/daemon/engine.py` — batching daemon engine
- `src/compendium/daemon/service.py` — launchd plist management

### Core

- `src/compendium/core/wiki_fs.py` — project directory structure, file I/O, archive dirs
- `src/compendium/core/config.py` — pydantic config model from `compendium.toml`
- `src/compendium/core/frontmatter.py` — YAML frontmatter models
- `src/compendium/core/wikilinks.py` — `[[wikilink]]` parsing and resolution

### Ingestion

- `src/compendium/ingest/file_drop.py` — batch file ingestion (PDF, markdown, CSV, images)
- `src/compendium/ingest/web_clip.py` — web clipping with image download
- `src/compendium/ingest/apple_books.py` — Apple Books extraction, selective sync config
- `src/compendium/ingest/watcher.py` — filesystem watcher for auto-ingestion
- `src/compendium/ingest/media.py` — remote image download for offline access

### Pipeline

- `src/compendium/pipeline/controller.py` — 6-step compilation and incremental update
- `src/compendium/pipeline/archive.py` — source-agnostic archive/restore with dependency cascade
- `src/compendium/pipeline/deps.py` — dependency graph (source -> article tracking)
- `src/compendium/pipeline/steps.py` — individual compilation steps
- `src/compendium/pipeline/sessions.py` — interactive compile/update sessions

### LLM providers

- `src/compendium/llm/factory.py` — provider factory with cloud-only enforcement
- `src/compendium/llm/ollama.py` — Ollama provider with model auto-discovery
- `src/compendium/llm/anthropic.py`, `openai_provider.py`, `gemini.py` — cloud providers

## Viewing with Obsidian

The project directory is a standard Obsidian vault. Open it in Obsidian to get:

- **Graph View** — visualize connections between wiki articles via `[[wikilinks]]`
- **Dataview** — query frontmatter fields (category, sources, tags, status) as tables
- **Built-in search** — Cmd+Shift+F for full-text search across wiki articles

## What a Compendium Project Looks Like

```text
my-wiki/
  compendium.toml
  raw/
    images/
    originals/
  wiki/
    index.md
    concepts.md
    log.md
    ...
  archive/
    sources/
    wiki/
  output/
```

- `raw/` — original source material (immutable)
- `wiki/` — LLM-compiled knowledge pages and indexes
- `archive/` — soft-deleted sources and articles (restorable)
- `output/` — generated reports, slides, charts

## Main CLI Commands

```bash
uv run compendium init              # Create a new project
uv run compendium ingest <files>    # Ingest PDFs, markdown, CSV, images
uv run compendium clip <urls>       # Clip web pages with images
uv run compendium apple-books       # Export Apple Books highlights
uv run compendium compile           # Full 6-step LLM compilation
uv run compendium update --all-new  # Incremental update
uv run compendium ask "question"    # Q&A with citations
uv run compendium lint              # Health checks
uv run compendium watch             # Watch raw/ for new files
uv run compendium download-media    # Download remote images
uv run compendium daemon start      # Start background daemon
uv run compendium daemon install    # Install as LaunchAgent
uv run compendium status            # Project summary
uv run compendium config set-key    # Store API key in Keychain
```

## Tests and Checks

```bash
uv run pytest tests -q              # 227 tests
uv run ruff check src tests         # Lint
./scripts/build_app.sh              # Build standalone .app + .dmg
```

## Design Principles

- Local-first files over hosted lock-in
- Markdown wiki as the source of truth
- Explicit indexes and logs instead of hidden state
- Model choice per operation (cloud or local)
- Generated outputs should be reusable, not disposable
- Non-destructive archive/restore over permanent deletion

## License

MIT
