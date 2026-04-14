"""Ollama Model Manager — browse, search, pull and manage the full Ollama library.

Usage examples::

    # Browse all categories
    python scripts/ollama_manager.py browse

    # Browse a specific category
    python scripts/ollama_manager.py browse --category coding

    # Search the library
    python scripts/ollama_manager.py search llama vision

    # Pull a model (with live progress bar)
    python scripts/ollama_manager.py pull llama3.2:3b

    # List locally installed models
    python scripts/ollama_manager.py list

    # Show detailed info for an installed model
    python scripts/ollama_manager.py info llama3.2

    # Show currently running models (in GPU/CPU memory)
    python scripts/ollama_manager.py running

    # Delete a local model
    python scripts/ollama_manager.py delete llama3.2:3b

    # Set a model as the active Ollama model in config.yaml
    python scripts/ollama_manager.py use deepseek-r1:7b

    # Copy a model to a custom name
    python scripts/ollama_manager.py copy llama3.2 my-llama
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

# Ensure project root is on sys.path
_ROOT = Path(__file__).parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import click
from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    DownloadColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeElapsedColumn,
    TransferSpeedColumn,
)
from rich.table import Table
from rich.text import Text

from src.providers.ollama import OllamaProvider, OLLAMA_CATALOG
from src.config import get_config

console = Console()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_provider() -> OllamaProvider:
    cfg = get_config()
    ollama_cfg = cfg.get_provider_config("ollama")
    return OllamaProvider(
        base_url=ollama_cfg.get("base_url", "http://localhost:11434"),
        model=ollama_cfg.get("model", "llama3.2"),
        timeout=int(ollama_cfg.get("timeout", 120)),
    )


def _fmt_bytes(n: int) -> str:
    """Human-readable file size."""
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024  # type: ignore[assignment]
    return f"{n:.1f} TB"


def _check_connection(provider: OllamaProvider) -> bool:
    if not provider.is_available():
        console.print(
            Panel(
                "[red]Ollama is not running.[/red]\n\n"
                "Start it with:  [bold cyan]ollama serve[/bold cyan]\n"
                "Or download from: [link=https://ollama.com]https://ollama.com[/link]",
                title="[red]Connection Error[/red]",
                border_style="red",
            )
        )
        return False
    return True


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

@click.group()
def cli() -> None:
    """Ollama Model Manager — full library access for AutoCAD Electrical MCP."""


# ── browse ──────────────────────────────────────────────────────────────────

@cli.command()
@click.option("--category", "-c", default="", help="Filter by category name (partial match).")
def browse(category: str) -> None:
    """Browse the Ollama model catalog by category."""
    catalog = OLLAMA_CATALOG

    if category:
        # Single category view
        matched = {k: v for k, v in catalog.items() if category.lower() in k.lower()}
        if not matched:
            console.print(f"[red]No category matching '{category}'.[/red]")
            console.print("Available:", ", ".join(catalog.keys()))
            return
        for cat_name, models in matched.items():
            _print_category_table(cat_name, models)
    else:
        # All categories summary
        summary = Table(title="Ollama Library — Categories", show_header=True, border_style="blue")
        summary.add_column("Category", style="cyan", min_width=25)
        summary.add_column("Models", style="green", justify="right")
        summary.add_column("Example models", style="dim")
        for cat_name, models in catalog.items():
            examples = ", ".join(m["name"] for m in models[:3])
            summary.add_row(cat_name, str(len(models)), examples + ("…" if len(models) > 3 else ""))
        console.print(summary)
        console.print(
            "\n[dim]Use [bold]browse --category <name>[/bold] to see models in a category.[/dim]"
        )


def _print_category_table(cat_name: str, models: list[dict]) -> None:
    table = Table(title=f"[cyan]{cat_name}[/cyan]", show_header=True, border_style="cyan")
    table.add_column("Model", style="bold green", min_width=22)
    table.add_column("Description", style="white", min_width=40)
    table.add_column("Available sizes", style="yellow")
    for m in models:
        sizes = "  ".join(m["sizes"])
        table.add_row(m["name"], m["desc"], sizes)
    console.print(table)
    console.print(
        "[dim]Pull example: [bold]python scripts/ollama_manager.py pull llama3.2:3b[/bold][/dim]\n"
    )


# ── search ──────────────────────────────────────────────────────────────────

@cli.command()
@click.argument("query", nargs=-1, required=True)
@click.option("--limit", "-n", default=20, help="Max results (default 20).")
@click.option("--offline", is_flag=True, default=False, help="Use offline catalog only.")
def search(query: tuple[str, ...], limit: int, offline: bool) -> None:
    """Search the Ollama library for models matching QUERY."""
    q = " ".join(query)
    provider = _make_provider()

    if offline:
        results = provider._search_offline_catalog(q, limit)
    else:
        console.print(f"[dim]Searching Ollama library for '[bold]{q}[/bold]'…[/dim]")
        results = asyncio.run(provider.search_library(q, limit))

    if not results:
        console.print(f"[yellow]No models found for '{q}'.[/yellow]")
        return

    table = Table(
        title=f"Search results for '[cyan]{q}[/cyan]'",
        show_header=True,
        border_style="green",
    )
    table.add_column("Model", style="bold green", min_width=22)
    table.add_column("Description", style="white", min_width=40)
    table.add_column("Sizes / Tags", style="yellow")
    table.add_column("Source", style="dim")

    for r in results:
        sizes = ""
        if "sizes" in r:
            sizes = "  ".join(r["sizes"])
        elif "tags" in r:
            sizes = str(r.get("tags", ""))
        desc = r.get("description", r.get("desc", ""))
        source = r.get("source", "registry")
        table.add_row(r["name"], desc, sizes, source)

    console.print(table)
    console.print(
        "[dim]Pull a model: [bold]python scripts/ollama_manager.py pull <name>:<size>[/bold][/dim]"
    )


# ── pull ────────────────────────────────────────────────────────────────────

@cli.command()
@click.argument("model")
@click.option("--set-active", "-a", is_flag=True, default=False,
              help="Set as the active Ollama model in config.yaml after pulling.")
def pull(model: str, set_active: bool) -> None:
    """Pull MODEL from the Ollama registry with a live progress bar."""
    provider = _make_provider()
    if not _check_connection(provider):
        return

    console.print(f"[cyan]Pulling[/cyan] [bold]{model}[/bold] from Ollama registry…\n")

    progress = Progress(
        SpinnerColumn(),
        TextColumn("[bold blue]{task.description}"),
        BarColumn(bar_width=40),
        DownloadColumn(),
        TransferSpeedColumn(),
        TimeElapsedColumn(),
        console=console,
    )

    async def _do_pull() -> None:
        task_id = progress.add_task(f"Pulling {model}", total=None)
        with progress:
            async for chunk in provider.pull_model(model):
                status = chunk["status"]
                total = chunk["total"]
                completed = chunk["completed"]
                if total > 0:
                    progress.update(task_id, total=total, completed=completed,
                                    description=f"[blue]{status}[/blue]")
                else:
                    progress.update(task_id, description=f"[dim]{status}[/dim]")

    try:
        asyncio.run(_do_pull())
        console.print(f"\n[green]Successfully pulled[/green] [bold]{model}[/bold]")

        if set_active:
            _set_active_model(model)
    except Exception as exc:
        console.print(f"\n[red]Pull failed:[/red] {exc}")
        sys.exit(1)


# ── list ────────────────────────────────────────────────────────────────────

@cli.command(name="list")
def list_models() -> None:
    """List all models installed locally in Ollama."""
    provider = _make_provider()
    if not _check_connection(provider):
        return

    models = asyncio.run(provider.list_models())

    if not models:
        console.print("[yellow]No models installed. Use 'pull' to download one.[/yellow]")
        return

    # Get active model from config
    cfg = get_config()
    active = cfg.get_provider_config("ollama").get("model", "")

    table = Table(title="Locally Installed Ollama Models", show_header=True, border_style="green")
    table.add_column("Model", style="bold", min_width=28)
    table.add_column("Size", justify="right", style="yellow")
    table.add_column("Family", style="cyan")
    table.add_column("Quantization", style="dim")
    table.add_column("Active", style="bold green")

    for m in models:
        name = m["name"]
        size = _fmt_bytes(m.get("size", 0))
        details = m.get("details", {})
        family = details.get("family", details.get("families", ["-"])[0] if details.get("families") else "-")
        quant = details.get("quantization_level", "-")
        is_active = "✓" if name == active or name.split(":")[0] == active else ""
        table.add_row(name, size, str(family), str(quant), is_active)

    console.print(table)
    console.print(f"\n[dim]Total models: {len(models)}[/dim]")
    console.print("[dim]Use [bold]use <model>[/bold] to set the active model.[/dim]")


# ── info ────────────────────────────────────────────────────────────────────

@cli.command()
@click.argument("model")
def info(model: str) -> None:
    """Show detailed information about an installed model."""
    provider = _make_provider()
    if not _check_connection(provider):
        return

    data = asyncio.run(provider.get_model_info(model))

    if "error" in data:
        console.print(f"[red]Error:[/red] {data['error']}")
        return

    console.print(Panel(f"[bold cyan]{model}[/bold cyan]", title="Model Info"))

    # Model file
    if "modelfile" in data:
        lines = data["modelfile"].splitlines()[:20]
        console.print("[bold]Modelfile (first 20 lines):[/bold]")
        for line in lines:
            console.print(f"  [dim]{line}[/dim]")
        console.print()

    # Details table
    details = data.get("details", {})
    if details:
        table = Table(show_header=False, box=None, padding=(0, 2))
        table.add_column("Key", style="cyan")
        table.add_column("Value", style="white")
        for k, v in details.items():
            table.add_row(k.replace("_", " ").title(), str(v))
        console.print(table)

    # Parameters
    if "parameters" in data and data["parameters"]:
        console.print(f"\n[bold]Parameters:[/bold]\n[dim]{data['parameters']}[/dim]")

    # License
    if "license" in data and data["license"]:
        preview = data["license"][:200] + ("…" if len(data["license"]) > 200 else "")
        console.print(f"\n[bold]License:[/bold] [dim]{preview}[/dim]")


# ── running ──────────────────────────────────────────────────────────────────

@cli.command()
def running() -> None:
    """Show models currently loaded in GPU/CPU memory."""
    provider = _make_provider()
    if not _check_connection(provider):
        return

    models = asyncio.run(provider.list_running_models())

    if not models:
        console.print("[yellow]No models currently loaded in memory.[/yellow]")
        return

    table = Table(title="Running Ollama Models", show_header=True, border_style="yellow")
    table.add_column("Model", style="bold green", min_width=28)
    table.add_column("VRAM", justify="right", style="cyan")
    table.add_column("RAM", justify="right", style="blue")
    table.add_column("Expires at", style="dim")

    for m in models:
        name = m.get("name", "?")
        vram = _fmt_bytes(m.get("size_vram", 0))
        ram = _fmt_bytes(m.get("size", 0) - m.get("size_vram", 0))
        expires = m.get("expires_at", "-")
        if isinstance(expires, str) and len(expires) > 19:
            expires = expires[:19].replace("T", " ")
        table.add_row(name, vram, ram, expires)

    console.print(table)


# ── delete ───────────────────────────────────────────────────────────────────

@cli.command()
@click.argument("model")
@click.option("--yes", "-y", is_flag=True, default=False, help="Skip confirmation prompt.")
def delete(model: str, yes: bool) -> None:
    """Delete a locally installed model."""
    provider = _make_provider()
    if not _check_connection(provider):
        return

    if not yes:
        click.confirm(
            f"Delete [bold]{model}[/bold] from local storage?", abort=True
        )

    result = asyncio.run(provider.delete_model(model))
    if result.get("success"):
        console.print(f"[green]Deleted[/green] [bold]{model}[/bold]")
    else:
        console.print(f"[red]Failed to delete:[/red] {result.get('error', 'Unknown error')}")


# ── use ──────────────────────────────────────────────────────────────────────

@cli.command()
@click.argument("model")
def use(model: str) -> None:
    """Set MODEL as the active Ollama model in config.yaml."""
    _set_active_model(model)


def _set_active_model(model: str) -> None:
    cfg = get_config(reload=True)
    cfg._data["active_provider"] = "ollama"
    cfg._data["providers"]["ollama"]["model"] = model
    cfg.save()
    console.print(
        f"[green]Active model set to:[/green] [bold cyan]{model}[/bold cyan] "
        f"[dim](provider: ollama)[/dim]"
    )
    console.print("[dim]config.yaml updated. Restart the MCP server to apply.[/dim]")


# ── copy ─────────────────────────────────────────────────────────────────────

@cli.command()
@click.argument("source")
@click.argument("destination")
def copy(source: str, destination: str) -> None:
    """Copy SOURCE model to DESTINATION name (useful for custom variants)."""
    provider = _make_provider()
    if not _check_connection(provider):
        return

    result = asyncio.run(provider.copy_model(source, destination))
    if result.get("success"):
        console.print(
            f"[green]Copied[/green] [bold]{source}[/bold] → [bold cyan]{destination}[/bold cyan]"
        )
    else:
        console.print(f"[red]Copy failed:[/red] {result.get('error', 'Unknown error')}")


# ── categories ───────────────────────────────────────────────────────────────

@cli.command()
def categories() -> None:
    """List all model categories in the offline catalog."""
    provider = _make_provider()
    cats = provider.list_categories()
    table = Table(title="Ollama Model Categories", show_header=True, border_style="cyan")
    table.add_column("#", style="dim", justify="right")
    table.add_column("Category", style="cyan")
    table.add_column("Browse command", style="dim")
    for i, cat in enumerate(cats, 1):
        slug = cat.split("/")[0].strip().lower().replace(" ", "-")
        table.add_row(str(i), cat, f"browse --category {slug}")
    console.print(table)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    cli()
