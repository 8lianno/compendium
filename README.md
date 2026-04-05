# Compendium

Compendium is a local-first knowledge tool that turns a pile of source material into a living
markdown wiki.

In simple terms:

- You drop files and web clips into `raw/`
- Compendium reads them and writes structured notes into `wiki/`
- You ask questions against the wiki instead of against the raw files
- You can save useful answers back into the wiki so the knowledge base keeps improving

The project is built for people who want their research, notes, and generated outputs to stay on
disk in plain files instead of being trapped inside a hosted app.

## The Idea

Most research workflows are messy:

- PDFs live in one folder
- clipped articles live somewhere else
- notes are manual and inconsistent
- AI outputs are useful for five minutes and then disappear

Compendium tries to fix that by creating one loop:

1. Ingest source material
2. Compile it into a clean wiki
3. Ask questions against that wiki
4. Turn useful answers into permanent pages
5. Rebuild search, graph, and indexes automatically

The end result is not just "chat with files". It is a small knowledge system that keeps getting
better as you use it.

## What It Does

Compendium currently includes:

- file and web ingestion with automatic deduplication
- PDF extraction with OCR support
- a compile/update pipeline that writes wiki pages
- interactive and batch compile modes
- question answering with citations
- report, slides, HTML, and chart outputs
- filing generated outputs back into the wiki
- wiki linting and health checks (broken links, orphans, conflicts, staleness)
- file watcher for auto-ingestion from OS automation and cloud sync
- remote image download for offline access
- Obsidian-native: valid YAML frontmatter (Dataview), standard `[[wikilinks]]` (Graph View)

## How It Works

At a high level, the flow looks like this:

```text
raw sources -> summaries -> concepts -> wiki pages -> search/index/graph
                                           |
                                           v
                                   Q&A and generated outputs
                                           |
                                           v
                                  file useful outputs back
```

The important idea is that the wiki is the center of the system.

- `raw/` is the input
- `wiki/` is the durable knowledge layer
- `output/` is where generated artifacts land before optional filing

## Repository Layout

This repository contains the Compendium application itself, not a sample knowledge project.

```text
src/compendium/         Python CLI, pipeline, ingestion, Q&A, and lint
prompts/                Prompt files used by the compile and Q&A pipeline
tests/                  Tests
README.md               This file
pyproject.toml          Python package and dependency config
```

## Code Overview In Simple Terms

If you are new to the codebase, these are the most important areas:

### Entry point

- `src/compendium/cli.py`
  - The command-line app.
  - Commands: `init`, `ingest`, `compile`, `update`, `ask`, `lint`, `watch`, `download-media`, and more.

### Core filesystem and config

- `src/compendium/core/wiki_fs.py`
  - Handles project folders and wiki file operations.
  - Also handles log writes and auto-commit helpers.

- `src/compendium/core/config.py`
  - Defines the project config model loaded from `compendium.toml`.

- `src/compendium/core/templates.py`
  - Starter schema templates such as `research`, `book-reading`, and `competitive-analysis`.

### Ingestion

- `src/compendium/ingest/file_drop.py`
  - Batch file ingestion.
  - Handles worker concurrency, duplicate rules, and per-file results.

- `src/compendium/ingest/pdf.py`
  - PDF extraction and OCR-related metadata.

- `src/compendium/ingest/web_clip.py`
  - Web clipping logic, metadata capture, duplicate resolution, and raw HTML fallback.

### Compilation pipeline

- `src/compendium/pipeline/controller.py`
  - Runs the main compile/update flow.
  - Regenerates wiki artifacts like `index.md` and `concepts.md`.

- `src/compendium/pipeline/steps.py`
  - Contains the lower-level wiki generation and logging steps.

- `src/compendium/pipeline/sessions.py`
  - Handles interactive compile/update sessions and approval flow.

### Q&A and output filing

- `src/compendium/qa/engine.py`
  - Answers questions against the wiki.

- `src/compendium/qa/output.py`
  - Renders reports, slides, standalone HTML, and chart bundles.

- `src/compendium/qa/filing.py`
  - Files generated outputs back into the wiki with merge/replace/keep-both rules.

### Linting

- `src/compendium/lint/engine.py`
  - Health checks for broken links, stale content, contradictions, and coverage gaps.

### File watching and media

- `src/compendium/ingest/watcher.py`
  - Watches `raw/` for new files and auto-ingests them.

- `src/compendium/ingest/media.py`
  - Downloads remote images in wiki articles for offline access.

### LLM providers

- `src/compendium/llm/factory.py`
  - Creates the provider used for each operation.

- `src/compendium/llm/anthropic.py`
- `src/compendium/llm/openai_provider.py`
- `src/compendium/llm/gemini.py`
- `src/compendium/llm/ollama.py`
  - Concrete provider integrations.

- `src/compendium/llm/retry.py`
  - Shared retry/backoff logic for remote model calls.

## Viewing with Obsidian

The project directory is a standard Obsidian vault. Open it in Obsidian to get:

- **Graph View** — visualize connections between wiki articles via `[[wikilinks]]`
- **Dataview** — query frontmatter fields (category, sources, tags, status) as tables
- **Built-in search** — Cmd+Shift+F for full-text search across wiki articles
- **Web Clipper** — use the Obsidian Web Clipper extension to clip articles into `raw/`

## What a Compendium Project Looks Like

When you run `compendium init`, you get a local knowledge workspace that looks roughly like this:

```text
my-wiki/
  compendium.toml
  raw/
    .clip-log.json
    images/
    originals/
  wiki/
    index.md
    concepts.md
    log.md
    ...
  output/
  prompts/
```

The important folders are:

- `raw/`: original source material and ingest artifacts
- `wiki/`: compiled knowledge pages and indexes
- `output/`: generated reports, slides, HTML, and chart notes

## Using Compendium

### 1. Install dependencies for this repository

```bash
uv sync --group dev
```

### 2. Create a knowledge project

```bash
uv run compendium init demo-wiki --template research
cd demo-wiki
```

### 3. Configure a model provider

For example:

```bash
uv run compendium config set-key anthropic
```

You can also point some operations at Ollama if you want a local model.

### 4. Add sources

```bash
uv run compendium ingest ~/Downloads/paper.pdf ~/Downloads/notes.md
```

### 5. Compile the wiki

Batch mode:

```bash
uv run compendium compile --mode batch
```

Interactive mode:

```bash
uv run compendium compile --mode interactive
```

### 6. Ask questions

```bash
uv run compendium ask "What are the main themes across these sources?"
```

Generate a report:

```bash
uv run compendium ask "Compare the strongest arguments" --output report
```

Generate slides and file them back into the wiki:

```bash
uv run compendium ask "Summarize this for a team update" --output slides --file
```

### 7. Open in Obsidian

Open the project directory as an Obsidian vault. Install the Dataview plugin for
queryable frontmatter tables.

### 8. Watch for new files (optional)

```bash
uv run compendium watch
```

This monitors `raw/` and auto-ingests new files — works with Obsidian Web Clipper,
OS automation (Hazel, Shortcuts), cloud sync, and voice transcriptions.

## Main CLI Commands

```bash
uv run compendium init
uv run compendium ingest
uv run compendium compile
uv run compendium update
uv run compendium ask
uv run compendium lint
uv run compendium watch
uv run compendium download-media
uv run compendium status
uv run compendium usage
uv run compendium config set-key
uv run compendium config test
```

Useful examples:

```bash
uv run compendium update --all-new
uv run compendium ask "Turn this into a summary page" --output html --file
uv run compendium lint --deep
uv run compendium download-media --dry-run
```

## Running the Codebase Locally as a Developer

```bash
uv sync --group dev
```

## Tests and Checks

```bash
uv run pytest tests -q
uv run ruff check src tests
```

## Design Principles

Compendium is built around a few simple rules:

- local-first files over hosted lock-in
- markdown wiki as the source of truth
- explicit indexes and logs instead of hidden state
- model choice per operation instead of one global provider
- generated outputs should be reusable, not disposable

## Current Status

This codebase includes:

- CLI-driven workflow (no server required)
- ingestion, compile/update, Q&A, filing, and lint flows
- file watcher for auto-ingestion
- Obsidian-native vault with Dataview and Graph View compatibility

It is best thought of as a tool for building and maintaining a personal or team knowledge
wiki with LLM assistance, using Obsidian as the viewing layer.

## License

MIT
