"""Test script for the AutoCAD COM connection.

Prints AutoCAD version, active document info, and basic drawing stats.

Usage::

    python scripts/test_connection.py
    python scripts/test_connection.py --com-object "AutoCAD.Application.25"
"""

from __future__ import annotations

import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import click
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

console = Console()


@click.command(context_settings={"help_option_names": ["-h", "--help"]})
@click.option(
    "--com-object",
    default="AutoCAD.Application",
    show_default=True,
    help="COM ProgID for AutoCAD (e.g. 'AutoCAD.Application.25' for 2025).",
)
@click.option(
    "--timeout",
    default=30,
    show_default=True,
    type=int,
    help="Connection timeout in seconds.",
)
def main(com_object: str, timeout: int) -> None:
    """Test the COM connection to AutoCAD Electrical 2025."""

    console.print(Panel.fit(
        "[bold cyan]AutoCAD Electrical MCP – Connection Test[/bold cyan]",
        border_style="cyan",
    ))

    # -----------------------------------------------------------------------
    # Step 1: Check pywin32
    # -----------------------------------------------------------------------
    console.print("\n[bold]1. Checking pywin32 installation…[/bold]")
    try:
        import win32com.client
        import pywintypes
        console.print("  [green]OK[/green] pywin32 is installed.")
    except ImportError:
        console.print(
            "  [red]X[/red] pywin32 is NOT installed.\n"
            "  Run: [cyan]pip install pywin32[/cyan]"
        )
        sys.exit(1)

    # -----------------------------------------------------------------------
    # Step 2: Attempt COM connection
    # -----------------------------------------------------------------------
    console.print(f"\n[bold]2. Connecting to AutoCAD via COM object '{com_object}'…[/bold]")
    try:
        from src.autocad.connection import AutoCADConnection, reset_connection
        reset_connection()  # ensure fresh instance for the test
        conn = AutoCADConnection(com_object=com_object, timeout=timeout)
        conn.connect()
        console.print("  [green]OK[/green] COM connection established.")
    except Exception as exc:
        console.print(f"  [red]X[/red] Connection failed: {exc}")
        console.print(
            "\n  [yellow]Make sure AutoCAD Electrical 2025 is running "
            "and has a drawing open.[/yellow]"
        )
        sys.exit(1)

    # -----------------------------------------------------------------------
    # Step 3: Application info
    # -----------------------------------------------------------------------
    console.print("\n[bold]3. AutoCAD Application Info[/bold]")
    try:
        app = conn.get_application()
        table = Table(show_header=False, box=None, padding=(0, 2))
        table.add_column("Property", style="dim")
        table.add_column("Value", style="green")
        table.add_row("Name", app.Name)
        table.add_row("Version", app.Version)
        table.add_row("Full name", app.FullName)
        table.add_row("Visible", str(app.Visible))
        console.print(table)
    except Exception as exc:
        console.print(f"  [yellow]Could not retrieve app info: {exc}[/yellow]")

    # -----------------------------------------------------------------------
    # Step 4: Active document
    # -----------------------------------------------------------------------
    console.print("\n[bold]4. Active Document[/bold]")
    try:
        doc = conn.get_active_document()
        ms = conn.get_model_space()
        table = Table(show_header=False, box=None, padding=(0, 2))
        table.add_column("Property", style="dim")
        table.add_column("Value", style="green")
        table.add_row("Name", doc.Name)
        table.add_row("Full path", doc.FullName or "(not saved)")
        table.add_row("Saved", str(doc.Saved))
        table.add_row("ModelSpace entity count", str(ms.Count))
        console.print(table)
    except Exception as exc:
        console.print(
            f"  [yellow]No active document or could not query it: {exc}[/yellow]\n"
            "  Open a drawing in AutoCAD and re-run this test."
        )

    # -----------------------------------------------------------------------
    # Step 5: Open documents list
    # -----------------------------------------------------------------------
    console.print("\n[bold]5. All Open Documents[/bold]")
    try:
        app = conn.get_application()
        docs_table = Table("#", "Name", "Saved", show_header=True)
        for i in range(app.Documents.Count):
            d = app.Documents.Item(i)
            docs_table.add_row(str(i + 1), d.Name, str(d.Saved))
        console.print(docs_table)
    except Exception as exc:
        console.print(f"  [yellow]Could not enumerate documents: {exc}[/yellow]")

    # -----------------------------------------------------------------------
    # Step 6: Send a harmless command
    # -----------------------------------------------------------------------
    console.print("\n[bold]6. Sending a test command (ZOOM Extents)…[/bold]")
    try:
        conn.send_command("ZOOM E ")
        console.print("  [green]OK[/green] Command sent successfully.")
    except Exception as exc:
        console.print(f"  [yellow]Command send failed: {exc}[/yellow]")

    # -----------------------------------------------------------------------
    # Done
    # -----------------------------------------------------------------------
    console.print(Panel.fit(
        "[bold green]All connection tests passed.[/bold green]\n"
        "The AutoCAD Electrical MCP server is ready to use.",
        border_style="green",
    ))
    conn.disconnect()


if __name__ == "__main__":
    main()
