"""Q&A engine — index-first retrieval, context assembly, cited answers."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

    from compendium.llm.prompts import PromptLoader
    from compendium.llm.provider import LlmProvider
    from compendium.qa.session import ConversationSession


def _score_relevance(query: str, title: str, summary: str) -> float:
    """Simple keyword overlap relevance scoring."""
    query_terms = set(re.findall(r"\w+", query.lower()))
    doc_terms = set(re.findall(r"\w+", (title + " " + summary).lower()))
    if not query_terms:
        return 0.0
    overlap = query_terms & doc_terms
    return len(overlap) / len(query_terms)


def _parse_index(index_path: Path) -> list[dict[str, str]]:
    """Parse INDEX.md into a list of article entries."""
    if not index_path.exists():
        return []

    content = index_path.read_text()
    entries: list[dict[str, str]] = []

    for line in content.split("\n"):
        # Parse table rows containing wikilinks
        if not line.startswith("|") or "[[" not in line:
            continue

        # Extract wikilink first (before splitting by |, which conflicts with display syntax)
        link_match = re.search(r"\[\[([^\]|]+?)(?:\|([^\]]+?))?\]\]", line)
        if not link_match:
            continue

        slug = link_match.group(1).strip()
        title = (link_match.group(2) or slug).strip()

        # Extract remaining cells after the wikilink
        # Remove the wikilink portion, then split the rest by |
        after_link = line[line.index("]]") + 2 :]
        remaining_cells = [c.strip() for c in after_link.split("|") if c.strip()]

        page_type = remaining_cells[0] if remaining_cells else ""
        summary = remaining_cells[1] if len(remaining_cells) > 1 else ""
        entries.append(
            {
                "slug": slug,
                "title": title,
                "category": page_type,
                "type": page_type,
                "summary": summary,
            }
        )

    return entries


def _find_article_file(slug: str, wiki_dir: Path) -> Path | None:
    """Find an article file by slug, searching all subdirectories."""
    # Try direct match
    for md_file in wiki_dir.rglob("*.md"):
        if md_file.stem == slug:
            return md_file
    return None


async def ask_question(
    question: str,
    wiki_dir: Path,
    llm: LlmProvider,
    prompt_loader: PromptLoader,
    session: ConversationSession | None = None,
    max_articles: int = 10,
    context_budget_pct: float = 0.8,
) -> dict:
    """Ask a question against the wiki and get a cited answer.

    Args:
        question: The user's question
        wiki_dir: Path to the wiki directory
        llm: LLM provider for generating the answer
        prompt_loader: Prompt template loader
        session: Optional conversation session for follow-ups
        max_articles: Maximum articles to load into context
        context_budget_pct: Fraction of context window to use

    Returns:
        Dict with: answer, sources_used, tokens_used
    """
    from compendium.llm.provider import CompletionRequest, Message

    index_path = wiki_dir / "INDEX.md"
    index_entries = _parse_index(index_path)

    if not index_entries:
        return {
            "answer": "Your knowledge base is empty. "
            "Compile sources first with `compendium compile`.",
            "sources_used": [],
            "tokens_used": 0,
        }

    # Score and rank articles by relevance
    scored = []
    for entry in index_entries:
        score = _score_relevance(question, entry["title"], entry["summary"])
        scored.append((score, entry))

    scored.sort(key=lambda x: -x[0])

    # Load top-N relevant articles
    token_budget = int(llm.context_window * context_budget_pct)
    loaded_articles: list[dict[str, str]] = []
    total_tokens = 0

    for score, entry in scored[:max_articles]:
        if score <= 0 and loaded_articles:
            break  # Stop if no keyword overlap and we have some articles

        article_path = _find_article_file(entry["slug"], wiki_dir)
        if article_path is None:
            continue

        content = article_path.read_text()
        estimated_tokens = llm.estimate_tokens(content)

        if total_tokens + estimated_tokens > token_budget:
            break

        loaded_articles.append(
            {
                "title": entry["title"],
                "slug": entry["slug"],
                "content": content,
            }
        )
        total_tokens += estimated_tokens

    # If no articles scored, load a few anyway for broad questions
    if not loaded_articles and scored:
        for _, entry in scored[:3]:
            article_path = _find_article_file(entry["slug"], wiki_dir)
            if article_path:
                loaded_articles.append(
                    {
                        "title": entry["title"],
                        "slug": entry["slug"],
                        "content": article_path.read_text(),
                    }
                )

    if not loaded_articles:
        return {
            "answer": "I don't have information about this in your knowledge base. "
            "Would you like to add sources about this topic?",
            "sources_used": [],
            "tokens_used": 0,
        }

    # Build prompt
    index_content = index_path.read_text() if index_path.exists() else "No index available."
    articles_text = ""
    for a in loaded_articles:
        articles_text += f"\n---\n### {a['title']}\n{a['content']}\n"

    conversation_history = ""
    if session and session.messages:
        history_lines = []
        for msg in session.messages[-10:]:  # Last 10 messages
            role = "User" if msg["role"] == "user" else "Assistant"
            history_lines.append(f"{role}: {msg['content'][:500]}")
        conversation_history = "\n".join(history_lines)

    template = prompt_loader.load("qa_answer")
    prompt = template.render(
        question=question,
        index_content=index_content[:2000],
        articles_content=articles_text,
        conversation_history=conversation_history or "No prior conversation.",
    )

    response = await llm.complete(
        CompletionRequest(
            messages=[Message(role="user", content=prompt)],
            system_prompt="You are a research assistant. Answer from the provided wiki only. "
            "Cite sources with [[Article Name]] wikilinks.",
            max_tokens=4000,
            temperature=0.3,
        )
    )

    # Track in session
    if session:
        session.add_message("user", question)
        session.add_message("assistant", response.content)

    sources_used = [a["title"] for a in loaded_articles]

    return {
        "answer": response.content,
        "sources_used": sources_used,
        "tokens_used": response.usage.input_tokens + response.usage.output_tokens,
        "articles_loaded": len(loaded_articles),
    }
