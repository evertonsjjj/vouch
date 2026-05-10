"""curio command-line interface."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from . import __version__
from .catalog import Catalog, Site
from .engine import SearchEngine

app = typer.Typer(
    add_completion=False,
    help="curio — curated AI search for agents.",
    no_args_is_help=True,
)
catalog_app = typer.Typer(help="Manage the site catalog.", no_args_is_help=True)
mcp_app = typer.Typer(help="Run curio as an MCP server.", no_args_is_help=True)
app.add_typer(catalog_app, name="catalog")
app.add_typer(mcp_app, name="mcp")
console = Console()


@app.callback(invoke_without_command=True)
def _main(
    ctx: typer.Context,
    version: bool = typer.Option(False, "--version", "-V", is_eager=True, help="Show version and exit"),
):
    if version:
        console.print(f"curio {__version__}")
        raise typer.Exit()
    if ctx.invoked_subcommand is None:
        typer.echo(ctx.get_help())
        raise typer.Exit()


# --- top-level commands -----------------------------------------------------


@app.command()
def search(
    query: str,
    catalog: Optional[Path] = typer.Option(None, "--catalog", "-c", help="YAML catalog path"),
    sites: Optional[str] = typer.Option(None, "--sites", help="Comma-separated list (overrides catalog)"),
    llm: str = typer.Option("ollama/qwen2.5:14b", "--llm"),
    depth: int = typer.Option(1, "--depth", "-d", min=0, max=3),
    json_out: bool = typer.Option(False, "--json", help="Print JSON instead of table"),
    max_results: int = typer.Option(10, "--max-results", "-n"),
):
    """Run a search and print the results."""
    if catalog:
        engine = SearchEngine.from_yaml(catalog, llm=llm)
        result = engine.search(query, depth=depth, max_results=max_results)
    else:
        site_list = [s.strip() for s in (sites or "").split(",") if s.strip()]
        if not site_list:
            console.print("[red]Provide --catalog or --sites[/red]")
            raise typer.Exit(1)
        from .engine import search as one_shot

        result = one_shot(query, sites=site_list, llm=llm, depth=depth, max_results=max_results)

    if json_out:
        console.print_json(result.model_dump_json())
        return

    console.print(
        f"\n[bold]{len(result.chunks)}[/bold] results "
        f"in {result.duration_ms:.0f} ms "
        f"(${result.cost_estimate_usd:.4f}, {result.tokens_used.input + result.tokens_used.output} tokens)"
    )
    if result.errors:
        for err in result.errors:
            console.print(f"[yellow]warn[/yellow] {err}")

    table = Table(show_lines=False)
    table.add_column("#", justify="right", style="dim")
    table.add_column("Site")
    table.add_column("Title")
    table.add_column("Score", justify="right")
    for i, c in enumerate(result.chunks, 1):
        table.add_row(str(i), c.site, c.title[:80], f"{c.relevance_score:.2f}")
    console.print(table)
    for i, c in enumerate(result.chunks, 1):
        console.print(f"\n[dim]{i}.[/dim] [link]{c.source_url}[/link]")
        if c.snippet:
            console.print(f"   {c.snippet[:200]}")


@app.command("install-browser")
def install_browser(
    browser: str = typer.Option("chromium", "--browser", "-b"),
):
    """Install Playwright browsers needed by the browser adapter."""
    try:
        import playwright  # noqa: F401
    except ImportError:
        console.print("[red]playwright is not installed. Run: pip install 'curio[browser]'[/red]")
        raise typer.Exit(1) from None
    cmd = [sys.executable, "-m", "playwright", "install", browser]
    console.print(f"[dim]$ {' '.join(cmd)}[/dim]")
    raise typer.Exit(subprocess.call(cmd))


@app.command()
def serve(
    port: int = typer.Option(8080, "--port", "-p"),
    host: str = typer.Option("127.0.0.1", "--host"),
    catalog: Optional[Path] = typer.Option(None, "--catalog", "-c"),
):
    """Start the FastAPI dashboard."""
    try:
        import uvicorn

        from .server import build_app
    except ImportError:
        console.print("[red]Dashboard requires extras: pip install 'curio[server]'[/red]")
        raise typer.Exit(1) from None
    fastapi_app = build_app(catalog_path=catalog)
    uvicorn.run(fastapi_app, host=host, port=port, log_level="info")


# --- catalog sub-app --------------------------------------------------------


@catalog_app.command("add")
def catalog_add(
    url: str,
    category: Optional[str] = typer.Option(None, "--category"),
    description: Optional[str] = typer.Option(None, "--description", "-D"),
    tags: Optional[str] = typer.Option(None, "--tags", help="Comma-separated tags"),
    db: Path = typer.Option(Path("~/.curio/catalog.db").expanduser(), "--db"),
):
    cat = Catalog(db.expanduser())
    site = Site(
        url=url,
        category=category,
        description=description,
        tags=[t.strip() for t in (tags or "").split(",") if t.strip()],
    )
    cat.add(site, replace=True)
    console.print(f"[green]added[/green] {site.url}")


@catalog_app.command("list")
def catalog_list(
    db: Path = typer.Option(Path("~/.curio/catalog.db").expanduser(), "--db"),
    json_out: bool = typer.Option(False, "--json"),
):
    cat = Catalog(db.expanduser())
    sites = cat.list()
    if json_out:
        console.print_json(json.dumps(cat.to_dicts()))
        return
    table = Table()
    table.add_column("URL")
    table.add_column("Category")
    table.add_column("Tags")
    table.add_column("Behavior")
    for s in sites:
        table.add_row(s.url, s.category or "-", ", ".join(s.tags) or "-", s.behavior)
    console.print(table)
    console.print(f"[dim]{len(sites)} site(s)[/dim]")


@catalog_app.command("remove")
def catalog_remove(
    url: str,
    db: Path = typer.Option(Path("~/.curio/catalog.db").expanduser(), "--db"),
):
    cat = Catalog(db.expanduser())
    if cat.remove(url):
        console.print(f"[green]removed[/green] {url}")
    else:
        console.print(f"[yellow]not found:[/yellow] {url}")


@catalog_app.command("import")
def catalog_import(
    yaml_path: Path,
    db: Path = typer.Option(Path("~/.curio/catalog.db").expanduser(), "--db"),
):
    cat = Catalog(db.expanduser())
    added = cat.load_yaml(yaml_path, replace=True)
    console.print(f"[green]imported[/green] {len(added)} site(s) from {yaml_path}")


@catalog_app.command("export")
def catalog_export(
    out: Path = typer.Argument(..., help="Output YAML path"),
    db: Path = typer.Option(Path("~/.curio/catalog.db").expanduser(), "--db"),
):
    cat = Catalog(db.expanduser())
    out.write_text(cat.export_yaml(), encoding="utf-8")
    console.print(f"[green]wrote[/green] {out}")


# --- mcp sub-app ------------------------------------------------------------


@mcp_app.command("serve")
def mcp_serve(
    catalog: Path = typer.Option(..., "--catalog", "-c"),
    llm: str = typer.Option("ollama/qwen2.5:14b", "--llm"),
):
    """Run curio as an MCP server. Requires `pip install 'curio[mcp]'`."""
    try:
        from .integrations.mcp import run_stdio_server
    except ImportError as e:
        console.print(f"[red]MCP extras not installed: {e}[/red]")
        raise typer.Exit(1) from None
    run_stdio_server(catalog_path=catalog, llm=llm)


if __name__ == "__main__":
    app()
