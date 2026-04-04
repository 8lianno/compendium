"""Tests for search engine."""

from __future__ import annotations

from typing import TYPE_CHECKING

import frontmatter
import pytest

from compendium.search.engine import SearchEngine, _build_snippet

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def wiki_with_search(tmp_path: Path) -> Path:
    """Create a wiki directory with articles for search testing."""
    wiki_dir = tmp_path / "wiki"
    wiki_dir.mkdir()
    concepts_dir = wiki_dir / "concepts"
    concepts_dir.mkdir()
    methods_dir = wiki_dir / "methods"
    methods_dir.mkdir()

    post1 = frontmatter.Post(
        "# Transformer Architecture\n\n"
        "The transformer model uses self-attention mechanisms to process sequences "
        "in parallel. It achieves state-of-the-art results on machine translation "
        "and other NLP tasks.",
        title="Transformer Architecture",
        category="concepts",
    )
    (concepts_dir / "transformer-architecture.md").write_text(frontmatter.dumps(post1))

    post2 = frontmatter.Post(
        "# Attention Mechanisms\n\n"
        "Scaled dot-product attention computes attention weights using queries, "
        "keys, and values. Multi-head attention runs multiple attention operations "
        "in parallel.",
        title="Attention Mechanisms",
        category="methods",
    )
    (methods_dir / "attention-mechanisms.md").write_text(frontmatter.dumps(post2))

    post3 = frontmatter.Post(
        "# BERT Model\n\n"
        "BERT uses bidirectional transformer encoders for pre-training. "
        "It achieves strong results on natural language understanding benchmarks.",
        title="BERT Model",
        category="concepts",
    )
    (concepts_dir / "bert.md").write_text(frontmatter.dumps(post3))

    return wiki_dir


class TestSearchEngine:
    def test_build_index(self, wiki_with_search: Path) -> None:
        engine = SearchEngine(wiki_with_search)
        count = engine.build_index()
        assert count == 3

    def test_search_basic(self, wiki_with_search: Path) -> None:
        engine = SearchEngine(wiki_with_search)
        engine.build_index()

        results = engine.search("transformer attention")
        assert len(results) >= 1
        # Transformer or attention article should be top result
        titles = [r["title"] for r in results]
        assert any("Transformer" in t or "Attention" in t for t in titles)

    def test_search_relevance_order(self, wiki_with_search: Path) -> None:
        engine = SearchEngine(wiki_with_search)
        engine.build_index()

        results = engine.search("BERT bidirectional")
        assert len(results) >= 1
        assert results[0]["title"] == "BERT Model"

    def test_search_no_results(self, wiki_with_search: Path) -> None:
        engine = SearchEngine(wiki_with_search)
        engine.build_index()

        results = engine.search("xyzzyplugh nonexistent42")
        assert len(results) == 0

    def test_search_with_limit(self, wiki_with_search: Path) -> None:
        engine = SearchEngine(wiki_with_search)
        engine.build_index()

        results = engine.search("model", limit=1)
        assert len(results) <= 1

    def test_search_returns_snippets(self, wiki_with_search: Path) -> None:
        engine = SearchEngine(wiki_with_search)
        engine.build_index()

        results = engine.search("attention")
        assert len(results) >= 1
        assert results[0]["snippet"]  # Non-empty snippet

    def test_search_returns_score(self, wiki_with_search: Path) -> None:
        engine = SearchEngine(wiki_with_search)
        engine.build_index()

        results = engine.search("transformer")
        assert all(r["score"] > 0 for r in results)

    def test_auto_build_on_first_search(self, wiki_with_search: Path) -> None:
        """Index should auto-build if it doesn't exist."""
        engine = SearchEngine(wiki_with_search)
        # Don't call build_index() — it should auto-build
        results = engine.search("transformer")
        assert len(results) >= 1

    def test_update_article(self, wiki_with_search: Path) -> None:
        engine = SearchEngine(wiki_with_search)
        engine.build_index()

        # Add a new article to the index
        engine.update_article(
            "concepts/gpt.md",
            "GPT Architecture",
            "concepts",
            "GPT uses autoregressive decoding with transformer decoders.",
        )

        results = engine.search("GPT autoregressive")
        assert len(results) >= 1
        assert results[0]["title"] == "GPT Architecture"

    def test_remove_article(self, wiki_with_search: Path) -> None:
        engine = SearchEngine(wiki_with_search)
        engine.build_index()

        engine.remove_article("concepts/bert.md")

        results = engine.search("BERT bidirectional")
        assert len(results) == 0


class TestSnippetBuilder:
    def test_snippet_around_match(self) -> None:
        text = "word " * 50 + "transformer is great " + "word " * 50
        snippet = _build_snippet(text, "transformer", max_words=10)
        assert "transformer" in snippet

    def test_snippet_with_ellipsis(self) -> None:
        text = "word " * 100
        snippet = _build_snippet(text, "word", max_words=10)
        assert "..." in snippet

    def test_snippet_empty(self) -> None:
        snippet = _build_snippet("", "query", max_words=10)
        assert snippet == ""
