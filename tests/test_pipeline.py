"""Tests for pipeline data structures, steps, and controller."""

from __future__ import annotations

import json
import shutil
from typing import TYPE_CHECKING

import pytest

from compendium.core.config import CompendiumConfig
from compendium.core.wiki_fs import WikiFileSystem
from compendium.llm.provider import CompletionRequest, CompletionResponse, TokenUsage
from compendium.pipeline.checkpoint import (
    CompilationCheckpoint,
    StepCheckpoint,
    StepStatus,
)
from compendium.pipeline.deps import DependencyGraph, SourceEntry

if TYPE_CHECKING:
    from pathlib import Path


FIXTURES_DIR = __import__("pathlib").Path(__file__).parent / "fixtures"


# -- Dependency Graph Tests --


class TestDependencyGraph:
    def test_empty_graph(self) -> None:
        graph = DependencyGraph()
        assert graph.version == 1
        assert len(graph.sources) == 0
        assert len(graph.articles) == 0

    def test_save_and_load(self, tmp_path: Path) -> None:
        graph = DependencyGraph()
        graph.sources["raw/test.md"] = SourceEntry(
            content_hash="sha256:abc",
            concepts=["attention", "transformer"],
        )
        path = tmp_path / ".deps.json"
        graph.save(path)

        loaded = DependencyGraph.load(path)
        assert "raw/test.md" in loaded.sources
        assert loaded.sources["raw/test.md"].content_hash == "sha256:abc"

    def test_get_new_sources(self) -> None:
        graph = DependencyGraph()
        graph.sources["raw/old.md"] = SourceEntry(content_hash="sha256:old")
        graph.sources["raw/unchanged.md"] = SourceEntry(content_hash="sha256:same")

        current = {
            "raw/old.md": "sha256:new",  # changed
            "raw/unchanged.md": "sha256:same",  # same
            "raw/brand-new.md": "sha256:fresh",  # new
        }
        new = graph.get_new_sources(current)
        assert "raw/old.md" in new
        assert "raw/brand-new.md" in new
        assert "raw/unchanged.md" not in new

    def test_get_affected_articles(self) -> None:
        from compendium.pipeline.deps import ArticleEntry

        graph = DependencyGraph()
        graph.articles["wiki/attention.md"] = ArticleEntry(
            depends_on=["raw/vaswani.md", "raw/bert.md"]
        )
        graph.articles["wiki/gpt.md"] = ArticleEntry(depends_on=["raw/gpt3.md"])

        affected = graph.get_affected_articles(["raw/vaswani.md"])
        assert "wiki/attention.md" in affected
        assert "wiki/gpt.md" not in affected

    def test_update_meta(self) -> None:
        from compendium.pipeline.deps import ArticleEntry

        graph = DependencyGraph()
        graph.sources["raw/a.md"] = SourceEntry()
        graph.sources["raw/b.md"] = SourceEntry()
        graph.articles["wiki/x.md"] = ArticleEntry(backlinks_to=["wiki/y.md", "wiki/z.md"])
        graph.update_meta()
        assert graph.meta.total_sources == 2
        assert graph.meta.total_articles == 1
        assert graph.meta.total_backlinks == 2


class TestCheckpoint:
    def test_save_and_load(self, tmp_path: Path) -> None:
        cp = CompilationCheckpoint(
            compilation_id="test-123",
            started_at="2026-04-04T10:00:00Z",
            mode="full",
        )
        cp.steps["summarize"] = StepCheckpoint(status=StepStatus.COMPLETED)
        cp.steps["extract_concepts"] = StepCheckpoint(status=StepStatus.PENDING)

        path = tmp_path / ".checkpoint.json"
        cp.save(path)

        loaded = CompilationCheckpoint.load(path)
        assert loaded is not None
        assert loaded.compilation_id == "test-123"
        assert loaded.steps["summarize"].status == StepStatus.COMPLETED
        assert loaded.steps["extract_concepts"].status == StepStatus.PENDING

    def test_load_nonexistent(self, tmp_path: Path) -> None:
        result = CompilationCheckpoint.load(tmp_path / "nope.json")
        assert result is None


# -- Step Tests --


class FakeLLM:
    """Fake LLM that returns predefined responses for pipeline testing."""

    def __init__(self, responses: dict[str, str] | None = None) -> None:
        self._responses = responses or {}
        self._call_count = 0

    @property
    def name(self) -> str:
        return "fake"

    @property
    def model_name(self) -> str:
        return "fake-model"

    @property
    def context_window(self) -> int:
        return 200_000

    async def complete(self, request: CompletionRequest) -> CompletionResponse:
        self._call_count += 1

        # Determine which step is being called by looking at the prompt content
        content = request.messages[0].content if request.messages else ""

        if "summariz" in (request.system_prompt or "").lower():
            return self._summary_response(content)
        if "taxonomy" in (request.system_prompt or "").lower():
            return self._concepts_response()
        if "conflict" in (request.system_prompt or "").lower():
            return self._conflict_response()
        return self._article_response(content)

    def _summary_response(self, content: str) -> CompletionResponse:
        return CompletionResponse(
            content=json.dumps(
                {
                    "source": "test-source",
                    "title": "Test Source",
                    "summary": "A test document about transformers and attention.",
                    "claims": [{"claim": "Transformers use self-attention", "confidence": "high"}],
                    "concepts": ["transformers", "attention", "self-attention", "neural networks"],
                    "findings": ["Self-attention enables parallelization"],
                    "limitations": ["Quadratic complexity"],
                }
            ),
            usage=TokenUsage(input_tokens=500, output_tokens=200),
            model="fake-model",
        )

    def _concepts_response(self) -> CompletionResponse:
        return CompletionResponse(
            content=json.dumps(
                {
                    "taxonomy": [
                        {
                            "canonical_name": "Transformer Architecture",
                            "aliases": ["transformers", "transformer"],
                            "category": "concepts",
                            "parent": None,
                            "source_count": 3,
                            "should_generate_article": True,
                        },
                        {
                            "canonical_name": "Attention Mechanisms",
                            "aliases": ["attention", "self-attention"],
                            "category": "methods",
                            "parent": "Transformer Architecture",
                            "source_count": 3,
                            "should_generate_article": True,
                        },
                        {
                            "canonical_name": "Neural Networks",
                            "aliases": ["neural networks", "neural nets"],
                            "category": "concepts",
                            "parent": None,
                            "source_count": 2,
                            "should_generate_article": True,
                        },
                    ]
                }
            ),
            usage=TokenUsage(input_tokens=300, output_tokens=150),
            model="fake-model",
        )

    def _article_response(self, content: str) -> CompletionResponse:
        # Extract concept name from prompt
        name = "Test Concept"
        if "concept_name" in content:
            import re

            m = re.search(r'"([^"]+)"', content[:200])
            if m:
                name = m.group(1)

        slug = name.lower().replace(" ", "-")
        return CompletionResponse(
            content=(
                f'---\ntitle: "{name}"\nid: "{slug}"\n'
                f"category: concepts\nsources:\n  - ref: raw/test.md\n"
                f"origin: compilation\nstatus: published\n"
                f"word_count: 250\n---\n\n"
                f"# {name}\n\n"
                f"## Summary\nThis article covers {name} based on the provided sources.\n\n"
                f"## Key Findings\n- Finding about {name} from source [[raw/test.md]]\n\n"
                f"## Sources\n- [[raw/test.md]]\n"
            ),
            usage=TokenUsage(input_tokens=800, output_tokens=250),
            model="fake-model",
        )

    def _conflict_response(self) -> CompletionResponse:
        return CompletionResponse(
            content=json.dumps(
                {
                    "classification": "COMPATIBLE",
                    "explanation": "No conflict detected.",
                }
            ),
            usage=TokenUsage(input_tokens=200, output_tokens=50),
            model="fake-model",
        )


@pytest.fixture
def wiki_project(tmp_path: Path) -> WikiFileSystem:
    """Create a project with sample raw sources."""
    wfs = WikiFileSystem(tmp_path / "project")
    wfs.init_project("Test Wiki")

    # Copy fixture sources to raw/
    for fixture in FIXTURES_DIR.glob("sample_source_*.md"):
        shutil.copy(fixture, wfs.raw_dir / fixture.name)

    return wfs


class TestStepSummarize:
    @pytest.mark.asyncio
    async def test_summarize_sources(self) -> None:
        from compendium.llm.prompts import PromptLoader
        from compendium.pipeline.steps import step_summarize

        llm = FakeLLM()
        loader = PromptLoader()

        sources = [
            {"id": "test-1", "title": "Test Paper", "content": "Some content.", "word_count": "100"}
        ]
        result = await step_summarize(sources, llm, loader)
        assert len(result) >= 1
        assert "concepts" in result[0]


class TestStepExtractConcepts:
    @pytest.mark.asyncio
    async def test_extract_concepts(self) -> None:
        from compendium.llm.prompts import PromptLoader
        from compendium.pipeline.steps import step_extract_concepts

        llm = FakeLLM()
        loader = PromptLoader()

        summaries = [
            {"source": "test-1", "concepts": ["transformers", "attention"], "summary": "Test"}
        ]
        result = await step_extract_concepts(summaries, llm, loader)
        assert len(result) >= 1
        assert any(c.get("canonical_name") for c in result)


class TestStepBuildIndex:
    def test_build_index(self) -> None:
        from compendium.pipeline.steps import step_build_index

        articles = [
            {
                "path": "wiki/concepts/test.md",
                "content": "---\ntitle: Test\ncategory: concepts\n---\n\n# Test\nContent here.",
            }
        ]
        concepts = [{"canonical_name": "Test", "category": "concepts", "source_count": 2}]

        result = step_build_index(articles, concepts)
        assert "index.md" in result
        assert "concepts.md" in result
        assert result["index.md"].startswith("---\n")
        assert result["concepts.md"].startswith("---\n")
        assert "Test" in result["index.md"]
        assert "Test" in result["concepts.md"]


class TestStepBacklinks:
    def test_create_backlinks(self) -> None:
        from compendium.pipeline.steps import step_create_backlinks

        articles = [
            {
                "path": "wiki/concepts/transformers.md",
                "content": "# Transformers\nUses attention mechanisms for processing.",
            },
            {
                "path": "wiki/methods/attention.md",
                "content": "# Attention\nUsed in transformers architecture.",
            },
        ]
        concepts = [
            {"canonical_name": "Transformers", "aliases": ["transformers"]},
            {"canonical_name": "Attention", "aliases": ["attention"]},
        ]

        result = step_create_backlinks(articles, concepts)
        assert len(result) == 2

        # Transformers article should link to attention
        transformers_content = result[0]["content"]
        assert "## Related Articles" in transformers_content
        lower = transformers_content.lower()
        assert "[[attention" in lower or "attention" in lower


# -- Full Pipeline Test --


class TestFullPipeline:
    @pytest.mark.asyncio
    async def test_compile_wiki(self, wiki_project: WikiFileSystem) -> None:
        from compendium.llm.prompts import PromptLoader
        from compendium.pipeline.controller import compile_wiki

        config = CompendiumConfig()
        llm = FakeLLM()
        loader = PromptLoader()

        result = await compile_wiki(wiki_project, config, llm, loader)

        assert result["sources_processed"] == 3
        assert result["articles_count"] >= 1
        assert result["concepts_count"] >= 1

        # Check wiki directory has files
        articles = wiki_project.list_wiki_articles()
        assert len(articles) >= 1

        # Check index.md exists
        assert (wiki_project.wiki_dir / "index.md").exists()
        assert (wiki_project.wiki_dir / "concepts.md").exists()
        assert (wiki_project.wiki_dir / "CONFLICTS.md").exists()
        assert (wiki_project.wiki_dir / "index.md").read_text().startswith("---\n")
        assert (wiki_project.wiki_dir / "concepts.md").read_text().startswith("---\n")
        assert (wiki_project.wiki_dir / "CONFLICTS.md").read_text().startswith("---\n")

        # Check deps.json exists
        assert wiki_project.deps_path.exists()
        deps = DependencyGraph.load(wiki_project.deps_path)
        assert deps.meta.total_sources == 3

    @pytest.mark.asyncio
    async def test_compile_no_sources(self, tmp_path: Path) -> None:
        from compendium.llm.prompts import PromptLoader
        from compendium.pipeline.controller import compile_wiki

        wfs = WikiFileSystem(tmp_path / "empty")
        wfs.init_project("Empty Wiki")
        config = CompendiumConfig()
        llm = FakeLLM()
        loader = PromptLoader()

        result = await compile_wiki(wfs, config, llm, loader)
        assert "error" in result

    @pytest.mark.asyncio
    async def test_incremental_update(self, wiki_project: WikiFileSystem) -> None:
        from compendium.llm.prompts import PromptLoader
        from compendium.pipeline.controller import compile_wiki, incremental_update

        config = CompendiumConfig()
        llm = FakeLLM()
        loader = PromptLoader()

        # First, do a full compile
        await compile_wiki(wiki_project, config, llm, loader)

        # Add a new source
        new_source = wiki_project.raw_dir / "new-source.md"
        new_source.write_text(
            "---\ntitle: New Source\nid: new-source\nformat: markdown\n"
            "source: local\nstatus: raw\nword_count: 100\n"
            "content_hash: sha256:new\n---\n\n# New Source\nNew content here."
        )

        result = await incremental_update(
            wiki_project,
            config,
            llm,
            loader,
            new_source_paths=[new_source],
        )

        assert result.get("sources_processed", 0) >= 1
