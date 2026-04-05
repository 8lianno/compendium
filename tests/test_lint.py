"""Tests for wiki linting and health checks."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from compendium.lint.engine import LintReport, lint_wiki

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def wiki_for_lint(tmp_path: Path) -> dict[str, Path]:
    """Create a wiki with intentional issues for linting."""
    wiki_dir = tmp_path / "wiki"
    raw_dir = tmp_path / "raw"
    wiki_dir.mkdir()
    raw_dir.mkdir()
    concepts_dir = wiki_dir / "concepts"
    concepts_dir.mkdir()

    # Article with a broken link + mentions of "Reinforcement Learning"
    (concepts_dir / "transformers.md").write_text(
        "---\ntitle: Transformers\ncategory: concepts\n"
        "sources:\n  - ref: raw/source-a.md\n---\n\n"
        "# Transformers\n\nSee [[attention-mechanisms]] and [[nonexistent-article]].\n"
        "Some researchers compare transformers to reinforcement learning approaches.\n"
    )

    # Article that links back to transformers
    (concepts_dir / "attention-mechanisms.md").write_text(
        "---\ntitle: Attention Mechanisms\ncategory: methods\n---\n\n"
        "# Attention Mechanisms\n\nUsed in [[transformers]] architecture.\n"
        "Attention is also used in reinforcement learning agents.\n"
    )

    # Orphan article (no other article links to it)
    (concepts_dir / "orphan-concept.md").write_text(
        "---\ntitle: Orphan Concept\ncategory: concepts\n---\n\n"
        "# Orphan Concept\n\nThis article has no inbound links.\n"
        "Reinforcement learning methods differ from supervised approaches.\n"
    )

    # index.md
    (wiki_dir / "index.md").write_text(
        "# Index\n\n| Article | Category | Summary |\n"
        "|---------|----------|--------|\n"
        "| [[transformers|Transformers]] | concepts | Core arch |\n"
    )

    # concepts.md with a concept that has no article
    (wiki_dir / "concepts.md").write_text(
        "# Concepts\n\n## Concepts\n"
        "- **Transformers** — 3 sources\n"
        "- **Attention Mechanisms** — 3 sources\n"
        "- **Reinforcement Learning** — 5 sources\n"
    )

    # Raw source for staleness check
    (raw_dir / "source-a.md").write_text("---\ntitle: Source A\nid: source-a\n---\n\nContent.")

    return {"wiki": wiki_dir, "raw": raw_dir}


class TestLintReport:
    def test_empty_report(self) -> None:
        report = LintReport()
        assert report.total == 0
        assert report.critical_count == 0
        md = report.to_markdown()
        assert md.startswith("---\n")
        assert "healthy" in md.lower()

    def test_report_counts(self) -> None:
        from compendium.lint.engine import LintIssue

        report = LintReport()
        report.add(LintIssue("critical", "broken_link", "test.md", "broken"))
        report.add(LintIssue("warning", "orphan", "orphan.md", "orphan"))
        report.add(LintIssue("info", "stale", "stale.md", "stale"))

        assert report.critical_count == 1
        assert report.warning_count == 1
        assert report.info_count == 1
        assert report.total == 3

    def test_report_markdown(self) -> None:
        from compendium.lint.engine import LintIssue

        report = LintReport()
        report.add(
            LintIssue(
                "critical",
                "broken_link",
                "test.md",
                "Link [[missing]] does not resolve",
                "Create the article",
            )
        )

        md = report.to_markdown()
        assert md.startswith("---\n")
        assert "Critical" in md
        assert "broken" in md.lower()
        assert "test.md" in md


class TestBrokenLinks:
    def test_detects_broken_link(self, wiki_for_lint: dict[str, Path]) -> None:
        report = lint_wiki(wiki_for_lint["wiki"])

        broken = [i for i in report.issues if i.category == "broken_link"]
        assert len(broken) >= 1
        assert any("nonexistent-article" in i.description for i in broken)

    def test_valid_links_not_flagged(self, wiki_for_lint: dict[str, Path]) -> None:
        report = lint_wiki(wiki_for_lint["wiki"])

        broken = [i for i in report.issues if i.category == "broken_link"]
        # The link to attention-mechanisms should NOT be flagged
        assert not any("attention-mechanisms" in i.description for i in broken)


class TestOrphans:
    def test_detects_orphan(self, wiki_for_lint: dict[str, Path]) -> None:
        report = lint_wiki(wiki_for_lint["wiki"])

        orphans = [i for i in report.issues if i.category == "orphan"]
        assert any("orphan-concept" in i.location for i in orphans)

    def test_linked_articles_not_orphan(self, wiki_for_lint: dict[str, Path]) -> None:
        report = lint_wiki(wiki_for_lint["wiki"])

        orphans = [i for i in report.issues if i.category == "orphan"]
        orphan_locations = [i.location for i in orphans]
        # transformers is linked from attention-mechanisms, so not an orphan
        assert "transformers" not in orphan_locations


class TestCoverageGaps:
    def test_detects_gap(self, wiki_for_lint: dict[str, Path]) -> None:
        report = lint_wiki(wiki_for_lint["wiki"])

        gaps = [i for i in report.issues if i.category == "coverage_gap"]
        # "Reinforcement Learning" is in concepts.md but has no article
        assert any("Reinforcement Learning" in i.description for i in gaps)


class TestMissingCrossrefs:
    def test_detects_unlinked_mentions(self, wiki_for_lint: dict[str, Path]) -> None:
        orphan = wiki_for_lint["wiki"] / "concepts" / "orphan-concept.md"
        orphan.write_text(
            "---\ntitle: Orphan Concept\ncategory: concepts\n---\n\n"
            "# Orphan Concept\n\nThis article mentions Transformers but forgets the wikilink.\n"
        )

        report = lint_wiki(wiki_for_lint["wiki"])

        crossrefs = [i for i in report.issues if i.category == "missing_crossref"]
        assert any("Transformers" in i.description for i in crossrefs)


class TestConflictFile:
    def test_surfaces_conflicts_md_entries(self, wiki_for_lint: dict[str, Path]) -> None:
        (wiki_for_lint["wiki"] / "CONFLICTS.md").write_text(
            "# Conflicts\n\n## Warning\n\n### Transformers vs Attention Mechanisms\n"
            "- **Explanation:** Conflicting conclusions.\n"
        )

        report = lint_wiki(wiki_for_lint["wiki"])
        contradictions = [i for i in report.issues if i.category == "contradiction"]
        assert any("Transformers vs Attention Mechanisms" in i.description for i in contradictions)


class TestStructure:
    def test_missing_index(self, tmp_path: Path) -> None:
        wiki_dir = tmp_path / "wiki"
        wiki_dir.mkdir()
        # Create a single article but no index.md
        (wiki_dir / "test.md").write_text("# Test\nContent.")

        report = lint_wiki(wiki_dir)
        structure = [i for i in report.issues if i.category == "structure"]
        assert any("index.md" in i.location for i in structure)


class TestStaleness:
    def test_detects_stale(self, wiki_for_lint: dict[str, Path]) -> None:
        import os
        import time

        # Make the raw source newer than the wiki article
        raw_source = wiki_for_lint["raw"] / "source-a.md"
        article = wiki_for_lint["wiki"] / "concepts" / "transformers.md"

        # Set article mtime to the past
        old_time = time.time() - 3600
        os.utime(article, (old_time, old_time))
        # Touch the raw source to make it newer
        raw_source.write_text(raw_source.read_text() + "\nUpdated.")

        report = lint_wiki(wiki_for_lint["wiki"], raw_dir=wiki_for_lint["raw"])
        stale = [i for i in report.issues if i.category == "stale"]
        assert len(stale) >= 1


class TestFullLint:
    def test_lint_returns_all_issue_types(self, wiki_for_lint: dict[str, Path]) -> None:
        report = lint_wiki(wiki_for_lint["wiki"], raw_dir=wiki_for_lint["raw"])

        categories = {i.category for i in report.issues}
        # Should find at least broken links and orphans
        assert "broken_link" in categories
        assert "orphan" in categories

    def test_lint_empty_wiki(self, tmp_path: Path) -> None:
        wiki_dir = tmp_path / "wiki"
        wiki_dir.mkdir()

        report = lint_wiki(wiki_dir)
        # Should find structural issues (missing index.md, etc.)
        assert report.total >= 1
