"""Project management tools for AutoCAD Electrical MCP Server.

Provides MCP tools for querying project info, listing drawings, opening/closing
drawings, and running project-wide synchronisation.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from src.autocad.connection import get_connection, AutoCADConnectionError

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _get_conn():
    conn = get_connection(auto_connect=False)
    if not conn.is_connected():
        try:
            conn.connect()
        except AutoCADConnectionError as exc:
            raise AutoCADConnectionError(str(exc)) from exc
    return conn


# ---------------------------------------------------------------------------
# MCP Tool functions
# ---------------------------------------------------------------------------

def get_project_info() -> dict[str, Any]:
    """Return information about the currently active AutoCAD Electrical project.

    AutoCAD Electrical stores project data in a ``.wdp`` file.  This function
    queries the application for all open documents and attempts to locate the
    active project file.

    Returns
    -------
    dict
        Project name, path, and list of drawings.
    """
    try:
        conn = _get_conn()
        app = conn.get_application()
        doc = conn.get_active_document()

        # Attempt to find a .wdp project file in the same directory as the active drawing
        doc_path = Path(doc.FullName)
        project_name = "Unknown"
        project_path = ""
        wdp_files = list(doc_path.parent.glob("*.wdp"))
        if wdp_files:
            project_path = str(wdp_files[0])
            project_name = wdp_files[0].stem

        drawings: list[str] = []
        for i in range(app.Documents.Count):
            try:
                d = app.Documents.Item(i)
                drawings.append(d.Name)
            except Exception:
                pass

        return {
            "success": True,
            "project_name": project_name,
            "project_path": project_path,
            "active_drawing": doc.Name,
            "active_drawing_path": doc.FullName,
            "open_drawings": drawings,
            "open_drawing_count": len(drawings),
        }
    except AutoCADConnectionError as exc:
        return {"success": False, "error": str(exc)}
    except Exception as exc:
        logger.exception("get_project_info failed")
        return {"success": False, "error": str(exc)}


def list_drawings() -> dict[str, Any]:
    """List all drawings currently open in AutoCAD.

    Returns sheet numbers (parsed from drawing names if they follow the
    AutoCAD Electrical naming convention) along with save state.

    Returns
    -------
    dict
        ``{"success": True, "drawings": [...], "count": N}``
    """
    try:
        conn = _get_conn()
        app = conn.get_application()

        drawings: list[dict[str, Any]] = []
        for i in range(app.Documents.Count):
            try:
                d = app.Documents.Item(i)
                # AutoCAD Electrical typically names drawings like "Sheet_01.dwg"
                name = d.Name
                sheet_num = ""
                for part in name.replace("_", " ").split():
                    if part.isdigit():
                        sheet_num = part
                        break
                drawings.append({
                    "name": name,
                    "full_path": d.FullName,
                    "sheet_number": sheet_num,
                    "saved": d.Saved,
                    "active": (d.Name == app.ActiveDocument.Name),
                })
            except Exception:
                pass

        return {
            "success": True,
            "drawings": drawings,
            "count": len(drawings),
        }
    except AutoCADConnectionError as exc:
        return {"success": False, "error": str(exc)}
    except Exception as exc:
        logger.exception("list_drawings failed")
        return {"success": False, "error": str(exc)}


def open_drawing(sheet_number_or_name: str) -> dict[str, Any]:
    """Switch to or open a drawing by sheet number or file name.

    If the drawing is already open it is simply activated.  If not, AutoCAD's
    ``OPEN`` command is used to open it from the project directory.

    Parameters
    ----------
    sheet_number_or_name : str
        Sheet number (e.g. ``"3"``) or drawing filename (e.g.
        ``"Sheet_03.dwg"``).

    Returns
    -------
    dict
        Success/error dict with the activated drawing name.
    """
    try:
        conn = _get_conn()
        app = conn.get_application()
        query = sheet_number_or_name.strip().lower()

        # Try to find the drawing among open documents
        for i in range(app.Documents.Count):
            try:
                d = app.Documents.Item(i)
                name_lower = d.Name.lower()
                if query in name_lower or name_lower.startswith(query):
                    app.ActiveDocument = d
                    return {
                        "success": True,
                        "drawing": d.Name,
                        "action": "activated",
                    }
            except Exception:
                pass

        # Try to open from the project directory
        active_dir = Path(app.ActiveDocument.FullName).parent
        candidates = list(active_dir.glob(f"*{query}*.dwg"))
        if not candidates:
            candidates = list(active_dir.glob(f"*{sheet_number_or_name}*.dwg"))

        if candidates:
            file_path = str(candidates[0])
            conn.send_command(f'(command "OPEN" "{file_path}")\n')
            return {
                "success": True,
                "drawing": candidates[0].name,
                "action": "opened",
                "path": file_path,
            }

        return {
            "success": False,
            "error": (
                f"Drawing '{sheet_number_or_name}' not found among open documents "
                f"or in '{active_dir}'."
            ),
        }
    except AutoCADConnectionError as exc:
        return {"success": False, "error": str(exc)}
    except Exception as exc:
        logger.exception("open_drawing failed")
        return {"success": False, "error": str(exc)}


def close_drawing(save: bool = True) -> dict[str, Any]:
    """Close the currently active drawing.

    Parameters
    ----------
    save : bool
        When ``True`` (default), save the drawing before closing.

    Returns
    -------
    dict
        Success/error dict.
    """
    try:
        conn = _get_conn()
        doc = conn.get_active_document()
        name = doc.Name
        if save:
            doc.Save()
        doc.Close(save)
        return {
            "success": True,
            "drawing": name,
            "saved": save,
        }
    except AutoCADConnectionError as exc:
        return {"success": False, "error": str(exc)}
    except Exception as exc:
        logger.exception("close_drawing failed")
        return {"success": False, "error": str(exc)}


def sync_project() -> dict[str, Any]:
    """Run a project-wide update/synchronisation via AutoCAD Electrical.

    Sends the ``WDSYNCH`` command which re-numbers wires, updates cross-
    references, and refreshes all project data across all drawings.

    Returns
    -------
    dict
        Success/error dict.
    """
    try:
        conn = _get_conn()
        conn.send_command("WDSYNCH\n\n")
        return {
            "success": True,
            "message": "WDSYNCH project synchronisation command sent.",
        }
    except AutoCADConnectionError as exc:
        return {"success": False, "error": str(exc)}
    except Exception as exc:
        logger.exception("sync_project failed")
        return {"success": False, "error": str(exc)}


def get_active_drawing() -> dict[str, Any]:
    """Return information about the currently active drawing.

    Returns
    -------
    dict
        Drawing name, full path, saved state, and entity count.
    """
    try:
        conn = _get_conn()
        doc = conn.get_active_document()
        ms = conn.get_model_space()

        entity_count = 0
        try:
            entity_count = ms.Count
        except Exception:
            pass

        return {
            "success": True,
            "name": doc.Name,
            "full_path": doc.FullName,
            "saved": doc.Saved,
            "entity_count": entity_count,
            "read_only": doc.ReadOnly if hasattr(doc, "ReadOnly") else False,
        }
    except AutoCADConnectionError as exc:
        return {"success": False, "error": str(exc)}
    except Exception as exc:
        logger.exception("get_active_drawing failed")
        return {"success": False, "error": str(exc)}
