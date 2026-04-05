"""Persistent compile/update sessions for interactive and batch workflows."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Literal
from uuid import uuid4

import frontmatter
from pydantic import BaseModel, Field

from compendium.core.templates import generate_schema_md
from compendium.pipeline.controller import (
    _generate_overview,
    _get_source_concepts,
    _load_source_data,
    _write_source_summary_pages,
    compile_wiki,
    incremental_update,
)
from compendium.pipeline.deps import (
    ArticleEntry,
    ConceptEntry,
    DependencyGraph,
    SourceEntry,
)
from compendium.pipeline.steps import (
    _parse_json_response,
    build_log_entry,
    step_build_index,
    step_create_backlinks,
    step_detect_conflicts,
    step_extract_concepts,
    step_generate_articles,
)

if TYPE_CHECKING:
    from pathlib import Path

    from compendium.core.config import CompendiumConfig
    from compendium.core.wiki_fs import WikiFileSystem
    from compendium.llm.prompts import PromptLoader
    from compendium.llm.provider import LlmProvider


SessionKind = Literal["compile", "update"]
SessionMode = Literal["interactive", "batch"]
SessionStatus = Literal["running", "awaiting_approval", "completed", "cancelled", "failed"]


class SessionSummary(BaseModel):
    """Persisted session envelope returned by CLI and API surfaces."""

    session_id: str
    kind: SessionKind
    mode: SessionMode
    status: SessionStatus
    created_at: str
    updated_at: str
    branch: str | None = None
    source_count: int = 0
    current_index: int = 0
    sources: list[dict[str, str]] = Field(default_factory=list)
    pending_source: dict[str, str] | None = None
    pending_summary: dict[str, Any] | None = None
    approved_summaries: list[dict[str, Any]] = Field(default_factory=list)
    result: dict[str, Any] | None = None
    error: str | None = None
    audit_log_path: str | None = None


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _sessions_dir(wfs: WikiFileSystem) -> Path:
    path = wfs.staging_dir / "sessions"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _session_path(wfs: WikiFileSystem, session_id: str) -> Path:
    return _sessions_dir(wfs) / f"{session_id}.json"


def _audit_path(wfs: WikiFileSystem, session_id: str) -> Path:
    wfs.compilation_log_dir.mkdir(parents=True, exist_ok=True)
    return wfs.compilation_log_dir / f"{session_id}.jsonl"


def _write_audit(path: Path, event: str, payload: dict[str, Any]) -> None:
    record = {
        "timestamp": _now_iso(),
        "event": event,
        **payload,
    }
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=True) + "\n")


def _save_session(wfs: WikiFileSystem, session: SessionSummary) -> SessionSummary:
    session.updated_at = _now_iso()
    _session_path(wfs, session.session_id).write_text(session.model_dump_json(indent=2))
    return session


def load_session(wfs: WikiFileSystem, session_id: str) -> SessionSummary | None:
    """Load a persisted session if it exists."""
    path = _session_path(wfs, session_id)
    if not path.exists():
        return None
    return SessionSummary.model_validate_json(path.read_text())


def _raw_source_descriptor(wfs: WikiFileSystem, raw_path: Path) -> dict[str, str]:
    post = frontmatter.load(str(raw_path))
    source_id = post.metadata.get("id", raw_path.stem)
    return {
        "id": str(source_id),
        "title": str(post.metadata.get("title", raw_path.stem)),
        "word_count": str(post.metadata.get("word_count", len(post.content.split()))),
        "path": str(raw_path.relative_to(wfs.root)),
    }


def _resolve_raw_paths(
    wfs: WikiFileSystem,
    raw_paths: list[Path] | None = None,
) -> list[Path]:
    if raw_paths is None:
        return wfs.list_raw_sources()

    resolved: list[Path] = []
    for path in raw_paths:
        candidate = path if path.is_absolute() else (wfs.root / path)
        if not candidate.exists():
            candidate = wfs.raw_dir / path.name
        if candidate.exists():
            resolved.append(candidate.resolve())
    return sorted(dict.fromkeys(resolved))


async def _summarize_single_source(
    wfs: WikiFileSystem,
    source: dict[str, str],
    llm: LlmProvider,
    prompt_loader: PromptLoader,
    audit_log_path: Path,
) -> dict[str, Any]:
    from compendium.llm.provider import CompletionRequest, Message

    raw_path = wfs.root / source["path"]
    post = frontmatter.load(str(raw_path))
    template = prompt_loader.load("summarize")
    schema_context = wfs.schema_context()
    prompt = template.render(
        schema_context=schema_context,
        title=source["title"],
        word_count=source["word_count"],
        content=post.content,
        source_id=source["id"],
    )

    _write_audit(
        audit_log_path,
        "summarize_prompt",
        {
            "source_id": source["id"],
            "title": source["title"],
            "path": source["path"],
            "prompt": prompt,
        },
    )

    response = await llm.complete(
        CompletionRequest(
            messages=[Message(role="user", content=prompt)],
            system_prompt="You are a research summarization engine. Respond only with valid JSON.",
            max_tokens=2000,
            temperature=0.2,
        )
    )

    _write_audit(
        audit_log_path,
        "summarize_response",
        {
            "source_id": source["id"],
            "model": response.model,
            "usage": {
                "input_tokens": response.usage.input_tokens,
                "output_tokens": response.usage.output_tokens,
            },
            "content": response.content,
        },
    )

    try:
        summary = _parse_json_response(response.content)
        if isinstance(summary, list):
            return dict(summary[0]) if summary else {}
        return dict(summary)
    except (json.JSONDecodeError, TypeError, ValueError):
        fallback = {
            "source": source["id"],
            "title": source["title"],
            "summary": response.content[:500],
            "claims": [],
            "concepts": [],
            "findings": [],
            "limitations": [],
        }
        _write_audit(
            audit_log_path,
            "summarize_fallback",
            {
                "source_id": source["id"],
                "summary": fallback,
            },
        )
        return fallback


async def _finalize_compile_from_summaries(
    wfs: WikiFileSystem,
    config: CompendiumConfig,
    llm: LlmProvider,
    prompt_loader: PromptLoader,
    source_data: list[dict[str, str]],
    summaries: list[dict[str, Any]],
    audit_log_path: Path,
) -> dict[str, Any]:
    wfs.clear_staging()
    schema_context = wfs.schema_context()

    source_contents: dict[str, str] = {}
    for source in source_data:
        raw_path = wfs.root / source["path"]
        post = frontmatter.load(str(raw_path))
        source_contents[source["id"]] = post.content

    concepts = await step_extract_concepts(
        summaries,
        llm,
        prompt_loader,
        schema_context=schema_context,
    )
    _write_audit(
        audit_log_path,
        "extract_concepts_complete",
        {"concept_count": len(concepts)},
    )

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
    _write_audit(
        audit_log_path,
        "generate_articles_complete",
        {"article_count": len(articles)},
    )

    articles = step_create_backlinks(articles, concepts)
    index_files = step_build_index(articles, concepts, "Interactive compile")
    conflicts_md = await step_detect_conflicts(
        articles,
        concepts,
        summaries,
        llm,
        prompt_loader,
        schema_context=schema_context,
    )

    if wfs.list_wiki_articles():
        wfs.create_backup()

    for article in articles:
        article_path = wfs.staging_dir / article["path"].removeprefix("wiki/")
        article_path.parent.mkdir(parents=True, exist_ok=True)
        article_path.write_text(article["content"])

    _write_source_summary_pages(wfs.staging_dir, summaries)

    overview = _generate_overview(articles, concepts, summaries, _load_source_data(wfs))
    (wfs.staging_dir / "overview.md").write_text(overview)

    for filename, content in index_files.items():
        (wfs.staging_dir / filename).write_text(content)

    (wfs.staging_dir / "CONFLICTS.md").write_text(conflicts_md)
    (wfs.staging_dir / "SCHEMA.md").write_text(
        generate_schema_md(config.templates.default, config.templates.domain)
    )

    wfs.promote_staging()
    wfs.append_log_entry(
        build_log_entry(
            "compile",
            articles_count=len(articles),
            concepts_count=len(concepts),
            sources_count=len(source_data),
            notes="mode: interactive",
        )
    )
    deps = DependencyGraph()
    for source in source_data:
        raw_path = wfs.root / source["path"]
        deps.sources[source["path"]] = SourceEntry(
            content_hash=wfs.content_hash(raw_path),
            compiled_at=_now_iso(),
            concepts=[c.lower() for c in _get_source_concepts(source["id"], summaries)],
        )

    for article in articles:
        path = article["path"]
        try:
            post = frontmatter.loads(article["content"])
            sources_list = [
                source.get("ref", "") if isinstance(source, dict) else str(source)
                for source in post.metadata.get("sources", [])
            ]
        except Exception:
            sources_list = []

        deps.articles[path] = ArticleEntry(
            depends_on=sources_list,
            content_hash=f"sha256:{hashlib.sha256(article['content'].encode('utf-8')).hexdigest()}",
            word_count=len(article["content"].split()),
            origin="compilation",
            last_compiled=_now_iso(),
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

    wfs.auto_commit("[rebuild]: interactive compile wiki", paths=[wfs.wiki_dir, wfs.deps_path])

    result = {
        "articles_count": len(articles),
        "concepts_count": len(concepts),
        "conflicts_detected": 0 if "No conflicts detected" in conflicts_md else 1,
        "sources_processed": len(source_data),
        "mode": "interactive",
    }
    _write_audit(audit_log_path, "compile_complete", result)
    return result


async def start_compile_session(
    wfs: WikiFileSystem,
    config: CompendiumConfig,
    llm: LlmProvider,
    prompt_loader: PromptLoader,
    mode: SessionMode = "batch",
    branch: str | None = None,
) -> SessionSummary:
    """Start a compile session and persist its state."""
    session_id = f"compile-{uuid4().hex[:10]}"
    audit_log_path = _audit_path(wfs, session_id)

    if branch and not wfs.checkout_branch(branch):
        session = SessionSummary(
            session_id=session_id,
            kind="compile",
            mode=mode,
            status="failed",
            created_at=_now_iso(),
            updated_at=_now_iso(),
            branch=branch,
            error=f"Could not switch to branch '{branch}'",
            audit_log_path=str(audit_log_path.relative_to(wfs.root)),
        )
        _write_audit(audit_log_path, "branch_error", {"branch": branch})
        return _save_session(wfs, session)

    raw_paths = _resolve_raw_paths(wfs)
    source_data = [_raw_source_descriptor(wfs, path) for path in raw_paths]

    session = SessionSummary(
        session_id=session_id,
        kind="compile",
        mode=mode,
        status="running",
        created_at=_now_iso(),
        updated_at=_now_iso(),
        branch=branch,
        source_count=len(source_data),
        sources=source_data,
        audit_log_path=str(audit_log_path.relative_to(wfs.root)),
    )
    _write_audit(
        audit_log_path,
        "session_created",
        {
            "kind": "compile",
            "mode": mode,
            "branch": branch,
            "source_count": len(source_data),
        },
    )

    if not source_data:
        session.status = "failed"
        session.error = "No raw sources found in raw/"
        _write_audit(audit_log_path, "session_failed", {"error": session.error})
        return _save_session(wfs, session)

    if mode == "batch":
        try:
            result = await compile_wiki(wfs, config, llm, prompt_loader)
            session.result = result
            session.status = "failed" if "error" in result else "completed"
            session.error = result.get("error")
            _write_audit(audit_log_path, "batch_compile_complete", {"result": result})
        except Exception as exc:  # pragma: no cover - defensive
            session.status = "failed"
            session.error = str(exc)
            _write_audit(audit_log_path, "session_failed", {"error": str(exc)})
        return _save_session(wfs, session)

    try:
        first_source = source_data[0]
        session.pending_source = first_source
        session.pending_summary = await _summarize_single_source(
            wfs,
            first_source,
            llm,
            prompt_loader,
            audit_log_path,
        )
        session.current_index = 0
        session.status = "awaiting_approval"
    except Exception as exc:  # pragma: no cover - defensive
        session.status = "failed"
        session.error = str(exc)
        _write_audit(audit_log_path, "session_failed", {"error": str(exc)})

    return _save_session(wfs, session)


async def approve_compile_session(
    wfs: WikiFileSystem,
    session_id: str,
    config: CompendiumConfig,
    llm: LlmProvider,
    prompt_loader: PromptLoader,
    approve: bool = True,
    summary_override: dict[str, Any] | None = None,
) -> SessionSummary:
    """Approve the current interactive summary and advance the session."""
    session = load_session(wfs, session_id)
    if session is None:
        msg = f"Session not found: {session_id}"
        raise FileNotFoundError(msg)

    audit_log_path = _audit_path(wfs, session_id)

    if session.status != "awaiting_approval" or session.pending_summary is None:
        return session

    if not approve and summary_override is None:
        session.status = "cancelled"
        session.error = "Session cancelled during summary approval."
        _write_audit(audit_log_path, "summary_rejected", {"index": session.current_index})
        return _save_session(wfs, session)

    accepted_summary = summary_override or session.pending_summary
    session.approved_summaries.append(accepted_summary)
    _write_audit(
        audit_log_path,
        "summary_approved",
        {
            "index": session.current_index,
            "source_id": session.pending_source.get("id") if session.pending_source else None,
        },
    )

    next_index = session.current_index + 1
    if next_index < len(session.sources):
        next_source = session.sources[next_index]
        session.current_index = next_index
        session.pending_source = next_source
        session.pending_summary = await _summarize_single_source(
            wfs,
            next_source,
            llm,
            prompt_loader,
            audit_log_path,
        )
        session.status = "awaiting_approval"
        return _save_session(wfs, session)

    session.pending_source = None
    session.pending_summary = None
    session.status = "running"
    _save_session(wfs, session)

    try:
        session.result = await _finalize_compile_from_summaries(
            wfs,
            config,
            llm,
            prompt_loader,
            session.sources,
            session.approved_summaries,
            audit_log_path,
        )
        session.status = "completed"
        session.error = None
    except Exception as exc:  # pragma: no cover - defensive
        session.status = "failed"
        session.error = str(exc)
        _write_audit(audit_log_path, "session_failed", {"error": str(exc)})

    return _save_session(wfs, session)


async def start_update_session(
    wfs: WikiFileSystem,
    config: CompendiumConfig,
    llm: LlmProvider,
    prompt_loader: PromptLoader,
    new_source_paths: list[Path] | None = None,
    branch: str | None = None,
) -> SessionSummary:
    """Start a batch incremental update session."""
    session_id = f"update-{uuid4().hex[:10]}"
    audit_log_path = _audit_path(wfs, session_id)

    if branch and not wfs.checkout_branch(branch):
        session = SessionSummary(
            session_id=session_id,
            kind="update",
            mode="batch",
            status="failed",
            created_at=_now_iso(),
            updated_at=_now_iso(),
            branch=branch,
            error=f"Could not switch to branch '{branch}'",
            audit_log_path=str(audit_log_path.relative_to(wfs.root)),
        )
        _write_audit(audit_log_path, "branch_error", {"branch": branch})
        return _save_session(wfs, session)

    resolved_paths = _resolve_raw_paths(wfs, new_source_paths) if new_source_paths else None
    source_data = [_raw_source_descriptor(wfs, path) for path in resolved_paths or []]

    session = SessionSummary(
        session_id=session_id,
        kind="update",
        mode="batch",
        status="running",
        created_at=_now_iso(),
        updated_at=_now_iso(),
        branch=branch,
        source_count=len(source_data),
        sources=source_data,
        audit_log_path=str(audit_log_path.relative_to(wfs.root)),
    )
    _write_audit(
        audit_log_path,
        "session_created",
        {
            "kind": "update",
            "mode": "batch",
            "branch": branch,
            "sources": [item["path"] for item in source_data],
            "all_new": resolved_paths is None,
        },
    )

    try:
        result = await incremental_update(
            wfs,
            config,
            llm,
            prompt_loader,
            new_source_paths=resolved_paths,
        )
        session.result = result
        session.status = "failed" if "error" in result else "completed"
        session.error = result.get("error")
        _write_audit(audit_log_path, "update_complete", {"result": result})
    except Exception as exc:  # pragma: no cover - defensive
        session.status = "failed"
        session.error = str(exc)
        _write_audit(audit_log_path, "session_failed", {"error": str(exc)})

    return _save_session(wfs, session)
