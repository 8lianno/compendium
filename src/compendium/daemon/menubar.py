"""macOS Menu Bar app — lightweight status/control UI for the daemon."""

from __future__ import annotations

import logging
import re
import threading
from pathlib import Path
from typing import TYPE_CHECKING

import rumps

from compendium.daemon.engine import DaemonEngine, DaemonState

if TYPE_CHECKING:
    from compendium.core.wiki_fs import WikiFileSystem

logger = logging.getLogger("compendium.menubar")

# Icon file directory (SVG assets shipped with the package)
_ICONS_DIR = Path(__file__).parent / "icons"

# State -> (icon_filename, emoji_fallback)
_ICON_MAP: dict[DaemonState, tuple[str, str]] = {
    DaemonState.IDLE: ("icon_active.svg", "\u26AA"),
    DaemonState.PROCESSING: ("icon_processing.svg", "\U0001F7E2"),
    DaemonState.PAUSED: ("icon_paused.svg", "\U0001F534"),
    DaemonState.ERROR: ("icon_error.svg", "\u26A0\uFE0F"),
}


def _resolve_icon(state: DaemonState) -> str | None:
    """Return the icon file path for a state, or None to use emoji fallback."""
    filename, _ = _ICON_MAP[state]
    icon_path = _ICONS_DIR / filename
    if icon_path.exists():
        return str(icon_path)
    return None

_STATUS_LABELS: dict[DaemonState, str] = {
    DaemonState.IDLE: "Status: Watching",
    DaemonState.PROCESSING: "Status: Processing...",
    DaemonState.PAUSED: "Status: Paused",
    DaemonState.ERROR: "Status: Error",
}

# Providers that can be configured via the Settings menu
_CONFIGURABLE_PROVIDERS = ("anthropic", "openai", "gemini")


class CompendiumMenuBar(rumps.App):
    """Menu bar app wrapping the DaemonEngine."""

    def __init__(self, wfs: WikiFileSystem, engine: DaemonEngine) -> None:
        # Try file-based icon first, fall back to emoji title
        icon_path = _resolve_icon(DaemonState.IDLE)
        _, emoji_fallback = _ICON_MAP[DaemonState.IDLE]
        super().__init__(
            name="Compendium",
            icon=icon_path,
            title=None if icon_path else emoji_fallback,
            quit_button=None,  # We add our own
        )
        self.wfs = wfs
        self.engine = engine
        self.engine._on_state_change = self._on_state_change

        # Build menu items
        self._status_item = rumps.MenuItem("Status: Watching", callback=None)
        self._status_item.set_callback(None)
        self._toggle_item = rumps.MenuItem("Pause Watcher", callback=self._toggle_watcher)
        self._sync_item = rumps.MenuItem("Sync Now", callback=self._force_sync)
        self._books_menu = rumps.MenuItem("Manage Apple Books")
        self._books_refresh = rumps.MenuItem("Refresh List", callback=self._refresh_books)
        self._books_menu.add(self._books_refresh)
        self._logs_item = rumps.MenuItem("View Recent Activity", callback=self._show_logs)
        self._settings_item = rumps.MenuItem("Settings", callback=self._show_settings)
        self._quit_item = rumps.MenuItem("Quit Compendium", callback=self._quit)

        self.menu = [
            self._status_item,
            None,  # separator
            self._toggle_item,
            self._sync_item,
            self._books_menu,
            None,
            self._logs_item,
            self._settings_item,
            None,
            self._quit_item,
        ]

        # Populate books submenu on launch (best-effort)
        try:
            self._refresh_books_submenu()
        except Exception:
            logger.exception("Failed to populate Apple Books submenu")

    # -- State change callback (called from engine thread) --

    def _on_state_change(self, new_state: DaemonState) -> None:
        """Update icon and status text when engine state changes."""
        icon_path = _resolve_icon(new_state)
        _, emoji_fallback = _ICON_MAP.get(new_state, (None, "\u26AA"))
        if icon_path:
            self.icon = icon_path
            self.title = None
        else:
            self.icon = None
            self.title = emoji_fallback
        label = _STATUS_LABELS.get(new_state, "Status: Unknown")
        if new_state == DaemonState.ERROR and self.engine.stats.last_error:
            label = f"Status: Error \u2014 {self.engine.stats.last_error[:60]}"
        self._status_item.title = label

    # -- US-2: Play / Pause / Quit --

    @rumps.clicked("Pause Watcher")
    def _toggle_watcher(self, sender: rumps.MenuItem) -> None:
        if self.engine.state == DaemonState.PAUSED:
            self.engine.resume()
            sender.title = "Pause Watcher"
        else:
            self.engine.pause()
            sender.title = "Resume Watcher"

    def _quit(self, _sender: rumps.MenuItem) -> None:
        self.engine.stop()
        rumps.quit_application()

    # -- US-3: Force Manual Sync --

    @rumps.clicked("Sync Now")
    def _force_sync(self, _sender: rumps.MenuItem) -> None:
        if self.engine.state == DaemonState.PROCESSING:
            rumps.notification(
                "Compendium", "Already processing", "Wait for current batch to complete."
            )
            return

        def _sync_and_notify() -> None:
            did_work = self.engine.force_sync()
            if not did_work:
                rumps.notification(
                    "Compendium",
                    "Vault is up to date",
                    "No new files in raw/ and no new Apple Books highlights.",
                )

        threading.Thread(target=_sync_and_notify, daemon=True).start()

    # -- US-4: View Recent Activity (parsed from wiki/log.md) --

    @rumps.clicked("View Recent Activity")
    def _show_logs(self, _sender: rumps.MenuItem) -> None:
        entries = _parse_recent_log_entries(self.wfs, limit=5)
        if not entries:
            # Fall back to in-memory daemon logs
            mem_logs = self.engine.recent_logs[-5:]
            text = "\n".join(mem_logs) if mem_logs else "No recent activity."
        else:
            text = "\n\n".join(entries)

        rumps.alert(
            title="Compendium \u2014 Recent Activity",
            message=text,
            ok="Close",
        )

    # -- US-5: Secure API Configuration --

    @rumps.clicked("Settings")
    def _show_settings(self, _sender: rumps.MenuItem) -> None:
        from compendium.llm.factory import get_api_key, set_api_key

        for provider in _CONFIGURABLE_PROVIDERS:
            existing = get_api_key(provider)
            mask = f"{'*' * 8}{existing[-4:]}" if existing else "not set"

            response = rumps.Window(
                title=f"API Key: {provider.title()}",
                message=f"Current: {mask}\n\nPaste your API key (leave empty to skip):",
                ok="Save",
                cancel="Skip",
                dimensions=(320, 24),
            ).run()

            if response.clicked and response.text.strip():
                set_api_key(provider, response.text.strip())
                rumps.notification(
                    "Compendium",
                    f"{provider.title()} key saved",
                    "Stored securely in macOS Keychain.",
                )

        # Ollama model selection
        from compendium.llm.ollama import list_ollama_models

        models = list_ollama_models()
        if models:
            model_list = "\n".join(f"  \u2022 {m}" for m in models)
            from compendium.core.config import CompendiumConfig

            config = CompendiumConfig.load(self.wfs.root / "compendium.toml")
            current = config.models.compilation.model

            resp = rumps.Window(
                title="Ollama \u2014 Local Models",
                message=(
                    f"Detected models:\n{model_list}\n\n"
                    f"Current: {current}\n"
                    "Type a model name to switch (or leave empty to skip):"
                ),
                ok="Save",
                cancel="Skip",
                dimensions=(350, 24),
                default_text=current if config.models.compilation.provider == "ollama" else "",
            ).run()

            if resp.clicked and resp.text.strip():
                from compendium.daemon.menubar_entry import apply_engine_choice

                apply_engine_choice(
                    self.wfs.root / "compendium.toml",
                    "ollama",
                    model=resp.text.strip(),
                    endpoint="http://localhost:11434",
                )
                rumps.notification(
                    "Compendium", "Ollama model updated", f"Now using: {resp.text.strip()}"
                )


    # -- Apple Books selective sync --

    def _refresh_books(self, _sender: rumps.MenuItem) -> None:
        """Refresh the Apple Books submenu."""
        self._refresh_books_submenu()
        rumps.notification("Compendium", "Books list refreshed", "")

    def _refresh_books_submenu(self) -> None:
        """Rebuild the books submenu from discover_books() + config."""
        from compendium.ingest.apple_books import (
            discover_books,
            load_books_config,
            save_books_config,
        )

        books = discover_books()
        config = load_books_config(self.wfs.root)

        # Clear existing book items (keep Refresh at the end)
        keys_to_remove = [
            k for k in self._books_menu
            if k != "Refresh List"
        ]
        for k in keys_to_remove:
            del self._books_menu[k]

        if not books:
            empty = rumps.MenuItem("No annotated books found", callback=None)
            empty.set_callback(None)
            self._books_menu.insert_before("Refresh List", empty)
            return

        # Ensure all discovered books have a config entry
        updated = False
        for book in books:
            aid = book["asset_id"]
            if aid not in config:
                config[aid] = {
                    "title": book["title"],
                    "author": book["author"],
                    "enabled": False,
                }
                updated = True

        if updated:
            save_books_config(self.wfs.root, config)

        # Add separator before Refresh
        self._books_menu.insert_before("Refresh List", None)

        # Add a menu item per book with checkmark state
        for book in books:
            aid = book["asset_id"]
            enabled = config.get(aid, {}).get("enabled", True)
            label = f"{book['title']} \u2014 {book['author']}"
            item = rumps.MenuItem(label, callback=self._toggle_book)
            item.state = 1 if enabled else 0
            # Store asset_id on the item for the callback
            item._compendium_asset_id = aid  # type: ignore[attr-defined]
            item._compendium_title = book["title"]  # type: ignore[attr-defined]
            self._books_menu.insert_before("Refresh List", item)

    def _toggle_book(self, sender: rumps.MenuItem) -> None:
        """Toggle a book's sync state and archive/restore accordingly."""
        from compendium.ingest.apple_books import (
            find_source_for_book,
            load_books_config,
            save_books_config,
        )

        asset_id = sender._compendium_asset_id  # type: ignore[attr-defined]
        book_title = sender._compendium_title  # type: ignore[attr-defined]
        new_enabled = not bool(sender.state)

        # Update config
        config = load_books_config(self.wfs.root)
        if asset_id in config:
            config[asset_id]["enabled"] = new_enabled
            save_books_config(self.wfs.root, config)

        sender.state = 1 if new_enabled else 0

        # Archive or restore in background
        source = find_source_for_book(self.wfs.raw_dir, book_title)
        if source and not new_enabled:
            # Toggling OFF → archive
            rel = str(source.relative_to(self.wfs.root))
            threading.Thread(
                target=self._run_archive, args=(rel, book_title), daemon=True
            ).start()
        elif new_enabled:
            # Toggling ON → restore from archive or extract fresh
            from compendium.ingest.file_drop import slugify

            slug = slugify(f"{book_title}-highlights")
            archived = self.wfs.archive_sources_dir / f"{slug}.md"
            if archived.exists():
                rel = f"raw/{slug}.md"
                threading.Thread(
                    target=self._run_restore, args=(rel, book_title), daemon=True
                ).start()
            elif not source:
                # Brand new sync — extract highlights immediately
                threading.Thread(
                    target=self._run_extract_book,
                    args=(asset_id, book_title),
                    daemon=True,
                ).start()

    def _run_archive(self, source_rel: str, title: str) -> None:
        from compendium.pipeline.archive import archive_source

        result = archive_source(self.wfs, source_rel)
        if result.sources_moved:
            rumps.notification(
                "Compendium",
                f"Archived: {title}",
                f"{len(result.articles_archived)} article(s) archived, "
                f"{len(result.articles_patched)} patched",
            )
            self.engine._add_log(f"Archived: {title}")

    def _run_restore(self, source_rel: str, title: str) -> None:
        from compendium.pipeline.archive import restore_source

        result = restore_source(self.wfs, source_rel)
        if result.sources_moved:
            rumps.notification(
                "Compendium",
                f"Restored: {title}",
                f"{len(result.articles_restored)} article(s) restored",
            )
            self.engine._add_log(f"Restored: {title}")
            # Trigger compilation to re-weave backlinks
            if self.engine.auto_compile:
                self.engine._run_incremental_update()

    def _run_extract_book(self, asset_id: str, title: str) -> None:
        """Extract a single book's highlights and optionally compile."""
        from compendium.ingest.apple_books import export_to_markdown, extract_highlights

        exports = extract_highlights(asset_id=asset_id)
        if not exports:
            rumps.notification("Compendium", title, "No highlights found for this book.")
            return

        for book in exports:
            output, msg = export_to_markdown(book, self.wfs.raw_dir, duplicate_mode="overwrite")
            if output:
                self.engine._add_log(f"Synced: {msg}")
                self.engine.stats.books_synced += 1

        rumps.notification("Compendium", f"Synced: {title}", "Highlights extracted to raw/")

        # Trigger compilation
        if self.engine.auto_compile:
            self.engine._run_incremental_update()


def _parse_recent_log_entries(wfs: WikiFileSystem, *, limit: int = 5) -> list[str]:
    """Parse the last N entries from wiki/log.md into human-readable summaries."""
    log_path = wfs.wiki_dir / "log.md"
    if not log_path.exists():
        return []

    try:
        content = log_path.read_text()
    except OSError:
        return []

    # Each entry starts with "## [date] event | title"
    pattern = re.compile(r"^## \[([^\]]+)\] (.+)$", re.MULTILINE)
    matches = list(pattern.finditer(content))
    if not matches:
        return []

    entries: list[str] = []
    for match in matches[-limit:]:
        date = match.group(1)
        rest = match.group(2).strip()

        # Extract body lines after the header until next header or EOF
        start = match.end()
        body_end = content.find("\n## ", start)
        body = content[start : body_end if body_end != -1 else len(content)].strip()

        # Parse key-value lines from the body
        details: list[str] = []
        for line in body.split("\n"):
            line = line.strip().lstrip("- ")
            if ":" in line:
                details.append(line)

        summary = f"{date}: {rest}"
        if details:
            summary += f" ({'; '.join(details[:2])})"
        entries.append(summary)

    return entries


def run_menubar(wfs: WikiFileSystem, engine: DaemonEngine) -> None:
    """Launch the menu bar app (blocks on the macOS run loop)."""
    engine.start_background()
    app = CompendiumMenuBar(wfs, engine)
    app.run()
