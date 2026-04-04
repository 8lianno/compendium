"""Wikilink parsing, resolution, and insertion utilities."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

# Pattern: [[target]] or [[target|display text]]
WIKILINK_PATTERN = re.compile(r"\[\[([^\]|]+)(?:\|([^\]]+))?\]\]")


@dataclass
class Wikilink:
    """A parsed wikilink."""

    target: str  # The link target (article id or path)
    display: str | None = None  # Optional display text

    def __str__(self) -> str:
        if self.display:
            return f"[[{self.target}|{self.display}]]"
        return f"[[{self.target}]]"


def parse_wikilinks(text: str) -> list[Wikilink]:
    """Extract all wikilinks from markdown text."""
    return [
        Wikilink(target=m.group(1).strip(), display=m.group(2))
        for m in WIKILINK_PATTERN.finditer(text)
    ]


def resolve_wikilink(link: Wikilink, wiki_dir: Path) -> Path | None:
    """Resolve a wikilink to an actual file path in the wiki directory.

    Tries:
    1. Exact path match (e.g., [[concepts/attention.md]])
    2. Slug match in any subdirectory (e.g., [[attention]] -> concepts/attention.md)
    3. Case-insensitive slug match
    """
    # Try exact path
    exact = wiki_dir / link.target
    if exact.exists():
        return exact
    if exact.with_suffix(".md").exists():
        return exact.with_suffix(".md")

    # Try slug match across all subdirs
    slug = link.target.lower().replace(" ", "-")
    for md_file in wiki_dir.rglob("*.md"):
        if md_file.stem.lower() == slug:
            return md_file

    return None


def insert_wikilink(text: str, target: str, context_phrase: str | None = None) -> str:
    """Insert a wikilink into text.

    If context_phrase is given, wraps the first occurrence of that phrase with a wikilink.
    Otherwise, appends to the Related Articles section.
    """
    link = f"[[{target}]]"
    if context_phrase:
        # Wrap first occurrence of the phrase
        return text.replace(context_phrase, f"{context_phrase} {link}", 1)
    return text


def validate_wikilinks(text: str, wiki_dir: Path) -> list[Wikilink]:
    """Return list of broken wikilinks (those that don't resolve to a file)."""
    links = parse_wikilinks(text)
    return [link for link in links if resolve_wikilink(link, wiki_dir) is None]
