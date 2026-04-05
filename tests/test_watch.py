"""Tests for the raw/ file watcher."""

from __future__ import annotations

from typing import TYPE_CHECKING

from compendium.core.wiki_fs import WikiFileSystem

if TYPE_CHECKING:
    from pathlib import Path
from compendium.ingest.watcher import IngestEventHandler


def _make_wfs(tmp_path: Path) -> WikiFileSystem:
    wfs = WikiFileSystem(tmp_path)
    wfs.init_project(name="Watch Test")
    return wfs


class TestIngestEventHandler:
    def test_ignores_dotfiles(self, tmp_path: Path) -> None:
        wfs = _make_wfs(tmp_path)
        handler = IngestEventHandler(wfs, debounce_seconds=0)
        assert handler._should_ignore(str(tmp_path / ".hidden.md"))

    def test_ignores_temp_files(self, tmp_path: Path) -> None:
        wfs = _make_wfs(tmp_path)
        handler = IngestEventHandler(wfs, debounce_seconds=0)
        assert handler._should_ignore(str(tmp_path / "~tempfile.md"))

    def test_ignores_unsupported_extensions(self, tmp_path: Path) -> None:
        wfs = _make_wfs(tmp_path)
        handler = IngestEventHandler(wfs, debounce_seconds=0)
        assert handler._should_ignore(str(tmp_path / "file.exe"))

    def test_accepts_markdown(self, tmp_path: Path) -> None:
        wfs = _make_wfs(tmp_path)
        handler = IngestEventHandler(wfs, debounce_seconds=0)
        assert not handler._should_ignore(str(tmp_path / "note.md"))

    def test_accepts_pdf(self, tmp_path: Path) -> None:
        wfs = _make_wfs(tmp_path)
        handler = IngestEventHandler(wfs, debounce_seconds=0)
        assert not handler._should_ignore(str(tmp_path / "doc.pdf"))

    def test_process_pending_ingests_file(self, tmp_path: Path) -> None:
        wfs = _make_wfs(tmp_path)
        handler = IngestEventHandler(wfs, debounce_seconds=0)

        # Create a markdown file in a temp location (not raw/)
        source = tmp_path / "incoming" / "test-note.md"
        source.parent.mkdir()
        source.write_text("# Test Note\n\nSome content here.")

        # Simulate file creation event
        handler._pending[str(source)] = 0  # already past debounce
        count = handler.process_pending()

        assert count == 1
        assert len(handler.processed) == 1
        assert len(handler.errors) == 0

    def test_debounce_prevents_early_processing(self, tmp_path: Path) -> None:
        import time

        wfs = _make_wfs(tmp_path)
        handler = IngestEventHandler(wfs, debounce_seconds=999)

        source = tmp_path / "incoming" / "note.md"
        source.parent.mkdir()
        source.write_text("# Note")

        handler._pending[str(source)] = time.monotonic()
        count = handler.process_pending()

        assert count == 0  # Not yet ready
        assert len(handler.processed) == 0

    def test_duplicate_cancel_mode(self, tmp_path: Path) -> None:
        wfs = _make_wfs(tmp_path)
        handler = IngestEventHandler(wfs, debounce_seconds=0, duplicate_mode="cancel")

        # First ingest
        source = tmp_path / "incoming" / "note.md"
        source.parent.mkdir()
        source.write_text("# Duplicate Test\n\nContent.")

        handler._pending[str(source)] = 0
        handler.process_pending()

        # Second ingest of same content to a different path
        source2 = tmp_path / "incoming" / "note-copy.md"
        source2.write_text("# Duplicate Test\n\nContent.")

        handler._pending[str(source2)] = 0
        handler.process_pending()

        # First succeeds, second is a duplicate (not counted as error, just skipped)
        assert len(handler.processed) == 1

    def test_missing_file_handled_gracefully(self, tmp_path: Path) -> None:
        wfs = _make_wfs(tmp_path)
        handler = IngestEventHandler(wfs, debounce_seconds=0)

        handler._pending[str(tmp_path / "nonexistent.md")] = 0
        count = handler.process_pending()

        assert count == 1  # Removed from pending
        assert len(handler.processed) == 0
        assert len(handler.errors) == 0
