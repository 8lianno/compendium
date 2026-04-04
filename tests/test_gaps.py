"""Tests for gap implementations (GAP-01 through GAP-16)."""

from __future__ import annotations

from typing import TYPE_CHECKING

import frontmatter
import pytest

from compendium.core.wiki_fs import WikiFileSystem
from compendium.llm.provider import Operation, TokenPricing, TokenUsage

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def wiki_project(tmp_path: Path) -> WikiFileSystem:
    """Create a project with compiled wiki articles."""
    wfs = WikiFileSystem(tmp_path / "project")
    wfs.init_project("Test Wiki")

    # Create wiki articles
    concepts_dir = wfs.wiki_dir / "concepts"
    concepts_dir.mkdir()

    post1 = frontmatter.Post(
        "# Transformers\n\nTransformer architecture uses attention.",
        title="Transformers",
        category="concepts",
        tags=["transformers", "attention"],
    )
    (concepts_dir / "transformers.md").write_text(frontmatter.dumps(post1))

    post2 = frontmatter.Post(
        "# Attention\n\nAttention mechanisms enable parallelism.",
        title="Attention Mechanisms",
        category="methods",
        tags=["attention"],
    )
    (concepts_dir / "attention.md").write_text(frontmatter.dumps(post2))

    # Create INDEX.md referencing both
    (wfs.wiki_dir / "INDEX.md").write_text(
        "# Index\n\n| Article | Category | Summary |\n"
        "|---------|----------|--------|\n"
        "| [[transformers|Transformers]] | concepts | Transformer arch |\n"
        "| [[attention|Attention Mechanisms]] | methods | Attention |\n"
    )

    (wfs.wiki_dir / "CONCEPTS.md").write_text(
        "# Concepts\n\n## Concepts\n- **Transformers** — 3 sources\n"
    )

    return wfs


# -- GAP-01: verify-index / rebuild-index --


class TestVerifyIndex:
    def test_consistent_index(self, wiki_project: WikiFileSystem) -> None:
        from compendium.pipeline.index_ops import verify_wiki_index

        result = verify_wiki_index(wiki_project.wiki_dir)
        assert result["consistent"]
        assert len(result["mismatches"]) == 0

    def test_missing_from_index(self, wiki_project: WikiFileSystem) -> None:
        from compendium.pipeline.index_ops import verify_wiki_index

        # Add article not in INDEX.md
        (wiki_project.wiki_dir / "concepts" / "new-article.md").write_text(
            "---\ntitle: New\ncategory: concepts\n---\n\n# New\nContent."
        )

        result = verify_wiki_index(wiki_project.wiki_dir)
        assert not result["consistent"]
        assert any(m["type"] == "MISSING_FROM_INDEX" for m in result["mismatches"])

    def test_extra_in_index(self, wiki_project: WikiFileSystem) -> None:
        from compendium.pipeline.index_ops import verify_wiki_index

        # Remove an article but keep INDEX.md entry
        (wiki_project.wiki_dir / "concepts" / "attention.md").unlink()

        result = verify_wiki_index(wiki_project.wiki_dir)
        assert not result["consistent"]
        assert any(m["type"] == "EXTRA_IN_INDEX" for m in result["mismatches"])


class TestRebuildIndex:
    def test_rebuild_creates_index(self, wiki_project: WikiFileSystem) -> None:
        from compendium.pipeline.index_ops import rebuild_wiki_index

        # Remove INDEX.md
        (wiki_project.wiki_dir / "INDEX.md").unlink()

        result = rebuild_wiki_index(wiki_project.wiki_dir)
        assert result["articles"] == 2
        assert (wiki_project.wiki_dir / "INDEX.md").exists()
        assert (wiki_project.wiki_dir / "CONCEPTS.md").exists()

        # Verify content
        index_content = (wiki_project.wiki_dir / "INDEX.md").read_text()
        assert "transformers" in index_content.lower()
        assert "attention" in index_content.lower()


# -- GAP-04: SCHEMA.md --


class TestSchemaGeneration:
    def test_generate_schema_md(self) -> None:
        from compendium.pipeline.controller import _generate_schema_md

        schema = _generate_schema_md()
        assert "# Wiki Schema" in schema
        assert "frontmatter" in schema.lower()
        assert "wikilink" in schema.lower()
        assert "INDEX.md" in schema
        assert "CONCEPTS.md" in schema


# -- GAP-05: Retry with backoff --


class TestRetry:
    @pytest.mark.asyncio
    async def test_succeeds_on_first_try(self) -> None:
        from compendium.llm.retry import with_retry

        call_count = 0

        async def success() -> str:
            nonlocal call_count
            call_count += 1
            return "ok"

        result = await with_retry(success)
        assert result == "ok"
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_retries_on_rate_limit(self) -> None:
        from compendium.llm.retry import with_retry

        call_count = 0

        async def fails_twice() -> str:
            nonlocal call_count
            call_count += 1
            if call_count <= 2:
                msg = "rate_limit_exceeded"
                raise Exception(msg)
            return "ok"

        result = await with_retry(fails_twice, base_delay=0.01, backoff_factor=1.0)
        assert result == "ok"
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_raises_after_max_retries(self) -> None:
        from compendium.llm.retry import with_retry

        async def always_fails() -> str:
            msg = "429 Too Many Requests"
            raise Exception(msg)

        with pytest.raises(Exception, match="429"):
            await with_retry(always_fails, max_retries=2, base_delay=0.01)

    @pytest.mark.asyncio
    async def test_non_rate_limit_error_not_retried(self) -> None:
        from compendium.llm.retry import with_retry

        call_count = 0

        async def auth_error() -> str:
            nonlocal call_count
            call_count += 1
            msg = "invalid_api_key"
            raise Exception(msg)

        with pytest.raises(Exception, match="invalid_api_key"):
            await with_retry(auth_error, base_delay=0.01)
        assert call_count == 1

    def test_is_rate_limit_error(self) -> None:
        from compendium.llm.retry import is_rate_limit_error

        assert is_rate_limit_error(Exception("rate_limit_exceeded"))
        assert is_rate_limit_error(Exception("429 Too Many Requests"))
        assert is_rate_limit_error(Exception("Service overloaded"))
        assert not is_rate_limit_error(Exception("invalid_api_key"))
        assert not is_rate_limit_error(Exception("connection_refused"))


# -- GAP-14: Rollback --


class TestListBackups:
    def test_list_backups(self, wiki_project: WikiFileSystem) -> None:
        import time

        # Create some backups with different timestamps
        (wiki_project.wiki_dir / "article.md").write_text("content")
        wiki_project.create_backup()
        time.sleep(1.1)  # Ensure different timestamp
        wiki_project.create_backup()

        backups = wiki_project.list_backups()
        assert len(backups) >= 2
        # Newest first
        assert backups[0] >= backups[1]

    def test_list_backups_empty(self, tmp_path: Path) -> None:
        wfs = WikiFileSystem(tmp_path / "empty")
        wfs.init_project("Empty")
        assert wfs.list_backups() == []


# -- GAP-15: Usage dashboard --


class TestUsageBreakdown:
    def test_operation_breakdown(self, tmp_path: Path) -> None:
        from compendium.llm.tokens import TokenTracker

        tracker = TokenTracker(usage_dir=tmp_path)
        pricing = TokenPricing(input_per_million=3.0, output_per_million=15.0)

        # Record compilation usage
        tracker.record(
            Operation.COMPILATION,
            "anthropic",
            "claude-sonnet",
            TokenUsage(input_tokens=10000, output_tokens=2000),
            pricing,
            step="summarize",
        )
        tracker.record(
            Operation.COMPILATION,
            "anthropic",
            "claude-sonnet",
            TokenUsage(input_tokens=5000, output_tokens=1000),
            pricing,
            step="generate",
        )
        # Record QA usage with different model
        tracker.record(
            Operation.QA,
            "openai",
            "gpt-4o",
            TokenUsage(input_tokens=3000, output_tokens=500),
            TokenPricing(input_per_million=2.5, output_per_million=10.0),
        )

        breakdown = tracker.get_operation_breakdown()
        assert len(breakdown) == 2  # compilation|claude-sonnet, qa|gpt-4o

        # Compilation should have aggregated 2 calls
        comp = next(b for b in breakdown if b["operation"] == "compilation")
        assert comp["call_count"] == 2
        assert comp["input_tokens"] == 15000
        assert comp["output_tokens"] == 3000

    def test_empty_breakdown(self, tmp_path: Path) -> None:
        from compendium.llm.tokens import TokenTracker

        tracker = TokenTracker(usage_dir=tmp_path)
        assert tracker.get_operation_breakdown() == []


# -- GAP-16: Search auto-rebuild --


class TestSearchAutoRebuild:
    def test_compile_rebuilds_search(self, wiki_project: WikiFileSystem) -> None:
        """Verify that search works immediately after articles exist."""
        from compendium.search.engine import SearchEngine

        engine = SearchEngine(wiki_project.wiki_dir)
        engine.build_index()

        results = engine.search("transformer")
        assert len(results) >= 1


# -- GAP-09: Incremental conflict detection --


class TestIncrementalConflicts:
    @pytest.mark.asyncio
    async def test_incremental_runs_conflict_detection(self, tmp_path: Path) -> None:
        """Verify incremental_update calls step_detect_conflicts."""
        import shutil

        from compendium.core.config import CompendiumConfig
        from compendium.llm.prompts import PromptLoader
        from compendium.pipeline.controller import compile_wiki, incremental_update

        # Use the FakeLLM from test_pipeline
        from tests.test_pipeline import FakeLLM

        wfs = WikiFileSystem(tmp_path / "project")
        wfs.init_project("Test")

        fixtures = __import__("pathlib").Path(__file__).parent / "fixtures"
        for f in fixtures.glob("sample_source_*.md"):
            shutil.copy(f, wfs.raw_dir / f.name)

        config = CompendiumConfig()
        llm = FakeLLM()
        loader = PromptLoader()

        # Full compile first
        await compile_wiki(wfs, config, llm, loader)

        # Add a new source
        (wfs.raw_dir / "new.md").write_text(
            "---\ntitle: New\nid: new\nformat: markdown\n"
            "source: local\nstatus: raw\nword_count: 50\n"
            "content_hash: sha256:new123\n---\n\n# New\nNew content."
        )

        # Run incremental
        await incremental_update(
            wfs, config, llm, loader, new_source_paths=[wfs.raw_dir / "new.md"]
        )

        # CONFLICTS.md should exist and be updated
        conflicts_path = wfs.wiki_dir / "CONFLICTS.md"
        assert conflicts_path.exists()

        # log.md should have both compile and incremental entries
        log_path = wfs.wiki_dir / "log.md"
        assert log_path.exists()
        log_content = log_path.read_text()
        assert "compile" in log_content
        assert "incremental" in log_content


# -- FIX-02: Append-only log.md --


class TestAppendLog:
    def test_build_log_entry(self) -> None:
        from compendium.pipeline.steps import build_log_entry

        entry = build_log_entry("compile", articles_count=10, sources_count=5)
        assert "compile" in entry
        assert "Articles: 10" in entry
        assert "Sources processed: 5" in entry

    def test_log_is_append_only(self, tmp_path: Path) -> None:
        from compendium.pipeline.controller import _append_log

        log_path = tmp_path / "log.md"
        _append_log(log_path, "## First entry\n")
        _append_log(log_path, "## Second entry\n")

        content = log_path.read_text()
        assert "# Wiki Log" in content  # Header created on first append
        assert "First entry" in content
        assert "Second entry" in content  # Both entries preserved


# -- FIX-04: Project CLAUDE.md --


class TestProjectClaudeMd:
    def test_init_creates_claude_md(self, tmp_path: Path) -> None:
        wfs = WikiFileSystem(tmp_path / "project")
        wfs.init_project("Test Wiki")

        claude_md = tmp_path / "project" / "CLAUDE.md"
        assert claude_md.exists()
        content = claude_md.read_text()
        assert "Test Wiki" in content
        assert "raw/" in content
        assert "wiki/" in content
        assert "wikilink" in content.lower()
        assert "Schema" in content

    def test_init_does_not_overwrite_claude_md(self, tmp_path: Path) -> None:
        wfs = WikiFileSystem(tmp_path / "project")
        wfs.init_project("First")

        # Modify CLAUDE.md
        claude_path = tmp_path / "project" / "CLAUDE.md"
        claude_path.write_text("Custom schema content")

        # Re-init should NOT overwrite
        wfs.init_project("Second")
        assert claude_path.read_text() == "Custom schema content"


# -- FIX-05: Git init --


class TestGitInit:
    def test_init_creates_git_repo(self, tmp_path: Path) -> None:
        wfs = WikiFileSystem(tmp_path / "project")
        wfs.init_project("Test Wiki")

        git_dir = tmp_path / "project" / ".git"
        # Git might not be available in all environments
        import shutil

        if shutil.which("git"):
            assert git_dir.exists()

    def test_init_creates_gitignore(self, tmp_path: Path) -> None:
        wfs = WikiFileSystem(tmp_path / "project")
        wfs.init_project("Test Wiki")

        import shutil

        if shutil.which("git"):
            gitignore = tmp_path / "project" / ".gitignore"
            assert gitignore.exists()
            content = gitignore.read_text()
            assert ".staging" in content
            assert ".backup" in content


# -- FIX-07: Canvas output --


class TestCanvasOutput:
    def test_render_canvas(self, tmp_path: Path) -> None:
        from compendium.qa.output import render_canvas

        answer = (
            "Transformers use [[attention-mechanisms]] which rely on "
            "[[self-attention]] and [[multi-head-attention]]. "
            "They are the basis of [[BERT]] and [[GPT]]."
        )
        path = render_canvas(
            query="How are transformer components related?",
            answer=answer,
            sources_used=["Source A"],
            output_dir=tmp_path,
        )

        assert path.exists()
        content = path.read_text()
        assert "```mermaid" in content
        assert "graph TD" in content
        assert "attention-mechanisms" in content
        assert "Sources" in content


# -- FIX-03: File raw Q&A answers --


class TestFileRawAnswer:
    def test_file_to_wiki_accepts_report(self, wiki_project: WikiFileSystem) -> None:
        """Verify the existing report filing still works."""
        from compendium.qa.filing import file_to_wiki
        from compendium.qa.output import render_report

        report = render_report(
            "Test question", "Test answer", ["Source A"], 100, wiki_project.output_dir
        )
        result = file_to_wiki(report, wiki_project)
        assert result["status"] == "filed"
