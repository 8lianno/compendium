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
        self._logs_item = rumps.MenuItem("View Recent Activity", callback=self._show_logs)
        self._settings_item = rumps.MenuItem("Settings", callback=self._show_settings)
        self._quit_item = rumps.MenuItem("Quit Compendium", callback=self._quit)

        self.menu = [
            self._status_item,
            None,  # separator
            self._toggle_item,
            self._sync_item,
            None,
            self._logs_item,
            self._settings_item,
            None,
            self._quit_item,
        ]

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
