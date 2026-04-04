"""Dependency graph for tracking source→article relationships and incremental compilation."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from pathlib import Path


class SourceEntry(BaseModel):
    """Tracks a raw source's compilation state."""

    content_hash: str = ""
    compiled_at: str | None = None
    produces: list[str] = Field(default_factory=list)
    concepts: list[str] = Field(default_factory=list)


class ArticleEntry(BaseModel):
    """Tracks a wiki article's dependencies."""

    depends_on: list[str] = Field(default_factory=list)
    backlinks_to: list[str] = Field(default_factory=list)
    backlinked_from: list[str] = Field(default_factory=list)
    content_hash: str = ""
    patch_count: int = 0
    last_compiled: str | None = None
    word_count: int = 0
    origin: str = "compilation"


class ConceptEntry(BaseModel):
    """Tracks a concept's article mapping."""

    canonical: str
    aliases: list[str] = Field(default_factory=list)
    article: str | None = None
    source_count: int = 0
    sources: list[str] = Field(default_factory=list)
    category: str = ""


class DepsMetadata(BaseModel):
    """Aggregate stats."""

    total_sources: int = 0
    total_articles: int = 0
    total_concepts: int = 0
    total_backlinks: int = 0
    last_full_compile: str | None = None
    last_incremental: str | None = None


class DependencyGraph(BaseModel):
    """The wiki/.deps.json dependency graph."""

    version: int = 1
    sources: dict[str, SourceEntry] = Field(default_factory=dict)
    articles: dict[str, ArticleEntry] = Field(default_factory=dict)
    concepts: dict[str, ConceptEntry] = Field(default_factory=dict)
    meta: DepsMetadata = Field(default_factory=DepsMetadata)

    @classmethod
    def load(cls, path: Path) -> DependencyGraph:
        """Load dependency graph from .deps.json."""
        if not path.exists():
            return cls()
        data = json.loads(path.read_text())
        return cls.model_validate(data)

    def save(self, path: Path) -> None:
        """Save dependency graph to .deps.json."""
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.model_dump_json(indent=2))

    def get_new_sources(self, current_hashes: dict[str, str]) -> list[str]:
        """Find sources that are new or have changed content hash."""
        new = []
        for source_path, current_hash in current_hashes.items():
            existing = self.sources.get(source_path)
            if existing is None or existing.content_hash != current_hash:
                new.append(source_path)
        return new

    def get_affected_articles(self, source_paths: list[str]) -> list[str]:
        """Find wiki articles that depend on the given source paths."""
        affected = set()
        for article_path, entry in self.articles.items():
            if any(s in entry.depends_on for s in source_paths):
                affected.add(article_path)
        return sorted(affected)

    def get_affected_by_concepts(self, concepts: list[str]) -> list[str]:
        """Find wiki articles associated with the given concepts."""
        affected = set()
        for concept_name in concepts:
            concept = self.concepts.get(concept_name)
            if concept and concept.article:
                affected.add(concept.article)
        return sorted(affected)

    def update_meta(self) -> None:
        """Recalculate aggregate metadata."""
        total_backlinks = sum(len(a.backlinks_to) for a in self.articles.values())
        self.meta = DepsMetadata(
            total_sources=len(self.sources),
            total_articles=len(self.articles),
            total_concepts=len(self.concepts),
            total_backlinks=total_backlinks,
            last_full_compile=self.meta.last_full_compile,
            last_incremental=self.meta.last_incremental,
        )

    def mark_full_compile(self) -> None:
        self.meta.last_full_compile = datetime.now(UTC).isoformat()

    def mark_incremental(self) -> None:
        self.meta.last_incremental = datetime.now(UTC).isoformat()
