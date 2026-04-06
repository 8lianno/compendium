"""Pipeline controller — orchestrates the 6-step compilation pipeline."""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import frontmatter

from compendium.core.templates import generate_schema_md
from compendium.pipeline.checkpoint import (
    CompilationCheckpoint,
    StepCheckpoint,
    StepStatus,
)
from compendium.pipeline.deps import (
    ArticleEntry,
    ConceptEntry,
    DependencyGraph,
    SourceEntry,
)
from compendium.pipeline.steps import (
    build_log_entry,
    step_build_index,
    step_create_backlinks,
    step_detect_conflicts,
    step_extract_concepts,
    step_generate_articles,
    step_patch_article,
    step_summarize,
)

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from compendium.core.config import CompendiumConfig
    from compendium.core.wiki_fs import WikiFileSystem
    from compendium.llm.prompts import PromptLoader
    from compendium.llm.provider import LlmProvider


class ProgressCallback:
    """Simple progress callback interface."""

    def __init__(self, callback: Callable[[str, int, int, str], None] | None = None) -> None:
        self._callback = callback

    def report(self, step_name: str, current: int, total: int, detail: str = "") -> None:
        if self._callback:
            self._callback(step_name, current, total, detail)


def _merge_concepts(existing: list[dict], incoming: list[dict]) -> list[dict]:
    """Merge concept taxonomies by canonical name while preserving source coverage."""
    merged: dict[str, dict] = {}

    for concept in [*existing, *incoming]:
        canonical = concept.get("canonical_name")
        if not canonical:
            continue
        key = canonical.lower()
        current = merged.get(key)
        if current is None:
            merged[key] = {
                **concept,
                "aliases": list(dict.fromkeys(concept.get("aliases", []))),
            }
            continue

        merged[key] = {
            **current,
            **concept,
            "canonical_name": current.get("canonical_name") or canonical,
            "category": concept.get("category") or current.get("category", "concepts"),
            "parent": concept.get("parent") or current.get("parent"),
            "source_count": max(current.get("source_count", 0), concept.get("source_count", 0)),
            "should_generate_article": bool(
                current.get("should_generate_article") or concept.get("should_generate_article")
            ),
            "aliases": list(
                dict.fromkeys([*current.get("aliases", []), *concept.get("aliases", [])])
            ),
        }

    return sorted(merged.values(), key=lambda concept: concept["canonical_name"].lower())


async def compile_wiki(
    wfs: WikiFileSystem,
    config: CompendiumConfig,
    llm: LlmProvider,
    prompt_loader: PromptLoader,
    progress: ProgressCallback | None = None,
    resume: bool = False,
) -> dict[str, Any]:
    """Run the full 6-step compilation pipeline.

    Args:
        wfs: WikiFileSystem for the project
        config: Project configuration
        llm: LLM provider to use for compilation
        prompt_loader: Prompt template loader
        progress: Optional progress callback
        resume: Whether to resume from checkpoint

    Returns:
        Dict with compilation results: articles_count, concepts_count, conflicts_count, etc.
    """
    if progress is None:
        progress = ProgressCallback()

    # Load or create checkpoint
    checkpoint = None
    if resume:
        checkpoint = CompilationCheckpoint.load(wfs.checkpoint_path)

    if checkpoint is None:
        checkpoint = CompilationCheckpoint(
            compilation_id=f"comp-{datetime.now(UTC).strftime('%Y%m%d-%H%M%S')}",
            started_at=datetime.now(UTC).isoformat(),
            mode="full",
        )

    # Ensure staging dir exists
    wfs.staging_dir.mkdir(parents=True, exist_ok=True)

    # -- Load raw sources --
    raw_sources = wfs.list_raw_sources()
    if not raw_sources:
        return {"error": "No raw sources found in raw/"}

    source_data: list[dict[str, str]] = []
    source_contents: dict[str, str] = {}
    schema_context = wfs.schema_context()

    for path in raw_sources:
        post = frontmatter.load(str(path))
        source_id = post.metadata.get("id", path.stem)
        source_data.append(
            {
                "id": source_id,
                "title": post.metadata.get("title", path.stem),
                "content": post.content,
                "word_count": str(post.metadata.get("word_count", len(post.content.split()))),
                "path": str(path.relative_to(wfs.root)),
            }
        )
        source_contents[source_id] = post.content
        checkpoint.source_manifest[str(path.relative_to(wfs.root))] = wfs.content_hash(path)

    total_steps = 6

    # -- Step 1: Summarize --
    progress.report("summarize", 1, total_steps, f"Summarizing {len(source_data)} sources...")

    summaries: list[dict]
    if _step_completed(checkpoint, "summarize"):
        summaries = _load_step_output(wfs.staging_dir, "summaries")
    else:
        _mark_step_started(checkpoint, "summarize")
        summaries = await step_summarize(
            source_data,
            llm,
            prompt_loader,
            schema_context=schema_context,
        )
        _save_step_output(wfs.staging_dir, "summaries", summaries)
        _mark_step_completed(checkpoint, "summarize")
        _save_checkpoint(checkpoint, wfs.checkpoint_path)

    # -- Step 2: Extract concepts --
    progress.report("extract_concepts", 2, total_steps, "Extracting concept taxonomy...")

    concepts: list[dict]
    if _step_completed(checkpoint, "extract_concepts"):
        concepts = _load_step_output(wfs.staging_dir, "concepts")
    else:
        _mark_step_started(checkpoint, "extract_concepts")
        concepts = await step_extract_concepts(
            summaries,
            llm,
            prompt_loader,
            schema_context=schema_context,
        )
        _save_step_output(wfs.staging_dir, "concepts", concepts)
        _mark_step_completed(checkpoint, "extract_concepts")
        _save_checkpoint(checkpoint, wfs.checkpoint_path)

    # -- Step 3: Generate articles --
    article_concepts = [c for c in concepts if c.get("should_generate_article", True)]
    progress.report(
        "generate_articles", 3, total_steps, f"Generating {len(article_concepts)} articles..."
    )

    articles: list[dict[str, str]]
    if _step_completed(checkpoint, "generate_articles"):
        articles = _load_step_output(wfs.staging_dir, "articles")
    else:
        _mark_step_started(checkpoint, "generate_articles")
        articles = await step_generate_articles(
            concepts,
            summaries,
            source_contents,
            llm,
            prompt_loader,
            min_words=config.compilation.min_article_words,
            max_words=config.compilation.max_article_words,
            schema_context=schema_context,
        )
        _save_step_output(wfs.staging_dir, "articles", articles)
        _mark_step_completed(checkpoint, "generate_articles")
        _save_checkpoint(checkpoint, wfs.checkpoint_path)

    # -- Step 4: Create backlinks --
    progress.report("create_backlinks", 4, total_steps, "Creating backlinks...")

    if _step_completed(checkpoint, "create_backlinks"):
        articles = _load_step_output(wfs.staging_dir, "articles_linked")
    else:
        _mark_step_started(checkpoint, "create_backlinks")
        articles = step_create_backlinks(articles, concepts)
        _save_step_output(wfs.staging_dir, "articles_linked", articles)
        _mark_step_completed(checkpoint, "create_backlinks")
        _save_checkpoint(checkpoint, wfs.checkpoint_path)

    # -- Step 5: Build index --
    progress.report("build_index", 5, total_steps, "Building index.md and concepts.md...")

    index_files: dict[str, str]
    if _step_completed(checkpoint, "build_index"):
        index_files = _load_step_output(wfs.staging_dir, "index_files")
    else:
        _mark_step_started(checkpoint, "build_index")
        index_files = step_build_index(articles, concepts)
        _save_step_output(wfs.staging_dir, "index_files", index_files)
        _mark_step_completed(checkpoint, "build_index")
        _save_checkpoint(checkpoint, wfs.checkpoint_path)

    # -- Step 6: Conflict detection --
    progress.report("detect_conflicts", 6, total_steps, "Detecting conflicts...")

    conflicts_md: str
    if _step_completed(checkpoint, "detect_conflicts"):
        conflicts_data = _load_step_output(wfs.staging_dir, "conflicts")
        conflicts_md = conflicts_data.get("content", "# Conflicts\n\nNo conflicts detected.\n")
    else:
        _mark_step_started(checkpoint, "detect_conflicts")
        conflicts_md = await step_detect_conflicts(
            articles,
            concepts,
            summaries,
            llm,
            prompt_loader,
            schema_context=schema_context,
        )
        _save_step_output(wfs.staging_dir, "conflicts", {"content": conflicts_md})
        _mark_step_completed(checkpoint, "detect_conflicts")
        _save_checkpoint(checkpoint, wfs.checkpoint_path)

    # -- Write all files to staging --
    progress.report("promoting", 0, 0, "Writing files to wiki/...")

    # Create backup first
    if wfs.list_wiki_articles():
        wfs.create_backup()

    # Write articles to staging
    for article in articles:
        article_path = wfs.staging_dir / article["path"].removeprefix("wiki/")
        article_path.parent.mkdir(parents=True, exist_ok=True)
        article_path.write_text(article["content"])

    # Write per-source summary pages to staging
    _write_source_summary_pages(wfs.staging_dir, summaries)

    # Write overview page to staging
    overview = _generate_overview(articles, concepts, summaries, source_data)
    (wfs.staging_dir / "overview.md").write_text(overview)

    # Write index files to staging
    for filename, content in index_files.items():
        (wfs.staging_dir / filename).write_text(content)

    # Write CONFLICTS.md to staging
    (wfs.staging_dir / "CONFLICTS.md").write_text(conflicts_md)

    # Write SCHEMA.md to staging
    schema_md = _generate_schema_md(
        config.templates.default,
        config.templates.domain,
    )
    (wfs.staging_dir / "SCHEMA.md").write_text(schema_md)

    # Promote staging to wiki/
    wfs.promote_staging()

    # Append to log.md (append-only, never overwrite)
    log_entry = build_log_entry(
        "compile",
        articles_count=len(articles),
        concepts_count=len(concepts),
        sources_count=len(source_data),
    )
    wfs.append_log_entry(log_entry)

    # -- Update dependency graph --
    deps = DependencyGraph()
    for sd in source_data:
        rel_path = sd["path"]
        deps.sources[rel_path] = SourceEntry(
            content_hash=checkpoint.source_manifest.get(rel_path, ""),
            compiled_at=datetime.now(UTC).isoformat(),
            concepts=[c.lower() for c in _get_source_concepts(sd["id"], summaries)],
        )

    for article in articles:
        path = article["path"]
        try:
            post = frontmatter.loads(article["content"])
            sources_list = [
                s.get("ref", "") if isinstance(s, dict) else str(s)
                for s in post.metadata.get("sources", [])
            ]
        except Exception:
            sources_list = []

        deps.articles[path] = ArticleEntry(
            depends_on=sources_list,
            content_hash=f"sha256:{hash(article['content'])}",
            word_count=len(article["content"].split()),
            origin="compilation",
            last_compiled=datetime.now(UTC).isoformat(),
        )

    for concept in concepts:
        name_key = concept["canonical_name"].lower().replace(" ", "-")
        deps.concepts[name_key] = ConceptEntry(
            canonical=concept["canonical_name"],
            aliases=concept.get("aliases", []),
            source_count=concept.get("source_count", 0),
            category=concept.get("category", "concepts"),
        )

    deps.mark_full_compile()
    deps.update_meta()
    deps.save(wfs.deps_path)

    wfs.auto_commit(
        "[rebuild]: compile wiki",
        paths=[
            wfs.wiki_dir,
            wfs.deps_path,
        ],
    )

    # Clean up checkpoint
    if wfs.checkpoint_path.exists():
        wfs.checkpoint_path.unlink()

    # Record token usage if tracker provided
    total_tokens = _sum_checkpoint_tokens(checkpoint)

    return {
        "articles_count": len(articles),
        "concepts_count": len(concepts),
        "conflicts_detected": conflicts_md.count("###"),
        "sources_processed": len(source_data),
        "compilation_id": checkpoint.compilation_id,
        "total_input_tokens": total_tokens[0],
        "total_output_tokens": total_tokens[1],
    }


# -- Incremental compilation --


async def incremental_update(
    wfs: WikiFileSystem,
    config: CompendiumConfig,
    llm: LlmProvider,
    prompt_loader: PromptLoader,
    new_source_paths: list[Path] | None = None,
    progress: ProgressCallback | None = None,
) -> dict[str, Any]:
    """Incrementally update the wiki with new/changed sources.

    If new_source_paths is None, auto-detects all new/changed sources.
    """
    if progress is None:
        progress = ProgressCallback()

    deps = DependencyGraph.load(wfs.deps_path)

    # Detect new/changed sources
    all_sources = wfs.list_raw_sources()
    current_hashes: dict[str, str] = {}
    schema_context = wfs.schema_context()
    for path in all_sources:
        rel = str(path.relative_to(wfs.root))
        current_hashes[rel] = wfs.content_hash(path)

    if new_source_paths:
        changed = [str(p.relative_to(wfs.root)) for p in new_source_paths]
    else:
        changed = deps.get_new_sources(current_hashes)

    if not changed:
        return {"message": "No new or changed sources detected.", "updated": 0}

    progress.report("incremental", 1, 4, f"Processing {len(changed)} new/changed source(s)...")

    # Load new source data
    new_source_data: list[dict[str, str]] = []
    new_source_contents: dict[str, str] = {}
    for rel_path in changed:
        full_path = wfs.root / rel_path
        if not full_path.exists():
            continue
        post = frontmatter.load(str(full_path))
        source_id = post.metadata.get("id", full_path.stem)
        new_source_data.append(
            {
                "id": source_id,
                "title": post.metadata.get("title", full_path.stem),
                "content": post.content,
                "word_count": str(len(post.content.split())),
                "path": rel_path,
            }
        )
        new_source_contents[source_id] = post.content

    # Step 1: Summarize new sources
    progress.report("incremental", 2, 4, "Summarizing new sources...")
    new_summaries = await step_summarize(
        new_source_data,
        llm,
        prompt_loader,
        schema_context=schema_context,
    )

    # Step 2: Extract concepts from new summaries
    progress.report("incremental", 3, 4, "Matching concepts...")
    new_concepts = await step_extract_concepts(
        new_summaries,
        llm,
        prompt_loader,
        schema_context=schema_context,
    )

    # Determine affected existing articles
    new_concept_names = [c["canonical_name"].lower() for c in new_concepts]
    affected_paths = deps.get_affected_by_concepts(new_concept_names)

    # Also find affected via source dependencies
    affected_by_source = deps.get_affected_articles(changed)
    all_affected = sorted(set(affected_paths) | set(affected_by_source))

    progress.report(
        "incremental",
        4,
        6,
        f"Updating {len(all_affected)} existing + generating new articles...",
    )

    # Create backup before any changes
    wfs.create_backup()

    # --- Patch existing affected articles ---
    articles_patched = 0
    for article_rel in all_affected:
        article_path = wfs.root / article_rel
        if not article_path.exists():
            continue
        existing_content = article_path.read_text()

        # Find which new summaries are relevant to this article
        relevant_summaries = []
        for s in new_summaries:
            s_concepts = {c.lower() for c in s.get("concepts", [])}
            # Check overlap with article's concepts
            article_lower = existing_content.lower()
            if any(c in article_lower for c in s_concepts):
                relevant_summaries.append(s)

        if not relevant_summaries:
            continue

        # Patch the article with each relevant new summary
        patched = existing_content
        for summary in relevant_summaries:
            source_id = summary.get("source", "")
            source_content = new_source_contents.get(source_id, "")
            patched = await step_patch_article(
                patched,
                summary,
                source_content,
                llm,
                prompt_loader,
                schema_context=schema_context,
            )

        if patched != existing_content:
            article_path.write_text(patched)
            articles_patched += 1

    existing_concepts = [
        {
            "canonical_name": concept.canonical,
            "aliases": concept.aliases,
            "category": concept.category,
            "source_count": concept.source_count,
            "should_generate_article": True,
        }
        for concept in deps.concepts.values()
    ]
    all_summaries = new_summaries
    all_concepts = _merge_concepts(existing_concepts, new_concepts)

    new_articles = await step_generate_articles(
        all_concepts,
        all_summaries,
        new_source_contents,
        llm,
        prompt_loader,
        min_words=config.compilation.min_article_words,
        max_words=config.compilation.max_article_words,
        schema_context=schema_context,
    )

    for article in new_articles:
        article_path = wfs.wiki_dir / article["path"].removeprefix("wiki/")
        # Only write if article doesn't already exist (new concepts only)
        if not article_path.exists():
            article_path.parent.mkdir(parents=True, exist_ok=True)
            article_path.write_text(article["content"])

    # Maintain 1:1 source summaries for new/changed sources.
    _write_source_summary_pages(wfs.wiki_dir, new_summaries)

    # Rebuild backlinks and index from the article corpus.
    all_articles = _load_wiki_article_corpus(wfs)
    all_articles = step_create_backlinks(all_articles, all_concepts)
    for article in all_articles:
        article_path = wfs.root / article["path"]
        article_path.parent.mkdir(parents=True, exist_ok=True)
        article_path.write_text(article["content"])

    index_files = step_build_index(all_articles, all_concepts, "Incremental update")
    for filename, content in index_files.items():
        (wfs.wiki_dir / filename).write_text(content)

    all_source_data = _load_source_data(wfs)
    overview = _generate_overview(all_articles, all_concepts, [], all_source_data)
    (wfs.wiki_dir / "overview.md").write_text(overview)

    # Run conflict detection on new articles vs all existing
    progress.report("incremental", 5, 5, "Checking for conflicts...")
    conflicts_md = await step_detect_conflicts(
        all_articles,
        all_concepts,
        new_summaries,
        llm,
        prompt_loader,
        schema_context=schema_context,
    )
    (wfs.wiki_dir / "CONFLICTS.md").write_text(conflicts_md)

    # Update deps
    for sd in new_source_data:
        deps.sources[sd["path"]] = SourceEntry(
            content_hash=current_hashes.get(sd["path"], ""),
            compiled_at=datetime.now(UTC).isoformat(),
            concepts=[c.lower() for c in _get_source_concepts(sd["id"], new_summaries)],
        )

    for concept in all_concepts:
        name_key = concept["canonical_name"].lower().replace(" ", "-")
        deps.concepts[name_key] = ConceptEntry(
            canonical=concept["canonical_name"],
            aliases=concept.get("aliases", []),
            source_count=concept.get("source_count", 0),
            category=concept.get("category", "concepts"),
        )

    deps.mark_incremental()
    deps.update_meta()
    deps.save(wfs.deps_path)

    # Append to log.md
    log_entry = build_log_entry(
        "incremental update",
        articles_count=len(new_articles),
        sources_count=len(changed),
        notes=f"{articles_patched} articles patched, {len(all_affected)} affected",
    )
    wfs.append_log_entry(log_entry)

    wfs.auto_commit(
        "[schema-update]: incremental wiki update",
        paths=[
            wfs.wiki_dir,
            wfs.deps_path,
        ],
    )

    return {
        "articles_added": len(new_articles),
        "articles_patched": articles_patched,
        "articles_affected": len(all_affected),
        "sources_processed": len(changed),
    }


# -- Helper functions --


def _step_completed(checkpoint: CompilationCheckpoint, step_name: str) -> bool:
    step = checkpoint.steps.get(step_name)
    return step is not None and step.status == StepStatus.COMPLETED


def _mark_step_started(checkpoint: CompilationCheckpoint, step_name: str) -> None:
    checkpoint.steps[step_name] = StepCheckpoint(
        status=StepStatus.IN_PROGRESS,
        started_at=datetime.now(UTC).isoformat(),
    )


def _mark_step_completed(checkpoint: CompilationCheckpoint, step_name: str) -> None:
    step = checkpoint.steps.get(step_name, StepCheckpoint())
    step.status = StepStatus.COMPLETED
    step.completed_at = datetime.now(UTC).isoformat()
    checkpoint.steps[step_name] = step


def _save_checkpoint(checkpoint: CompilationCheckpoint, path: Path) -> None:
    checkpoint.checkpoint_at = datetime.now(UTC).isoformat()
    checkpoint.save(path)


def _save_step_output(staging_dir: Path, name: str, data: Any) -> None:
    output_dir = staging_dir / "step_outputs"
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / f"{name}.json").write_text(json.dumps(data, indent=2, default=str))


def _load_step_output(staging_dir: Path, name: str) -> Any:
    path = staging_dir / "step_outputs" / f"{name}.json"
    if path.exists():
        return json.loads(path.read_text())
    return {}


def _get_source_concepts(source_id: str, summaries: list[dict]) -> list[str]:
    """Get concepts mentioned in a specific source's summary."""
    for s in summaries:
        if s.get("source") == source_id:
            return s.get("concepts", [])
    return []


def _load_source_data(wfs: WikiFileSystem) -> list[dict[str, str]]:
    """Load all raw sources into the manifest shape used by overview generation."""
    source_data: list[dict[str, str]] = []
    for path in wfs.list_raw_sources():
        post = frontmatter.load(str(path))
        source_id = post.metadata.get("id", path.stem)
        source_data.append(
            {
                "id": source_id,
                "title": post.metadata.get("title", path.stem),
                "content": post.content,
                "word_count": str(post.metadata.get("word_count", len(post.content.split()))),
                "path": str(path.relative_to(wfs.root)),
            }
        )
    return source_data


def _write_source_summary_pages(base_dir: Path, summaries: list[dict]) -> None:
    """Write or refresh per-source summary pages under wiki/sources/."""
    sources_dir = base_dir / "sources"
    sources_dir.mkdir(parents=True, exist_ok=True)

    for summary in summaries:
        source_id = str(summary.get("source", "unknown"))
        title = str(summary.get("title", source_id))
        body = f"---\ntitle: \"Source: {title}\"\nid: \"source-{source_id}\"\n"
        body += "type: source-summary\ncategory: sources\norigin: compilation\n---\n\n"
        body += f"# {title}\n\n## Summary\n{summary.get('summary', '')}\n\n"

        claims = summary.get("claims", [])
        if claims:
            body += "## Key Claims\n"
            for claim in claims:
                claim_text = claim.get("claim", claim) if isinstance(claim, dict) else str(claim)
                body += f"- {claim_text}\n"
            body += "\n"

        findings = summary.get("findings", [])
        if findings:
            body += "## Findings\n" + "".join(f"- {finding}\n" for finding in findings) + "\n"

        limitations = summary.get("limitations", [])
        if limitations:
            body += "## Limitations\n"
            body += "".join(f"- {limitation}\n" for limitation in limitations)
            body += "\n"

        concepts_list = summary.get("concepts", [])
        if concepts_list:
            body += "## Concepts\n"
            body += ", ".join(f"[[{concept}]]" for concept in concepts_list)
            body += "\n\n"

        body += f"## Raw Source\n[[raw/{source_id}.md]]\n"
        slug = re.sub(r"[^\w\s-]", "", source_id.lower())
        slug = re.sub(r"[\s_]+", "-", slug).strip("-")[:80]
        (sources_dir / f"{slug}.md").write_text(body)


def _load_wiki_article_corpus(wfs: WikiFileSystem) -> list[dict[str, str]]:
    """Load the primary wiki article corpus, excluding structural pages and source summaries."""
    structural = {
        "INDEX.md",
        "CONCEPTS.md",
        "index.md",
        "concepts.md",
        "CONFLICTS.md",
        "CHANGELOG.md",
        "HEALTH_REPORT.md",
        "SCHEMA.md",
        "overview.md",
        "log.md",
    }
    articles: list[dict[str, str]] = []

    for md_path in wfs.list_wiki_articles():
        rel_to_wiki = md_path.relative_to(wfs.wiki_dir)
        if md_path.name in structural:
            continue
        if rel_to_wiki.parts and rel_to_wiki.parts[0] == "sources":
            continue
        articles.append(
            {
                "path": str(md_path.relative_to(wfs.root)),
                "content": md_path.read_text(),
            }
        )

    return articles


def _generate_overview(
    articles: list[dict[str, str]],
    concepts: list[dict],
    summaries: list[dict],
    source_data: list[dict[str, str]],
) -> str:
    """Generate an overview.md — a top-level synthesis of the entire wiki."""
    now = datetime.now(UTC).isoformat()

    lines = [
        "---",
        'title: "Wiki Overview"',
        'id: "overview"',
        'category: "meta"',
        "origin: compilation",
        "---",
        "",
        "# Wiki Overview",
        "",
        f"*Last compiled: {now}*",
        f"*Sources: {len(source_data)} | Articles: {len(articles)} "
        f"| Concepts: {len(concepts)}*",
        "",
        "## Sources",
        "",
    ]

    for sd in source_data:
        source_id = sd.get("id", "unknown")
        title = sd.get("title", source_id)
        lines.append(f"- [[source-{source_id}|{title}]]")
    lines.append("")

    # Top concepts
    top_concepts = sorted(concepts, key=lambda c: -c.get("source_count", 0))[:15]
    if top_concepts:
        lines.append("## Key Concepts")
        lines.append("")
        for c in top_concepts:
            name = c["canonical_name"]
            count = c.get("source_count", 0)
            lines.append(f"- **{name}** ({count} sources)")
        lines.append("")

    # Article listing by category
    categories: dict[str, list[str]] = {}
    for a in articles:
        slug = a["path"].split("/")[-1].replace(".md", "")
        cat = a["path"].split("/")[-2] if "/" in a["path"].rsplit("/", 1)[0] else "general"
        categories.setdefault(cat, []).append(slug)

    if categories:
        lines.append("## Articles by Category")
        lines.append("")
        for cat, slugs in sorted(categories.items()):
            lines.append(f"### {cat.title()}")
            for s in slugs:
                lines.append(f"- [[{s}]]")
            lines.append("")

    # Cross-source themes from summaries
    all_concepts_flat: dict[str, int] = {}
    for s in summaries:
        for c in s.get("concepts", []):
            all_concepts_flat[c.lower()] = all_concepts_flat.get(c.lower(), 0) + 1
    if not all_concepts_flat:
        for concept in concepts:
            canonical = str(concept.get("canonical_name", "")).strip().lower()
            if canonical:
                all_concepts_flat[canonical] = int(concept.get("source_count", 0))
    themes = sorted(all_concepts_flat.items(), key=lambda x: -x[1])[:10]
    if themes:
        lines.append("## Cross-Source Themes")
        lines.append("")
        for theme, count in themes:
            lines.append(f"- **{theme}** (appears in {count} sources)")
        lines.append("")

    return "\n".join(lines) + "\n"


def _append_log(log_path: Path, entry: str) -> None:
    """Append an entry to log.md (creates file with header if needed)."""
    header = (
        "---\n"
        'title: "Wiki Log"\n'
        'id: "log"\n'
        'category: "meta"\n'
        'type: "log"\n'
        'origin: "system"\n'
        'status: "published"\n'
        "---\n\n"
        "# Wiki Log\n\n"
        "Chronological record of all wiki operations.\n\n"
    )
    if not log_path.exists():
        log_path.write_text(header)
    elif not log_path.read_text().startswith("---"):
        log_path.write_text(header + log_path.read_text())
    with open(log_path, "a") as f:
        f.write(entry)


def _sum_checkpoint_tokens(checkpoint: CompilationCheckpoint) -> tuple[int, int]:
    """Sum input/output tokens across all checkpoint steps."""
    total_in = 0
    total_out = 0
    for step in checkpoint.steps.values():
        total_in += step.tokens_used.input_tokens
        total_out += step.tokens_used.output_tokens
    return total_in, total_out


def _generate_schema_md(template: str = "research", domain: str = "") -> str:
    """Generate SCHEMA.md documenting the wiki format."""
    return generate_schema_md(template, domain)
