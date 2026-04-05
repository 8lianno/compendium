"""Extract highlights and annotations from Apple Books on macOS."""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import frontmatter

from compendium.ingest.dedup import text_hash
from compendium.ingest.file_drop import slugify

if TYPE_CHECKING:
    from pathlib import Path

# Apple Books database paths (macOS)
_CONTAINER = "~/Library/Containers/com.apple.iBooksX/Data/Documents"
_BKLIBRARY_GLOB = "BKLibrary/BKLibrary*.sqlite"
_ANNOTATIONS_GLOB = "AEAnnotation/AEAnnotation*.sqlite"


@dataclass
class Highlight:
    """A single highlight or annotation from Apple Books."""

    text: str
    note: str | None = None
    chapter: str | None = None
    style: int = 0  # 0=highlight, 1=underline, 2=note
    created_at: datetime | None = None
    location: str | None = None


@dataclass
class BookExport:
    """All highlights from a single book."""

    title: str
    author: str
    asset_id: str
    highlights: list[Highlight] = field(default_factory=list)
    genre: str | None = None


def _find_db(container: Path, glob_pattern: str) -> Path | None:
    """Find the Apple Books SQLite database file."""
    matches = sorted(container.glob(glob_pattern))
    return matches[0] if matches else None


def _apple_cocoa_to_datetime(cocoa_ts: float | None) -> datetime | None:
    """Convert Apple's Core Data timestamp (seconds since 2001-01-01) to datetime."""
    if cocoa_ts is None or cocoa_ts == 0:
        return None
    # Core Data epoch is 2001-01-01 00:00:00 UTC
    # Unix epoch offset: 978307200 seconds
    try:
        return datetime.fromtimestamp(cocoa_ts + 978307200, tz=UTC)
    except (OSError, OverflowError, ValueError):
        return None


def discover_books(container_path: Path | None = None) -> list[dict[str, str]]:
    """List all books in the Apple Books library.

    Returns list of dicts with 'title', 'author', 'asset_id'.
    """
    from pathlib import Path

    container = container_path or Path(_CONTAINER).expanduser()
    lib_db = _find_db(container, _BKLIBRARY_GLOB)
    if lib_db is None:
        return []

    conn = sqlite3.connect(f"file:{lib_db}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            "SELECT ZASSETID, ZTITLE, ZAUTHOR, ZGENRE "
            "FROM ZBKLIBRARYASSET "
            "WHERE ZTITLE IS NOT NULL "
            "ORDER BY ZTITLE"
        ).fetchall()
        return [
            {
                "title": row["ZTITLE"] or "Untitled",
                "author": row["ZAUTHOR"] or "Unknown",
                "asset_id": row["ZASSETID"] or "",
                "genre": row["ZGENRE"] or "",
            }
            for row in rows
        ]
    except sqlite3.OperationalError:
        return []
    finally:
        conn.close()


def extract_highlights(
    asset_id: str | None = None,
    container_path: Path | None = None,
) -> list[BookExport]:
    """Extract highlights and annotations from Apple Books.

    Args:
        asset_id: If given, only extract for this book. Otherwise extract all.
        container_path: Override the Apple Books container path (for testing).

    Returns:
        List of BookExport objects, one per book with highlights.
    """
    from pathlib import Path

    container = container_path or Path(_CONTAINER).expanduser()
    lib_db = _find_db(container, _BKLIBRARY_GLOB)
    ann_db = _find_db(container, _ANNOTATIONS_GLOB)
    if lib_db is None or ann_db is None:
        return []

    # Load book metadata
    lib_conn = sqlite3.connect(f"file:{lib_db}?mode=ro", uri=True)
    lib_conn.row_factory = sqlite3.Row
    try:
        if asset_id:
            books = lib_conn.execute(
                "SELECT ZASSETID, ZTITLE, ZAUTHOR, ZGENRE "
                "FROM ZBKLIBRARYASSET WHERE ZASSETID = ?",
                (asset_id,),
            ).fetchall()
        else:
            books = lib_conn.execute(
                "SELECT ZASSETID, ZTITLE, ZAUTHOR, ZGENRE "
                "FROM ZBKLIBRARYASSET WHERE ZTITLE IS NOT NULL "
                "ORDER BY ZTITLE"
            ).fetchall()
    except sqlite3.OperationalError:
        lib_conn.close()
        return []

    book_map = {
        row["ZASSETID"]: {
            "title": row["ZTITLE"] or "Untitled",
            "author": row["ZAUTHOR"] or "Unknown",
            "genre": row["ZGENRE"] or "",
        }
        for row in books
    }
    lib_conn.close()

    if not book_map:
        return []

    # Load annotations
    ann_conn = sqlite3.connect(f"file:{ann_db}?mode=ro", uri=True)
    ann_conn.row_factory = sqlite3.Row
    try:
        placeholders = ",".join("?" for _ in book_map)
        rows = ann_conn.execute(
            "SELECT ZANNOTATIONASSETID, ZANNOTATIONSELECTEDTEXT, "
            "ZANNOTATIONNOTE, ZFUTUREPROOFING5 AS CHAPTER, "
            "ZANNOTATIONSTYLE, ZANNOTATIONCREATIONDATE, "
            "ZANNOTATIONLOCATION "
            "FROM ZAEANNOTATION "
            f"WHERE ZANNOTATIONASSETID IN ({placeholders}) "
            "AND ZANNOTATIONDELETED = 0 "
            "ORDER BY ZANNOTATIONASSETID, ZPLLOCATIONRANGESTART",
            list(book_map.keys()),
        ).fetchall()
    except sqlite3.OperationalError:
        ann_conn.close()
        return []
    ann_conn.close()

    # Group by book
    exports: dict[str, BookExport] = {}
    for row in rows:
        aid = row["ZANNOTATIONASSETID"]
        if aid not in book_map:
            continue
        text = (row["ZANNOTATIONSELECTEDTEXT"] or "").strip()
        if not text:
            continue

        if aid not in exports:
            meta = book_map[aid]
            exports[aid] = BookExport(
                title=meta["title"],
                author=meta["author"],
                asset_id=aid,
                genre=meta["genre"] or None,
            )

        exports[aid].highlights.append(
            Highlight(
                text=text,
                note=(row["ZANNOTATIONNOTE"] or "").strip() or None,
                chapter=(row["CHAPTER"] or "").strip() or None,
                style=row["ZANNOTATIONSTYLE"] or 0,
                created_at=_apple_cocoa_to_datetime(row["ZANNOTATIONCREATIONDATE"]),
                location=(row["ZANNOTATIONLOCATION"] or "").strip() or None,
            )
        )

    return list(exports.values())


def _clean_chapter(chapter: str | None) -> str | None:
    """Clean chapter text from Apple Books location data."""
    if not chapter:
        return None
    # Remove numbering artifacts
    chapter = re.sub(r"^\d+\.\s*", "", chapter).strip()
    return chapter if chapter else None


def export_to_markdown(
    book: BookExport,
    raw_dir: Path,
    duplicate_mode: str = "cancel",
) -> tuple[Path | None, str]:
    """Export a book's highlights to a markdown file in raw/.

    Returns (output_path, status_message).
    """
    if not book.highlights:
        return None, f"No highlights for: {book.title}"

    slug = slugify(f"{book.title}-highlights")
    output_path = raw_dir / f"{slug}.md"

    # Dedup check
    if output_path.exists() and duplicate_mode == "cancel":
        return None, f"Already exported: {book.title}"
    if not output_path.exists():
        counter = 2
        base = slug
        while output_path.exists():
            output_path = raw_dir / f"{base}-{counter}.md"
            counter += 1

    # Group highlights by chapter
    chapters: dict[str, list[Highlight]] = {}
    no_chapter: list[Highlight] = []
    for h in book.highlights:
        ch = _clean_chapter(h.chapter)
        if ch:
            chapters.setdefault(ch, []).append(h)
        else:
            no_chapter.append(h)

    # Build markdown body
    lines: list[str] = [f"# {book.title} — Highlights\n"]

    if book.author and book.author != "Unknown":
        lines.append(f"**Author:** {book.author}\n")

    lines.append(f"**Total highlights:** {len(book.highlights)}\n")
    lines.append("---\n")

    if chapters:
        for chapter_name, highlights in chapters.items():
            lines.append(f"## {chapter_name}\n")
            for h in highlights:
                lines.append(f"> {h.text}\n")
                if h.note:
                    lines.append(f"**Note:** {h.note}\n")
                lines.append("")
    if no_chapter:
        if chapters:
            lines.append("## Other Highlights\n")
        for h in no_chapter:
            lines.append(f"> {h.text}\n")
            if h.note:
                lines.append(f"**Note:** {h.note}\n")
            lines.append("")

    body = "\n".join(lines)

    # Build frontmatter
    fm_data = {
        "title": f"{book.title} — Highlights",
        "id": slug,
        "author": book.author,
        "source": "local",
        "format": "book-highlights",
        "clipped_at": datetime.now(UTC).isoformat(),
        "word_count": len(body.split()),
        "content_hash": text_hash(body),
        "status": "raw",
        "book_title": book.title,
        "book_author": book.author,
    }
    if book.genre:
        fm_data["genre"] = book.genre

    post = frontmatter.Post(body, **fm_data)
    output_path.write_text(frontmatter.dumps(post))

    return output_path, f"Exported: {book.title} ({len(book.highlights)} highlights)"
