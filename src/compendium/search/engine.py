"""Full-text search engine using Whoosh with BM25 ranking."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

import frontmatter
from whoosh import index as whoosh_index
from whoosh.analysis import StemmingAnalyzer
from whoosh.fields import ID, TEXT, Schema
from whoosh.qparser import MultifieldParser, OrGroup

if TYPE_CHECKING:
    from pathlib import Path

SCHEMA = Schema(
    path=ID(stored=True, unique=True),
    title=TEXT(stored=True, analyzer=StemmingAnalyzer()),
    category=ID(stored=True),
    content=TEXT(stored=True, analyzer=StemmingAnalyzer()),
)


class SearchEngine:
    """Full-text search over wiki articles using Whoosh/BM25."""

    def __init__(self, wiki_dir: Path) -> None:
        self._wiki_dir = wiki_dir
        self._index_dir = wiki_dir / ".search-index"
        self._ix: whoosh_index.FileIndex | None = None

    def build_index(self) -> int:
        """Build or rebuild the search index from all wiki articles.

        Returns the number of articles indexed.
        """
        self._index_dir.mkdir(parents=True, exist_ok=True)
        ix = whoosh_index.create_in(str(self._index_dir), SCHEMA)
        writer = ix.writer()
        count = 0

        for md_file in self._wiki_dir.rglob("*.md"):
            # Skip dot-dirs and meta files
            rel = md_file.relative_to(self._wiki_dir)
            if any(part.startswith(".") for part in rel.parts):
                continue
            if md_file.name in ("INDEX.md", "CONCEPTS.md", "CONFLICTS.md", "CHANGELOG.md"):
                continue

            try:
                post = frontmatter.load(str(md_file))
                title = post.metadata.get("title", md_file.stem)
                category = post.metadata.get("category", "")
                content = post.content
            except Exception:
                title = md_file.stem
                category = ""
                content = md_file.read_text()

            writer.add_document(
                path=str(rel),
                title=title,
                category=category,
                content=content,
            )
            count += 1

        writer.commit()
        self._ix = ix
        return count

    def _get_index(self) -> whoosh_index.FileIndex:
        """Get or open the search index."""
        if self._ix is not None:
            return self._ix
        if self._index_dir.exists() and whoosh_index.exists_in(str(self._index_dir)):
            self._ix = whoosh_index.open_dir(str(self._index_dir))
            return self._ix
        # Auto-build if no index exists
        self.build_index()
        assert self._ix is not None
        return self._ix

    def search(
        self,
        query: str,
        limit: int = 10,
    ) -> list[dict]:
        """Search the wiki and return ranked results.

        Returns list of dicts with: path, title, category, score, snippet
        """
        ix = self._get_index()

        parser = MultifieldParser(
            ["title", "content"],
            schema=ix.schema,
            group=OrGroup,
        )

        try:
            parsed = parser.parse(query)
        except Exception:
            # Fallback for queries with special characters
            clean = re.sub(r"[^\w\s]", " ", query)
            parsed = parser.parse(clean)

        results: list[dict] = []
        with ix.searcher() as searcher:
            hits = searcher.search(parsed, limit=limit)
            for hit in hits:
                # Build snippet from content
                content = hit.get("content", "")
                snippet = _build_snippet(content, query, max_words=30)

                results.append(
                    {
                        "path": hit["path"],
                        "title": hit.get("title", ""),
                        "category": hit.get("category", ""),
                        "score": round(hit.score, 3),
                        "snippet": snippet,
                    }
                )

        return results

    def update_article(self, rel_path: str, title: str, category: str, content: str) -> None:
        """Update a single article in the index (add or replace)."""
        ix = self._get_index()
        writer = ix.writer()
        writer.update_document(
            path=rel_path,
            title=title,
            category=category,
            content=content,
        )
        writer.commit()

    def remove_article(self, rel_path: str) -> None:
        """Remove an article from the index."""
        ix = self._get_index()
        writer = ix.writer()
        writer.delete_by_term("path", rel_path)
        writer.commit()


def _build_snippet(content: str, query: str, max_words: int = 30) -> str:
    """Build a context snippet around query terms."""
    words = content.split()
    query_terms = set(re.findall(r"\w+", query.lower()))

    # Find the first occurrence of any query term
    best_pos = 0
    for i, word in enumerate(words):
        if word.lower().strip(".,;:!?()[]") in query_terms:
            best_pos = i
            break

    # Extract window around the match
    start = max(0, best_pos - max_words // 2)
    end = min(len(words), start + max_words)
    snippet_words = words[start:end]

    snippet = " ".join(snippet_words)
    if start > 0:
        snippet = "..." + snippet
    if end < len(words):
        snippet = snippet + "..."

    return snippet
