"""Tests for the daemon engine, service plist generation, and Apple Books sync cache."""

from __future__ import annotations

import json
import time
from typing import TYPE_CHECKING
from unittest.mock import patch

from compendium.core.wiki_fs import WikiFileSystem
from compendium.daemon.engine import (
    BatchEvent,
    DaemonEngine,
    DaemonState,
    _BatchEventHandler,
)

if TYPE_CHECKING:
    from pathlib import Path


def _make_wfs(tmp_path: Path) -> WikiFileSystem:
    wfs = WikiFileSystem(tmp_path)
    wfs.init_project(name="Daemon Test")
    return wfs


# -- DaemonEngine state management --


class TestDaemonState:
    def test_initial_state_is_idle(self, tmp_path: Path) -> None:
        wfs = _make_wfs(tmp_path)
        engine = DaemonEngine(wfs, debounce_seconds=1)
        assert engine.state == DaemonState.IDLE

    def test_pause_and_resume(self, tmp_path: Path) -> None:
        wfs = _make_wfs(tmp_path)
        engine = DaemonEngine(wfs, debounce_seconds=1)
        engine.pause()
        assert engine.state == DaemonState.PAUSED
        engine.resume()
        assert engine.state == DaemonState.IDLE

    def test_state_change_callback(self, tmp_path: Path) -> None:
        wfs = _make_wfs(tmp_path)
        states: list[DaemonState] = []
        engine = DaemonEngine(wfs, debounce_seconds=1, on_state_change=states.append)
        engine.pause()
        engine.resume()
        assert states == [DaemonState.PAUSED, DaemonState.IDLE]


# -- Batch event handler --


class TestBatchEventHandler:
    def test_ignores_dotfiles(self, tmp_path: Path) -> None:
        wfs = _make_wfs(tmp_path)
        engine = DaemonEngine(wfs, debounce_seconds=1)
        handler = _BatchEventHandler(engine)
        assert handler._should_ignore(str(tmp_path / ".hidden.md"))

    def test_ignores_unsupported(self, tmp_path: Path) -> None:
        wfs = _make_wfs(tmp_path)
        engine = DaemonEngine(wfs, debounce_seconds=1)
        handler = _BatchEventHandler(engine)
        assert handler._should_ignore(str(tmp_path / "file.exe"))

    def test_accepts_markdown(self, tmp_path: Path) -> None:
        wfs = _make_wfs(tmp_path)
        engine = DaemonEngine(wfs, debounce_seconds=1)
        handler = _BatchEventHandler(engine)
        assert not handler._should_ignore(str(tmp_path / "note.md"))


# -- Enqueue and debounce --


class TestBatching:
    def test_enqueue_adds_to_batch(self, tmp_path: Path) -> None:
        wfs = _make_wfs(tmp_path)
        engine = DaemonEngine(wfs, debounce_seconds=60)
        engine.enqueue("/fake/file.md")
        assert len(engine._batch) == 1

    def test_batch_not_ready_before_debounce(self, tmp_path: Path) -> None:
        wfs = _make_wfs(tmp_path)
        engine = DaemonEngine(wfs, debounce_seconds=999)
        engine.enqueue("/fake/file.md")
        # Tick should not drain the batch
        engine._tick()
        assert len(engine._batch) == 1

    def test_batch_ready_after_debounce(self, tmp_path: Path) -> None:
        wfs = _make_wfs(tmp_path)
        engine = DaemonEngine(wfs, debounce_seconds=0, auto_compile=False)

        # Create a real file to ingest
        source = tmp_path / "incoming" / "test.md"
        source.parent.mkdir()
        source.write_text("# Test\n\nContent.")

        # Manually add to batch with timestamp in the past
        engine._batch.append(BatchEvent(path=str(source), timestamp=0))
        engine._tick()

        # Batch should be drained
        assert len(engine._batch) == 0
        assert engine.stats.files_ingested == 1

    def test_debounce_resets_on_new_file(self, tmp_path: Path) -> None:
        wfs = _make_wfs(tmp_path)
        engine = DaemonEngine(wfs, debounce_seconds=5)

        # First file with old timestamp
        engine._batch.append(BatchEvent(path="/fake/a.md", timestamp=time.monotonic() - 10))
        # Second file arrives now — resets timer
        engine._batch.append(BatchEvent(path="/fake/b.md", timestamp=time.monotonic()))

        # The newest file is not past debounce yet, so batch should NOT drain
        engine._tick()
        assert len(engine._batch) == 2  # Still waiting

    def test_multiple_files_processed_as_batch(self, tmp_path: Path) -> None:
        wfs = _make_wfs(tmp_path)
        engine = DaemonEngine(wfs, debounce_seconds=0, auto_compile=False)

        for i in range(3):
            source = tmp_path / "incoming" / f"note-{i}.md"
            source.parent.mkdir(exist_ok=True)
            source.write_text(f"# Note {i}\n\nContent for note {i}.")
            engine._batch.append(BatchEvent(path=str(source), timestamp=0))

        engine._tick()

        assert len(engine._batch) == 0
        assert engine.stats.files_ingested == 3


# -- Cloud-only provider restriction --


class TestCloudOnly:
    def test_cloud_only_rejects_ollama(self) -> None:
        from compendium.core.config import ModelConfig
        from compendium.llm.factory import create_provider

        mc = ModelConfig(provider="ollama", model="llama3")
        try:
            create_provider(mc, cloud_only=True)
            assert False, "Should have raised"  # noqa: B011
        except ValueError as e:
            assert "cloud" in str(e).lower()

    def test_cloud_only_accepts_anthropic(self) -> None:
        from compendium.llm.factory import CLOUD_PROVIDERS

        assert "anthropic" in CLOUD_PROVIDERS
        assert "openai" in CLOUD_PROVIDERS
        assert "gemini" in CLOUD_PROVIDERS
        assert "ollama" not in CLOUD_PROVIDERS


# -- Service plist generation --


class TestServicePlist:
    def test_generate_plist(self, tmp_path: Path) -> None:
        from compendium.daemon.service import generate_plist

        plist = generate_plist(tmp_path)
        assert plist["Label"] == "com.compendium.daemon"
        assert plist["RunAtLoad"] is True
        assert plist["KeepAlive"] is True
        assert str(tmp_path) in plist["ProgramArguments"][-1]
        assert plist["WorkingDirectory"] == str(tmp_path)


# -- Apple Books sync cache --


class TestAppleBooksSyncCache:
    def test_load_returns_none_when_no_cache(self, tmp_path: Path) -> None:
        from compendium.ingest.apple_books import load_sync_cache

        assert load_sync_cache(tmp_path) is None

    def test_save_and_load_roundtrip(self, tmp_path: Path) -> None:
        from compendium.ingest.apple_books import load_sync_cache, save_sync_cache

        save_sync_cache(tmp_path)
        ts = load_sync_cache(tmp_path)
        assert ts is not None
        assert isinstance(ts, float)

    def test_cache_file_is_json(self, tmp_path: Path) -> None:
        from compendium.ingest.apple_books import save_sync_cache

        save_sync_cache(tmp_path)
        cache_path = tmp_path / ".apple-books-sync.json"
        assert cache_path.exists()
        data = json.loads(cache_path.read_text())
        assert "last_cocoa_timestamp" in data


# -- Logging --


class TestDaemonLogging:
    def test_add_log_keeps_recent(self, tmp_path: Path) -> None:
        wfs = _make_wfs(tmp_path)
        engine = DaemonEngine(wfs, debounce_seconds=1)
        for i in range(60):
            engine._add_log(f"Log entry {i}")
        # Should keep at most 50
        assert len(engine.recent_logs) == 50
        assert "Log entry 59" in engine.recent_logs[-1]

    def test_stats_track_errors(self, tmp_path: Path) -> None:
        wfs = _make_wfs(tmp_path)
        engine = DaemonEngine(wfs, debounce_seconds=0, auto_compile=False)

        # Enqueue a nonexistent file
        engine._batch.append(BatchEvent(path=str(tmp_path / "gone.md"), timestamp=0))
        engine._tick()

        # File didn't exist, so no ingest and no error (gracefully skipped)
        assert engine.stats.files_ingested == 0


# -- Resume catch-up scan --


class TestResumeCatchUp:
    def test_resume_queues_existing_files(self, tmp_path: Path) -> None:
        wfs = _make_wfs(tmp_path)
        engine = DaemonEngine(wfs, debounce_seconds=0, auto_compile=False)

        # Drop a file into raw/ while "paused"
        (wfs.raw_dir / "missed-note.md").write_text("# Missed\nContent.")

        engine.pause()
        engine.resume()

        # The catch-up scan should have queued the file
        assert len(engine._batch) >= 1

    def test_resume_ignores_dotfiles(self, tmp_path: Path) -> None:
        wfs = _make_wfs(tmp_path)
        engine = DaemonEngine(wfs, debounce_seconds=0, auto_compile=False)

        (wfs.raw_dir / ".hidden.md").write_text("hidden")

        engine.pause()
        engine.resume()

        # Dotfiles should not be queued
        paths = [e.path for e in engine._batch]
        assert not any(".hidden" in p for p in paths)


# -- Force sync feedback --


class TestForceSync:
    def test_force_sync_returns_false_when_empty(self, tmp_path: Path) -> None:
        wfs = _make_wfs(tmp_path)
        engine = DaemonEngine(wfs, debounce_seconds=0, auto_compile=False)
        # Patch Apple Books to return nothing (avoids real DB on dev machines)
        with patch("compendium.daemon.engine.DaemonEngine._poll_apple_books"):
            did_work = engine.force_sync()
        assert did_work is False

    def test_force_sync_returns_true_when_files_ingested(self, tmp_path: Path) -> None:
        wfs = _make_wfs(tmp_path)
        engine = DaemonEngine(wfs, debounce_seconds=0, auto_compile=False)

        # Drop a file into raw/
        (wfs.raw_dir / "new-note.md").write_text("# New\nContent.")

        did_work = engine.force_sync()
        assert did_work is True
        assert engine.stats.files_ingested >= 1


# -- Log.md parsing --


class TestLogParsing:
    def test_parse_recent_entries(self, tmp_path: Path) -> None:
        from compendium.daemon.menubar import _parse_recent_log_entries

        wfs = _make_wfs(tmp_path)
        wfs.wiki_dir.mkdir(exist_ok=True)
        log_path = wfs.wiki_dir / "log.md"
        log_path.write_text(
            "---\ntitle: Wiki Log\n---\n\n# Wiki Log\n\n"
            "## [2026-04-05] ingest | paper.pdf\n\n"
            "- event: daemon-batch\n- result: Ingested PDF\n\n"
            "## [2026-04-05] compile | incremental\n\n"
            "- articles_added: 3\n- concepts_new: 2\n\n"
            "## [2026-04-05] ingest | notes.md\n\n"
            "- event: watch\n- result: Ingested notes.md\n"
        )

        entries = _parse_recent_log_entries(wfs, limit=2)
        assert len(entries) == 2
        # Should have the last 2 entries
        assert "compile" in entries[0]
        assert "notes.md" in entries[1]

    def test_parse_empty_log(self, tmp_path: Path) -> None:
        from compendium.daemon.menubar import _parse_recent_log_entries

        wfs = _make_wfs(tmp_path)
        entries = _parse_recent_log_entries(wfs, limit=5)
        assert entries == []

    def test_parse_no_entries(self, tmp_path: Path) -> None:
        from compendium.daemon.menubar import _parse_recent_log_entries

        wfs = _make_wfs(tmp_path)
        wfs.wiki_dir.mkdir(exist_ok=True)
        (wfs.wiki_dir / "log.md").write_text("# Wiki Log\n\nNo entries yet.\n")

        entries = _parse_recent_log_entries(wfs, limit=5)
        assert entries == []


# -- DaemonConfig --


class TestDaemonConfig:
    def test_default_config(self) -> None:
        from compendium.core.config import CompendiumConfig

        config = CompendiumConfig()
        assert config.daemon.debounce_seconds == 60
        assert config.daemon.apple_books_poll_minutes == 5
        assert config.daemon.cloud_only is True
        assert config.daemon.auto_compile is True

    def test_load_with_daemon_section(self, tmp_path: Path) -> None:
        from compendium.core.config import CompendiumConfig

        config_file = tmp_path / "compendium.toml"
        config_file.write_text(
            '[daemon]\ndebounce_seconds = 30\napple_books_poll_minutes = 10\n'
            'cloud_only = false\n'
        )
        config = CompendiumConfig.load(config_file)
        assert config.daemon.debounce_seconds == 30
        assert config.daemon.apple_books_poll_minutes == 10
        assert config.daemon.cloud_only is False


# -- Engine choice onboarding --


class TestApplyEngineChoice:
    def test_cloud_provider_updates_config(self, tmp_path: Path) -> None:
        from compendium.core.config import CompendiumConfig
        from compendium.daemon.menubar_entry import apply_engine_choice

        # Create a default config
        config = CompendiumConfig()
        config_path = tmp_path / "compendium.toml"
        config.save(config_path)

        apply_engine_choice(config_path, "openai", model="gpt-4o")

        loaded = CompendiumConfig.load(config_path)
        assert loaded.models.default_provider == "openai"
        assert loaded.models.compilation.provider == "openai"
        assert loaded.models.compilation.model == "gpt-4o"
        assert loaded.models.qa.provider == "openai"
        assert loaded.models.lint.provider == "openai"
        assert loaded.daemon.cloud_only is True  # unchanged for cloud

    def test_ollama_sets_cloud_only_false(self, tmp_path: Path) -> None:
        from compendium.core.config import CompendiumConfig
        from compendium.daemon.menubar_entry import apply_engine_choice

        config = CompendiumConfig()
        config_path = tmp_path / "compendium.toml"
        config.save(config_path)

        apply_engine_choice(
            config_path, "ollama", model="llama3", endpoint="http://localhost:11434"
        )

        loaded = CompendiumConfig.load(config_path)
        assert loaded.models.default_provider == "ollama"
        assert loaded.models.compilation.provider == "ollama"
        assert loaded.models.compilation.endpoint == "http://localhost:11434"
        assert loaded.daemon.cloud_only is False

    def test_default_model_used_when_none(self, tmp_path: Path) -> None:
        from compendium.core.config import CompendiumConfig
        from compendium.daemon.menubar_entry import apply_engine_choice

        config = CompendiumConfig()
        config_path = tmp_path / "compendium.toml"
        config.save(config_path)

        apply_engine_choice(config_path, "anthropic")

        loaded = CompendiumConfig.load(config_path)
        assert loaded.models.compilation.model == "claude-sonnet-4-20250514"
