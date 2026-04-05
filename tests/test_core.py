"""Tests for core data models, config, and WikiFileSystem."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from compendium.core.config import CompendiumConfig
from compendium.core.frontmatter import (
    ArticleOrigin,
    RawSourceFrontmatter,
    SourceFormat,
    WikiArticleFrontmatter,
)
from compendium.core.wiki_fs import WikiFileSystem
from compendium.core.wikilinks import Wikilink, parse_wikilinks, validate_wikilinks

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def tmp_project(tmp_path: Path) -> Path:
    """Create a temporary project directory."""
    return tmp_path / "test-wiki"


@pytest.fixture
def wiki_fs(tmp_project: Path) -> WikiFileSystem:
    """Create and initialize a WikiFileSystem."""
    wfs = WikiFileSystem(tmp_project)
    wfs.init_project(name="Test Wiki")
    return wfs


class TestRawSourceFrontmatter:
    def test_defaults(self) -> None:
        fm = RawSourceFrontmatter(title="Test", id="test")
        assert fm.format == SourceFormat.MARKDOWN
        assert fm.status.value == "raw"
        assert fm.word_count == 0

    def test_full_fields(self) -> None:
        fm = RawSourceFrontmatter(
            title="Test Paper",
            id="test-paper",
            source_url="https://example.com",
            author="Author",
            format=SourceFormat.PDF_EXTRACTED,
            word_count=5000,
            content_hash="sha256:abc123",
        )
        assert fm.title == "Test Paper"
        assert fm.source_url == "https://example.com"
        assert fm.format == SourceFormat.PDF_EXTRACTED


class TestWikiArticleFrontmatter:
    def test_defaults(self) -> None:
        fm = WikiArticleFrontmatter(title="Test Article", id="test-article")
        assert fm.origin == ArticleOrigin.COMPILATION
        assert fm.status.value == "published"
        assert fm.related == []
        assert fm.referenced_by == []

    def test_with_sources(self) -> None:
        fm = WikiArticleFrontmatter(
            title="Test",
            id="test",
            sources=[{"ref": "raw/source.md", "sections": ["1.1"]}],
        )
        assert len(fm.sources) == 1
        assert fm.sources[0].ref == "raw/source.md"


class TestCompendiumConfig:
    def test_default_config(self) -> None:
        config = CompendiumConfig()
        assert config.project.name == "My Knowledge Wiki"
        assert config.models.default_provider == "anthropic"

    def test_load_nonexistent(self, tmp_path: Path) -> None:
        config = CompendiumConfig.load(tmp_path / "nonexistent.toml")
        assert config.project.name == "My Knowledge Wiki"

    def test_load_from_file(self, tmp_path: Path) -> None:
        config_file = tmp_path / "compendium.toml"
        config_file.write_text('[project]\nname = "My Test Wiki"\n')
        config = CompendiumConfig.load(config_file)
        assert config.project.name == "My Test Wiki"


class TestWikiFileSystem:
    def test_init_project(self, wiki_fs: WikiFileSystem) -> None:
        assert wiki_fs.raw_dir.exists()
        assert wiki_fs.wiki_dir.exists()
        assert wiki_fs.output_dir.exists()
        assert wiki_fs.staging_dir.exists()
        assert wiki_fs.backup_dir.exists()
        assert wiki_fs.config_path.exists()

    def test_list_raw_sources_empty(self, wiki_fs: WikiFileSystem) -> None:
        assert wiki_fs.list_raw_sources() == []

    def test_list_raw_sources(self, wiki_fs: WikiFileSystem) -> None:
        # Copy fixture files to raw/
        for fixture in FIXTURES_DIR.glob("sample_source_*.md"):
            shutil.copy(fixture, wiki_fs.raw_dir / fixture.name)
        sources = wiki_fs.list_raw_sources()
        assert len(sources) == 3

    def test_content_hash(self, wiki_fs: WikiFileSystem) -> None:
        test_file = wiki_fs.raw_dir / "test.md"
        test_file.write_text("hello world")
        h = wiki_fs.content_hash(test_file)
        assert h.startswith("sha256:")
        # Same content = same hash
        assert wiki_fs.content_hash(test_file) == h

    def test_staging_promotion(self, wiki_fs: WikiFileSystem) -> None:
        # Create a staged article
        staged = wiki_fs.staging_dir / "test-article.md"
        staged.write_text("# Test Article\nContent here.")

        # Promote
        wiki_fs.promote_staging()

        # Check it's in wiki/
        promoted = wiki_fs.wiki_dir / "test-article.md"
        assert promoted.exists()
        assert promoted.read_text() == "# Test Article\nContent here."

        # Staging should be cleaned
        assert not staged.exists()

    def test_backup_and_rollback(self, wiki_fs: WikiFileSystem) -> None:
        # Create a wiki article
        article = wiki_fs.wiki_dir / "article.md"
        article.write_text("# Original Content")

        # Create backup
        backup_id = wiki_fs.create_backup()
        assert backup_id

        # Modify article
        article.write_text("# Modified Content")
        assert article.read_text() == "# Modified Content"

        # Rollback
        wiki_fs.rollback(backup_id)
        assert article.read_text() == "# Original Content"

    def test_backup_pruning(self, wiki_fs: WikiFileSystem) -> None:
        # Create a wiki article
        article = wiki_fs.wiki_dir / "article.md"
        article.write_text("content")

        # Create 7 backups (should keep only 5)
        for _ in range(7):
            wiki_fs.create_backup()

        backups = [d for d in wiki_fs.backup_dir.iterdir() if d.is_dir() and d.name != ".gitkeep"]
        assert len(backups) <= 5

    def test_list_wiki_articles_excludes_dot_dirs(self, wiki_fs: WikiFileSystem) -> None:
        # Create articles in normal and dot directories
        (wiki_fs.wiki_dir / "concepts").mkdir()
        (wiki_fs.wiki_dir / "concepts" / "test.md").write_text("# Test")
        (wiki_fs.staging_dir / "staged.md").write_text("# Staged")

        articles = wiki_fs.list_wiki_articles()
        paths = [a.name for a in articles]
        assert "test.md" in paths
        assert "staged.md" not in paths


class TestWikilinks:
    def test_parse_simple(self) -> None:
        links = parse_wikilinks("See [[attention-mechanisms]] for details.")
        assert len(links) == 1
        assert links[0].target == "attention-mechanisms"
        assert links[0].display is None

    def test_parse_with_display(self) -> None:
        links = parse_wikilinks("See [[attention|Attention Mechanisms]] here.")
        assert len(links) == 1
        assert links[0].target == "attention"
        assert links[0].display == "Attention Mechanisms"

    def test_parse_multiple(self) -> None:
        text = "Combines [[transformers]] and [[attention]] from [[bert]]."
        links = parse_wikilinks(text)
        assert len(links) == 3

    def test_wikilink_str(self) -> None:
        assert str(Wikilink("test")) == "[[test]]"
        assert str(Wikilink("test", "Display")) == "[[test|Display]]"

    def test_validate_broken_links(self, tmp_path: Path) -> None:
        wiki_dir = tmp_path / "wiki"
        wiki_dir.mkdir()
        (wiki_dir / "existing.md").write_text("# Existing")

        text = "Links to [[existing]] and [[missing]]."
        broken = validate_wikilinks(text, wiki_dir)
        assert len(broken) == 1
        assert broken[0].target == "missing"
