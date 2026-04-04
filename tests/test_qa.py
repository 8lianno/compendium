"""Tests for Q&A engine, sessions, output rendering, and feedback filing."""

from __future__ import annotations

from typing import TYPE_CHECKING

import frontmatter
import pytest

from compendium.core.wiki_fs import WikiFileSystem
from compendium.llm.provider import CompletionRequest, CompletionResponse, TokenUsage

if TYPE_CHECKING:
    from pathlib import Path


# -- Fake LLM for Q&A --


class FakeQALLM:
    """Fake LLM that returns Q&A-style answers."""

    @property
    def name(self) -> str:
        return "fake"

    @property
    def model_name(self) -> str:
        return "fake-model"

    @property
    def context_window(self) -> int:
        return 200_000

    @property
    def pricing(self):
        from compendium.llm.provider import TokenPricing

        return TokenPricing(input_per_million=3.0, output_per_million=15.0)

    def estimate_tokens(self, text: str) -> int:
        return len(text) // 4

    async def complete(self, request: CompletionRequest) -> CompletionResponse:
        return CompletionResponse(
            content="Based on the wiki, transformers use self-attention mechanisms "
            "[[Transformer Architecture]] to process sequences in parallel "
            "[[Attention Mechanisms]]. This enables significant speedups.",
            usage=TokenUsage(input_tokens=500, output_tokens=100),
            model="fake-model",
        )

    async def test_connection(self) -> bool:
        return True


@pytest.fixture
def wiki_with_articles(tmp_path: Path) -> WikiFileSystem:
    """Create a wiki project with pre-compiled articles."""
    wfs = WikiFileSystem(tmp_path / "project")
    wfs.init_project("Test Wiki")

    # Create INDEX.md
    (wfs.wiki_dir / "INDEX.md").write_text(
        "# Wiki Index\n\n"
        "| Article | Category | Summary |\n"
        "|---------|----------|--------|\n"
        "| [[transformer-architecture|Transformer Architecture]] | concepts | "
        "Core architecture using self-attention |\n"
        "| [[attention-mechanisms|Attention Mechanisms]] | methods | "
        "Scaled dot-product and multi-head attention |\n"
        "| [[bert|BERT]] | concepts | Bidirectional encoder model |\n"
    )

    # Create CONCEPTS.md
    (wfs.wiki_dir / "CONCEPTS.md").write_text(
        "# Concepts\n\n"
        "## Concepts\n"
        "- **Transformer Architecture** — 3 sources\n"
        "- **BERT** — 2 sources\n\n"
        "## Methods\n"
        "- **Attention Mechanisms** — 3 sources\n"
    )

    # Create articles
    concepts_dir = wfs.wiki_dir / "concepts"
    concepts_dir.mkdir()
    methods_dir = wfs.wiki_dir / "methods"
    methods_dir.mkdir()

    (concepts_dir / "transformer-architecture.md").write_text(
        "---\ntitle: Transformer Architecture\ncategory: concepts\n---\n\n"
        "# Transformer Architecture\n\n"
        "The transformer uses self-attention to process sequences.\n"
        "It achieves state-of-the-art results on translation tasks.\n"
    )

    (methods_dir / "attention-mechanisms.md").write_text(
        "---\ntitle: Attention Mechanisms\ncategory: methods\n---\n\n"
        "# Attention Mechanisms\n\n"
        "Scaled dot-product attention computes weights.\n"
        "Multi-head attention enables parallel processing.\n"
    )

    (concepts_dir / "bert.md").write_text(
        "---\ntitle: BERT\ncategory: concepts\n---\n\n"
        "# BERT\n\n"
        "BERT uses bidirectional transformer encoders.\n"
    )

    return wfs


# -- Q&A Engine Tests --


class TestQAEngine:
    @pytest.mark.asyncio
    async def test_ask_basic_question(self, wiki_with_articles: WikiFileSystem) -> None:
        from compendium.llm.prompts import PromptLoader
        from compendium.qa.engine import ask_question

        llm = FakeQALLM()
        loader = PromptLoader()

        result = await ask_question(
            "How do transformers work?",
            wiki_with_articles.wiki_dir,
            llm,
            loader,
        )

        assert "answer" in result
        assert len(result["answer"]) > 0
        assert "sources_used" in result
        assert len(result["sources_used"]) > 0

    @pytest.mark.asyncio
    async def test_ask_empty_wiki(self, tmp_path: Path) -> None:
        from compendium.llm.prompts import PromptLoader
        from compendium.qa.engine import ask_question

        wfs = WikiFileSystem(tmp_path / "empty")
        wfs.init_project("Empty")

        llm = FakeQALLM()
        loader = PromptLoader()

        result = await ask_question("test?", wfs.wiki_dir, llm, loader)
        assert "empty" in result["answer"].lower() or "compile" in result["answer"].lower()

    @pytest.mark.asyncio
    async def test_ask_with_session(self, wiki_with_articles: WikiFileSystem) -> None:
        from compendium.llm.prompts import PromptLoader
        from compendium.qa.engine import ask_question
        from compendium.qa.session import ConversationSession

        llm = FakeQALLM()
        loader = PromptLoader()
        session = ConversationSession("test-session")

        await ask_question(
            "How do transformers work?",
            wiki_with_articles.wiki_dir,
            llm,
            loader,
            session=session,
        )

        assert len(session.messages) == 2  # user + assistant
        assert session.messages[0]["role"] == "user"
        assert session.messages[1]["role"] == "assistant"


# -- Index Parsing Tests --


class TestIndexParsing:
    def test_parse_index(self, wiki_with_articles: WikiFileSystem) -> None:
        from compendium.qa.engine import _parse_index

        entries = _parse_index(wiki_with_articles.wiki_dir / "INDEX.md")
        assert len(entries) == 3
        assert entries[0]["slug"] == "transformer-architecture"
        assert entries[0]["title"] == "Transformer Architecture"

    def test_parse_empty_index(self, tmp_path: Path) -> None:
        from compendium.qa.engine import _parse_index

        entries = _parse_index(tmp_path / "nonexistent.md")
        assert entries == []

    def test_relevance_scoring(self) -> None:
        from compendium.qa.engine import _score_relevance

        score = _score_relevance(
            "transformer architecture attention",
            "Transformer Architecture",
            "Core architecture using self-attention",
        )
        assert score > 0.5

        score_low = _score_relevance(
            "reinforcement learning policy",
            "Transformer Architecture",
            "Core architecture using self-attention",
        )
        assert score_low < score


# -- Session Tests --


class TestConversationSession:
    def test_add_messages(self) -> None:
        from compendium.qa.session import ConversationSession

        session = ConversationSession("test")
        session.add_message("user", "Hello")
        session.add_message("assistant", "Hi there")

        assert len(session.messages) == 2
        assert session.messages[0]["role"] == "user"
        assert session.messages[1]["role"] == "assistant"

    def test_max_turns(self) -> None:
        from compendium.qa.session import ConversationSession

        session = ConversationSession("test")
        for i in range(50):
            session.add_message("user", f"msg {i}")

        assert len(session.messages) <= ConversationSession.MAX_TURNS * 2

    def test_persistence(self, tmp_path: Path) -> None:
        from compendium.qa.session import ConversationSession

        session = ConversationSession("persist-test", storage_dir=tmp_path)
        session.add_message("user", "Hello")
        session.add_message("assistant", "Hi")

        # Load from disk
        loaded = ConversationSession.load("persist-test", tmp_path)
        assert len(loaded.messages) == 2
        assert loaded.messages[0]["content"] == "Hello"

    def test_list_sessions(self, tmp_path: Path) -> None:
        from compendium.qa.session import ConversationSession

        s1 = ConversationSession("session-1", storage_dir=tmp_path)
        s1.add_message("user", "test")
        s2 = ConversationSession("session-2", storage_dir=tmp_path)
        s2.add_message("user", "test")

        sessions = ConversationSession.list_sessions(tmp_path)
        assert len(sessions) == 2

    def test_clear(self) -> None:
        from compendium.qa.session import ConversationSession

        session = ConversationSession("test")
        session.add_message("user", "Hello")
        session.clear()
        assert len(session.messages) == 0


# -- Output Rendering Tests --


class TestOutputRendering:
    def test_render_report(self, tmp_path: Path) -> None:
        from compendium.qa.output import render_report

        path = render_report(
            query="How do transformers work?",
            answer="Transformers use self-attention...",
            sources_used=["Transformer Architecture", "Attention Mechanisms"],
            tokens_used=500,
            output_dir=tmp_path,
        )

        assert path.exists()
        assert path.suffix == ".md"
        post = frontmatter.load(str(path))
        assert post.metadata["type"] == "report"
        assert post.metadata["query"] == "How do transformers work?"
        assert len(post.metadata["sources_used"]) == 2

    def test_render_slides(self, tmp_path: Path) -> None:
        from compendium.qa.output import render_slides

        answer = (
            "## Overview\nTransformers are powerful.\n\n"
            "## Architecture\nThey use self-attention.\n\n"
            "## Results\nState of the art performance.\n"
        )

        path = render_slides(
            query="Explain transformers",
            answer=answer,
            sources_used=["Source A"],
            output_dir=tmp_path,
            slide_count=5,
        )

        assert path.exists()
        content = path.read_text()
        assert "marp: true" in content
        assert "---" in content  # Slide separators
        assert "Sources" in content


# -- Feedback Filing Tests --


class TestFeedbackFiling:
    def test_file_report_to_wiki(self, wiki_with_articles: WikiFileSystem) -> None:
        from compendium.qa.filing import file_to_wiki
        from compendium.qa.output import render_report

        # Create a report
        report_path = render_report(
            query="Compare BERT and GPT",
            answer="BERT is bidirectional while GPT is unidirectional...",
            sources_used=["BERT", "Transformer Architecture"],
            tokens_used=300,
            output_dir=wiki_with_articles.output_dir,
        )

        result = file_to_wiki(report_path, wiki_with_articles)
        assert result["status"] == "filed"
        assert "filed_path" in result

        # Verify the file exists in wiki
        filed = __import__("pathlib").Path(result["filed_path"])
        assert filed.exists()
        post = frontmatter.load(str(filed))
        assert post.metadata["origin"] == "qa-output"

    def test_file_nonexistent(self, wiki_with_articles: WikiFileSystem) -> None:
        from compendium.qa.filing import file_to_wiki

        fake_path = wiki_with_articles.root / "nonexistent.md"
        result = file_to_wiki(fake_path, wiki_with_articles)
        assert result["status"] == "error"

    def test_category_detection(self, wiki_with_articles: WikiFileSystem) -> None:
        from compendium.qa.filing import _detect_category

        concepts_path = wiki_with_articles.wiki_dir / "CONCEPTS.md"

        # Content mentioning transformers should match "concepts" category
        category = _detect_category(
            "The transformer architecture uses attention.",
            concepts_path,
        )
        assert category in ("concepts", "methods")

    def test_index_updated_after_filing(self, wiki_with_articles: WikiFileSystem) -> None:
        from compendium.qa.filing import file_to_wiki
        from compendium.qa.output import render_report

        report = render_report(
            query="New analysis",
            answer="Analysis content...",
            sources_used=[],
            tokens_used=100,
            output_dir=wiki_with_articles.output_dir,
        )

        file_to_wiki(report, wiki_with_articles)

        index = (wiki_with_articles.wiki_dir / "INDEX.md").read_text()
        assert "new-analysis" in index.lower() or "New analysis" in index
