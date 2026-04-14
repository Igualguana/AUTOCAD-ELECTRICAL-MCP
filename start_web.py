"""
start_web.py — Starts the AutoCAD Electrical Web Interface (Mode B).

Usage
-----
    python start_web.py              # default: http://127.0.0.1:8080
    python start_web.py --port 9090
    python start_web.py --host 0.0.0.0 --port 8080   # expose on LAN
"""

from __future__ import annotations

import argparse
import os
import sys
import webbrowser
from pathlib import Path

# ── Ensure project root is in sys.path ──────────────────────────────────────
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

# ── Pre-flight checks ────────────────────────────────────────────────────────
def check_dependencies() -> bool:
    missing = []
    for pkg, import_name in [
        ("fastapi",   "fastapi"),
        ("uvicorn",   "uvicorn"),
        ("httpx",     "httpx"),
        ("pyyaml",    "yaml"),
        ("python-dotenv", "dotenv"),
    ]:
        try:
            __import__(import_name)
        except ImportError:
            missing.append(pkg)

    if missing:
        print(f"\n[ERROR] Missing packages: {', '.join(missing)}")
        print("Install with:")
        print(f"  pip install {' '.join(missing)}\n")
        return False
    return True


def check_env() -> None:
    env_file = ROOT / ".env"
    if not env_file.exists():
        example = ROOT / ".env.example"
        if example.exists():
            import shutil
            shutil.copy(example, env_file)
            print(f"[INFO] Created .env from .env.example — edit it to add API keys if needed.")
        else:
            print("[WARN] No .env file found. API keys may be missing for non-Ollama providers.")


def main() -> None:
    parser = argparse.ArgumentParser(description="AutoCAD Electrical Web Interface")
    parser.add_argument("--host", default="127.0.0.1", help="Host to bind (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8080, help="Port (default: 8080)")
    parser.add_argument("--no-browser", action="store_true", help="Don't open browser automatically")
    parser.add_argument("--reload", action="store_true", help="Enable auto-reload (development mode)")
    args = parser.parse_args()

    print("\n" + "=" * 60)
    print("  AutoCAD Electrical - AI Control Center")
    print("  Mode B: Web Interface + Ollama (without Claude)")
    print("=" * 60)

    if not check_dependencies():
        sys.exit(1)

    check_env()

    url = f"http://{args.host}:{args.port}"
    print(f"\n  Backend:   {url}/api/docs")
    print(f"  Frontend:  {url}")
    print(f"\n  Press Ctrl+C to stop.\n")

    if not args.no_browser:
        import threading
        threading.Timer(1.5, lambda: webbrowser.open(url)).start()

    import uvicorn
    uvicorn.run(
        "web.backend.app:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_level="info",
        access_log=True,
    )


if __name__ == "__main__":
    main()
