"""FastAPI backend for AutoCAD Electrical Web Interface — Mode B (without Claude).

Endpoints
---------
GET  /                      Serve the frontend dashboard
GET  /api/status            AutoCAD + Ollama + MCP status
GET  /api/tools             List all 34 registered tools
GET  /api/logs              Recent log entries
GET  /api/history           Chat history
GET  /api/drawing/info      Active drawing + project info
GET  /api/providers         Configured AI providers
POST /api/providers/switch  Switch active provider
POST /api/chat              Natural-language → AI → AutoCAD
POST /api/execute           Direct tool execution (no AI)
DELETE /api/history         Clear chat history
DELETE /api/logs            Clear log buffer
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Any, Optional

# Ensure project root is in sys.path so src.* imports work when the server is
# started from the project directory via `python start_web.py`.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from src.autocad.connection import AutoCADConnectionError, get_connection
from src.autocad.detector import detect as _detect_autocad
from src.config import get_config
from src.providers import get_provider
from web.backend.chat import TOOL_REGISTRY, process_message
from web.backend.state import (
    add_log,
    clear_history,
    clear_logs,
    get_history,
    get_logs,
)
from src.tools.project import (
    list_drawings  as _tool_list_drawings,
    open_drawing   as _tool_open_drawing,
    get_active_drawing as _tool_get_active,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------

app = FastAPI(
    title="AutoCAD Electrical — Web Interface",
    description="Local web UI for AutoCAD Electrical MCP Server (Mode B — without Claude)",
    version="1.0.0",
    docs_url="/api/docs",
    redoc_url=None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

_FRONTEND_DIR = Path(__file__).parent.parent / "frontend"
app.mount("/static", StaticFiles(directory=str(_FRONTEND_DIR)), name="static")

add_log("INFO", "Web backend initialised — AutoCAD Electrical Mode B", "system")


# ---------------------------------------------------------------------------
# Static frontend
# ---------------------------------------------------------------------------

@app.get("/", include_in_schema=False)
def root() -> FileResponse:
    return FileResponse(str(_FRONTEND_DIR / "index.html"))


# ---------------------------------------------------------------------------
# PWA — manifest, service worker, favicon
# ---------------------------------------------------------------------------

@app.get("/manifest.json", include_in_schema=False)
def manifest_json() -> FileResponse:
    return FileResponse(
        str(_FRONTEND_DIR / "manifest.json"),
        media_type="application/manifest+json",
    )


@app.get("/sw.js", include_in_schema=False)
def service_worker() -> FileResponse:
    # Service-Worker-Allowed header lets the SW control scope "/"
    # even though the file is served from /sw.js.
    return FileResponse(
        str(_FRONTEND_DIR / "sw.js"),
        media_type="application/javascript",
        headers={"Service-Worker-Allowed": "/"},
    )


@app.get("/favicon.ico", include_in_schema=False)
def favicon() -> FileResponse:
    return FileResponse(
        str(_FRONTEND_DIR / "icons" / "favicon.png"),
        media_type="image/png",
    )


# ---------------------------------------------------------------------------
# Status
# ---------------------------------------------------------------------------

@app.get("/api/status")
def get_status() -> dict[str, Any]:
    """Return live status of AutoCAD, Ollama, and the MCP server."""
    status: dict[str, Any] = {
        "autocad": {"connected": False, "version": None, "drawing": None, "error": None},
        "ollama": {"available": False, "url": None, "models": [], "error": None},
        "mcp": {"running": True, "tools": len(TOOL_REGISTRY)},
        "provider": {"active": None, "model": None},
    }

    # ── AutoCAD ──────────────────────────────────────────────────────────
    try:
        try:
            import pythoncom
            pythoncom.CoInitialize()
        except Exception:
            pass

        cfg = get_config()
        ac_cfg = cfg.autocad
        conn = get_connection(
            com_object=ac_cfg.get("com_object", "AutoCAD.Application"),
            timeout=5,
            auto_connect=True,
        )
        if conn.is_connected():
            app_obj = conn.get_application()
            status["autocad"]["connected"] = True
            status["autocad"]["version"] = str(app_obj.Name)
            try:
                doc = conn.get_active_document()
                status["autocad"]["drawing"] = doc.Name if doc else None
            except Exception:
                pass
    except AutoCADConnectionError as exc:
        status["autocad"]["error"] = str(exc)
    except Exception as exc:
        status["autocad"]["error"] = str(exc)

    # ── Ollama ───────────────────────────────────────────────────────────
    try:
        cfg = get_config()
        ollama_cfg = cfg.get_provider_config("ollama")
        base_url: str = ollama_cfg.get("base_url", "http://localhost:11434")
        status["ollama"]["url"] = base_url
        with httpx.Client(timeout=2.0) as client:
            resp = client.get(f"{base_url}/api/tags")
            if resp.status_code == 200:
                models = resp.json().get("models", [])
                status["ollama"]["available"] = True
                status["ollama"]["models"] = [m["name"] for m in models]
    except Exception as exc:
        status["ollama"]["error"] = str(exc)

    # ── AutoCAD variant detection ────────────────────────────────────────
    try:
        acad_info = _detect_autocad(force=False)
        status["autocad"]["variant"] = acad_info.variant
        status["autocad"]["features"] = acad_info.features
        status["autocad"]["detection_method"] = acad_info.detection_method
    except Exception:
        pass

    # ── Active provider ──────────────────────────────────────────────────
    try:
        cfg = get_config()
        active = cfg.active_provider
        p_cfg = cfg.get_provider_config(active)
        status["provider"]["active"] = active
        status["provider"]["model"] = p_cfg.get("model", "")
    except Exception:
        pass

    return status


# ---------------------------------------------------------------------------
# AutoCAD detection info
# ---------------------------------------------------------------------------

@app.get("/api/autocad/info")
def get_autocad_info() -> dict[str, Any]:
    """Return detected AutoCAD variant, version, features, and running state."""
    try:
        info = _detect_autocad(force=True)   # force re-detect on request
        return info.to_dict()
    except Exception as exc:
        return {"error": str(exc), "variant": "unknown"}


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

@app.get("/api/tools")
def get_tools() -> dict[str, Any]:
    """Return all registered AutoCAD tools grouped by category."""
    by_category: dict[str, list[dict]] = {}
    for name, info in TOOL_REGISTRY.items():
        cat = info.get("category", "Other")
        by_category.setdefault(cat, []).append(
            {
                "name": name,
                "description": info["description"],
                "params": info["params"],
                "category": cat,
            }
        )
    return {"tools": by_category, "count": len(TOOL_REGISTRY)}


# ---------------------------------------------------------------------------
# Logs & History
# ---------------------------------------------------------------------------

@app.get("/api/logs")
def get_log_entries(limit: int = 100, min_level: str = "DEBUG") -> dict[str, Any]:
    return {"logs": get_logs(limit, min_level)}


@app.delete("/api/logs")
def delete_logs() -> dict[str, bool]:
    clear_logs()
    return {"success": True}


@app.get("/api/history")
def get_chat_history(limit: int = 50) -> dict[str, Any]:
    return {"history": get_history(limit)}


@app.delete("/api/history")
def delete_history() -> dict[str, bool]:
    clear_history()
    return {"success": True}


# ---------------------------------------------------------------------------
# Drawing info
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Drawing management — list open drawings, open/activate a drawing
# ---------------------------------------------------------------------------

@app.get("/api/drawings")
def get_drawings() -> dict[str, Any]:
    """Return all drawings currently open in AutoCAD, marked with which is active.
    Each drawing entry is enriched with file_size (bytes) and last_modified (unix ts).
    """
    import os as _os
    try:
        try:
            import pythoncom
            pythoncom.CoInitialize()
        except Exception:
            pass
        result = _tool_list_drawings()
        if result.get("success"):
            for dwg in result.get("drawings", []):
                path = dwg.get("full_path", "")
                try:
                    if path and _os.path.exists(path):
                        st = _os.stat(path)
                        dwg["file_size"]     = st.st_size
                        dwg["last_modified"] = st.st_mtime
                    else:
                        dwg["file_size"]     = 0
                        dwg["last_modified"] = 0
                except Exception:
                    dwg["file_size"]     = 0
                    dwg["last_modified"] = 0
        return result
    except Exception as exc:
        return {"success": False, "error": str(exc), "drawings": [], "count": 0}


class OpenDrawingRequest(BaseModel):
    name_or_path: str


@app.post("/api/drawings/open")
def open_drawing_endpoint(req: OpenDrawingRequest) -> dict[str, Any]:
    """Open or activate a drawing by sheet number, file name, or partial path."""
    if not req.name_or_path.strip():
        raise HTTPException(status_code=400, detail="name_or_path cannot be empty.")
    try:
        try:
            import pythoncom
            pythoncom.CoInitialize()
        except Exception:
            pass
        result = _tool_open_drawing(req.name_or_path)
        if result.get("success"):
            add_log("INFO", f"Drawing activated: {result.get('drawing', req.name_or_path)}", "drawings")
        else:
            add_log("WARN", f"Could not open drawing: {result.get('error', '?')}", "drawings")
        return result
    except Exception as exc:
        add_log("ERROR", f"open_drawing exception: {exc}", "drawings")
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/drawing/info")
def get_drawing_info() -> dict[str, Any]:
    try:
        try:
            import pythoncom
            pythoncom.CoInitialize()
        except Exception:
            pass
        from src.tools import project as proj
        drawing_result = proj.get_active_drawing()
        project_result = proj.get_project_info() if drawing_result.get("success") else None
        return {"drawing": drawing_result, "project": project_result}
    except Exception as exc:
        return {"drawing": {"success": False, "error": str(exc)}, "project": None}


# ---------------------------------------------------------------------------
# Providers
# ---------------------------------------------------------------------------

@app.get("/api/providers")
def get_providers() -> dict[str, Any]:
    cfg = get_config()
    active = cfg.active_provider
    result = []
    for name in cfg.list_providers():
        p_cfg = cfg.get_provider_config(name)
        result.append(
            {
                "name": name,
                "active": name == active,
                "model": p_cfg.get("model", ""),
                "base_url": p_cfg.get("base_url", ""),
            }
        )
    return {"providers": result, "active": active}


class ProviderSwitchRequest(BaseModel):
    provider: str
    model: Optional[str] = None


@app.post("/api/providers/switch")
def switch_provider(req: ProviderSwitchRequest) -> dict[str, Any]:
    cfg = get_config()
    if req.provider not in cfg.list_providers():
        raise HTTPException(status_code=404, detail=f"Provider '{req.provider}' is not configured.")
    cfg._data["active_provider"] = req.provider
    if req.model:
        cfg._data["providers"][req.provider]["model"] = req.model
    cfg.save()
    add_log("INFO", f"Provider switched → {req.provider} / {req.model or 'default model'}", "system")
    return {"success": True, "active_provider": req.provider, "model": req.model}


# ---------------------------------------------------------------------------
# Chat — natural language → AI → AutoCAD
# ---------------------------------------------------------------------------

class ChatRequest(BaseModel):
    message: str
    provider: Optional[str] = None
    mode: Optional[str] = None   # "auto" | "electrical" | "2d" | "3d"


@app.post("/api/chat")
async def chat(req: ChatRequest) -> dict[str, Any]:
    """Send a natural-language message; AI decides what AutoCAD tool to call.

    *mode* controls which tool subset is shown to the AI:
    - ``"electrical"`` — all 46 tools (Electrical + Drawing + 3D + …)
    - ``"3d"``         — Drawing + Drawing3D + Project (23 tools)
    - ``"2d"``         — Drawing + Project (14 tools)
    - ``"auto"``       — all 46 tools, AI picks the right one (default)
    """
    if not req.message.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty.")
    return await process_message(req.message, req.provider, req.mode)


# ---------------------------------------------------------------------------
# Direct tool execution — no AI, explicit tool + params
# ---------------------------------------------------------------------------

class ToolRequest(BaseModel):
    tool: str
    params: dict[str, Any] = {}


@app.post("/api/execute")
def execute_tool(req: ToolRequest) -> dict[str, Any]:
    """Execute a specific AutoCAD tool directly, bypassing the AI layer."""
    if req.tool not in TOOL_REGISTRY:
        raise HTTPException(status_code=404, detail=f"Tool '{req.tool}' not found.")

    add_log("INFO", f"Direct execute: {req.tool}({req.params})", "tool")

    try:
        try:
            import pythoncom
            pythoncom.CoInitialize()
        except Exception:
            pass

        func = TOOL_REGISTRY[req.tool]["func"]
        result: dict = func(**req.params)

        if result.get("success"):
            add_log("INFO", f"✓ {req.tool} OK", "tool")
        else:
            add_log("WARN", f"✗ {req.tool}: {result.get('error')}", "tool")

        return result
    except Exception as exc:
        add_log("ERROR", f"✗ {req.tool} exception: {exc}", "tool")
        raise HTTPException(status_code=500, detail=str(exc))
