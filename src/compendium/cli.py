"""Compendium CLI — the primary interface for managing knowledge wikis."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from compendium.core.config import CompendiumConfig
from compendium.core.wiki_fs import WikiFileSystem

app = typer.Typer(
    name="compendium",
    help="LLM-native knowledge compiler — compile research into a living wiki.",
    no_args_is_help=True,
)
console = Console()

# Sub-command groups
config_app = typer.Typer(help="Configure LLM providers and settings.")
app.add_typer(config_app, name="config")


def _get_wiki_fs(project_dir: Path | None = None) -> WikiFileSystem:
    """Get WikiFileSystem for the current or specified project directory."""
    root = project_dir or Path.cwd()
    return WikiFileSystem(root)


def _get_config(project_dir: Path | None = None) -> CompendiumConfig:
    """Load config from current or specified project directory."""
    root = project_dir or Path.cwd()
    return CompendiumConfig.load(root / "compendium.toml")


# -- init --


@app.command()
def init(
    path: Annotated[
        str | None,
        typer.Argument(help="Directory to initialize (default: current dir)"),
    ] = None,
    name: Annotated[str, typer.Option(help="Wiki project name")] = "My Knowledge Wiki",
    template: Annotated[
        str,
        typer.Option(help="Starter schema template"),
    ] = "research",
    domain: Annotated[
        str,
        typer.Option(help="Optional domain description for the starter schema"),
    ] = "",
) -> None:
    """Initialize a new Compendium project."""
    project_dir = Path(path) if path else Path.cwd()
    project_dir.mkdir(parents=True, exist_ok=True)

    wfs = WikiFileSystem(project_dir)
    wfs.init_project(name=name, template=template, domain=domain)

    console.print(
        Panel(
            f"[green]Initialized Compendium project:[/green] {project_dir}\n\n"
            f"  [dim]raw/[/dim]       — Drop your source documents here\n"
            f"  [dim]wiki/[/dim]      — Compiled wiki articles (LLM-maintained)\n"
            f"  [dim]output/[/dim]    — Q&A reports, slides, charts\n\n"
            f"Next steps:\n"
            f"  1. Open this folder in Obsidian as a vault\n"
            f"  2. Configure LLM: [cyan]compendium config set-key anthropic[/cyan]\n"
            f"  3. Add sources: [cyan]compendium ingest <file>[/cyan]\n"
            f"  4. Compile wiki: [cyan]compendium compile --mode batch[/cyan]\n"
            f"  5. Auto-ingest: [cyan]compendium watch[/cyan]",
            title=f"[bold]{name}[/bold]",
        )
    )


# -- compile --


@app.command()
def compile(
    project_dir: Annotated[
        Path | None, typer.Option("--dir", "-d", help="Project directory")
    ] = None,
    mode: Annotated[
        str,
        typer.Option(help="Compile mode: interactive or batch"),
    ] = "batch",
    branch: Annotated[
        str | None,
        typer.Option(help="Optional git branch for experimental compile runs"),
    ] = None,
) -> None:
    """Compile raw sources into a wiki (6-step LLM pipeline)."""
    import asyncio

    from compendium.llm.factory import create_provider
    from compendium.llm.prompts import PromptLoader
    from compendium.pipeline.sessions import approve_compile_session, start_compile_session

    wfs = _get_wiki_fs(project_dir)
    config = _get_config(project_dir)
    sources = wfs.list_raw_sources()

    if mode not in {"interactive", "batch"}:
        console.print(f"[red]Unsupported mode:[/red] {mode}")
        raise typer.Exit(1)

    if not sources:
        console.print("[yellow]No raw sources found in raw/. Add sources first.[/yellow]")
        raise typer.Exit(1)

    console.print(f"Found [bold]{len(sources)}[/bold] raw sources. Starting compilation...\n")

    try:
        llm = create_provider(config.models.compilation)
        prompt_loader = PromptLoader(project_prompts_dir=wfs.root / "prompts")
        session = asyncio.run(
            start_compile_session(
                wfs,
                config,
                llm,
                prompt_loader,
                mode="interactive" if mode == "interactive" else "batch",
                branch=branch,
            )
        )
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1) from None
    except Exception as e:
        console.print(f"[red]Compilation failed:[/red] {e}")
        raise typer.Exit(1) from None

    if session.error:
        console.print(f"[red]{session.error}[/red]")
        raise typer.Exit(1)

    if session.mode == "interactive":
        while session.status == "awaiting_approval":
            pending_source = session.pending_source or {}
            pending_summary = session.pending_summary or {}
            console.print(
                Panel(
                    (
                        f"[bold]{pending_source.get('title', 'Untitled source')}[/bold]\n"
                        f"{pending_source.get('path', '')}\n\n"
                        f"{pending_summary.get('summary', 'No summary generated.')}"
                    ),
                    title=f"Review {session.current_index + 1}/{session.source_count}",
                )
            )
            approved = typer.confirm("Approve this source summary?", default=True)
            session = asyncio.run(
                approve_compile_session(
                    wfs,
                    session.session_id,
                    config,
                    llm,
                    prompt_loader,
                    approve=approved,
                )
            )
            if session.error and session.status != "completed":
                console.print(f"[red]{session.error}[/red]")
                raise typer.Exit(1)

    result = session.result or {}
    if session.status != "completed":
        console.print(f"[red]{session.error or 'Compilation failed'}[/red]")
        raise typer.Exit(1)

    console.print(
        f"\n[green]Compilation complete![/green]\n"
        f"  Articles: [bold]{result['articles_count']}[/bold]\n"
        f"  Concepts: [bold]{result['concepts_count']}[/bold]\n"
        f"  Conflicts: [bold]{result['conflicts_detected']}[/bold]\n"
        f"  Sources: [bold]{result['sources_processed']}[/bold]\n"
        f"  Session: [dim]{session.session_id}[/dim]"
    )


# -- update --


@app.command()
def update(
    source: Annotated[
        str | None,
        typer.Argument(help="Path to new source, or --all-new for all uncompiled"),
    ] = None,
    all_new: Annotated[bool, typer.Option("--all-new", help="Update all new sources")] = False,
    branch: Annotated[
        str | None,
        typer.Option(help="Optional git branch for experimental update runs"),
    ] = None,
    project_dir: Annotated[
        Path | None, typer.Option("--dir", "-d", help="Project directory")
    ] = None,
) -> None:
    """Incrementally update the wiki with new or changed sources."""
    import asyncio

    from compendium.llm.factory import create_provider
    from compendium.llm.prompts import PromptLoader
    from compendium.pipeline.sessions import start_update_session

    wfs = _get_wiki_fs(project_dir)
    config = _get_config(project_dir)

    new_paths = None
    if source:
        new_paths = [Path(source)]
    elif not all_new:
        console.print("Specify a source path or use --all-new to update all new sources.")
        raise typer.Exit(1)

    try:
        llm = create_provider(config.models.compilation)
        prompt_loader = PromptLoader(project_prompts_dir=wfs.root / "prompts")
        session = asyncio.run(
            start_update_session(
                wfs,
                config,
                llm,
                prompt_loader,
                new_source_paths=new_paths,
                branch=branch,
            )
        )
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1) from None

    result = session.result or {}
    if session.status != "completed":
        console.print(f"[red]{session.error or 'Update failed'}[/red]")
        raise typer.Exit(1)

    if "message" in result:
        console.print(result["message"])
    if result.get("articles_added"):
        console.print(f"[green]Added {result['articles_added']} article(s)[/green]")
    console.print(f"[dim]Session: {session.session_id}[/dim]")


# -- ask --


@app.command()
def ask(
    question: Annotated[str, typer.Argument(help="Question to ask against the wiki")],
    output: Annotated[
        str | None,
        typer.Option(help="Output format: text (default), report, slides, html, or chart"),
    ] = None,
    count: Annotated[int, typer.Option(help="Number of slides (for --output slides)")] = 10,
    file_to_wiki: Annotated[
        bool, typer.Option("--file", help="File the output into the wiki")
    ] = False,
    resolution: Annotated[
        str | None,
        typer.Option(help="Duplicate filing resolution: merge, replace, keep_both, or cancel"),
    ] = None,
    project_dir: Annotated[
        Path | None, typer.Option("--dir", "-d", help="Project directory")
    ] = None,
) -> None:
    """Ask a question against your knowledge base."""
    import asyncio

    from compendium.llm.factory import create_provider
    from compendium.llm.prompts import PromptLoader
    from compendium.pipeline.steps import build_log_entry
    from compendium.qa.engine import ask_question
    from compendium.qa.filing import file_to_wiki as _file_to_wiki
    from compendium.qa.output import render_chart_bundle, render_html, render_report, render_slides
    from compendium.qa.session import ConversationSession

    wfs = _get_wiki_fs(project_dir)
    config = _get_config(project_dir)

    has_index = (wfs.wiki_dir / "index.md").exists() or (wfs.wiki_dir / "INDEX.md").exists()
    if not wfs.wiki_dir.exists() or not has_index:
        console.print("[yellow]No compiled wiki found. Run `compendium compile` first.[/yellow]")
        raise typer.Exit(1)

    try:
        llm = create_provider(config.models.qa)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1) from None

    prompt_loader = PromptLoader(project_prompts_dir=wfs.root / "prompts")
    session_dir = wfs.root / ".sessions"
    session = ConversationSession.load("cli-default", session_dir)

    console.print(f"[bold]Q:[/bold] {question}\n")

    result = asyncio.run(ask_question(question, wfs.wiki_dir, llm, prompt_loader, session))

    answer = result["answer"]
    sources = result["sources_used"]

    # Display answer
    console.print(answer)
    if sources:
        console.print(f"\n[dim]Sources: {', '.join(sources)}[/dim]")

    # Render output if requested
    output_path = None
    if output == "report":
        output_path = render_report(
            question, answer, sources, result.get("tokens_used", 0), wfs.output_dir
        )
        console.print(f"\n[green]Report saved:[/green] {output_path}")
    elif output == "slides":
        output_path = render_slides(question, answer, sources, wfs.output_dir, slide_count=count)
        console.print(f"\n[green]Slides saved:[/green] {output_path}")
    elif output == "canvas":
        from compendium.qa.output import render_canvas

        output_path = render_canvas(question, answer, sources, wfs.output_dir)
        console.print(f"\n[green]Canvas saved:[/green] {output_path}")
    elif output == "html":
        output_path = render_html(question, answer, sources, wfs.output_dir)
        console.print(f"\n[green]HTML saved:[/green] {output_path}")
    elif output == "chart":
        chart_path, note_path = render_chart_bundle(question, answer, sources, wfs.output_dir)
        output_path = note_path
        if chart_path is not None:
            console.print(f"\n[green]Chart PNG saved:[/green] {chart_path}")
        console.print(f"[green]Chart note saved:[/green] {note_path}")

    # File to wiki if requested
    if file_to_wiki:
        if output_path is None:
            # File the raw answer directly (no report/slides rendered)
            output_path = render_report(
                question, answer, sources, result.get("tokens_used", 0), wfs.output_dir
            )
        filing_result = _file_to_wiki(output_path, wfs, resolution=resolution)
        if filing_result["status"] == "similar" and resolution is None:
            choice = typer.prompt(
                "A similar page already exists. Choose merge, replace, keep_both, or cancel",
                default="merge",
            )
            filing_result = _file_to_wiki(output_path, wfs, resolution=choice)
        if filing_result["status"] == "filed":
            console.print(
                f"[green]Filed to wiki:[/green] {filing_result['filed_path']} "
                f"({filing_result['backlinks_added']} backlinks added)"
            )
        else:
            console.print(f"[yellow]{filing_result['message']}[/yellow]")

    wfs.append_log_entry(
        build_log_entry(
            "query",
            title=question[:80],
            notes=(
                f"output: {output or 'text'}; "
                f"articles loaded: {result.get('articles_loaded', 0)}; "
                f"filed: {'yes' if file_to_wiki else 'no'}"
            ),
        )
    )


# -- search --


@app.command()
def search(
    query: Annotated[str, typer.Argument(help="Search query")],
    project_dir: Annotated[
        Path | None, typer.Option("--dir", "-d", help="Project directory")
    ] = None,
) -> None:
    """Search the wiki (deprecated — use Obsidian search)."""
    console.print(
        "[yellow]Full-text search has been removed.[/yellow]\n\n"
        "Use Obsidian's built-in search (Cmd+Shift+F) or:\n"
        "  [cyan]compendium ask \"your question\"[/cyan] — semantic search with citations"
    )
    raise typer.Exit(0)


# -- lint --


@app.command()
def lint(
    deep: Annotated[
        bool, typer.Option("--deep", help="Run LLM-based contradiction detection")
    ] = False,
    project_dir: Annotated[
        Path | None, typer.Option("--dir", "-d", help="Project directory")
    ] = None,
) -> None:
    """Run wiki health checks (broken links, contradictions, gaps)."""
    from compendium.lint.engine import lint_wiki

    wfs = _get_wiki_fs(project_dir)
    config = _get_config(project_dir)

    if not wfs.wiki_dir.exists():
        console.print("[yellow]No wiki found. Run `compendium compile` first.[/yellow]")
        raise typer.Exit(1)

    llm = None
    if deep:
        config = _get_config(project_dir)
        try:
            from compendium.llm.factory import create_provider

            llm = create_provider(config.models.lint)
        except ValueError as e:
            console.print(f"[red]Cannot run --deep lint: {e}[/red]")
            raise typer.Exit(1) from None

    report = lint_wiki(wfs.wiki_dir, raw_dir=wfs.raw_dir, llm=llm)
    if config.lint.missing_data_web_search:
        for issue in report.issues:
            query = issue.location.replace(".md", "").replace("-", " ").strip() or "missing data"
            search_url = f"https://www.google.com/search?q={query.replace(' ', '+')}"
            if issue.suggestion:
                issue.suggestion = f"{issue.suggestion} Research lead: {search_url}"
            else:
                issue.suggestion = f"Research lead: {search_url}"

    # Write HEALTH_REPORT.md
    report_path = wfs.wiki_dir / "HEALTH_REPORT.md"
    report_path.write_text(report.to_markdown())

    # Display summary
    if report.total == 0:
        console.print("[green]No issues found. Wiki is healthy![/green]")
        return

    console.print(
        f"[bold]Health check:[/bold] {report.total} issue(s) found\n"
        f"  [red]Critical:[/red] {report.critical_count}\n"
        f"  [yellow]Warning:[/yellow] {report.warning_count}\n"
        f"  [dim]Info:[/dim] {report.info_count}\n"
    )

    for issue in report.issues:
        match issue.severity:
            case "critical":
                icon = "[red]CRIT[/red]"
            case "warning":
                icon = "[yellow]WARN[/yellow]"
            case _:
                icon = "[dim]INFO[/dim]"
        console.print(f"  {icon}  {issue.location}: {issue.description}")

    console.print(f"\n[dim]Full report: {report_path}[/dim]")

    from compendium.pipeline.steps import build_log_entry

    log_entry = build_log_entry(
        "lint",
        notes=f"{report.critical_count} critical, "
        f"{report.warning_count} warning, {report.info_count} info",
    )
    wfs.append_log_entry(log_entry)
    wfs.auto_commit("[lint]: refresh health report", paths=[report_path, wfs.wiki_dir / "log.md"])


# -- ingest --


@app.command()
def ingest(
    paths: Annotated[list[str], typer.Argument(help="Files or directories to ingest")],
    duplicate_mode: Annotated[
        str,
        typer.Option(help="Duplicate handling: cancel, overwrite, or keep_both"),
    ] = "cancel",
    discuss: Annotated[
        bool,
        typer.Option("--discuss", help="Discuss key takeaways with LLM after ingest"),
    ] = False,
    project_dir: Annotated[
        Path | None, typer.Option("--dir", "-d", help="Project directory")
    ] = None,
) -> None:
    """Ingest files into raw/ (PDF, markdown, CSV, images)."""
    from rich.progress import Progress

    from compendium.ingest.file_drop import ingest_batch
    from compendium.pipeline.steps import build_log_entry

    wfs = _get_wiki_fs(project_dir)
    file_paths = [Path(p) for p in paths]

    with Progress(console=console) as progress:
        task = progress.add_task("Ingesting...", total=len(file_paths))
        result = ingest_batch(
            file_paths,
            raw_dir=wfs.raw_dir,
            images_dir=wfs.raw_images_dir,
            originals_dir=wfs.raw_originals_dir,
            duplicate_mode=duplicate_mode,
        )
        progress.update(task, completed=result.total)

    for r in result.results:
        if r.success:
            console.print(f"  [green]OK[/green]  {r.message}")
        else:
            console.print(f"  [red]FAIL[/red]  {r.source_path.name}: {r.message}")

    console.print(
        f"\n[bold]{result.succeeded}[/bold] ingested, "
        f"[bold]{result.failed}[/bold] failed "
        f"(of {result.total} total)"
    )

    wfs.append_log_entry(
        build_log_entry(
            "ingest",
            title="CLI ingest",
            sources_count=result.succeeded,
            notes=f"failed: {result.failed}; duplicate_mode: {duplicate_mode}",
        )
    )
    wfs.auto_commit("[ingest]: add raw sources", paths=[wfs.raw_dir, wfs.wiki_dir / "log.md"])

    # Conversational ingest: discuss takeaways with LLM
    if discuss and result.succeeded > 0:
        import asyncio

        from compendium.llm.factory import create_provider
        from compendium.llm.provider import CompletionRequest, Message

        config = _get_config(project_dir)
        try:
            llm = create_provider(config.models.qa)
        except ValueError as e:
            console.print(f"[yellow]Cannot discuss: {e}[/yellow]")
            return

        # Read all successfully ingested sources
        source_texts: list[str] = []
        for r in result.results:
            if r.success and r.output_path and r.output_path.exists():
                content = r.output_path.read_text()[:3000]
                source_texts.append(f"--- {r.output_path.name} ---\n{content}")

        prompt = (
            "I just ingested the following sources into my knowledge base. "
            "Summarize the key takeaways, note anything surprising, "
            "and suggest what questions I should explore:\n\n" + "\n\n".join(source_texts)
        )

        console.print("\n[bold]Key takeaways:[/bold]\n")
        response = asyncio.run(
            llm.complete(
                CompletionRequest(
                    messages=[Message(role="user", content=prompt)],
                    max_tokens=2000,
                    temperature=0.3,
                )
            )
        )
        console.print(response.content)


# -- clip --


@app.command()
def clip(
    urls: Annotated[list[str], typer.Argument(help="URLs to clip")],
    duplicate_mode: Annotated[
        str, typer.Option(help="Duplicate handling: cancel | overwrite")
    ] = "cancel",
    project_dir: Annotated[
        Path | None, typer.Option("--dir", "-d", help="Project directory")
    ] = None,
) -> None:
    """Clip web pages into raw/ with metadata and local images."""
    import asyncio

    import httpx

    from compendium.ingest.web_clip import clip_webpage
    from compendium.pipeline.steps import build_log_entry

    wfs = _get_wiki_fs(project_dir)
    clipped = 0
    failed = 0

    async def _clip_all() -> None:
        nonlocal clipped, failed
        async with httpx.AsyncClient(follow_redirects=True, timeout=30.0) as client:
            for url in urls:
                console.print(f"  [dim]Fetching {url}...[/dim]")
                try:
                    resp = await client.get(url)
                    resp.raise_for_status()
                    html = resp.text
                except httpx.HTTPError as e:
                    console.print(f"  [red]FAIL[/red]  {url}: {e}")
                    failed += 1
                    continue

                output, msg = await clip_webpage(
                    url, html, wfs.raw_dir, wfs.raw_images_dir, duplicate_mode
                )
                if output:
                    console.print(f"  [green]OK[/green]  {msg}")
                    clipped += 1
                else:
                    console.print(f"  [yellow]SKIP[/yellow]  {msg}")

    asyncio.run(_clip_all())

    console.print(f"\n[bold]{clipped}[/bold] clipped, [bold]{failed}[/bold] failed")

    if clipped > 0:
        wfs.append_log_entry(
            build_log_entry(
                "ingest",
                title="CLI clip",
                sources_count=clipped,
                notes=f"failed: {failed}; urls: {len(urls)}",
            )
        )
        wfs.auto_commit(
            f"[clip]: {clipped} web page(s)",
            paths=[wfs.raw_dir, wfs.wiki_dir / "log.md"],
        )


# -- apple-books --


@app.command("apple-books")
def apple_books(
    project_dir: Annotated[
        Path | None, typer.Option("--dir", "-d", help="Project directory")
    ] = None,
    book: Annotated[
        str | None, typer.Option(help="Export only this book (by title substring)")
    ] = None,
    list_books: Annotated[
        bool, typer.Option("--list", help="List available books and exit")
    ] = False,
    duplicate_mode: Annotated[
        str, typer.Option(help="Duplicate handling: cancel | overwrite")
    ] = "cancel",
) -> None:
    """Export Apple Books highlights and annotations into raw/."""
    from compendium.ingest.apple_books import (
        discover_books,
        export_to_markdown,
        extract_highlights,
    )

    if list_books:
        books = discover_books()
        if not books:
            console.print("[yellow]No Apple Books library found.[/yellow]")
            raise typer.Exit(1)
        table = Table(title="Apple Books Library")
        table.add_column("Title", style="cyan")
        table.add_column("Author")
        table.add_column("Genre", style="dim")
        for b in books:
            table.add_row(b["title"], b["author"], b["genre"])
        console.print(table)
        return

    wfs = _get_wiki_fs(project_dir)

    # Extract highlights
    exports = extract_highlights()
    if not exports:
        console.print(
            "[yellow]No highlights found. "
            "Ensure Apple Books has highlights and Full Disk Access is granted.[/yellow]"
        )
        raise typer.Exit(1)

    # Filter by book title if specified
    if book:
        needle = book.lower()
        exports = [e for e in exports if needle in e.title.lower()]
        if not exports:
            console.print(f"[yellow]No books matching '{book}'.[/yellow]")
            raise typer.Exit(1)

    exported = 0
    skipped = 0
    for bk in exports:
        output, msg = export_to_markdown(bk, wfs.raw_dir, duplicate_mode)
        if output:
            console.print(f"  [green]+[/green] {msg}")
            exported += 1
        else:
            console.print(f"  [dim]-[/dim] {msg}")
            skipped += 1

    console.print(
        f"\n[bold]{exported}[/bold] exported, [bold]{skipped}[/bold] skipped"
    )

    if exported > 0:
        from compendium.pipeline.steps import build_log_entry

        wfs.append_log_entry(
            build_log_entry(
                "ingest",
                title="Apple Books export",
                sources_count=exported,
                notes=f"skipped: {skipped}",
            )
        )
        wfs.auto_commit(
            f"[apple-books]: export {exported} book(s)",
            paths=[wfs.raw_dir, wfs.wiki_dir / "log.md"],
        )


# -- watch --


@app.command()
def watch(
    project_dir: Annotated[
        Path | None, typer.Option("--dir", "-d", help="Project directory")
    ] = None,
    duplicate_mode: Annotated[
        str, typer.Option(help="Duplicate handling: cancel | overwrite")
    ] = "cancel",
    debounce: Annotated[
        float, typer.Option(help="Seconds to wait for file to stabilize")
    ] = 2.0,
) -> None:
    """Watch raw/ for new files and auto-ingest them."""
    from compendium.ingest.watcher import run_watcher

    wfs = _get_wiki_fs(project_dir)
    console.print(
        f"[bold]Watching[/bold] {wfs.raw_dir} for new files... (Ctrl+C to stop)"
    )

    processed, errors = run_watcher(
        wfs,
        duplicate_mode=duplicate_mode,
        debounce_seconds=debounce,
        console=console,
    )

    console.print(
        f"\n[bold]{len(processed)}[/bold] ingested, "
        f"[bold]{len(errors)}[/bold] errors"
    )


# -- download-media --


@app.command("download-media")
def download_media(
    project_dir: Annotated[
        Path | None, typer.Option("--dir", "-d", help="Project directory")
    ] = None,
    dry_run: Annotated[
        bool, typer.Option("--dry-run", help="Show what would be downloaded")
    ] = False,
) -> None:
    """Download remote images in wiki articles for offline access."""
    from compendium.ingest.media import download_and_localize, scan_remote_images

    wfs = _get_wiki_fs(project_dir)
    results = scan_remote_images(wfs.wiki_dir)

    if not results:
        console.print("No remote images found in wiki articles.")
        return

    total_urls = sum(len(urls) for _, urls in results)
    console.print(
        f"Found [bold]{total_urls}[/bold] remote image(s) across "
        f"[bold]{len(results)}[/bold] article(s)."
    )

    if dry_run:
        for article_path, urls in results:
            rel = article_path.relative_to(wfs.wiki_dir)
            console.print(f"\n  [cyan]{rel}[/cyan]")
            for url in urls:
                console.print(f"    {url}")
        return

    images_dir = wfs.wiki_dir / "images"
    total_downloaded = 0
    total_failed = 0

    for article_path, _ in results:
        rel = article_path.relative_to(wfs.wiki_dir)
        downloaded, failed = download_and_localize(article_path, images_dir)
        if downloaded:
            console.print(f"  [green]+{downloaded}[/green] {rel}")
        if failed:
            console.print(f"  [red]x{failed}[/red] {rel}")
        total_downloaded += downloaded
        total_failed += failed

    console.print(
        f"\nDownloaded [bold]{total_downloaded}[/bold] images "
        f"([bold]{total_failed}[/bold] failed)"
    )

    from compendium.pipeline.steps import build_log_entry

    wfs.append_log_entry(
        build_log_entry(
            "download-media",
            title="Download remote images",
            notes=f"downloaded: {total_downloaded}; failed: {total_failed}",
        )
    )
    wfs.auto_commit(
        f"[media]: download {total_downloaded} remote images",
        paths=[wfs.wiki_dir],
    )


# -- status --


@app.command()
def status(
    project_dir: Annotated[
        Path | None, typer.Option("--dir", "-d", help="Project directory")
    ] = None,
) -> None:
    """Show project status summary."""
    wfs = _get_wiki_fs(project_dir)
    config = _get_config(project_dir)

    raw_sources = wfs.list_raw_sources()
    wiki_articles = wfs.list_wiki_articles()

    table = Table(title=config.project.name)
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="bold")

    table.add_row("Raw sources", str(len(raw_sources)))
    table.add_row("Wiki articles", str(len(wiki_articles)))
    table.add_row("Default provider", config.models.default_provider)
    table.add_row("Compilation model", config.models.compilation.model)
    table.add_row("Q&A model", config.models.qa.model)
    table.add_row("Project root", str(wfs.root))

    console.print(table)


# -- verify-index --


@app.command("verify-index")
def verify_index(
    project_dir: Annotated[
        Path | None, typer.Option("--dir", "-d", help="Project directory")
    ] = None,
) -> None:
    """Check index.md consistency against actual wiki contents."""
    from compendium.pipeline.index_ops import verify_wiki_index

    wfs = _get_wiki_fs(project_dir)
    result = verify_wiki_index(wfs.wiki_dir)

    if not result["mismatches"]:
        console.print("[green]Index is consistent. No mismatches found.[/green]")
        return

    console.print(f"[yellow]Found {len(result['mismatches'])} mismatch(es):[/yellow]\n")
    for m in result["mismatches"]:
        console.print(f"  [{m['type']}]  {m['detail']}")

    console.print("\n[dim]Run `compendium rebuild-index` to fix.[/dim]")


# -- rebuild-index --


@app.command("rebuild-index")
def rebuild_index(
    project_dir: Annotated[
        Path | None, typer.Option("--dir", "-d", help="Project directory")
    ] = None,
) -> None:
    """Rebuild index.md and concepts.md from wiki contents."""
    from compendium.pipeline.index_ops import rebuild_wiki_index

    wfs = _get_wiki_fs(project_dir)
    result = rebuild_wiki_index(wfs.wiki_dir)

    console.print(
        f"[green]Index rebuilt:[/green] "
        f"{result['articles']} articles, "
        f"{result['concepts']} concepts"
    )


# -- usage --


@app.command()
def usage(
    project_dir: Annotated[
        Path | None, typer.Option("--dir", "-d", help="Project directory")
    ] = None,
) -> None:
    """Show token usage and cost summary."""
    from compendium.llm.tokens import TokenTracker

    tracker = TokenTracker()
    summary = tracker.get_monthly_summary()
    breakdown = tracker.get_operation_breakdown()

    totals = summary.get("totals", {})
    console.print(f"[bold]Token Usage — {summary.get('month', 'current')}[/bold]\n")

    if not breakdown:
        console.print("[dim]No usage recorded this month.[/dim]")
        return

    table = Table()
    table.add_column("Operation", style="cyan")
    table.add_column("Model")
    table.add_column("Calls", justify="right")
    table.add_column("Input Tokens", justify="right")
    table.add_column("Output Tokens", justify="right")
    table.add_column("Cost (USD)", justify="right", style="green")

    for row in breakdown:
        table.add_row(
            row["operation"],
            row["model"],
            str(row["call_count"]),
            f"{row['input_tokens']:,}",
            f"{row['output_tokens']:,}",
            f"${row['estimated_cost_usd']:.4f}",
        )

    console.print(table)
    console.print(f"\n[bold]Total: ${totals.get('estimated_cost_usd', 0):.4f}[/bold]")


# -- rollback --


@app.command()
def rollback(
    backup_id: Annotated[str | None, typer.Argument(help="Backup ID to restore")] = None,
    list_all: Annotated[bool, typer.Option("--list", help="List available backups")] = False,
    project_dir: Annotated[
        Path | None, typer.Option("--dir", "-d", help="Project directory")
    ] = None,
) -> None:
    """Restore wiki from a backup."""
    wfs = _get_wiki_fs(project_dir)
    backups = wfs.list_backups()

    if list_all or backup_id is None:
        if not backups:
            console.print("[yellow]No backups available.[/yellow]")
            raise typer.Exit(0)
        console.print("[bold]Available backups:[/bold]")
        for b in backups:
            console.print(f"  {b}")
        if backup_id is None:
            raise typer.Exit(0)

    if backup_id and backup_id not in backups:
        console.print(f"[red]Backup '{backup_id}' not found.[/red]")
        raise typer.Exit(1)

    if backup_id:
        confirm = typer.confirm(
            f"Restore wiki from backup {backup_id}? This overwrites the current wiki."
        )
        if not confirm:
            raise typer.Exit(0)
        wfs.rollback(backup_id)
        console.print(f"[green]Wiki restored from backup {backup_id}.[/green]")


# -- config subcommands --


@config_app.command("set-key")
def config_set_key(
    provider: Annotated[str, typer.Argument(help="Provider name: anthropic, openai, gemini")],
) -> None:
    """Store an API key in the OS keychain."""
    from compendium.llm.factory import get_api_key, set_api_key

    existing = get_api_key(provider)
    if existing:
        overwrite = typer.confirm(f"API key for {provider} already exists. Overwrite?")
        if not overwrite:
            raise typer.Exit(0)

    api_key = typer.prompt(f"Enter API key for {provider}", hide_input=True)
    set_api_key(provider, api_key)
    console.print(f"[green]API key for {provider} saved to system keychain.[/green]")


@config_app.command("delete-key")
def config_delete_key(
    provider: Annotated[str, typer.Argument(help="Provider name: anthropic, openai, gemini")],
) -> None:
    """Remove an API key from the OS keychain."""
    from compendium.llm.factory import delete_api_key

    delete_api_key(provider)
    console.print(f"[yellow]API key for {provider} removed from system keychain.[/yellow]")


@config_app.command("test")
def config_test(
    project_dir: Annotated[
        Path | None, typer.Option("--dir", "-d", help="Project directory")
    ] = None,
) -> None:
    """Test connection to all configured LLM providers."""
    import asyncio

    from rich.status import Status

    from compendium.llm.factory import create_provider

    config = _get_config(project_dir)
    console.print(f"[bold]Testing providers for:[/bold] {config.project.name}\n")

    model_configs = {
        "compilation": config.models.compilation,
        "qa": config.models.qa,
        "lint": config.models.lint,
    }

    # Deduplicate by provider:model
    seen: dict[str, list[str]] = {}
    for op_name, mc in model_configs.items():
        key = f"{mc.provider}:{mc.model}"
        seen.setdefault(key, []).append(op_name)

    for key, ops in seen.items():
        provider_name, model = key.split(":", 1)
        ops_str = ", ".join(ops)

        with Status(f"Testing {key}..."):
            # Find the first matching model config
            mc = model_configs[ops[0]]
            try:
                provider = create_provider(mc)
                ok = asyncio.run(provider.test_connection())
                if ok:
                    console.print(
                        f"  [green]OK[/green]  {provider_name} / {model} [dim]({ops_str})[/dim]"
                    )
                else:
                    console.print(
                        f"  [red]FAIL[/red]  {provider_name} / {model} "
                        f"[dim]({ops_str})[/dim] — connection failed"
                    )
            except ValueError as e:
                console.print(
                    f"  [red]SKIP[/red]  {provider_name} / {model} [dim]({ops_str})[/dim] — {e}"
                )


@config_app.command("show")
def config_show(
    project_dir: Annotated[
        Path | None, typer.Option("--dir", "-d", help="Project directory")
    ] = None,
) -> None:
    """Show current configuration."""
    config = _get_config(project_dir)
    console.print_json(config.model_dump_json(indent=2))
