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
) -> None:
    """Initialize a new Compendium project."""
    project_dir = Path(path) if path else Path.cwd()
    project_dir.mkdir(parents=True, exist_ok=True)

    wfs = WikiFileSystem(project_dir)
    wfs.init_project(name=name)

    console.print(
        Panel(
            f"[green]Initialized Compendium project:[/green] {project_dir}\n\n"
            f"  [dim]raw/[/dim]       — Drop your source documents here\n"
            f"  [dim]wiki/[/dim]      — Compiled wiki articles (LLM-maintained)\n"
            f"  [dim]output/[/dim]    — Q&A reports, slides, charts\n\n"
            f"Next steps:\n"
            f"  1. Add sources: [cyan]compendium ingest <file>[/cyan]\n"
            f"  2. Configure LLM: [cyan]compendium config set-key anthropic[/cyan]\n"
            f"  3. Compile wiki: [cyan]compendium compile[/cyan]",
            title=f"[bold]{name}[/bold]",
        )
    )


# -- compile --


@app.command()
def compile(
    project_dir: Annotated[
        Path | None, typer.Option("--dir", "-d", help="Project directory")
    ] = None,
    resume: Annotated[bool, typer.Option(help="Resume from checkpoint")] = False,
) -> None:
    """Compile raw sources into a wiki (6-step LLM pipeline)."""
    import asyncio

    from rich.status import Status

    from compendium.llm.factory import create_provider
    from compendium.llm.prompts import PromptLoader
    from compendium.pipeline.controller import ProgressCallback, compile_wiki

    wfs = _get_wiki_fs(project_dir)
    config = _get_config(project_dir)
    sources = wfs.list_raw_sources()

    if not sources:
        console.print("[yellow]No raw sources found in raw/. Add sources first.[/yellow]")
        raise typer.Exit(1)

    console.print(f"Found [bold]{len(sources)}[/bold] raw sources. Starting compilation...\n")

    step_names = {
        "summarize": "Step 1/6: Summarizing sources",
        "extract_concepts": "Step 2/6: Extracting concepts",
        "generate_articles": "Step 3/6: Generating articles",
        "create_backlinks": "Step 4/6: Creating backlinks",
        "build_index": "Step 5/6: Building index",
        "detect_conflicts": "Step 6/6: Detecting conflicts",
        "promoting": "Finalizing",
    }
    status_ctx = Status("")
    status_ctx.start()

    def on_progress(step: str, current: int, total: int, detail: str = "") -> None:
        label = step_names.get(step, step)
        status_ctx.update(f"{label}: {detail}")

    try:
        llm = create_provider(config.models.compilation)
        prompt_loader = PromptLoader(project_prompts_dir=wfs.root / "prompts")
        progress = ProgressCallback(on_progress)

        result = asyncio.run(compile_wiki(wfs, config, llm, prompt_loader, progress, resume))
    except ValueError as e:
        status_ctx.stop()
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1) from None
    except Exception as e:
        status_ctx.stop()
        console.print(f"[red]Compilation failed:[/red] {e}")
        raise typer.Exit(1) from None
    finally:
        status_ctx.stop()

    if "error" in result:
        console.print(f"[red]{result['error']}[/red]")
        raise typer.Exit(1)

    console.print(
        f"\n[green]Compilation complete![/green]\n"
        f"  Articles: [bold]{result['articles_count']}[/bold]\n"
        f"  Concepts: [bold]{result['concepts_count']}[/bold]\n"
        f"  Conflicts: [bold]{result['conflicts_detected']}[/bold]\n"
        f"  Sources: [bold]{result['sources_processed']}[/bold]"
    )


# -- update --


@app.command()
def update(
    source: Annotated[
        str | None,
        typer.Argument(help="Path to new source, or --all-new for all uncompiled"),
    ] = None,
    all_new: Annotated[bool, typer.Option("--all-new", help="Update all new sources")] = False,
    project_dir: Annotated[
        Path | None, typer.Option("--dir", "-d", help="Project directory")
    ] = None,
) -> None:
    """Incrementally update the wiki with new or changed sources."""
    import asyncio

    from compendium.llm.factory import create_provider
    from compendium.llm.prompts import PromptLoader
    from compendium.pipeline.controller import ProgressCallback, incremental_update

    wfs = _get_wiki_fs(project_dir)
    config = _get_config(project_dir)

    new_paths = None
    if source:
        new_paths = [Path(source)]
    elif not all_new:
        console.print("Specify a source path or use --all-new to update all new sources.")
        raise typer.Exit(1)

    def on_progress(step: str, current: int, total: int, detail: str = "") -> None:
        console.print(f"  [dim]{detail}[/dim]")

    try:
        llm = create_provider(config.models.compilation)
        prompt_loader = PromptLoader(project_prompts_dir=wfs.root / "prompts")
        progress = ProgressCallback(on_progress)

        result = asyncio.run(
            incremental_update(wfs, config, llm, prompt_loader, new_paths, progress)
        )
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1) from None

    if "message" in result:
        console.print(result["message"])
    if result.get("articles_added"):
        console.print(f"[green]Added {result['articles_added']} article(s)[/green]")


# -- ask --


@app.command()
def ask(
    question: Annotated[str, typer.Argument(help="Question to ask against the wiki")],
    output: Annotated[
        str | None,
        typer.Option(help="Output format: text (default), report, slides"),
    ] = None,
    count: Annotated[int, typer.Option(help="Number of slides (for --output slides)")] = 10,
    file_to_wiki: Annotated[
        bool, typer.Option("--file", help="File the output into the wiki")
    ] = False,
    project_dir: Annotated[
        Path | None, typer.Option("--dir", "-d", help="Project directory")
    ] = None,
) -> None:
    """Ask a question against your knowledge base."""
    import asyncio

    from compendium.llm.factory import create_provider
    from compendium.llm.prompts import PromptLoader
    from compendium.qa.engine import ask_question
    from compendium.qa.filing import file_to_wiki as _file_to_wiki
    from compendium.qa.output import render_report, render_slides
    from compendium.qa.session import ConversationSession

    wfs = _get_wiki_fs(project_dir)
    config = _get_config(project_dir)

    if not wfs.wiki_dir.exists() or not (wfs.wiki_dir / "INDEX.md").exists():
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

    # File to wiki if requested
    if file_to_wiki:
        if output_path is None:
            # File the raw answer directly (no report/slides rendered)
            output_path = render_report(
                question, answer, sources, result.get("tokens_used", 0), wfs.output_dir
            )
        filing_result = _file_to_wiki(output_path, wfs)
        if filing_result["status"] == "filed":
            console.print(
                f"[green]Filed to wiki:[/green] {filing_result['filed_path']} "
                f"({filing_result['backlinks_added']} backlinks added)"
            )
        else:
            console.print(f"[yellow]{filing_result['message']}[/yellow]")


# -- search --


@app.command()
def search(
    query: Annotated[str, typer.Argument(help="Search query")],
    limit: Annotated[int, typer.Option(help="Max results")] = 5,
    json_output: Annotated[
        bool, typer.Option("--json", help="Output as JSON (for LLM agent use)")
    ] = False,
    rebuild: Annotated[
        bool, typer.Option("--rebuild", help="Rebuild search index before searching")
    ] = False,
    project_dir: Annotated[
        Path | None, typer.Option("--dir", "-d", help="Project directory")
    ] = None,
) -> None:
    """Search the wiki using full-text search."""
    import json

    from compendium.search.engine import SearchEngine

    wfs = _get_wiki_fs(project_dir)
    engine = SearchEngine(wfs.wiki_dir)

    if rebuild:
        count = engine.build_index()
        console.print(f"[dim]Indexed {count} articles.[/dim]")

    results = engine.search(query, limit=limit)

    if json_output:
        console.print_json(json.dumps(results, indent=2))
        return

    if not results:
        console.print(f"No articles match '{query}'.")
        return

    console.print(f"[bold]{len(results)}[/bold] result(s) for '{query}':\n")
    for r in results:
        console.print(
            f"  [cyan]{r['title']}[/cyan] [dim]({r['category']}, score: {r['score']})[/dim]"
        )
        if r["snippet"]:
            console.print(f"    {r['snippet'][:120]}")
        console.print()


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

    # Append to log.md
    from compendium.pipeline.controller import _append_log
    from compendium.pipeline.steps import build_log_entry

    log_entry = build_log_entry(
        "lint",
        notes=f"{report.critical_count} critical, "
        f"{report.warning_count} warning, {report.info_count} info",
    )
    _append_log(wfs.wiki_dir / "log.md", log_entry)


# -- ingest --


@app.command()
def ingest(
    paths: Annotated[list[str], typer.Argument(help="Files or directories to ingest")],
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

    wfs = _get_wiki_fs(project_dir)
    file_paths = [Path(p) for p in paths]

    with Progress(console=console) as progress:
        task = progress.add_task("Ingesting...", total=len(file_paths))
        result = ingest_batch(
            file_paths,
            raw_dir=wfs.raw_dir,
            images_dir=wfs.raw_images_dir,
            originals_dir=wfs.raw_originals_dir,
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
    """Check INDEX.md consistency against actual wiki contents."""
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
    """Rebuild INDEX.md and CONCEPTS.md from wiki contents."""
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


# -- serve --


@app.command()
def serve(
    project_dir: Annotated[
        Path | None, typer.Option("--dir", "-d", help="Project directory")
    ] = None,
    port: Annotated[int, typer.Option(help="Server port")] = 17394,
    host: Annotated[str, typer.Option(help="Server host")] = "127.0.0.1",
) -> None:
    """Start the Compendium web server."""
    import uvicorn

    console.print(f"[bold]Starting Compendium server at http://{host}:{port}[/bold]")
    uvicorn.run(
        "compendium.server:create_app",
        factory=True,
        host=host,
        port=port,
        reload=False,
    )
