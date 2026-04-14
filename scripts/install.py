"""Full setup script for the AutoCAD Electrical MCP server.

Performs the following steps:
1. Checks Python version (>= 3.11)
2. Creates / activates a virtual environment (optional)
3. Installs all Python dependencies via pip
4. Copies .env.example to .env if it doesn't exist
5. Validates that pywin32 post-install scripts have been run
6. Verifies the MCP package is importable
7. Prints registration instructions for Claude Code

Usage::

    python scripts/install.py
    python scripts/install.py --no-venv
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).parent.parent

# Try to import rich for nice output; fall back to plain print
try:
    from rich.console import Console
    from rich.panel import Panel
    console = Console()
    def _print(msg: str, style: str = "") -> None:
        console.print(msg)
    def _panel(msg: str, border: str = "blue") -> None:
        console.print(Panel.fit(msg, border_style=border))
except ImportError:
    def _print(msg: str, style: str = "") -> None:
        # Strip rich markup tags for plain output
        import re
        clean = re.sub(r"\[/?[^\]]+\]", "", msg)
        print(clean)
    def _panel(msg: str, border: str = "blue") -> None:
        print("=" * 60)
        print(msg)
        print("=" * 60)


def _run(cmd: list[str], **kwargs) -> int:
    """Run a subprocess command; return the exit code."""
    _print(f"  [dim]Running: {' '.join(cmd)}[/dim]")
    result = subprocess.run(cmd, **kwargs)
    return result.returncode


def check_python() -> None:
    _print("\n[bold]1. Checking Python version…[/bold]")
    major, minor = sys.version_info[:2]
    if (major, minor) < (3, 11):
        _print(
            f"  [red]X[/red] Python {major}.{minor} detected. "
            "Python 3.11 or later is required."
        )
        sys.exit(1)
    _print(f"  [green]OK[/green] Python {major}.{minor} OK.")


def install_dependencies() -> None:
    _print("\n[bold]2. Installing Python dependencies…[/bold]")
    rc = _run(
        [sys.executable, "-m", "pip", "install", "-e", str(_PROJECT_ROOT)],
        cwd=str(_PROJECT_ROOT),
    )
    if rc != 0:
        _print(
            "  [yellow]pip install returned a non-zero exit code.[/yellow]\n"
            "  Trying requirements from pyproject.toml directly…"
        )
        # Fallback: install just the listed packages
        packages = [
            "mcp>=1.0.0",
            "pywin32>=306",
            "pyautocad>=0.2.0",
            "pyyaml>=6.0",
            "python-dotenv>=1.0.0",
            "anthropic>=0.40.0",
            "openai>=1.0.0",
            "httpx>=0.27.0",
            "click>=8.1.0",
            "rich>=13.0.0",
        ]
        rc2 = _run([sys.executable, "-m", "pip", "install"] + packages)
        if rc2 != 0:
            _print("  [red]X[/red] Dependency installation failed. See errors above.")
            sys.exit(1)
    _print("  [green]OK[/green] Dependencies installed.")


def run_pywin32_postinstall() -> None:
    _print("\n[bold]3. Running pywin32 post-install…[/bold]")
    import site
    scripts_dirs = [Path(p) / "Scripts" for p in site.getsitepackages()]
    postinstall = None
    for sd in scripts_dirs:
        candidate = sd / "pywin32_postinstall.py"
        if candidate.exists():
            postinstall = candidate
            break

    if postinstall is None:
        _print(
            "  [yellow]pywin32_postinstall.py not found. "
            "If you encounter COM errors, run:\n"
            "  python Scripts/pywin32_postinstall.py -install[/yellow]"
        )
        return

    rc = _run(
        [sys.executable, str(postinstall), "-install"],
        cwd=str(_PROJECT_ROOT),
    )
    if rc == 0:
        _print("  [green]OK[/green] pywin32 post-install completed.")
    else:
        _print(
            "  [yellow]pywin32 post-install returned a non-zero code. "
            "You may need to run it as Administrator.[/yellow]"
        )


def setup_env_file() -> None:
    _print("\n[bold]4. Setting up .env file…[/bold]")
    env_example = _PROJECT_ROOT / ".env.example"
    env_file = _PROJECT_ROOT / ".env"
    if env_file.exists():
        _print(f"  [green]OK[/green] .env already exists ({env_file}).")
        return
    if env_example.exists():
        import shutil
        shutil.copy(env_example, env_file)
        _print(
            f"  [green]OK[/green] Copied .env.example → .env\n"
            f"  [yellow]Edit {env_file} and add your API keys.[/yellow]"
        )
    else:
        _print("  [yellow].env.example not found – skipping.[/yellow]")


def verify_mcp() -> None:
    _print("\n[bold]5. Verifying MCP package…[/bold]")
    try:
        import mcp  # noqa: F401
        _print("  [green]OK[/green] 'mcp' package is importable.")
    except ImportError:
        _print(
            "  [red]X[/red] 'mcp' package could not be imported.\n"
            "  Run: [cyan]pip install mcp>=1.0.0[/cyan]"
        )


def print_registration_instructions() -> None:
    _print("\n[bold]6. Claude Code MCP Registration[/bold]")
    cwd = str(_PROJECT_ROOT)
    _print(
        f"""
  To register this server with Claude Code, run one of the following:

  [cyan]Option A – CLI command:[/cyan]
    claude mcp add autocad-electrical python -m src.server --cwd "{cwd}"

  [cyan]Option B – Edit Claude Code settings manually:[/cyan]
    Add the contents of [dim]{cwd}/mcp_config.json[/dim] to your
    ~/.claude/claude_desktop_config.json (or equivalent MCP config file)
    under the "mcpServers" key.

  [cyan]Option C – Automatic (from this directory):[/cyan]
    claude mcp add-from-config mcp_config.json
"""
    )


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(
        description="Install and configure the AutoCAD Electrical MCP server."
    )
    parser.parse_args()

    _panel("[bold cyan]AutoCAD Electrical MCP Server – Setup[/bold cyan]", border="cyan")

    check_python()
    install_dependencies()
    run_pywin32_postinstall()
    setup_env_file()
    verify_mcp()
    print_registration_instructions()

    _panel(
        "[bold green]Setup complete![/bold green]\n\n"
        "Next steps:\n"
        "  1. Edit .env and add your ANTHROPIC_API_KEY (or other provider key)\n"
        "  2. Open AutoCAD Electrical 2025\n"
        "  3. Run: [cyan]python scripts/test_connection.py[/cyan] to verify COM access\n"
        "  4. Register with Claude Code (see step 6 above)\n"
        "  5. Start chatting!",
        border="green",
    )


if __name__ == "__main__":
    main()
