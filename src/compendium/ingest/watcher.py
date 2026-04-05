"""Watch raw/ for new files and auto-ingest them."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from compendium.ingest.file_drop import SUPPORTED_EXTENSIONS, ingest_file

if TYPE_CHECKING:
    from rich.console import Console
    from watchdog.events import DirCreatedEvent, DirMovedEvent, FileCreatedEvent, FileMovedEvent

    from compendium.core.wiki_fs import WikiFileSystem


class IngestEventHandler(FileSystemEventHandler):
    """Debounced handler that auto-ingests new files in raw/."""

    def __init__(
        self,
        wfs: WikiFileSystem,
        *,
        duplicate_mode: str = "cancel",
        debounce_seconds: float = 2.0,
        console: Console | None = None,
    ) -> None:
        super().__init__()
        self.wfs = wfs
        self.duplicate_mode = duplicate_mode
        self.debounce_seconds = debounce_seconds
        self.console = console
        self._pending: dict[str, float] = {}
        self.processed: list[str] = []
        self.errors: list[str] = []

    def _should_ignore(self, path: str) -> bool:
        """Ignore dotfiles, temp files, and unsupported extensions."""
        from pathlib import Path

        p = Path(path)
        if p.name.startswith((".", "~")):
            return True
        return p.suffix.lower() not in SUPPORTED_EXTENSIONS

    def on_created(self, event: FileCreatedEvent | DirCreatedEvent) -> None:
        if not event.is_directory and not self._should_ignore(event.src_path):
            self._pending[event.src_path] = time.monotonic()

    def on_moved(self, event: FileMovedEvent | DirMovedEvent) -> None:
        if not event.is_directory and not self._should_ignore(event.dest_path):
            self._pending[event.dest_path] = time.monotonic()

    def process_pending(self) -> int:
        """Process files that have been stable for the debounce period. Returns count processed."""
        now = time.monotonic()
        ready = [p for p, t in self._pending.items() if (now - t) >= self.debounce_seconds]
        for path_str in ready:
            del self._pending[path_str]
            self._ingest_one(path_str)
        return len(ready)

    def _ingest_one(self, path_str: str) -> None:
        from pathlib import Path

        path = Path(path_str)
        if not path.exists():
            return

        result = ingest_file(
            path,
            self.wfs.raw_dir,
            self.wfs.raw_images_dir,
            self.wfs.raw_originals_dir,
            self.duplicate_mode,
        )

        if result.success:
            self.processed.append(path_str)
            if self.console:
                self.console.print(f"  [green]+[/green] {result.message}")
            self.wfs.append_log_entry(
                f"## [{_now_date()}] ingest | {path.name}\n\n"
                f"- event: watch\n- result: {result.message}\n"
            )
        else:
            self.errors.append(f"{path.name}: {result.message}")
            if self.console:
                self.console.print(f"  [red]x[/red] {result.message}")


def run_watcher(
    wfs: WikiFileSystem,
    *,
    duplicate_mode: str = "cancel",
    debounce_seconds: float = 2.0,
    console: Console | None = None,
    poll_interval: float = 0.5,
) -> tuple[list[str], list[str]]:
    """Block until Ctrl+C, watching raw/ for new files.

    Returns (processed, errors) lists on shutdown.
    """
    handler = IngestEventHandler(
        wfs,
        duplicate_mode=duplicate_mode,
        debounce_seconds=debounce_seconds,
        console=console,
    )
    observer = Observer()
    observer.schedule(handler, str(wfs.raw_dir), recursive=True)
    observer.start()

    try:
        while True:
            handler.process_pending()
            time.sleep(poll_interval)
    except KeyboardInterrupt:
        pass
    finally:
        observer.stop()
        observer.join()

    # Process any remaining pending files
    handler.debounce_seconds = 0
    handler.process_pending()

    return handler.processed, handler.errors


def _now_date() -> str:
    from datetime import UTC, datetime

    return datetime.now(UTC).strftime("%Y-%m-%d")
