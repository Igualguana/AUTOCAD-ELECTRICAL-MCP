"""CLI tool to switch the active AI provider and model.

Usage examples::

    python scripts/switch_model.py --provider ollama --model llama3.2
    python scripts/switch_model.py --provider claude --model claude-sonnet-4-6
    python scripts/switch_model.py --list
    python scripts/switch_model.py --status

The script modifies ``config.yaml`` in the project root so that the next
server startup (or ``get_config(reload=True)`` call) uses the new provider.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure the project root is on sys.path when running as a script
_PROJECT_ROOT = Path(__file__).parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import click
from rich.console import Console
from rich.table import Table

from src.config import get_config

console = Console(highlight=False)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_config():
    return get_config(reload=True)


def _print_provider_table(cfg) -> None:
    table = Table(title="Configured AI Providers", show_header=True)
    table.add_column("Provider", style="cyan")
    table.add_column("Model", style="green")
    table.add_column("Base URL / API", style="dim")
    table.add_column("Active", style="bold yellow")

    active = cfg.get_active_provider()
    for name, settings in cfg.providers.items():
        model = settings.get("model", "-")
        base = settings.get("base_url", settings.get("api_key", "-"))
        # Mask API keys
        if "api_key" in settings and settings["api_key"] and settings["api_key"] != "lm-studio":
            base = f"API key: {'*' * 8}"
        is_active = "[*]" if name == active else ""
        table.add_row(name, model, base, is_active)

    console.print(table)


# ---------------------------------------------------------------------------
# CLI commands
# ---------------------------------------------------------------------------

@click.command(context_settings={"help_option_names": ["-h", "--help"]})
@click.option(
    "--provider", "-p",
    type=str,
    default=None,
    help="Provider name: claude | ollama | openai | groq | lmstudio",
)
@click.option(
    "--model", "-m",
    type=str,
    default=None,
    help="Model identifier to set for the chosen provider.",
)
@click.option(
    "--list", "-l", "list_providers",
    is_flag=True,
    default=False,
    help="List all configured providers and their current models.",
)
@click.option(
    "--status", "-s",
    is_flag=True,
    default=False,
    help="Show the currently active provider and model.",
)
@click.option(
    "--ollama-list", "ollama_list",
    is_flag=True,
    default=False,
    help="List locally installed Ollama models.",
)
@click.option(
    "--ollama-search", "ollama_search",
    type=str,
    default=None,
    metavar="QUERY",
    help="Search the Ollama library (e.g. --ollama-search vision).",
)
@click.option(
    "--ollama-browse", "ollama_browse",
    is_flag=True,
    default=False,
    help="Browse the Ollama model catalog by category.",
)
def main(
    provider: str | None,
    model: str | None,
    list_providers: bool,
    status: bool,
    ollama_list: bool,
    ollama_search: str | None,
    ollama_browse: bool,
) -> None:
    """Switch the active AI provider / model for the AutoCAD Electrical MCP server.

    Changes are written to config.yaml and take effect on the next server start.

    \b
    Quick Ollama examples:
      --ollama-list              Show installed models
      --ollama-search vision     Search library for vision models
      --ollama-browse            Browse all categories
      -p ollama -m llama3.2:3b   Switch to a specific Ollama model

    For full Ollama management (pull, delete, info…) use:
      python scripts/ollama_manager.py --help
    """
    import asyncio
    from src.providers.ollama import OllamaProvider, OLLAMA_CATALOG

    cfg = _load_config()
    ollama_cfg = cfg.get_provider_config("ollama")
    ollama_provider = OllamaProvider(
        base_url=ollama_cfg.get("base_url", "http://localhost:11434"),
        model=ollama_cfg.get("model", "llama3.2"),
    )

    # --ollama-list
    if ollama_list:
        if not ollama_provider.is_available():
            console.print("[red]Ollama is not running.[/red] Start it with: [bold]ollama serve[/bold]")
            return
        models = asyncio.run(ollama_provider.list_models())
        if not models:
            console.print("[yellow]No Ollama models installed. Pull one with:[/yellow]")
            console.print("  python scripts/ollama_manager.py pull llama3.2")
            return
        t = Table(title="Installed Ollama Models", show_header=True)
        t.add_column("Model", style="green")
        t.add_column("Size", justify="right", style="yellow")
        t.add_column("Family", style="cyan")
        for m in models:
            size_gb = m.get("size", 0) / 1e9
            family = m.get("details", {}).get("family", "-")
            t.add_row(m["name"], f"{size_gb:.1f} GB", str(family))
        console.print(t)
        console.print("[dim]Use -p ollama -m <name> to switch to a model.[/dim]")
        return

    # --ollama-search
    if ollama_search:
        console.print(f"[dim]Searching for '[bold]{ollama_search}[/bold]'…[/dim]")
        results = asyncio.run(ollama_provider.search_library(ollama_search, limit=15))
        if not results:
            console.print(f"[yellow]No results for '{ollama_search}'.[/yellow]")
            return
        t = Table(title=f"Ollama search: {ollama_search}", show_header=True)
        t.add_column("Model", style="green", min_width=20)
        t.add_column("Description", style="white", min_width=35)
        t.add_column("Sizes", style="yellow")
        for r in results:
            sizes = "  ".join(r.get("sizes", [])) or str(r.get("tags", "-"))
            t.add_row(r["name"], r.get("description", r.get("desc", "")), sizes)
        console.print(t)
        console.print("[dim]Pull: python scripts/ollama_manager.py pull <model>:<size>[/dim]")
        return

    # --ollama-browse
    if ollama_browse:
        t = Table(title="Ollama Library Categories", show_header=True)
        t.add_column("Category", style="cyan", min_width=25)
        t.add_column("Models", justify="right", style="green")
        t.add_column("Examples", style="dim")
        for cat, models in OLLAMA_CATALOG.items():
            examples = ", ".join(m["name"] for m in models[:3])
            t.add_row(cat, str(len(models)), examples + ("…" if len(models) > 3 else ""))
        console.print(t)
        console.print("[dim]Full browser: python scripts/ollama_manager.py browse[/dim]")
        return

    # --list
    if list_providers:
        _print_provider_table(cfg)
        return

    # --status
    if status:
        active = cfg.get_active_provider()
        provider_cfg = cfg.get_provider_config(active)
        current_model = provider_cfg.get("model", "unknown")
        console.print(
            f"[bold]Active provider:[/bold] [cyan]{active}[/cyan]  "
            f"[bold]Model:[/bold] [green]{current_model}[/green]"
        )
        return

    # No flags and no --provider → show help
    if provider is None and model is None:
        click.echo(click.get_current_context().get_help())
        return

    # Validate provider
    if provider is not None and provider not in cfg.list_providers():
        available = ", ".join(cfg.list_providers())
        console.print(
            f"[red]Error:[/red] Unknown provider '{provider}'. "
            f"Available providers: {available}"
        )
        sys.exit(1)

    # Apply changes
    if provider is not None:
        cfg.active_provider = provider
        console.print(f"[green]Active provider set to:[/green] [cyan]{provider}[/cyan]")

    if model is not None:
        target_provider = provider or cfg.get_active_provider()
        provider_cfg = cfg.get_provider_config(target_provider)
        provider_cfg["model"] = model
        # Write back into the config data structure
        cfg._data["providers"][target_provider]["model"] = model
        console.print(
            f"[green]Model for '{target_provider}' set to:[/green] [cyan]{model}[/cyan]"
        )

    # Persist to config.yaml
    try:
        cfg.save()
        console.print("[dim]config.yaml updated.[/dim]")
    except Exception as exc:
        console.print(f"[red]Failed to save config.yaml:[/red] {exc}")
        sys.exit(1)

    # Show the resulting status
    active = cfg.get_active_provider()
    current_model = cfg.get_provider_config(active).get("model", "unknown")
    console.print(
        f"\n[bold]Now using:[/bold] [cyan]{active}[/cyan] / [green]{current_model}[/green]"
    )


if __name__ == "__main__":
    main()
