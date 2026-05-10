"""farol command-line interface."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from . import __version__
from .catalog import Catalog, Site
from .engine import SearchEngine

app = typer.Typer(
    add_completion=False,
    help="farol — curated AI search for agents.",
    no_args_is_help=True,
)
catalog_app = typer.Typer(help="Manage the site catalog.", no_args_is_help=True)
mcp_app = typer.Typer(help="Run farol as an MCP server.", no_args_is_help=True)
profiles_app = typer.Typer(help="Browse curated site profiles.", no_args_is_help=True)
app.add_typer(catalog_app, name="catalog")
app.add_typer(mcp_app, name="mcp")
app.add_typer(profiles_app, name="profiles")
console = Console()


@app.callback(invoke_without_command=True)
def _main(
    ctx: typer.Context,
    version: bool = typer.Option(
        False, "--version", "-V", is_eager=True, help="Show version and exit"
    ),
):
    if version:
        console.print(f"farol {__version__}")
        raise typer.Exit()
    if ctx.invoked_subcommand is None:
        typer.echo(ctx.get_help())
        raise typer.Exit()


# --- top-level commands -----------------------------------------------------


@app.command()
def search(
    query: str,
    catalog: Path | None = typer.Option(None, "--catalog", "-c", help="YAML catalog path"),
    sites: str | None = typer.Option(
        None, "--sites", help="Comma-separated list (overrides catalog)"
    ),
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
        console.print("[red]playwright is not installed. Run: pip install 'farol[browser]'[/red]")
        raise typer.Exit(1) from None
    cmd = [sys.executable, "-m", "playwright", "install", browser]
    console.print(f"[dim]$ {' '.join(cmd)}[/dim]")
    raise typer.Exit(subprocess.call(cmd))


@app.command()
def serve(
    port: int = typer.Option(8080, "--port", "-p"),
    host: str = typer.Option("127.0.0.1", "--host"),
    catalog: Path | None = typer.Option(None, "--catalog", "-c"),
):
    """Start the FastAPI dashboard."""
    try:
        import uvicorn

        from .server import build_app
    except ImportError:
        console.print("[red]Dashboard requires extras: pip install 'farol[server]'[/red]")
        raise typer.Exit(1) from None
    fastapi_app = build_app(catalog_path=catalog)
    uvicorn.run(fastapi_app, host=host, port=port, log_level="info")


# --- catalog sub-app --------------------------------------------------------


@catalog_app.command("add")
def catalog_add(
    url: str,
    category: str | None = typer.Option(None, "--category"),
    description: str | None = typer.Option(None, "--description", "-D"),
    tags: str | None = typer.Option(None, "--tags", help="Comma-separated tags"),
    db: Path = typer.Option(Path("~/.farol/catalog.db").expanduser(), "--db"),
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
    db: Path = typer.Option(Path("~/.farol/catalog.db").expanduser(), "--db"),
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
    db: Path = typer.Option(Path("~/.farol/catalog.db").expanduser(), "--db"),
):
    cat = Catalog(db.expanduser())
    if cat.remove(url):
        console.print(f"[green]removed[/green] {url}")
    else:
        console.print(f"[yellow]not found:[/yellow] {url}")


@catalog_app.command("import")
def catalog_import(
    yaml_path: Path,
    db: Path = typer.Option(Path("~/.farol/catalog.db").expanduser(), "--db"),
):
    cat = Catalog(db.expanduser())
    added = cat.load_yaml(yaml_path, replace=True)
    console.print(f"[green]imported[/green] {len(added)} site(s) from {yaml_path}")


@catalog_app.command("export")
def catalog_export(
    out: Path = typer.Argument(..., help="Output YAML path"),
    db: Path = typer.Option(Path("~/.farol/catalog.db").expanduser(), "--db"),
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
    """Run farol as an MCP server. Requires `pip install 'farol[mcp]'`."""
    try:
        from .integrations.mcp import run_stdio_server
    except ImportError as e:
        console.print(f"[red]MCP extras not installed: {e}[/red]")
        raise typer.Exit(1) from None
    run_stdio_server(catalog_path=catalog, llm=llm)


# --- profiles sub-app -------------------------------------------------------


@profiles_app.command("list")
def profiles_list():
    """List all curated site profiles bundled with farol."""
    from .profiles import list_profiles

    domains = list_profiles()
    if not domains:
        console.print("[yellow]No profiles bundled.[/yellow]")
        return
    console.print(f"[bold]{len(domains)}[/bold] curated profile(s):")
    for d in domains:
        console.print(f"  • {d}")


@profiles_app.command("show")
def profiles_show(domain: str):
    """Show a single profile in detail."""
    from .profiles import get_profile

    site = get_profile(domain)
    if not site:
        console.print(f"[yellow]No profile for {domain!r}[/yellow]")
        raise typer.Exit(1)
    table = Table(show_header=False)
    table.add_row("URL", site.url)
    table.add_row("Category", site.category or "-")
    table.add_row("Description", site.description or "-")
    table.add_row("Tags", ", ".join(site.tags) or "-")
    table.add_row("Search URL template", site.search_url_template or "-")
    table.add_row("Behavior", site.behavior)
    console.print(table)


@profiles_app.command("import")
def profiles_import(
    domains: str = typer.Argument(..., help="Comma-separated list, or 'all'"),
    db: Path = typer.Option(Path("~/.farol/catalog.db").expanduser(), "--db"),
):
    """Import one or more curated profiles into the local catalog."""
    from .catalog import Catalog
    from .profiles import get_profile, list_profiles

    cat = Catalog(db.expanduser())
    targets = (
        list_profiles()
        if domains.strip().lower() == "all"
        else [d.strip() for d in domains.split(",") if d.strip()]
    )
    added = 0
    for d in targets:
        site = get_profile(d)
        if not site:
            console.print(f"[yellow]skip {d}: no profile[/yellow]")
            continue
        cat.add(site, replace=True)
        added += 1
        console.print(f"[green]+[/green] {site.url}")
    console.print(f"\n[bold]{added}[/bold] profile(s) imported.")


if __name__ == "__main__":
    app()
