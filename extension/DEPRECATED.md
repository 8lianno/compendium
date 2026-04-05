# Browser Extension — Deprecated

This browser extension was designed for the web server architecture (FastAPI + WebSocket) which has been removed in favor of the Obsidian-native, file-first approach.

## Migration

Use one of these alternatives for web clipping:

1. **Obsidian Web Clipper** (recommended) — clips directly into your vault's `raw/` folder
2. **CLI ingestion** — `compendium ingest <url>` to clip a URL from the terminal
3. **Watch mode** — `compendium watch` auto-ingests any file dropped into `raw/`

## Why

Browser extensions cannot write directly to the local filesystem. The original extension communicated with a local server over WebSocket (`ws://127.0.0.1:17394/ws/clip`). Since the server has been removed, this extension no longer functions.
