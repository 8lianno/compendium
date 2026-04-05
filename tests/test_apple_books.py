"""Tests for Apple Books highlight extraction."""

from __future__ import annotations

import sqlite3
from typing import TYPE_CHECKING

from compendium.ingest.apple_books import (
    BookExport,
    Highlight,
    _apple_cocoa_to_datetime,
    _clean_chapter,
    discover_books,
    export_to_markdown,
    extract_highlights,
)

if TYPE_CHECKING:
    from pathlib import Path


def _create_test_databases(container: Path) -> None:
    """Create minimal Apple Books SQLite databases for testing."""
    # BKLibrary database
    bk_dir = container / "BKLibrary"
    bk_dir.mkdir(parents=True)
    bk_db = bk_dir / "BKLibrary-1-test.sqlite"
    conn = sqlite3.connect(str(bk_db))
    conn.execute(
        "CREATE TABLE ZBKLIBRARYASSET ("
        "ZASSETID TEXT, ZTITLE TEXT, ZAUTHOR TEXT, ZGENRE TEXT)"
    )
    conn.execute(
        "INSERT INTO ZBKLIBRARYASSET VALUES (?, ?, ?, ?)",
        ("BOOK001", "Deep Work", "Cal Newport", "Self-Help"),
    )
    conn.execute(
        "INSERT INTO ZBKLIBRARYASSET VALUES (?, ?, ?, ?)",
        ("BOOK002", "Thinking Fast and Slow", "Daniel Kahneman", "Psychology"),
    )
    conn.commit()
    conn.close()

    # AEAnnotation database
    ae_dir = container / "AEAnnotation"
    ae_dir.mkdir(parents=True)
    ae_db = ae_dir / "AEAnnotation_v10.sqlite"
    conn = sqlite3.connect(str(ae_db))
    conn.execute(
        "CREATE TABLE ZAEANNOTATION ("
        "ZANNOTATIONASSETID TEXT, ZANNOTATIONSELECTEDTEXT TEXT, "
        "ZANNOTATIONNOTE TEXT, ZFUTUREPROOFING5 TEXT, "
        "ZANNOTATIONSTYLE INTEGER, ZANNOTATIONCREATIONDATE REAL, "
        "ZANNOTATIONLOCATION TEXT, ZANNOTATIONDELETED INTEGER, "
        "ZPLLOCATIONRANGESTART INTEGER)"
    )
    # Deep Work highlights
    conn.execute(
        "INSERT INTO ZAEANNOTATION VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            "BOOK001",
            "The ability to perform deep work is becoming rare.",
            "Key thesis",
            "Chapter 1: Deep Work Is Valuable",
            0,
            700000000.0,  # ~2023
            "loc1",
            0,
            100,
        ),
    )
    conn.execute(
        "INSERT INTO ZAEANNOTATION VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            "BOOK001",
            "Focus requires eliminating distractions.",
            None,
            "Chapter 2: Deep Work Is Rare",
            0,
            700000100.0,
            "loc2",
            0,
            200,
        ),
    )
    # Deleted annotation (should be filtered out)
    conn.execute(
        "INSERT INTO ZAEANNOTATION VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        ("BOOK001", "This was deleted", None, None, 0, 700000200.0, "loc3", 1, 300),
    )
    # Thinking Fast and Slow highlight
    conn.execute(
        "INSERT INTO ZAEANNOTATION VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            "BOOK002",
            "System 1 operates automatically and quickly.",
            None,
            "Part I",
            0,
            700000300.0,
            "loc1",
            0,
            100,
        ),
    )
    conn.commit()
    conn.close()


class TestAppleCocoaTimestamp:
    def test_converts_valid_timestamp(self) -> None:
        dt = _apple_cocoa_to_datetime(700000000.0)
        assert dt is not None
        assert dt.year == 2023

    def test_returns_none_for_zero(self) -> None:
        assert _apple_cocoa_to_datetime(0) is None

    def test_returns_none_for_none(self) -> None:
        assert _apple_cocoa_to_datetime(None) is None


class TestCleanChapter:
    def test_removes_numbering(self) -> None:
        assert _clean_chapter("1. Introduction") == "Introduction"

    def test_preserves_clean_chapter(self) -> None:
        assert _clean_chapter("Chapter One") == "Chapter One"

    def test_returns_none_for_empty(self) -> None:
        assert _clean_chapter("") is None
        assert _clean_chapter(None) is None


class TestDiscoverBooks:
    def test_discovers_books(self, tmp_path: Path) -> None:
        _create_test_databases(tmp_path)
        books = discover_books(container_path=tmp_path)
        assert len(books) == 2
        assert books[0]["title"] == "Deep Work"
        assert books[0]["author"] == "Cal Newport"

    def test_returns_empty_when_no_db(self, tmp_path: Path) -> None:
        books = discover_books(container_path=tmp_path)
        assert books == []


class TestExtractHighlights:
    def test_extracts_all_highlights(self, tmp_path: Path) -> None:
        _create_test_databases(tmp_path)
        exports = extract_highlights(container_path=tmp_path)
        assert len(exports) == 2

        deep_work = next(e for e in exports if "Deep Work" in e.title)
        assert len(deep_work.highlights) == 2  # Deleted one excluded
        assert deep_work.author == "Cal Newport"
        assert deep_work.highlights[0].note == "Key thesis"

    def test_extracts_single_book(self, tmp_path: Path) -> None:
        _create_test_databases(tmp_path)
        exports = extract_highlights(asset_id="BOOK001", container_path=tmp_path)
        assert len(exports) == 1
        assert exports[0].title == "Deep Work"

    def test_returns_empty_when_no_db(self, tmp_path: Path) -> None:
        exports = extract_highlights(container_path=tmp_path)
        assert exports == []


class TestExportToMarkdown:
    def test_exports_book(self, tmp_path: Path) -> None:
        raw_dir = tmp_path / "raw"
        raw_dir.mkdir()

        book = BookExport(
            title="Deep Work",
            author="Cal Newport",
            asset_id="BOOK001",
            genre="Self-Help",
            highlights=[
                Highlight(text="Focus is rare.", chapter="Chapter 1", note="Important"),
                Highlight(text="Eliminate distractions.", chapter="Chapter 2"),
            ],
        )

        output, msg = export_to_markdown(book, raw_dir)
        assert output is not None
        assert output.exists()
        assert "2 highlights" in msg

        import frontmatter

        post = frontmatter.load(str(output))
        assert post["title"] == "Deep Work — Highlights"
        assert post["author"] == "Cal Newport"
        assert post["format"] == "book-highlights"
        assert post["book_title"] == "Deep Work"
        assert post["book_author"] == "Cal Newport"
        assert post["genre"] == "Self-Help"
        assert post["status"] == "raw"
        assert "Focus is rare" in post.content
        assert "**Note:** Important" in post.content
        assert "## Chapter 1" in post.content

    def test_skips_duplicate(self, tmp_path: Path) -> None:
        raw_dir = tmp_path / "raw"
        raw_dir.mkdir()

        book = BookExport(
            title="Test Book",
            author="Author",
            asset_id="X",
            highlights=[Highlight(text="Hello")],
        )

        # First export
        export_to_markdown(book, raw_dir)
        # Second export should skip
        output, msg = export_to_markdown(book, raw_dir, duplicate_mode="cancel")
        assert output is None
        assert "Already exported" in msg

    def test_no_highlights(self, tmp_path: Path) -> None:
        raw_dir = tmp_path / "raw"
        raw_dir.mkdir()

        book = BookExport(title="Empty", author="X", asset_id="X", highlights=[])
        output, msg = export_to_markdown(book, raw_dir)
        assert output is None
        assert "No highlights" in msg


class TestIntegrationRoundtrip:
    def test_extract_and_export(self, tmp_path: Path) -> None:
        """Full roundtrip: create test DBs, extract, export to markdown."""
        _create_test_databases(tmp_path)
        raw_dir = tmp_path / "raw"
        raw_dir.mkdir()

        exports = extract_highlights(container_path=tmp_path)
        assert len(exports) >= 1

        for book in exports:
            output, msg = export_to_markdown(book, raw_dir)
            assert output is not None
            assert output.exists()

        # Verify all files exist
        md_files = list(raw_dir.glob("*.md"))
        assert len(md_files) == 2
