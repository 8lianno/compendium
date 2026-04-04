"""FastAPI local server — web UI backend, browser extension endpoint, progress WebSocket."""

from __future__ import annotations

import asyncio
import contextlib
import tempfile
from pathlib import Path
from typing import Annotated
from urllib.parse import unquote

from fastapi import FastAPI, File, Form, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from compendium import __version__
from compendium.core.config import CompendiumConfig
from compendium.core.wiki_fs import WikiFileSystem

UPLOAD_FILES_PARAM = File(...)


def create_app(project_dir: str | None = None) -> FastAPI:
    """Create and configure the FastAPI application."""
    root = Path(project_dir) if project_dir else Path.cwd()
    config = CompendiumConfig.load(root / "compendium.toml")
    wfs = WikiFileSystem(root)

    app = FastAPI(
        title="Compendium",
        description="LLM-native knowledge compiler",
        version=__version__,
    )

    # Store references for dependency injection
    app.state.config = config
    app.state.wfs = wfs
    app.state.lint_task = None

    def provider_saved(provider: str) -> bool:
        from compendium.llm.factory import get_api_key

        return bool(get_api_key(provider))

    def _safe_path(raw_path: str) -> Path | None:
        if not raw_path:
            return None

        normalized = unquote(raw_path).strip()
        if not normalized or normalized.startswith("/"):
            return None
        if any(part == ".." for part in Path(normalized).parts):
            return None

        candidate = (root / normalized).resolve()
        if not candidate.is_relative_to(root):
            return None
        return candidate

    def _pricing_payload(provider: object) -> dict[str, float] | None:
        pricing = getattr(provider, "pricing", None)
        if pricing is None:
            return None
        return {
            "input_per_million": float(pricing.input_per_million),
            "output_per_million": float(pricing.output_per_million),
        }

    def _model_details(model_config: object) -> dict[str, object]:
        from compendium.core.config import ModelConfig
        from compendium.llm.factory import create_provider

        if not isinstance(model_config, ModelConfig):
            return {"error": "Invalid model configuration"}

        details: dict[str, object] = {
            "provider": model_config.provider,
            "model": model_config.model,
            "endpoint": model_config.endpoint,
            "saved": provider_saved(model_config.provider) or model_config.provider == "ollama",
            "context_window": None,
            "pricing": None,
            "error": None,
        }

        try:
            provider = create_provider(model_config)
        except ValueError as exc:
            details["error"] = str(exc)
            return details

        details["context_window"] = getattr(provider, "context_window", None)
        details["pricing"] = _pricing_payload(provider)
        return details

    def _settings_payload() -> dict[str, object]:
        current_config: CompendiumConfig = app.state.config
        return {
            "models": current_config.models.model_dump(mode="json"),
            "templates": current_config.templates.model_dump(mode="json"),
            "lint": current_config.lint.model_dump(mode="json"),
            "providers": {
                "anthropic": {"saved": provider_saved("anthropic")},
                "openai": {"saved": provider_saved("openai")},
                "gemini": {"saved": provider_saved("gemini")},
                "ollama": {"saved": True},
            },
            "operations": {
                "default_provider": current_config.models.default_provider,
                "compilation": _model_details(current_config.models.compilation),
                "qa": _model_details(current_config.models.qa),
                "lint": _model_details(current_config.models.lint),
            },
        }

    def _decorate_missing_data_suggestions(report: object) -> None:
        if not app.state.config.lint.missing_data_web_search:
            return

        issues = getattr(report, "issues", [])
        for issue in issues:
            suggestion = getattr(issue, "suggestion", "")
            location = getattr(issue, "location", "")
            query = location.replace(".md", "").replace("-", " ").strip() or "missing data"
            search_url = f"https://www.google.com/search?q={query.replace(' ', '+')}"
            if suggestion:
                issue.suggestion = f"{suggestion} Research lead: {search_url}"
            else:
                issue.suggestion = f"Research lead: {search_url}"

    def _lint_response_payload(report: object, reason: str) -> dict[str, object]:
        return {
            "total": report.total,
            "critical": report.critical_count,
            "warning": report.warning_count,
            "info": report.info_count,
            "reason": reason,
            "issues": [
                {
                    "severity": issue.severity,
                    "category": issue.category,
                    "location": issue.location,
                    "description": issue.description,
                    "suggestion": issue.suggestion,
                }
                for issue in report.issues
            ],
        }

    def _run_lint(reason: str = "manual") -> dict[str, object]:
        from compendium.lint.engine import lint_wiki
        from compendium.pipeline.steps import build_log_entry

        report = lint_wiki(wfs.wiki_dir, raw_dir=wfs.raw_dir)
        _decorate_missing_data_suggestions(report)

        report_path = wfs.wiki_dir / "HEALTH_REPORT.md"
        report_path.write_text(report.to_markdown())
        wfs.append_log_entry(
            build_log_entry(
                "lint",
                title="Scheduled lint" if reason != "manual" else "Lint run",
                notes=(
                    f"reason: {reason}; {report.critical_count} critical, "
                    f"{report.warning_count} warning, {report.info_count} info"
                ),
            )
        )
        wfs.auto_commit(
            "[lint]: refresh health report",
            paths=[report_path, wfs.wiki_dir / "log.md"],
        )
        return _lint_response_payload(report, reason)

    def _schedule_seconds(schedule: str) -> int | None:
        return {
            "manual": None,
            "daily": 24 * 60 * 60,
            "weekly": 7 * 24 * 60 * 60,
        }.get(schedule)

    async def _scheduled_lint_loop(interval_seconds: int) -> None:
        while True:
            await asyncio.sleep(interval_seconds)
            with contextlib.suppress(Exception):
                _run_lint(reason=app.state.config.lint.schedule)

    def _restart_lint_schedule() -> None:
        existing = app.state.lint_task
        if existing is not None:
            existing.cancel()
            app.state.lint_task = None

        interval = _schedule_seconds(app.state.config.lint.schedule)
        if interval is None:
            return

        app.state.lint_task = asyncio.create_task(_scheduled_lint_loop(interval))

    def _save_settings(data: dict) -> dict[str, object]:
        from compendium.core.config import LintConfig, ModelConfig, TemplateConfig
        from compendium.core.templates import generate_schema_md, template_ids
        from compendium.pipeline.steps import build_log_entry

        current_config: CompendiumConfig = app.state.config
        changed_items: list[str] = []
        commit_paths: list[Path] = [wfs.config_path]

        model_payload = data.get("models", data)
        for field in ("compilation", "qa"):
            if field in model_payload:
                new_value = ModelConfig.model_validate(model_payload[field])
                if getattr(current_config.models, field) != new_value:
                    setattr(current_config.models, field, new_value)
                    changed_items.append(field)

        if "lint_model" in data:
            new_lint_model = ModelConfig.model_validate(data["lint_model"])
            if current_config.models.lint != new_lint_model:
                current_config.models.lint = new_lint_model
                changed_items.append("lint-model")
        elif isinstance(model_payload.get("lint"), dict) and "provider" in model_payload["lint"]:
            new_lint_model = ModelConfig.model_validate(model_payload["lint"])
            if current_config.models.lint != new_lint_model:
                current_config.models.lint = new_lint_model
                changed_items.append("lint-model")

        if (
            "default_provider" in data
            and data["default_provider"] != current_config.models.default_provider
        ):
            current_config.models.default_provider = str(data["default_provider"])
            changed_items.append("default-provider")

        if "templates" in data:
            new_templates = TemplateConfig.model_validate(data["templates"])
            if new_templates.default not in template_ids():
                msg = f"Unknown template: {new_templates.default}"
                raise ValueError(msg)
            if current_config.templates != new_templates:
                current_config.templates = new_templates
                changed_items.append("templates")
                schema_path = wfs.wiki_dir / "SCHEMA.md"
                schema_path.write_text(
                    generate_schema_md(new_templates.default, new_templates.domain)
                )
                commit_paths.append(schema_path)
                wfs.refresh_search_index()

        lint_payload = data.get("lint_settings")
        if (
            lint_payload is None
            and isinstance(data.get("lint"), dict)
            and "provider" not in data["lint"]
        ):
            lint_payload = data["lint"]
        if lint_payload is not None:
            new_lint = LintConfig.model_validate(lint_payload)
            if new_lint.schedule not in {"manual", "daily", "weekly"}:
                msg = f"Unsupported lint schedule: {new_lint.schedule}"
                raise ValueError(msg)
            if current_config.lint != new_lint:
                current_config.lint = new_lint
                changed_items.append("lint-settings")

        current_config.save(wfs.config_path)
        app.state.config = current_config

        if changed_items:
            wfs.append_log_entry(
                build_log_entry(
                    "schema-update",
                    title="Settings updated",
                    notes=f"changed: {', '.join(changed_items)}",
                )
            )
            commit_paths.append(wfs.wiki_dir / "log.md")
            wfs.auto_commit(
                f"[schema-update]: update settings ({', '.join(changed_items)})",
                paths=commit_paths,
            )

        _restart_lint_schedule()
        return {
            "status": "saved",
            "changed": changed_items,
            **_settings_payload(),
        }

    # -- API Routes --

    @app.get("/api/health")
    async def health() -> dict:
        return {
            "status": "ok",
            "version": __version__,
            "project": config.project.name,
        }

    @app.get("/api/status")
    async def status() -> dict:
        raw_sources = wfs.list_raw_sources()
        wiki_articles = wfs.list_wiki_articles()
        return {
            "project_name": config.project.name,
            "raw_source_count": len(raw_sources),
            "wiki_article_count": len(wiki_articles),
            "default_provider": config.models.default_provider,
        }

    @app.get("/api/sources")
    async def list_sources() -> list[dict]:
        sources = wfs.list_raw_sources()
        return [{"name": s.name, "path": str(s.relative_to(root))} for s in sources]

    @app.get("/api/articles")
    async def list_articles() -> list[dict]:
        articles = wfs.list_wiki_articles()
        return [{"name": a.name, "path": str(a.relative_to(root))} for a in articles]

    @app.get("/api/article/{path:path}")
    async def read_article(path: str) -> JSONResponse:
        article_path = _safe_path(path)
        if article_path is None:
            return JSONResponse({"error": "Invalid path"}, status_code=400)
        if not article_path.exists() or not article_path.is_file():
            return JSONResponse({"error": "Article not found"}, status_code=404)
        return JSONResponse(
            {
                "path": path,
                "content": article_path.read_text(),
            }
        )

    # -- Q&A API --

    @app.post("/api/ask")
    async def api_ask(data: dict) -> JSONResponse:
        from compendium.llm.factory import create_provider
        from compendium.llm.prompts import PromptLoader
        from compendium.pipeline.steps import build_log_entry
        from compendium.qa.engine import ask_question
        from compendium.qa.filing import file_to_wiki
        from compendium.qa.output import (
            render_chart_bundle,
            render_html,
            render_report,
            render_slides,
        )
        from compendium.qa.session import ConversationSession

        question = data.get("question", "")
        if not question:
            return JSONResponse({"error": "Missing question"}, status_code=400)

        try:
            llm = create_provider(config.models.qa)
        except ValueError as e:
            return JSONResponse({"error": str(e)}, status_code=500)

        prompt_loader = PromptLoader(project_prompts_dir=root / "prompts")
        session_dir = root / ".sessions"
        session_id = data.get("session_id", "web-default")
        session = ConversationSession.load(session_id, session_dir)

        result = await ask_question(question, wfs.wiki_dir, llm, prompt_loader, session)
        output_type = data.get("output", "text")
        if output_type not in {"text", "report", "slides", "html", "chart", "canvas"}:
            return JSONResponse(
                {"error": f"Unsupported output type: {output_type}"},
                status_code=400,
            )
        output_path = None
        extra_paths: list[str] = []
        if output_type == "report":
            output_path = render_report(
                question,
                result["answer"],
                result["sources_used"],
                result.get("tokens_used", 0),
                wfs.output_dir,
            )
        elif output_type == "slides":
            output_path = render_slides(
                question,
                result["answer"],
                result["sources_used"],
                wfs.output_dir,
                slide_count=int(data.get("count", 10)),
            )
        elif output_type == "html":
            output_path = render_html(
                question,
                result["answer"],
                result["sources_used"],
                wfs.output_dir,
            )
        elif output_type == "chart":
            png_path, note_path = render_chart_bundle(
                question,
                result["answer"],
                result["sources_used"],
                wfs.output_dir,
            )
            output_path = note_path
            if png_path:
                extra_paths.append(str(png_path.relative_to(root)))

        if question:
            notes = (
                f"Output: {output_type}; "
                f"articles loaded: {result.get('articles_loaded', 0)}"
            )
            wfs.append_log_entry(
                build_log_entry(
                    "query",
                    title=question[:80],
                    notes=notes,
                )
            )

        if data.get("file") and output_path is not None:
            filing_result = file_to_wiki(
                output_path,
                wfs,
                resolution=data.get("resolution"),
            )
            result["filing"] = filing_result

        if output_path is not None:
            result["output_path"] = str(output_path.relative_to(root))
        if extra_paths:
            result["extra_paths"] = extra_paths
        result["output"] = output_type
        return JSONResponse(result)

    @app.post("/api/file-to-wiki")
    async def api_file_to_wiki(data: dict) -> JSONResponse:
        from compendium.qa.filing import file_to_wiki

        report_path = _safe_path(str(data.get("path", "")))
        if report_path is None:
            return JSONResponse({"error": "Invalid path"}, status_code=400)
        if not report_path.exists():
            return JSONResponse({"error": "File not found"}, status_code=404)

        result = file_to_wiki(report_path, wfs, resolution=data.get("resolution"))
        return JSONResponse(result)

    @app.get("/api/download/{path:path}")
    async def api_download(path: str):
        if Path(unquote(path)).parts[:1] not in (("output",), ("wiki",), ("raw",)):
            return JSONResponse({"error": "Invalid path"}, status_code=400)
        download_path = _safe_path(path)
        if download_path is None:
            return JSONResponse({"error": "Invalid path"}, status_code=400)
        if not download_path.exists() or not download_path.is_file():
            return JSONResponse({"error": "File not found"}, status_code=404)
        return FileResponse(str(download_path), filename=download_path.name)

    @app.post("/api/output-render")
    async def api_output_render(data: dict) -> JSONResponse:
        from compendium.qa.output import (
            render_chart_bundle,
            render_html,
            render_report,
            render_slides,
        )

        query = data.get("query", "Output")
        answer = data.get("answer", "")
        sources_used = data.get("sources_used", [])
        output_type = data.get("output", "report")
        output_path: Path | None = None
        extra_paths: list[str] = []

        if output_type == "report":
            output_path = render_report(query, answer, sources_used, 0, wfs.output_dir)
        elif output_type == "slides":
            output_path = render_slides(query, answer, sources_used, wfs.output_dir)
        elif output_type == "html":
            output_path = render_html(query, answer, sources_used, wfs.output_dir)
        elif output_type == "chart":
            png_path, note_path = render_chart_bundle(query, answer, sources_used, wfs.output_dir)
            output_path = note_path
            if png_path:
                extra_paths.append(str(png_path.relative_to(root)))
        else:
            return JSONResponse(
                {"error": f"Unsupported output type: {output_type}"},
                status_code=400,
            )

        return JSONResponse(
            {
                "output": output_type,
                "output_path": str(output_path.relative_to(root)),
                "extra_paths": extra_paths,
            }
        )

    @app.post("/api/ingest/upload")
    async def api_ingest_upload(
        files: Annotated[list[UploadFile], UPLOAD_FILES_PARAM],
        duplicate_mode: Annotated[str, Form()] = "keep_both",
    ) -> JSONResponse:
        from compendium.ingest.file_drop import ingest_batch
        from compendium.pipeline.steps import build_log_entry

        saved_paths: list[Path] = []
        with tempfile.TemporaryDirectory(prefix="compendium-upload-", dir=str(root)) as temp_dir:
            temp_root = Path(temp_dir)
            for upload in files:
                target = temp_root / upload.filename
                target.write_bytes(await upload.read())
                saved_paths.append(target)

            result = ingest_batch(
                saved_paths,
                raw_dir=wfs.raw_dir,
                images_dir=wfs.raw_images_dir,
                originals_dir=wfs.raw_originals_dir,
                duplicate_mode=duplicate_mode,
            )

        wfs.append_log_entry(
            build_log_entry(
                "ingest",
                title="Batch upload",
                sources_count=result.succeeded,
                notes=f"Failed: {result.failed}",
            )
        )
        wfs.auto_commit("[ingest]: upload raw sources", paths=[wfs.raw_dir])

        return JSONResponse(
            {
                "total": result.total,
                "succeeded": result.succeeded,
                "failed": result.failed,
                "duplicate_mode": duplicate_mode,
                "results": [
                    {
                        "source_path": r.source_path.name,
                        "output_path": str(r.output_path.relative_to(root))
                        if r.output_path and r.output_path.exists()
                        else None,
                        "success": r.success,
                        "message": r.message,
                        "duplicate_of": r.duplicate_of,
                        "ocr_confidence": r.ocr_confidence,
                    }
                    for r in result.results
                ],
            }
        )

    # -- Usage API --

    @app.get("/api/usage")
    async def api_usage() -> JSONResponse:
        from compendium.llm.tokens import TokenTracker

        tracker = TokenTracker()
        return JSONResponse(
            {
                "summary": tracker.get_monthly_summary(),
                "breakdown": tracker.get_operation_breakdown(),
            }
        )

    @app.get("/api/settings")
    async def api_settings() -> JSONResponse:
        return JSONResponse(_settings_payload())

    @app.post("/api/settings/model-assignments")
    async def api_settings_model_assignments(data: dict) -> JSONResponse:
        try:
            return JSONResponse(_save_settings(data))
        except ValueError as exc:
            return JSONResponse({"error": str(exc)}, status_code=400)

    @app.post("/api/settings/test-provider")
    async def api_settings_test_provider(data: dict) -> JSONResponse:
        from compendium.core.config import ModelConfig
        from compendium.llm.factory import create_provider

        try:
            provider = create_provider(ModelConfig.model_validate(data))
        except ValueError as exc:
            return JSONResponse({"ok": False, "error": str(exc)}, status_code=400)
        ok = await provider.test_connection()
        return JSONResponse(
            {
                "ok": ok,
                "provider": provider.name,
                "model": provider.model_name,
                "context_window": provider.context_window,
                "pricing": _pricing_payload(provider),
            }
        )

    @app.post("/api/settings/key")
    async def api_settings_save_key(data: dict) -> JSONResponse:
        from compendium.llm.factory import delete_api_key, set_api_key

        provider = data.get("provider", "")
        key = data.get("key")
        if not provider:
            return JSONResponse({"error": "Missing provider"}, status_code=400)
        if key:
            set_api_key(provider, key)
            return JSONResponse({"status": "saved"})
        delete_api_key(provider)
        return JSONResponse({"status": "deleted"})

    @app.post("/api/compile/session")
    async def api_start_compile_session(data: dict) -> JSONResponse:
        from compendium.llm.factory import create_provider
        from compendium.llm.prompts import PromptLoader
        from compendium.pipeline.sessions import start_compile_session

        mode = str(data.get("mode", "batch"))
        if mode not in {"batch", "interactive"}:
            return JSONResponse({"error": f"Unsupported mode: {mode}"}, status_code=400)

        try:
            provider = create_provider(app.state.config.models.compilation)
        except ValueError as exc:
            return JSONResponse({"error": str(exc)}, status_code=400)

        prompt_loader = PromptLoader(project_prompts_dir=wfs.root / "prompts")
        session = await start_compile_session(
            wfs,
            app.state.config,
            provider,
            prompt_loader,
            mode=mode,
            branch=data.get("branch"),
        )
        return JSONResponse(session.model_dump(mode="json"))

    @app.get("/api/compile/session/{session_id}")
    async def api_get_compile_session(session_id: str) -> JSONResponse:
        from compendium.pipeline.sessions import load_session

        session = load_session(wfs, session_id)
        if session is None or session.kind != "compile":
            return JSONResponse({"error": "Session not found"}, status_code=404)
        return JSONResponse(session.model_dump(mode="json"))

    @app.post("/api/compile/session/{session_id}/approve")
    async def api_approve_compile_session(session_id: str, data: dict) -> JSONResponse:
        from compendium.llm.factory import create_provider
        from compendium.llm.prompts import PromptLoader
        from compendium.pipeline.sessions import approve_compile_session

        try:
            provider = create_provider(app.state.config.models.compilation)
        except ValueError as exc:
            return JSONResponse({"error": str(exc)}, status_code=400)

        prompt_loader = PromptLoader(project_prompts_dir=wfs.root / "prompts")
        try:
            session = await approve_compile_session(
                wfs,
                session_id,
                app.state.config,
                provider,
                prompt_loader,
                approve=bool(data.get("approve", True)),
                summary_override=data.get("summary_override"),
            )
        except FileNotFoundError as exc:
            return JSONResponse({"error": str(exc)}, status_code=404)

        return JSONResponse(session.model_dump(mode="json"))

    @app.post("/api/update/session")
    async def api_start_update_session(data: dict) -> JSONResponse:
        from compendium.llm.factory import create_provider
        from compendium.llm.prompts import PromptLoader
        from compendium.pipeline.sessions import start_update_session

        try:
            provider = create_provider(app.state.config.models.compilation)
        except ValueError as exc:
            return JSONResponse({"error": str(exc)}, status_code=400)

        prompt_loader = PromptLoader(project_prompts_dir=wfs.root / "prompts")
        raw_paths = [Path(path) for path in data.get("paths", [])] or None
        session = await start_update_session(
            wfs,
            app.state.config,
            provider,
            prompt_loader,
            new_source_paths=raw_paths,
            branch=data.get("branch"),
        )
        return JSONResponse(session.model_dump(mode="json"))

    @app.get("/api/update/session/{session_id}")
    async def api_get_update_session(session_id: str) -> JSONResponse:
        from compendium.pipeline.sessions import load_session

        session = load_session(wfs, session_id)
        if session is None or session.kind != "update":
            return JSONResponse({"error": "Session not found"}, status_code=404)
        return JSONResponse(session.model_dump(mode="json"))

    # -- Graph API --

    @app.get("/api/graph")
    async def api_graph() -> JSONResponse:
        """Return pre-computed graph data (nodes + edges) for visualization."""

        import frontmatter as fm

        from compendium.core.wikilinks import WIKILINK_PATTERN

        nodes: list[dict] = []
        edges: list[dict] = []
        node_set: set[str] = set()
        inbound_counts: dict[str, int] = {}

        # Scan all wiki articles
        for md_file in wfs.wiki_dir.rglob("*.md"):
            rel = md_file.relative_to(wfs.wiki_dir)
            if any(part.startswith(".") for part in rel.parts):
                continue
            if md_file.name in (
                "INDEX.md",
                "CONCEPTS.md",
                "CONFLICTS.md",
                "CHANGELOG.md",
                "HEALTH_REPORT.md",
                "SCHEMA.md",
            ):
                continue

            slug = md_file.stem
            try:
                post = fm.load(str(md_file))
                title = post.metadata.get("title", slug.replace("-", " ").title())
                category = post.metadata.get("category", "other")
                content = post.content
            except Exception:
                title = slug.replace("-", " ").title()
                category = "other"
                content = md_file.read_text()

            node_set.add(slug)
            nodes.append(
                {
                    "id": slug,
                    "name": title,
                    "category": category,
                    "path": str(md_file.relative_to(root)),
                }
            )

            # Extract wikilinks as edges
            for match in WIKILINK_PATTERN.finditer(content):
                target = match.group(1).strip()
                target_slug = target.split("/")[-1].replace(".md", "")
                if target_slug != slug and not target.startswith("raw/"):
                    edges.append({"source": slug, "target": target_slug})
                    inbound_counts[target_slug] = inbound_counts.get(target_slug, 0) + 1

        # Filter edges to only those with valid targets
        edges = [e for e in edges if e["target"] in node_set]

        # Add link counts to nodes
        for node in nodes:
            node["links"] = inbound_counts.get(node["id"], 0)

        return JSONResponse(
            {
                "nodes": nodes,
                "edges": edges,
                "node_count": len(nodes),
                "edge_count": len(edges),
            }
        )

    # -- Search API --

    @app.get("/api/search")
    async def api_search(q: str = "", limit: int = 10) -> JSONResponse:
        from compendium.search.engine import SearchEngine

        if not q:
            return JSONResponse({"error": "Missing query parameter 'q'"}, status_code=400)
        engine = SearchEngine(wfs.wiki_dir)
        results = engine.search(q, limit=limit)
        return JSONResponse({"query": q, "results": results})

    # -- Lint API --

    @app.get("/api/lint")
    async def api_lint() -> JSONResponse:
        return JSONResponse(_run_lint())

    # -- WebSocket for browser extension --

    @app.websocket("/ws/clip")
    async def clip_websocket(websocket: WebSocket) -> None:
        """WebSocket endpoint for browser extension to send clipped pages."""
        from compendium.ingest.web_clip import clip_webpage

        await websocket.accept()
        try:
            while True:
                data = await websocket.receive_json()
                url = data.get("url", "")
                html = data.get("html", "")

                if not url or not html:
                    await websocket.send_json({"status": "error", "message": "Missing url or html"})
                    continue

                output_path, message = await clip_webpage(
                    url=url,
                    html=html,
                    raw_dir=wfs.raw_dir,
                    images_dir=wfs.raw_images_dir,
                    duplicate_mode=data.get("resolution", "cancel"),
                )

                if output_path:
                    await websocket.send_json(
                        {
                            "status": "success",
                            "url": url,
                            "message": message,
                            "path": str(output_path.relative_to(root)),
                        }
                    )
                elif message.startswith("duplicate:"):
                    await websocket.send_json(
                        {"status": "duplicate", "url": url, "message": message}
                    )
                else:
                    await websocket.send_json({"status": "error", "url": url, "message": message})
        except WebSocketDisconnect:
            pass

    # -- WebSocket for progress events --

    @app.websocket("/ws/progress")
    async def progress_websocket(websocket: WebSocket) -> None:
        """WebSocket for real-time compilation/Q&A progress updates."""
        await websocket.accept()
        try:
            while True:
                await websocket.receive_text()
                await websocket.send_json({"status": "connected", "events": []})
        except WebSocketDisconnect:
            pass

    @app.on_event("startup")
    async def startup() -> None:
        _restart_lint_schedule()

    @app.on_event("shutdown")
    async def shutdown() -> None:
        lint_task = app.state.lint_task
        if lint_task is not None:
            lint_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await lint_task

    # -- Static files (Svelte SPA) --
    static_dir = Path(__file__).parent / "web" / "static"
    if static_dir.exists():
        app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="static")

    return app
