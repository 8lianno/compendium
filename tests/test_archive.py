"""Tests for source archive and restore operations."""

from __future__ import annotations

from typing import TYPE_CHECKING

import frontmatter

from compendium.core.wiki_fs import WikiFileSystem
from compendium.pipeline.archive import archive_source, restore_source
from compendium.pipeline.deps import ArticleEntry, DependencyGraph, SourceEntry

if TYPE_CHECKING:
    from pathlib import Path


def _make_project(tmp_path: Path) -> WikiFileSystem:
    """Create a test project with raw source, wiki article, and dependency graph."""
    wfs = WikiFileSystem(tmp_path)
    wfs.init_project(name="Archive Test")

    # Create a raw source
    source_post = frontmatter.Post(
        "# Deep Work Highlights\n\n> Focus is rare.",
        title="Deep Work — Highlights",
        id="deep-work-highlights",
        source="local",
        format="book-highlights",
        book_title="Deep Work",
    )
    (wfs.raw_dir / "deep-work-highlights.md").write_text(frontmatter.dumps(source_post))

    # Create a wiki article that depends on this source
    article_post = frontmatter.Post(
        "# Focus and Deep Work\n\nFocus is rare according to [[deep-work-highlights]].",
        title="Focus and Deep Work",
        id="focus-deep-work",
        category="concepts",
        sources=[{"ref": "raw/deep-work-highlights.md"}],
        status="published",
    )
    concepts_dir = wfs.wiki_dir / "concepts"
    concepts_dir.mkdir(exist_ok=True)
    (concepts_dir / "focus-deep-work.md").write_text(frontmatter.dumps(article_post))

    # Create index.md
    (wfs.wiki_dir / "index.md").write_text(
        "# Index\n\n| Article | Category |\n|---|---|\n"
        "| [[focus-deep-work]] | concepts |\n"
    )

    # Create dependency graph
    deps = DependencyGraph()
    deps.sources["raw/deep-work-highlights.md"] = SourceEntry(
        content_hash="sha256:abc",
        compiled_at="2026-01-01T00:00:00",
        produces=["wiki/concepts/focus-deep-work.md"],
        concepts=["focus", "deep work"],
    )
    deps.articles["wiki/concepts/focus-deep-work.md"] = ArticleEntry(
        depends_on=["raw/deep-work-highlights.md"],
        content_hash="sha256:def",
        word_count=50,
    )
    deps.save(wfs.deps_path)

    return wfs


def _make_multi_source_project(tmp_path: Path) -> WikiFileSystem:
    """Create a project where one article depends on TWO sources."""
    wfs = _make_project(tmp_path)

    # Add a second source
    source2 = frontmatter.Post(
        "# Atomic Habits\n\n> Small changes compound.",
        title="Atomic Habits — Highlights",
        id="atomic-habits-highlights",
        source="local",
        format="book-highlights",
        book_title="Atomic Habits",
    )
    (wfs.raw_dir / "atomic-habits-highlights.md").write_text(frontmatter.dumps(source2))

    # Update the article to depend on both sources
    article_path = wfs.wiki_dir / "concepts" / "focus-deep-work.md"
    post = frontmatter.load(str(article_path))
    post.metadata["sources"] = [
        {"ref": "raw/deep-work-highlights.md"},
        {"ref": "raw/atomic-habits-highlights.md"},
    ]
    article_path.write_text(frontmatter.dumps(post))

    # Update deps
    deps = DependencyGraph.load(wfs.deps_path)
    deps.sources["raw/atomic-habits-highlights.md"] = SourceEntry(
        content_hash="sha256:ghi",
        compiled_at="2026-01-01T00:00:00",
        produces=["wiki/concepts/focus-deep-work.md"],
    )
    deps.articles["wiki/concepts/focus-deep-work.md"].depends_on = [
        "raw/deep-work-highlights.md",
        "raw/atomic-habits-highlights.md",
    ]
    deps.save(wfs.deps_path)

    return wfs


class TestArchiveSource:
    def test_archive_moves_source(self, tmp_path: Path) -> None:
        wfs = _make_project(tmp_path)
        result = archive_source(wfs, "raw/deep-work-highlights.md")

        assert "raw/deep-work-highlights.md" in result.sources_moved
        assert not (wfs.raw_dir / "deep-work-highlights.md").exists()
        assert (wfs.archive_sources_dir / "deep-work-highlights.md").exists()

    def test_archive_moves_single_dep_article(self, tmp_path: Path) -> None:
        wfs = _make_project(tmp_path)
        result = archive_source(wfs, "raw/deep-work-highlights.md")

        assert "wiki/concepts/focus-deep-work.md" in result.articles_archived
        assert not (wfs.wiki_dir / "concepts" / "focus-deep-work.md").exists()
        assert (wfs.archive_wiki_dir / "concepts" / "focus-deep-work.md").exists()

    def test_archive_updates_deps(self, tmp_path: Path) -> None:
        wfs = _make_project(tmp_path)
        archive_source(wfs, "raw/deep-work-highlights.md")

        deps = DependencyGraph.load(wfs.deps_path)
        assert "raw/deep-work-highlights.md" not in deps.sources
        assert "raw/deep-work-highlights.md" in deps.archived_sources
        assert "wiki/concepts/focus-deep-work.md" not in deps.articles

    def test_archive_rebuilds_index(self, tmp_path: Path) -> None:
        wfs = _make_project(tmp_path)
        result = archive_source(wfs, "raw/deep-work-highlights.md")
        assert result.index_rebuilt

    def test_archive_patches_multi_source_article(self, tmp_path: Path) -> None:
        wfs = _make_multi_source_project(tmp_path)
        result = archive_source(wfs, "raw/deep-work-highlights.md")

        # Article should be patched, not archived (it still has another source)
        assert "wiki/concepts/focus-deep-work.md" in result.articles_patched
        assert (wfs.wiki_dir / "concepts" / "focus-deep-work.md").exists()

        # Source ref should be removed from frontmatter
        post = frontmatter.load(str(wfs.wiki_dir / "concepts" / "focus-deep-work.md"))
        refs = [s.get("ref", s) if isinstance(s, dict) else s for s in post.metadata["sources"]]
        assert "raw/deep-work-highlights.md" not in refs
        assert "raw/atomic-habits-highlights.md" in refs

    def test_archive_nonexistent_source(self, tmp_path: Path) -> None:
        wfs = _make_project(tmp_path)
        result = archive_source(wfs, "raw/nonexistent.md")
        assert result.sources_moved == []


class TestRestoreSource:
    def test_restore_moves_source_back(self, tmp_path: Path) -> None:
        wfs = _make_project(tmp_path)
        archive_source(wfs, "raw/deep-work-highlights.md")

        result = restore_source(wfs, "raw/deep-work-highlights.md")

        assert "raw/deep-work-highlights.md" in result.sources_moved
        assert (wfs.raw_dir / "deep-work-highlights.md").exists()
        assert not (wfs.archive_sources_dir / "deep-work-highlights.md").exists()

    def test_restore_moves_articles_back(self, tmp_path: Path) -> None:
        wfs = _make_project(tmp_path)
        archive_source(wfs, "raw/deep-work-highlights.md")

        result = restore_source(wfs, "raw/deep-work-highlights.md")

        assert "wiki/concepts/focus-deep-work.md" in result.articles_restored
        assert (wfs.wiki_dir / "concepts" / "focus-deep-work.md").exists()

    def test_restore_updates_deps(self, tmp_path: Path) -> None:
        wfs = _make_project(tmp_path)
        archive_source(wfs, "raw/deep-work-highlights.md")
        restore_source(wfs, "raw/deep-work-highlights.md")

        deps = DependencyGraph.load(wfs.deps_path)
        assert "raw/deep-work-highlights.md" in deps.sources
        assert "raw/deep-work-highlights.md" not in deps.archived_sources

    def test_restore_rebuilds_index(self, tmp_path: Path) -> None:
        wfs = _make_project(tmp_path)
        archive_source(wfs, "raw/deep-work-highlights.md")
        result = restore_source(wfs, "raw/deep-work-highlights.md")
        assert result.index_rebuilt

    def test_restore_nonexistent(self, tmp_path: Path) -> None:
        wfs = _make_project(tmp_path)
        result = restore_source(wfs, "raw/nonexistent.md")
        assert result.sources_moved == []

    def test_full_roundtrip(self, tmp_path: Path) -> None:
        """Archive then restore — everything back to original state."""
        wfs = _make_project(tmp_path)

        # Verify initial state
        assert (wfs.raw_dir / "deep-work-highlights.md").exists()
        assert (wfs.wiki_dir / "concepts" / "focus-deep-work.md").exists()

        # Archive
        archive_source(wfs, "raw/deep-work-highlights.md")
        assert not (wfs.raw_dir / "deep-work-highlights.md").exists()
        assert not (wfs.wiki_dir / "concepts" / "focus-deep-work.md").exists()

        # Restore
        restore_source(wfs, "raw/deep-work-highlights.md")
        assert (wfs.raw_dir / "deep-work-highlights.md").exists()
        assert (wfs.wiki_dir / "concepts" / "focus-deep-work.md").exists()

        # Deps should be back to normal
        deps = DependencyGraph.load(wfs.deps_path)
        assert "raw/deep-work-highlights.md" in deps.sources
        assert not deps.archived_sources
