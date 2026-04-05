"""Pipeline step implementations for the 6-step compilation pipeline."""

from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING, Any

import frontmatter

from compendium.core.wikilinks import WIKILINK_PATTERN

if TYPE_CHECKING:
    from compendium.llm.prompts import PromptLoader
    from compendium.llm.provider import LlmProvider


# -- Data structures for step outputs --


def _parse_json_response(text: str) -> Any:
    """Extract JSON from LLM response, handling markdown code blocks."""
    # Try to extract from ```json ... ``` blocks
    match = re.search(r"```(?:json)?\s*\n(.*?)\n```", text, re.DOTALL)
    if match:
        return json.loads(match.group(1))
    # Try direct parse
    return json.loads(text)


def _normalize_summary_record(summary: dict[str, Any], source: dict[str, str]) -> dict[str, Any]:
    """Anchor summary metadata to the source being processed.

    Summaries are produced one source at a time, so the source id/title should come
    from the ingest manifest rather than the model output. This keeps downstream
    summary pages, conflict checks, and dependency tracking stable even if the model
    paraphrases or mislabels the source metadata.
    """
    normalized = dict(summary)
    normalized["source"] = source["id"]
    normalized["title"] = source["title"]
    return normalized


def _meta_page_frontmatter(
    *,
    title: str,
    page_id: str,
    page_type: str,
    updated_at: str,
) -> str:
    """Build Dataview-friendly frontmatter for generated meta pages."""
    return (
        "---\n"
        f'title: "{title}"\n'
        f'id: "{page_id}"\n'
        'category: "meta"\n'
        f'type: "{page_type}"\n'
        'origin: "compilation"\n'
        'status: "published"\n'
        f'updated_at: "{updated_at}"\n'
        "---\n\n"
    )


# -- Step 1: Summarize --


async def step_summarize(
    sources: list[dict[str, str]],
    llm: LlmProvider,
    prompt_loader: PromptLoader,
    batch_size: int = 5,
    schema_context: str = "",
) -> list[dict]:
    """Summarize raw sources into structured JSON summaries.

    Args:
        sources: List of {"id": str, "title": str, "content": str, "word_count": str}
        llm: LLM provider to use
        prompt_loader: Prompt template loader
        batch_size: Sources per LLM call

    Returns:
        List of structured summary dicts (one per source)
    """
    from compendium.llm.provider import CompletionRequest, Message

    template = prompt_loader.load("summarize")
    summaries: list[dict] = []

    for source in sources:
        prompt = template.render(
            schema_context=schema_context,
            title=source["title"],
            word_count=source["word_count"],
            content=source["content"],
            source_id=source["id"],
        )

        response = await llm.complete(
            CompletionRequest(
                messages=[Message(role="user", content=prompt)],
                system_prompt="You are a research summarization engine. "
                "Respond only with valid JSON.",
                max_tokens=2000,
                temperature=0.2,
            )
        )

        try:
            summary = _parse_json_response(response.content)
            if isinstance(summary, list):
                summaries.extend(
                    _normalize_summary_record(item, source)
                    for item in summary
                    if isinstance(item, dict)
                )
            else:
                summaries.append(_normalize_summary_record(summary, source))
        except (json.JSONDecodeError, ValueError):
            # Fallback: create a minimal summary from the response
            summaries.append(
                {
                    "source": source["id"],
                    "title": source["title"],
                    "summary": response.content[:500],
                    "claims": [],
                    "concepts": [],
                    "findings": [],
                    "limitations": [],
                }
            )

    return summaries


# -- Step 2: Extract concepts --


async def step_extract_concepts(
    summaries: list[dict],
    llm: LlmProvider,
    prompt_loader: PromptLoader,
    schema_context: str = "",
) -> list[dict]:
    """Build a concept taxonomy from source summaries.

    Returns:
        List of concept dicts with canonical_name, aliases, category, etc.
    """
    from compendium.llm.provider import CompletionRequest, Message

    template = prompt_loader.load("extract_concepts")

    # Format summaries for the prompt
    summaries_text = json.dumps(summaries, indent=2)

    prompt = template.render(schema_context=schema_context, summaries=summaries_text)

    response = await llm.complete(
        CompletionRequest(
            messages=[Message(role="user", content=prompt)],
            system_prompt="You are a taxonomy construction engine. Respond only with valid JSON.",
            max_tokens=4000,
            temperature=0.1,
        )
    )

    try:
        data = _parse_json_response(response.content)
        taxonomy = data.get("taxonomy", data) if isinstance(data, dict) else data
        return taxonomy if isinstance(taxonomy, list) else [taxonomy]
    except (json.JSONDecodeError, ValueError):
        # Fallback: extract concepts from summaries directly
        all_concepts: dict[str, int] = {}
        for s in summaries:
            for c in s.get("concepts", []):
                c_lower = c.lower().strip()
                all_concepts[c_lower] = all_concepts.get(c_lower, 0) + 1

        return [
            {
                "canonical_name": name.title(),
                "aliases": [name],
                "category": "concepts",
                "parent": None,
                "source_count": count,
                "should_generate_article": count >= 2,
            }
            for name, count in sorted(all_concepts.items(), key=lambda x: -x[1])
        ]


# -- Step 3: Generate articles --


async def step_generate_articles(
    concepts: list[dict],
    summaries: list[dict],
    source_contents: dict[str, str],
    llm: LlmProvider,
    prompt_loader: PromptLoader,
    min_words: int = 200,
    max_words: int = 3000,
    schema_context: str = "",
) -> list[dict[str, str]]:
    """Generate wiki articles for concepts that warrant them.

    Returns:
        List of {"path": relative_path, "content": full_markdown_with_frontmatter}
    """
    from compendium.llm.provider import CompletionRequest, Message

    template = prompt_loader.load("generate_article")
    articles: list[dict[str, str]] = []

    # Filter to concepts that should generate articles
    article_concepts = [c for c in concepts if c.get("should_generate_article", True)]

    for concept in article_concepts:
        name = concept["canonical_name"]
        category = concept.get("category", "concepts")
        aliases = concept.get("aliases", [])

        # Find relevant summaries (those mentioning this concept)
        relevant_summaries = []
        for s in summaries:
            s_concepts = [c.lower() for c in s.get("concepts", [])]
            if any(a.lower() in s_concepts for a in [name, *aliases]):
                relevant_summaries.append(s)

        if not relevant_summaries:
            continue

        # Build source content for the prompt
        sources_text = ""
        for s in relevant_summaries:
            source_id = s.get("source", "")
            content = source_contents.get(source_id, "")
            sources_text += f"\n### Source: {s.get('title', source_id)}\n"
            sources_text += f"Summary: {s.get('summary', '')}\n"
            if content:
                # Include first 3000 words of source content
                words = content.split()
                truncated = " ".join(words[:3000])
                sources_text += f"\nFull text (truncated):\n{truncated}\n"

        related = [
            c["canonical_name"]
            for c in concepts
            if c["canonical_name"] != name and c.get("should_generate_article", True)
        ]

        prompt = template.render(
            schema_context=schema_context,
            concept_name=name,
            category=category,
            related_concepts=", ".join(related[:10]),
            sources_content=sources_text,
            min_words=str(min_words),
            max_words=str(max_words),
        )

        response = await llm.complete(
            CompletionRequest(
                messages=[Message(role="user", content=prompt)],
                max_tokens=4000,
                temperature=0.3,
            )
        )

        article_content = response.content

        # Ensure article has frontmatter
        if not article_content.strip().startswith("---"):
            slug = re.sub(r"[^\w\s-]", "", name.lower())
            slug = re.sub(r"[\s_]+", "-", slug).strip("-")
            source_refs = [f'  - ref: "raw/{s.get("source", "")}.md"' for s in relevant_summaries]
            fm = (
                f'---\ntitle: "{name}"\nid: "{slug}"\n'
                f'category: "{category}"\n'
                f"sources:\n" + "\n".join(source_refs) + "\n"
                f"origin: compilation\nstatus: published\n"
                f"word_count: {len(article_content.split())}\n---\n\n"
            )
            article_content = fm + article_content

        # Determine file path
        slug = re.sub(r"[^\w\s-]", "", name.lower())
        slug = re.sub(r"[\s_]+", "-", slug).strip("-")[:80]
        path = f"wiki/{category}/{slug}.md"

        articles.append({"path": path, "content": article_content})

    return articles


# -- Step 4: Create backlinks --


def step_create_backlinks(
    articles: list[dict[str, str]], concepts: list[dict]
) -> list[dict[str, str]]:
    """Insert bidirectional wikilinks into articles.

    This is primarily a local string operation — no LLM call needed.
    Scans each article for mentions of other concept names and inserts [[wikilinks]].
    Also builds Related Articles and Referenced By sections.
    """
    # Build concept name → slug mapping
    concept_slugs: dict[str, str] = {}
    for c in concepts:
        name = c["canonical_name"]
        slug = re.sub(r"[^\w\s-]", "", name.lower())
        slug = re.sub(r"[\s_]+", "-", slug).strip("-")[:80]
        concept_slugs[name] = slug
        for alias in c.get("aliases", []):
            concept_slugs[alias] = slug

    # Build path → article index
    article_by_slug: dict[str, int] = {}
    for i, a in enumerate(articles):
        slug = a["path"].split("/")[-1].replace(".md", "")
        article_by_slug[slug] = i

    def extract_section_links(content: str, heading: str) -> list[str]:
        pattern = re.compile(rf"## {re.escape(heading)}\n(.*?)(?=\n## |\Z)", re.DOTALL)
        match = pattern.search(content)
        if not match:
            return []
        links: list[str] = []
        for target, _display in WIKILINK_PATTERN.findall(match.group(1)):
            target_slug = target.strip().split("/")[-1].replace(".md", "").strip()
            if target_slug:
                links.append(target_slug)
        return links

    def upsert_section(content: str, heading: str, slugs: list[str]) -> str:
        if not slugs:
            return content
        unique = sorted(dict.fromkeys(slugs))
        bullets = "\n".join(f"- [[{slug}]]" for slug in unique)
        section = f"## {heading}\n{bullets}\n"
        pattern = re.compile(rf"\n## {re.escape(heading)}\n.*?(?=\n## |\Z)", re.DOTALL)
        if pattern.search(content):
            return pattern.sub(f"\n{section}", content)
        return content.rstrip() + f"\n\n{section}"

    related_map: dict[str, list[str]] = {}

    for article in articles:
        content = article["content"]
        my_slug = article["path"].split("/")[-1].replace(".md", "")

        # Find which other concepts are mentioned in this article's body
        related: list[str] = []
        for concept_name, slug in concept_slugs.items():
            if slug == my_slug:
                continue
            # Check if concept name appears in article body (case-insensitive)
            pattern = re.compile(re.escape(concept_name), re.IGNORECASE)
            if pattern.search(content) and slug not in related:
                related.append(slug)

        related_map[my_slug] = related[:15]

    inbound_map: dict[str, list[str]] = {slug: [] for slug in article_by_slug}
    for source_slug, targets in related_map.items():
        for target_slug in targets:
            if target_slug in inbound_map:
                inbound_map[target_slug].append(source_slug)

    updated_articles: list[dict[str, str]] = []
    for article in articles:
        content = article["content"]
        my_slug = article["path"].split("/")[-1].replace(".md", "")

        related = extract_section_links(content, "Related Articles") + related_map.get(my_slug, [])
        referenced_by = extract_section_links(
            content, "Referenced By"
        ) + inbound_map.get(my_slug, [])

        content = upsert_section(content, "Related Articles", related)
        content = upsert_section(content, "Referenced By", referenced_by)
        updated_articles.append({"path": article["path"], "content": content})

    return updated_articles


# -- Step 5: Build index --


def step_build_index(
    articles: list[dict[str, str]],
    concepts: list[dict],
    compilation_log: str = "",
) -> dict[str, str]:
    """Build `index.md` and `concepts.md`.

    Returns:
        Dict of {"index.md": content, "concepts.md": content}
    """
    from datetime import UTC, datetime

    now = datetime.now(UTC).isoformat()

    def extract_summary(body: str) -> str:
        for line in body.split("\n"):
            stripped = re.sub(r"[*_`#>\-\[\]]", "", line).strip()
            if stripped:
                return stripped[:140]
        return ""

    def extract_sources(metadata: dict) -> str:
        sources = metadata.get("sources", [])
        refs: list[str] = []
        for source in sources:
            if isinstance(source, dict):
                ref = str(source.get("ref", "")).strip()
            else:
                ref = str(source).strip()
            if not ref:
                continue
            ref = ref.replace("raw/", "").replace(".md", "")
            refs.append(ref)
        if not refs:
            return "—"
        if len(refs) <= 3:
            return ", ".join(refs)
        return f"{', '.join(refs[:3])}, +{len(refs) - 3} more"

    def extract_updated(metadata: dict) -> str:
        value = metadata.get("updated_at") or metadata.get("created_at") or now
        return str(value)[:10]

    rows_by_category: dict[str, list[tuple[str, str, str, str, str]]] = {}

    for article in articles:
        try:
            post = frontmatter.loads(article["content"])
            metadata = dict(post.metadata)
            title = metadata.get("title", article["path"].split("/")[-1])
            category = metadata.get("category", "uncategorized")
            page_type = metadata.get("type", category)
            summary = extract_summary(post.content.strip())
            sources_value = extract_sources(metadata)
            updated_value = extract_updated(metadata)
        except Exception:
            title = article["path"].split("/")[-1].replace(".md", "").replace("-", " ").title()
            category = "uncategorized"
            page_type = category
            summary = ""
            sources_value = "—"
            updated_value = now[:10]

        slug = article["path"].split("/")[-1].replace(".md", "")
        rows_by_category.setdefault(category, []).append(
            (title, slug, str(page_type), summary, sources_value, updated_value)
        )

    # -- index.md --
    index_lines = [
        _meta_page_frontmatter(
            title="Wiki Index",
            page_id="index",
            page_type="index",
            updated_at=now,
        ),
        "# Wiki Index\n",
        f"*Last updated: {now}*\n",
        f"*Articles: {len(articles)}*\n\n",
    ]

    for category in sorted(rows_by_category):
        index_lines.append(f"## {category.title()}\n\n")
        index_lines.append("| Page | Type | Summary | Sources | Updated |\n")
        index_lines.append("|------|------|---------|---------|---------|\n")
        for title, slug, page_type, summary, sources_value, updated_value in sorted(
            rows_by_category[category], key=lambda row: row[0].lower()
        ):
            safe_summary = summary.replace("|", "\\|")
            safe_sources = sources_value.replace("|", "\\|")
            index_lines.append(
                f"| [[{slug}|{title}]] | {page_type} | {safe_summary} | "
                f"{safe_sources} | {updated_value} |\n"
            )
        index_lines.append("\n")

    # -- concepts.md --
    concepts_lines = [
        _meta_page_frontmatter(
            title="Concept Taxonomy",
            page_id="concepts",
            page_type="taxonomy",
            updated_at=now,
        ),
        "# Concepts\n",
        f"*Last updated: {now}*\n\n",
    ]

    # Group by category
    by_category: dict[str, list[dict]] = {}
    for c in concepts:
        cat = c.get("category", "concepts")
        by_category.setdefault(cat, []).append(c)

    for cat, cat_concepts in sorted(by_category.items()):
        concepts_lines.append(f"## {cat.title()}\n")
        for c in sorted(cat_concepts, key=lambda x: -x.get("source_count", 0)):
            name = c["canonical_name"]
            count = c.get("source_count", 0)
            aliases = c.get("aliases", [])
            alias_str = f" (aliases: {', '.join(aliases)})" if aliases else ""
            article_marker = " *" if c.get("should_generate_article") else ""
            concepts_lines.append(f"- **{name}**{article_marker} — {count} sources{alias_str}\n")
        concepts_lines.append("\n")

    return {
        "index.md": "".join(index_lines),
        "concepts.md": "".join(concepts_lines),
    }


def build_log_entry(
    event_type: str,
    title: str | None = None,
    articles_count: int = 0,
    concepts_count: int = 0,
    sources_count: int = 0,
    notes: str = "",
) -> str:
    """Build an append-only log entry for log.md."""
    from datetime import UTC, datetime

    event_map = {
        "compile": ("rebuild", "Compile wiki"),
        "incremental update": ("schema-update", "Incremental update"),
        "file to wiki": ("file", "File output to wiki"),
        "file": ("file", "File output to wiki"),
        "lint": ("lint", "Lint wiki"),
        "ingest": ("ingest", "Ingest sources"),
        "query": ("query", "Query knowledge base"),
        "rebuild": ("rebuild", "Rebuild wiki artifacts"),
        "schema-update": ("schema-update", "Schema update"),
    }

    operation, default_title = event_map.get(event_type, (event_type, event_type.replace("-", " ")))
    heading_title = title or default_title

    now = datetime.now(UTC).strftime("%Y-%m-%d")
    parts = [f"## [{now}] {operation} | {heading_title}"]
    if event_type != operation:
        parts.append(f"- Event type: {event_type}")
    if articles_count:
        parts.append(f"- Articles: {articles_count}")
    if concepts_count:
        parts.append(f"- Concepts: {concepts_count}")
    if sources_count:
        parts.append(f"- Sources processed: {sources_count}")
    if notes:
        parts.append(f"- {notes}")
    parts.append("")
    return "\n".join(parts) + "\n"


# -- Step 3b: Patch existing article --


async def step_patch_article(
    existing_content: str,
    new_summary: dict,
    new_source_content: str,
    llm: LlmProvider,
    prompt_loader: PromptLoader,
    schema_context: str = "",
) -> str:
    """Patch an existing wiki article with information from a new source.

    Returns the updated article content (full markdown with frontmatter).
    """
    from compendium.llm.provider import CompletionRequest, Message

    template = prompt_loader.load("patch_article")
    prompt = template.render(
        schema_context=schema_context,
        existing_article=existing_content[:4000],
        new_summary=json.dumps(new_summary, indent=2)[:2000],
        new_content=new_source_content[:3000],
    )

    response = await llm.complete(
        CompletionRequest(
            messages=[Message(role="user", content=prompt)],
            max_tokens=4000,
            temperature=0.3,
        )
    )

    patched = response.content

    # Ensure the response has frontmatter (LLM should preserve it, but fallback)
    if not patched.strip().startswith("---"):
        return existing_content  # Fallback: keep original if LLM dropped frontmatter

    return patched


# -- Step 6: Conflict detection --


async def step_detect_conflicts(
    articles: list[dict[str, str]],
    concepts: list[dict],
    summaries: list[dict],
    llm: LlmProvider,
    prompt_loader: PromptLoader,
    schema_context: str = "",
) -> str:
    """Detect contradictions across articles. Returns CONFLICTS.md content."""
    from compendium.llm.provider import CompletionRequest, Message

    template = prompt_loader.load("detect_conflicts")
    conflicts: list[dict] = []

    # Pre-filter: find article pairs that share concepts
    article_concepts: dict[int, set[str]] = {}
    for i, article in enumerate(articles):
        try:
            post = frontmatter.loads(article["content"])
            tags = set(post.metadata.get("tags", []))
            # Also extract concepts from content mentions
            for c in concepts:
                name = c["canonical_name"].lower()
                if name in article["content"].lower():
                    tags.add(name)
            article_concepts[i] = tags
        except Exception:
            article_concepts[i] = set()

    # Find pairs sharing >= 2 concepts
    candidate_pairs: list[tuple[int, int]] = []
    for i in range(len(articles)):
        for j in range(i + 1, len(articles)):
            shared = article_concepts[i] & article_concepts[j]
            if len(shared) >= 2:
                candidate_pairs.append((i, j))

    # Limit to 10 pairs to control cost
    candidate_pairs = candidate_pairs[:10]

    for i, j in candidate_pairs:
        a_content = articles[i]["content"][:2000]
        b_content = articles[j]["content"][:2000]

        try:
            a_post = frontmatter.loads(articles[i]["content"])
            b_post = frontmatter.loads(articles[j]["content"])
            a_title = a_post.metadata.get("title", f"Article {i}")
            b_title = b_post.metadata.get("title", f"Article {j}")
        except Exception:
            a_title = f"Article {i}"
            b_title = f"Article {j}"

        shared = article_concepts[i] & article_concepts[j]
        concept_name = next(iter(shared)) if shared else "shared topic"

        prompt = template.render(
            schema_context=schema_context,
            concept=concept_name,
            article_a_title=a_title,
            article_a_content=a_content,
            article_b_title=b_title,
            article_b_content=b_content,
        )

        response = await llm.complete(
            CompletionRequest(
                messages=[Message(role="user", content=prompt)],
                system_prompt="You are a conflict detection engine. Respond only with valid JSON.",
                max_tokens=1000,
                temperature=0.2,
            )
        )

        try:
            result = _parse_json_response(response.content)
            if result.get("classification") in ("CONTRADICTION", "DISAGREEMENT"):
                result["article_a"] = a_title
                result["article_b"] = b_title
                conflicts.append(result)
        except (json.JSONDecodeError, ValueError):
            pass

    # Build CONFLICTS.md
    from datetime import UTC, datetime

    now = datetime.now(UTC).isoformat()
    lines = [
        _meta_page_frontmatter(
            title="Conflict Register",
            page_id="conflicts",
            page_type="conflicts",
            updated_at=now,
        ),
        "# Conflicts\n\n",
        f"*Last checked: {now}*\n",
        f"*Candidate pairs evaluated: {len(candidate_pairs)}*\n",
        f"*Conflicts found: {len(conflicts)}*\n\n",
    ]

    if not conflicts:
        lines.append("No conflicts detected.\n")
    else:
        critical = [c for c in conflicts if c.get("severity") == "critical"]
        warnings = [c for c in conflicts if c.get("severity") == "warning"]

        if critical:
            lines.append("## Critical\n\n")
            for c in critical:
                lines.append(f"### {c.get('article_a', '?')} vs {c.get('article_b', '?')}\n")
                lines.append(f"- **Claim A:** {c.get('claim_a', 'N/A')}\n")
                lines.append(f"- **Claim B:** {c.get('claim_b', 'N/A')}\n")
                lines.append(f"- **Explanation:** {c.get('explanation', '')}\n\n")

        if warnings:
            lines.append("## Warning\n\n")
            for c in warnings:
                lines.append(f"### {c.get('article_a', '?')} vs {c.get('article_b', '?')}\n")
                lines.append(f"- **Explanation:** {c.get('explanation', '')}\n\n")

    return "".join(lines)
