"""FastAPI local server — web UI backend, browser extension endpoint, progress WebSocket."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from compendium import __version__
from compendium.core.config import CompendiumConfig
from compendium.core.wiki_fs import WikiFileSystem


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
        article_path = root / path
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
        from compendium.qa.engine import ask_question
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
        return JSONResponse(result)

    @app.post("/api/file-to-wiki")
    async def api_file_to_wiki(data: dict) -> JSONResponse:
        from compendium.qa.filing import file_to_wiki

        report_path = root / data.get("path", "")
        if not report_path.exists():
            return JSONResponse({"error": "File not found"}, status_code=404)

        result = file_to_wiki(report_path, wfs)
        return JSONResponse(result)

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
        from compendium.lint.engine import lint_wiki

        report = lint_wiki(wfs.wiki_dir, raw_dir=wfs.raw_dir)
        report_path = wfs.wiki_dir / "HEALTH_REPORT.md"
        report_path.write_text(report.to_markdown())
        return JSONResponse(
            {
                "total": report.total,
                "critical": report.critical_count,
                "warning": report.warning_count,
                "info": report.info_count,
                "issues": [
                    {
                        "severity": i.severity,
                        "category": i.category,
                        "location": i.location,
                        "description": i.description,
                        "suggestion": i.suggestion,
                    }
                    for i in report.issues
                ],
            }
        )

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

    # -- Static files (Svelte SPA) --
    static_dir = Path(__file__).parent / "web" / "static"
    if static_dir.exists():
        app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="static")

    return app
