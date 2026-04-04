"""Batch file ingestion — PDF, markdown, text, CSV, images."""

from __future__ import annotations

import re
import shutil
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import frontmatter

from compendium.ingest.dedup import content_hash, find_duplicate_by_hash
from compendium.ingest.pdf import extract_pdf

if TYPE_CHECKING:
    from pathlib import Path

SUPPORTED_EXTENSIONS = {
    ".md",
    ".markdown",
    ".txt",
    ".csv",
    ".tsv",
    ".pdf",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".webp",
    ".svg",
}

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"}


def slugify(text: str, max_len: int = 80) -> str:
    """Convert text to a URL-friendly slug."""
    slug = text.lower().strip()
    slug = re.sub(r"[^\w\s-]", "", slug)
    slug = re.sub(r"[\s_]+", "-", slug)
    slug = re.sub(r"-+", "-", slug).strip("-")
    return slug[:max_len]


@dataclass
class IngestResult:
    """Result of ingesting a single file."""

    source_path: Path
    output_path: Path | None = None
    success: bool = False
    message: str = ""


@dataclass
class BatchResult:
    """Result of ingesting a batch of files."""

    results: list[IngestResult] = field(default_factory=list)

    @property
    def succeeded(self) -> int:
        return sum(1 for r in self.results if r.success)

    @property
    def failed(self) -> int:
        return sum(1 for r in self.results if not r.success)

    @property
    def total(self) -> int:
        return len(self.results)


def _ingest_markdown(path: Path, raw_dir: Path) -> IngestResult:
    """Ingest a markdown or text file — passthrough with frontmatter."""
    content = path.read_text(errors="replace")

    # Check if it already has frontmatter
    try:
        post = frontmatter.loads(content)
        existing_fm = dict(post.metadata)
        body = post.content
    except Exception:
        existing_fm = {}
        body = content

    # Add/merge frontmatter
    fm_data = {
        "title": existing_fm.get("title", path.stem.replace("-", " ").title()),
        "id": slugify(path.stem),
        "source": "local",
        "format": "markdown",
        "clipped_at": datetime.now(UTC).isoformat(),
        "word_count": len(body.split()),
        "content_hash": content_hash(path),
        "status": "raw",
        **existing_fm,  # Preserve existing frontmatter fields
    }

    post = frontmatter.Post(body, **fm_data)
    slug = slugify(path.stem)
    output_path = raw_dir / f"{slug}.md"

    counter = 2
    while output_path.exists():
        output_path = raw_dir / f"{slug}-{counter}.md"
        counter += 1

    output_path.write_text(frontmatter.dumps(post))
    return IngestResult(
        source_path=path,
        output_path=output_path,
        success=True,
        message=f"Ingested: {path.name} ({fm_data['word_count']} words)",
    )


def _ingest_csv(path: Path, raw_dir: Path) -> IngestResult:
    """Ingest a CSV/TSV file — preserve as-is with metadata frontmatter."""
    content = path.read_text(errors="replace")
    lines = content.strip().split("\n")
    row_count = len(lines) - 1  # Exclude header
    columns = lines[0].split("," if path.suffix == ".csv" else "\t") if lines else []

    fm_data = {
        "title": path.stem.replace("-", " ").title(),
        "id": slugify(path.stem),
        "source": "local",
        "format": "csv",
        "clipped_at": datetime.now(UTC).isoformat(),
        "word_count": len(content.split()),
        "content_hash": content_hash(path),
        "status": "raw",
        "row_count": row_count,
        "columns": [c.strip().strip('"') for c in columns],
    }

    # Wrap CSV in a code block for readability
    body = f"# {fm_data['title']}\n\n```csv\n{content}\n```"
    post = frontmatter.Post(body, **fm_data)

    slug = slugify(path.stem)
    output_path = raw_dir / f"{slug}.md"

    counter = 2
    while output_path.exists():
        output_path = raw_dir / f"{slug}-{counter}.md"
        counter += 1

    output_path.write_text(frontmatter.dumps(post))
    return IngestResult(
        source_path=path,
        output_path=output_path,
        success=True,
        message=f"Ingested: {path.name} ({row_count} rows, {len(columns)} columns)",
    )


def _ingest_image(path: Path, images_dir: Path) -> IngestResult:
    """Catalog an image file into raw/images/standalone/."""
    dest_dir = images_dir / "standalone"
    dest_dir.mkdir(parents=True, exist_ok=True)

    dest = dest_dir / path.name
    counter = 2
    while dest.exists():
        dest = dest_dir / f"{path.stem}-{counter}{path.suffix}"
        counter += 1

    shutil.copy2(path, dest)
    return IngestResult(
        source_path=path,
        output_path=dest,
        success=True,
        message=f"Cataloged image: {path.name}",
    )


def ingest_file(
    path: Path,
    raw_dir: Path,
    images_dir: Path,
    originals_dir: Path,
) -> IngestResult:
    """Ingest a single file into the raw/ directory.

    Dispatches to the appropriate handler based on file extension.
    """
    if not path.exists():
        return IngestResult(source_path=path, message=f"File not found: {path}")

    ext = path.suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        return IngestResult(
            source_path=path,
            message=f"Unsupported file type: {ext}. "
            f"Supported: {', '.join(sorted(SUPPORTED_EXTENSIONS))}",
        )

    # Dedup check
    file_hash = content_hash(path)
    dup = find_duplicate_by_hash(raw_dir, file_hash)
    if dup:
        return IngestResult(
            source_path=path,
            message=f"Duplicate of {dup.name} (identical content hash)",
        )

    try:
        if ext == ".pdf":
            output = extract_pdf(path, raw_dir, originals_dir, images_dir)
            return IngestResult(
                source_path=path,
                output_path=output,
                success=True,
                message=f"Ingested PDF: {path.name}",
            )
        elif ext in IMAGE_EXTENSIONS:
            return _ingest_image(path, images_dir)
        elif ext in (".csv", ".tsv"):
            return _ingest_csv(path, raw_dir)
        else:
            return _ingest_markdown(path, raw_dir)
    except Exception as e:
        return IngestResult(source_path=path, message=f"Error: {e}")


def ingest_batch(
    paths: list[Path],
    raw_dir: Path,
    images_dir: Path,
    originals_dir: Path,
) -> BatchResult:
    """Ingest a batch of files. Errors on individual files don't block others."""
    batch = BatchResult()
    for path in paths:
        if path.is_dir():
            # Recursively collect files from directory
            for child in sorted(path.rglob("*")):
                if child.is_file() and child.suffix.lower() in SUPPORTED_EXTENSIONS:
                    result = ingest_file(child, raw_dir, images_dir, originals_dir)
                    batch.results.append(result)
        else:
            result = ingest_file(path, raw_dir, images_dir, originals_dir)
            batch.results.append(result)
    return batch
