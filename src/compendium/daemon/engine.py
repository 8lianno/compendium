"""Batching daemon engine — watches raw/, auto-compiles, polls Apple Books."""

from __future__ import annotations

import contextlib
import logging
import threading
import time
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Any

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from compendium.ingest.file_drop import SUPPORTED_EXTENSIONS, ingest_file

if TYPE_CHECKING:
    from pathlib import Path

    from watchdog.events import DirCreatedEvent, DirMovedEvent, FileCreatedEvent, FileMovedEvent

    from compendium.core.wiki_fs import WikiFileSystem

logger = logging.getLogger("compendium.daemon")


class DaemonState(StrEnum):
    IDLE = "idle"
    PROCESSING = "processing"
    PAUSED = "paused"
    ERROR = "error"


@dataclass
class DaemonStats:
    """Accumulated daemon statistics."""

    files_ingested: int = 0
    compilations_run: int = 0
    books_synced: int = 0
    errors: int = 0
    last_compile_at: str | None = None
    last_error: str | None = None


@dataclass
class BatchEvent:
    """A file event queued for batch processing."""

    path: str
    timestamp: float


class _BatchEventHandler(FileSystemEventHandler):
    """Collects file events into the daemon's batch queue."""

    def __init__(self, engine: DaemonEngine) -> None:
        super().__init__()
        self.engine = engine

    def _should_ignore(self, path: str) -> bool:
        from pathlib import Path

        p = Path(path)
        if p.name.startswith((".", "~")):
            return True
        return p.suffix.lower() not in SUPPORTED_EXTENSIONS

    def on_created(self, event: FileCreatedEvent | DirCreatedEvent) -> None:
        if not event.is_directory and not self._should_ignore(event.src_path):
            self.engine.enqueue(event.src_path)

    def on_moved(self, event: FileMovedEvent | DirMovedEvent) -> None:
        if not event.is_directory and not self._should_ignore(event.dest_path):
            self.engine.enqueue(event.dest_path)


class DaemonEngine:
    """Core daemon: watches raw/, batches files, auto-compiles, polls Apple Books.

    Designed to run in a background thread, controlled by the menu bar app or CLI.
    """

    def __init__(
        self,
        wfs: WikiFileSystem,
        *,
        debounce_seconds: int = 60,
        apple_books_poll_minutes: int = 5,
        cloud_only: bool = True,
        auto_compile: bool = True,
        on_state_change: Any | None = None,
    ) -> None:
        self.wfs = wfs
        self.debounce_seconds = debounce_seconds
        self.apple_books_poll_minutes = apple_books_poll_minutes
        self.cloud_only = cloud_only
        self.auto_compile = auto_compile
        self._on_state_change = on_state_change

        self.state = DaemonState.IDLE
        self.stats = DaemonStats()
        self._batch: list[BatchEvent] = []
        self._batch_lock = threading.Lock()
        self._stop_event = threading.Event()
        self._observer: Observer | None = None
        self._last_books_poll: float = 0.0
        self.recent_logs: list[str] = []

    # -- Public control API --

    def start(self) -> None:
        """Start the watcher and main loop in the current thread (blocking)."""
        self._stop_event.clear()
        self._set_state(DaemonState.IDLE)

        handler = _BatchEventHandler(self)
        self._observer = Observer()
        self._observer.schedule(handler, str(self.wfs.raw_dir), recursive=True)
        self._observer.start()

        logger.info("Daemon started — watching %s", self.wfs.raw_dir)
        self._add_log("Daemon started")

        try:
            self._main_loop()
        finally:
            self._observer.stop()
            self._observer.join()
            self._observer = None
            logger.info("Daemon stopped")

    def start_background(self) -> threading.Thread:
        """Start the daemon in a background thread. Returns the thread."""
        thread = threading.Thread(target=self.start, daemon=True, name="compendium-daemon")
        thread.start()
        return thread

    def stop(self) -> None:
        """Signal the daemon to stop."""
        self._stop_event.set()

    def pause(self) -> None:
        """Pause the watcher (files accumulate but nothing processes)."""
        self._set_state(DaemonState.PAUSED)
        self._add_log("Daemon paused")
        logger.info("Daemon paused")

    def resume(self) -> None:
        """Resume from paused state and scan for files missed while paused."""
        self._set_state(DaemonState.IDLE)
        self._add_log("Daemon resumed")
        logger.info("Daemon resumed")
        self._catch_up_scan()

    def _catch_up_scan(self) -> None:
        """Scan raw/ for uncompiled files that arrived while paused."""
        if not self.wfs.raw_dir.exists():
            return
        for child in self.wfs.raw_dir.iterdir():
            if (
                child.is_file()
                and child.suffix.lower() in SUPPORTED_EXTENSIONS
                and not child.name.startswith((".", "~"))
            ):
                self.enqueue(str(child))
        count = len(self._batch)
        if count:
            self._add_log(f"Catch-up scan: {count} file(s) queued")
            logger.info("Catch-up scan queued %d file(s)", count)

    def force_sync(self) -> bool:
        """Force immediate processing of any pending batch + Apple Books poll.

        Returns True if any work was done, False if vault is already up to date.
        """
        self._add_log("Manual sync triggered")
        before_ingested = self.stats.files_ingested
        before_compiled = self.stats.compilations_run
        before_books = self.stats.books_synced

        self._catch_up_scan()
        self._process_batch()
        self._poll_apple_books()

        did_work = (
            self.stats.files_ingested > before_ingested
            or self.stats.compilations_run > before_compiled
            or self.stats.books_synced > before_books
        )
        if not did_work:
            self._add_log("Vault is up to date")
        return did_work

    def enqueue(self, path: str) -> None:
        """Add a file event to the batch queue, resetting the debounce timer."""
        with self._batch_lock:
            self._batch.append(BatchEvent(path=path, timestamp=time.monotonic()))
        logger.debug("Enqueued: %s (%d in batch)", path, len(self._batch))

    # -- Main loop --

    def _main_loop(self) -> None:
        """Tick-based main loop — checks batch timer and Apple Books poll."""
        while not self._stop_event.is_set():
            if self.state != DaemonState.PAUSED:
                self._tick()
            self._stop_event.wait(timeout=1.0)

    def _tick(self) -> None:
        """Single tick: check if batch is ready, check if books poll is due."""
        # Check batch readiness
        with self._batch_lock:
            if self._batch:
                newest = max(e.timestamp for e in self._batch)
                elapsed = time.monotonic() - newest
                if elapsed >= self.debounce_seconds:
                    batch = list(self._batch)
                    self._batch.clear()
                else:
                    batch = []
            else:
                batch = []

        if batch:
            self._process_batch_events(batch)

        # Check Apple Books polling
        now = time.monotonic()
        poll_interval = self.apple_books_poll_minutes * 60
        if poll_interval > 0 and (now - self._last_books_poll) >= poll_interval:
            self._poll_apple_books()
            self._last_books_poll = now

    # -- Batch processing --

    def _process_batch(self) -> None:
        """Drain and process whatever is in the batch queue right now."""
        with self._batch_lock:
            batch = list(self._batch)
            self._batch.clear()
        if batch:
            self._process_batch_events(batch)

    def _process_batch_events(self, batch: list[BatchEvent]) -> None:
        """Ingest a batch of files, then optionally run incremental update."""
        self._set_state(DaemonState.PROCESSING)
        ingested_paths: list[Path] = []

        for event in batch:
            from pathlib import Path

            path = Path(event.path)
            if not path.exists():
                continue
            try:
                result = ingest_file(
                    path,
                    self.wfs.raw_dir,
                    self.wfs.raw_images_dir,
                    self.wfs.raw_originals_dir,
                    "cancel",
                )
                if result.success and result.output_path:
                    ingested_paths.append(result.output_path)
                    self.stats.files_ingested += 1
                    self._add_log(f"Ingested: {path.name}")
                    self.wfs.append_log_entry(
                        f"## [{_now_date()}] ingest | {path.name}\n\n"
                        f"- event: daemon-batch\n- result: {result.message}\n"
                    )
            except Exception as exc:
                self.stats.errors += 1
                self.stats.last_error = str(exc)
                logger.exception("Ingest error for %s", path)
                self._add_log(f"Error ingesting {path.name}: {exc}")

        # Auto-compile if we ingested anything
        if ingested_paths and self.auto_compile:
            self._run_incremental_update()

        self._set_state(DaemonState.IDLE)

    def _run_incremental_update(self) -> None:
        """Run the incremental update pipeline (auto-detect new sources)."""
        import asyncio

        try:
            from compendium.core.config import CompendiumConfig
            from compendium.llm.factory import create_provider
            from compendium.llm.prompts import PromptLoader
            from compendium.pipeline.controller import incremental_update

            config = CompendiumConfig.load(self.wfs.root / "compendium.toml")
            llm = create_provider(config.models.compilation, cloud_only=self.cloud_only)
            prompt_loader = PromptLoader(project_prompts_dir=self.wfs.root / "prompts")

            self._add_log("Compiling wiki...")
            result = asyncio.run(
                incremental_update(self.wfs, config, llm, prompt_loader)
            )
            self.stats.compilations_run += 1
            self.stats.last_compile_at = _now_iso()

            updated = result.get("updated", 0)
            added = result.get("articles_added", 0)
            msg = result.get("message", f"Updated {updated} source(s), added {added} article(s)")
            self._add_log(f"Compiled: {msg}")
            logger.info("Incremental update complete: %s", msg)

        except Exception as exc:
            self.stats.errors += 1
            self.stats.last_error = str(exc)
            self._set_state(DaemonState.ERROR)
            logger.exception("Compilation error")
            self._add_log(f"Compile error: {exc}")

    # -- Apple Books polling --

    def _poll_apple_books(self) -> None:
        """Check for new Apple Books highlights and export them."""
        try:
            from compendium.ingest.apple_books import (
                export_to_markdown,
                extract_highlights,
                get_enabled_asset_ids,
                load_sync_cache,
                save_sync_cache,
            )

            since = load_sync_cache(self.wfs.root)
            exports = extract_highlights(since_cocoa_timestamp=since)
            if not exports:
                return

            # Filter by user's book selection (None = all enabled)
            enabled = get_enabled_asset_ids(self.wfs.root)
            if enabled is not None:
                exports = [b for b in exports if b.asset_id in enabled]
            if not exports:
                return

            exported = 0
            for book in exports:
                output, msg = export_to_markdown(
                    book, self.wfs.raw_dir, duplicate_mode="overwrite"
                )
                if output:
                    exported += 1
                    self.stats.books_synced += 1
                    self._add_log(f"Books: {msg}")
                    logger.info("Apple Books: %s", msg)

            if exported:
                save_sync_cache(self.wfs.root)
                self.wfs.append_log_entry(
                    f"## [{_now_date()}] ingest | Apple Books\n\n"
                    f"- event: daemon-poll\n- books exported: {exported}\n"
                )

        except Exception as exc:
            logger.debug("Apple Books poll failed: %s", exc)

    # -- State and logging helpers --

    def _set_state(self, new_state: DaemonState) -> None:
        old = self.state
        self.state = new_state
        if self._on_state_change and old != new_state:
            with contextlib.suppress(Exception):
                self._on_state_change(new_state)

    def _add_log(self, message: str) -> None:
        entry = f"[{_now_time()}] {message}"
        self.recent_logs.append(entry)
        # Keep last 50 entries
        if len(self.recent_logs) > 50:
            self.recent_logs = self.recent_logs[-50:]


def _now_date() -> str:
    from datetime import UTC, datetime

    return datetime.now(UTC).strftime("%Y-%m-%d")


def _now_iso() -> str:
    from datetime import UTC, datetime

    return datetime.now(UTC).isoformat()


def _now_time() -> str:
    from datetime import UTC, datetime

    return datetime.now(UTC).strftime("%H:%M:%S")
