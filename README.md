# Compendium

**LLM-native knowledge compiler** — compile research sources into a living, queryable markdown wiki.

Raw sources go in, a structured wiki comes out. Ask questions, get cited answers, file outputs back. Your knowledge compounds.

## Quick Start

```bash
# Install
uv tool install compendium

# Create a project
compendium init my-wiki
cd my-wiki

# Configure your LLM
compendium config set-key anthropic

# Add sources
compendium ingest paper.pdf article.md data.csv

# Compile into a wiki
compendium compile

# Ask questions
compendium ask "What are the key findings across all sources?"

# Generate a report
compendium ask "Compare methodology A vs B" --output report

# Search
compendium search "attention mechanisms"

# Health check
compendium lint

# Start the web UI
compendium serve
```

## How It Works

1. **Ingest** sources — PDFs, markdown, web clips, CSVs
2. **Compile** via 6-step LLM pipeline: summarize, extract concepts, generate articles, create backlinks, build index, detect conflicts
3. **Query** with cited, multi-hop answers grounded in your wiki
4. **File back** — Q&A outputs become wiki articles, closing the feedback loop
5. **Lint** — automated health checks catch broken links, contradictions, and gaps

## Architecture

```
your-wiki/
  compendium.toml       # Project config
  raw/                  # Your source documents
  wiki/                 # LLM-compiled articles
    INDEX.md            # Master index
    CONCEPTS.md         # Concept taxonomy
    CONFLICTS.md        # Detected contradictions
    concepts/           # Article subdirectories
    methods/
  output/               # Q&A reports, slides, charts
```

## Features

- **Local-first** — all data on your disk, zero telemetry
- **BYOM** — Anthropic Claude, OpenAI GPT, Ollama (local), per-operation model selection
- **6-step compilation** — summarize, concepts, articles, backlinks, index, conflicts
- **Incremental updates** — add one source, update only affected articles
- **Checkpoint/resume** — compilation survives interruptions
- **Q&A engine** — index-first retrieval, cited answers with `[[wikilinks]]`
- **Output rendering** — markdown reports, Marp slide decks, matplotlib charts
- **Feedback filing** — Q&A outputs become wiki articles with auto-backlinks
- **Full-text search** — BM25 ranking, CLI + web UI
- **Wiki linting** — broken links, orphans, staleness, coverage gaps
- **Knowledge graph** — D3.js force-directed visualization
- **Web clipper** — Chrome/Firefox extension clips articles with local images
- **Obsidian compatible** — `[[wikilinks]]`, flat markdown, works in Obsidian

## CLI Reference

| Command | Description |
|---------|-------------|
| `compendium init [path]` | Create a new project |
| `compendium ingest <files...>` | Ingest PDF, MD, CSV, images |
| `compendium compile` | Full 6-step wiki compilation |
| `compendium update [--all-new]` | Incremental update |
| `compendium ask "question"` | Q&A against wiki |
| `compendium search "query"` | Full-text search |
| `compendium lint` | Run health checks |
| `compendium status` | Project overview |
| `compendium serve` | Start web UI on :17394 |
| `compendium config set-key <provider>` | Store API key |
| `compendium config test` | Test LLM connections |

## Development

```bash
git clone https://github.com/youruser/compendium
cd compendium
uv sync
uv run pytest tests/ -v    # 121 tests
uv run ruff check src/     # Lint
cd frontend && pnpm build  # Build web UI
```

## License

MIT
