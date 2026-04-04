"""Deduplication utilities for source ingestion."""

from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING

import frontmatter

if TYPE_CHECKING:
    from pathlib import Path


def content_hash(path: Path) -> str:
    """Compute SHA-256 hash of file contents."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return f"sha256:{h.hexdigest()}"


def text_hash(text: str) -> str:
    """Compute SHA-256 hash of text content."""
    h = hashlib.sha256(text.encode())
    return f"sha256:{h.hexdigest()}"


def find_duplicate_by_url(raw_dir: Path, url: str) -> Path | None:
    """Check if a source with the same URL already exists in raw/."""
    if not raw_dir.exists():
        return None
    for md_file in raw_dir.iterdir():
        if md_file.suffix != ".md" or not md_file.is_file():
            continue
        try:
            post = frontmatter.load(str(md_file))
            if post.metadata.get("source_url") == url:
                return md_file
        except Exception:
            continue
    return None


def find_duplicate_by_hash(raw_dir: Path, hash_value: str) -> Path | None:
    """Check if a source with the same content hash already exists in raw/."""
    if not raw_dir.exists():
        return None
    for md_file in raw_dir.iterdir():
        if md_file.suffix != ".md" or not md_file.is_file():
            continue
        try:
            post = frontmatter.load(str(md_file))
            if post.metadata.get("content_hash") == hash_value:
                return md_file
        except Exception:
            continue
    return None
