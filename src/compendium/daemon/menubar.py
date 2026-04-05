"""macOS Menu Bar app — lightweight status/control UI for the daemon."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import rumps

from compendium.daemon.engine import DaemonEngine, DaemonState

if TYPE_CHECKING:
    from compendium.core.wiki_fs import WikiFileSystem

logger = logging.getLogger("compendium.menubar")

# State -> icon mapping
_ICONS: dict[DaemonState, str] = {
    DaemonState.IDLE: "\u26AA",       # white circle
    DaemonState.PROCESSING: "\U0001F7E2",  # green circle
    DaemonState.PAUSED: "\U0001F534",      # red circle
    DaemonState.ERROR: "\u26A0\uFE0F",     # warning sign
}


class CompendiumMenuBar(rumps.App):
    """Menu bar app wrapping the DaemonEngine."""

    def __init__(self, wfs: WikiFileSystem, engine: DaemonEngine) -> None:
        super().__init__(
            name="Compendium",
            title=_ICONS[DaemonState.IDLE],
            quit_button=None,  # We add our own
        )
        self.wfs = wfs
        self.engine = engine
        self.engine._on_state_change = self._on_state_change

        # Build menu items
        self._status_item = rumps.MenuItem("Status: Idle", callback=None)
        self._status_item.set_callback(None)
        self._toggle_item = rumps.MenuItem("Pause Watcher", callback=self._toggle_watcher)
        self._sync_item = rumps.MenuItem("Force Manual Sync", callback=self._force_sync)
        self._logs_item = rumps.MenuItem("View Recent Logs", callback=self._show_logs)
        self._quit_item = rumps.MenuItem("Quit", callback=self._quit)

        self.menu = [
            self._status_item,
            None,  # separator
            self._toggle_item,
            self._sync_item,
            None,
            self._logs_item,
            None,
            self._quit_item,
        ]

    def _on_state_change(self, new_state: DaemonState) -> None:
        """Callback from engine when state changes — update icon and status text."""
        self.title = _ICONS.get(new_state, "\u26AA")
        labels = {
            DaemonState.IDLE: "Status: Idle (Watching)",
            DaemonState.PROCESSING: "Status: Processing...",
            DaemonState.PAUSED: "Status: Paused",
            DaemonState.ERROR: f"Status: Error — {self.engine.stats.last_error or 'unknown'}",
        }
        self._status_item.title = labels.get(new_state, "Status: Unknown")

    @rumps.clicked("Pause Watcher")
    def _toggle_watcher(self, sender: rumps.MenuItem) -> None:
        if self.engine.state == DaemonState.PAUSED:
            self.engine.resume()
            sender.title = "Pause Watcher"
        else:
            self.engine.pause()
            sender.title = "Resume Watcher"

    @rumps.clicked("Force Manual Sync")
    def _force_sync(self, _sender: rumps.MenuItem) -> None:
        if self.engine.state == DaemonState.PROCESSING:
            rumps.notification(
                "Compendium", "Already processing", "Wait for current batch to complete."
            )
            return
        # Run sync in background thread to avoid blocking the menu bar
        import threading

        threading.Thread(target=self.engine.force_sync, daemon=True).start()

    @rumps.clicked("View Recent Logs")
    def _show_logs(self, _sender: rumps.MenuItem) -> None:
        logs = self.engine.recent_logs[-10:]
        text = "No recent activity." if not logs else "\n".join(logs)

        rumps.alert(
            title="Compendium — Recent Activity",
            message=text,
            ok="Close",
        )

    def _quit(self, _sender: rumps.MenuItem) -> None:
        self.engine.stop()
        rumps.quit_application()


def run_menubar(wfs: WikiFileSystem, engine: DaemonEngine) -> None:
    """Launch the menu bar app (blocks on the macOS run loop)."""
    # Start daemon engine in background thread
    engine.start_background()

    app = CompendiumMenuBar(wfs, engine)
    app.run()
