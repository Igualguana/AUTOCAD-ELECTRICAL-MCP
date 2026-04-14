"""Report generation tools for AutoCAD Electrical MCP Server.

Provides MCP tools for generating Bills of Materials, wire lists, terminal
plans, PLC I/O lists, and project summaries.

Reports are generated via AutoCAD Electrical's built-in WDREPORT command or
by programmatically scanning the drawing and exporting data to CSV/text files.
"""

from __future__ import annotations

import csv
import datetime
import logging
import os
from pathlib import Path
from typing import Any

from src.autocad.connection import get_connection, AutoCADConnectionError
from src.autocad.utils import get_block_attributes

logger = logging.getLogger(__name__)

_DEFAULT_REPORT_DIR = Path.home() / "Documents" / "AutoCAD Electrical Reports"


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


def _ensure_report_dir(output_path: str | None) -> Path:
    if output_path:
        p = Path(output_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        return p
    _DEFAULT_REPORT_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    return _DEFAULT_REPORT_DIR / timestamp


def _collect_components(ms: Any) -> list[dict[str, str]]:
    """Scan ModelSpace and return all Electrical component attribute dicts."""
    components: list[dict[str, str]] = []
    electrical_tags = {"TAG1", "TAG2", "INST", "LOC", "MFG", "CAT", "DESC1"}
    for i in range(ms.Count):
        try:
            obj = ms.Item(i)
            if obj.ObjectName != "AcDbBlockReference":
                continue
            attrs = get_block_attributes(obj)
            if attrs and bool({k.upper() for k in attrs} & electrical_tags):
                attrs["_BLOCK"] = obj.Name
                attrs["_HANDLE"] = obj.Handle
                components.append(attrs)
        except Exception:
            continue
    return components


def _write_csv(rows: list[dict[str, Any]], fieldnames: list[str], filepath: Path) -> None:
    with open(filepath, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


# ---------------------------------------------------------------------------
# MCP Tool functions
# ---------------------------------------------------------------------------

def generate_bom(
    output_format: str = "csv",
    output_path: str | None = None,
) -> dict[str, Any]:
    """Generate a Bill of Materials for the current drawing.

    Scans the active drawing for AutoCAD Electrical components and groups them
    by Manufacturer / Catalog number, producing a quantity-sorted BOM.

    For a full project BOM via the WDREPORT command use
    ``output_format="wdreport"``.

    Parameters
    ----------
    output_format : str
        ``"csv"`` (default) for a plain CSV file, or ``"wdreport"`` to
        invoke AutoCAD Electrical's native WDREPORT command.
    output_path : str or None
        Output file path.  When ``None`` a timestamped file is created in
        ``~/Documents/AutoCAD Electrical Reports/``.

    Returns
    -------
    dict
        Success/error dict with path to the generated file and item count.
    """
    try:
        conn = _get_conn()
        doc = conn.get_active_document()
        ms = conn.get_model_space()

        if output_format.lower() == "wdreport":
            # Delegate to AutoCAD Electrical's native report engine
            cmd = f"WDREPORT\nBOM\n\n"
            conn.send_command(cmd)
            return {
                "success": True,
                "report_type": "BOM",
                "method": "WDREPORT",
                "note": "WDREPORT command sent to AutoCAD Electrical.",
            }

        # Programmatic CSV BOM
        components = _collect_components(ms)

        # Group by MFG+CAT
        bom: dict[str, dict[str, Any]] = {}
        for comp in components:
            mfg = comp.get("MFG", "").strip()
            cat = comp.get("CAT", "").strip()
            desc = comp.get("DESC1", comp.get("DESC2", "")).strip()
            tag1 = comp.get("TAG1", "").strip()
            key = f"{mfg}|{cat}"
            if key not in bom:
                bom[key] = {
                    "MFG": mfg,
                    "CAT": cat,
                    "DESC1": desc,
                    "QTY": 0,
                    "TAGS": [],
                }
            bom[key]["QTY"] += 1
            if tag1:
                bom[key]["TAGS"].append(tag1)

        rows = sorted(bom.values(), key=lambda r: (-r["QTY"], r.get("MFG", "")))
        for row in rows:
            row["TAGS"] = ", ".join(sorted(row["TAGS"]))

        base = _ensure_report_dir(output_path)
        if output_path:
            filepath = base
        else:
            filepath = base.parent / f"{base.name}_BOM.csv"

        _write_csv(rows, ["QTY", "MFG", "CAT", "DESC1", "TAGS"], filepath)

        return {
            "success": True,
            "report_type": "BOM",
            "method": "csv",
            "file": str(filepath),
            "item_count": len(rows),
            "drawing": doc.Name,
        }
    except AutoCADConnectionError as exc:
        return {"success": False, "error": str(exc)}
    except Exception as exc:
        logger.exception("generate_bom failed")
        return {"success": False, "error": str(exc)}


def generate_wire_list(
    output_path: str | None = None,
) -> dict[str, Any]:
    """Generate a wire connection list (from-to report) for the active drawing.

    Parameters
    ----------
    output_path : str or None
        Output CSV file path.

    Returns
    -------
    dict
        Success/error dict with file path and wire count.
    """
    try:
        conn = _get_conn()
        doc = conn.get_active_document()
        ms = conn.get_model_space()

        # Collect all wire lines (entities on WIRES layer)
        wire_data: list[dict[str, str]] = []
        for i in range(ms.Count):
            try:
                obj = ms.Item(i)
                if obj.ObjectName != "AcDbLine":
                    continue
                if "WIRE" not in obj.Layer.upper():
                    continue
                sp = obj.StartPoint
                ep = obj.EndPoint
                wire_data.append({
                    "HANDLE": obj.Handle,
                    "LAYER": obj.Layer,
                    "START_X": str(round(sp[0], 4)),
                    "START_Y": str(round(sp[1], 4)),
                    "END_X": str(round(ep[0], 4)),
                    "END_Y": str(round(ep[1], 4)),
                    "LENGTH": str(round(
                        ((ep[0]-sp[0])**2 + (ep[1]-sp[1])**2) ** 0.5, 4
                    )),
                })
            except Exception:
                continue

        base = _ensure_report_dir(output_path)
        filepath = output_path or str(base.parent / f"{base.name}_WireList.csv")
        _write_csv(
            wire_data,
            ["HANDLE", "LAYER", "START_X", "START_Y", "END_X", "END_Y", "LENGTH"],
            Path(filepath),
        )

        return {
            "success": True,
            "report_type": "Wire List",
            "file": str(filepath),
            "wire_count": len(wire_data),
            "drawing": doc.Name,
        }
    except AutoCADConnectionError as exc:
        return {"success": False, "error": str(exc)}
    except Exception as exc:
        logger.exception("generate_wire_list failed")
        return {"success": False, "error": str(exc)}


def generate_terminal_plan(
    output_path: str | None = None,
) -> dict[str, Any]:
    """Generate a terminal strip report for the active drawing.

    Collects all components whose block name or attributes indicate a terminal
    (``WD_TERM``, ``TERM``, ``TB``, etc.) and writes a CSV.

    Parameters
    ----------
    output_path : str or None
        Output CSV file path.

    Returns
    -------
    dict
        Success/error dict with file path and terminal count.
    """
    try:
        conn = _get_conn()
        doc = conn.get_active_document()
        ms = conn.get_model_space()

        terminal_indicators = {"WD_TERM", "TERM", "_TB", "TERMINAL"}

        terminals: list[dict[str, str]] = []
        for i in range(ms.Count):
            try:
                obj = ms.Item(i)
                if obj.ObjectName != "AcDbBlockReference":
                    continue
                bname = obj.Name.upper()
                is_terminal = any(ind in bname for ind in terminal_indicators)
                if not is_terminal:
                    attrs = get_block_attributes(obj)
                    is_terminal = bool({"TERM", "TB", "TERMINAL"} & {
                        v.upper() for v in attrs.values()
                    })
                if is_terminal:
                    attrs = get_block_attributes(obj)
                    pt = obj.InsertionPoint
                    terminals.append({
                        "HANDLE": obj.Handle,
                        "BLOCK": obj.Name,
                        "TAG1": attrs.get("TAG1", ""),
                        "TERM": attrs.get("TERM", attrs.get("TERMINAL", "")),
                        "WIRE": attrs.get("WIRENO", attrs.get("WIRENUMBER", "")),
                        "DESC1": attrs.get("DESC1", ""),
                        "X": str(round(pt[0], 4)),
                        "Y": str(round(pt[1], 4)),
                    })
            except Exception:
                continue

        base = _ensure_report_dir(output_path)
        filepath = output_path or str(base.parent / f"{base.name}_TerminalPlan.csv")
        _write_csv(
            terminals,
            ["HANDLE", "BLOCK", "TAG1", "TERM", "WIRE", "DESC1", "X", "Y"],
            Path(filepath),
        )

        return {
            "success": True,
            "report_type": "Terminal Plan",
            "file": str(filepath),
            "terminal_count": len(terminals),
            "drawing": doc.Name,
        }
    except AutoCADConnectionError as exc:
        return {"success": False, "error": str(exc)}
    except Exception as exc:
        logger.exception("generate_terminal_plan failed")
        return {"success": False, "error": str(exc)}


def generate_plc_io_list(
    output_path: str | None = None,
) -> dict[str, Any]:
    """Generate a PLC I/O list for the active drawing.

    Parameters
    ----------
    output_path : str or None
        Output CSV file path.

    Returns
    -------
    dict
        Success/error dict with file path and I/O point count.
    """
    try:
        conn = _get_conn()
        doc = conn.get_active_document()
        ms = conn.get_model_space()

        plc_indicators = {"WD_PLC_IN", "WD_PLC_OUT", "WD_PLC_AI", "WD_PLC_AO", "PLC_"}

        io_points: list[dict[str, str]] = []
        for i in range(ms.Count):
            try:
                obj = ms.Item(i)
                if obj.ObjectName != "AcDbBlockReference":
                    continue
                bname = obj.Name.upper()
                if not any(ind in bname for ind in plc_indicators):
                    continue
                attrs = get_block_attributes(obj)
                io_points.append({
                    "HANDLE": obj.Handle,
                    "BLOCK": obj.Name,
                    "TAG1": attrs.get("TAG1", ""),
                    "RACK": attrs.get("RACK", ""),
                    "SLOT": attrs.get("SLOT", ""),
                    "ADDRESS": attrs.get("ADDRESS", attrs.get("ADDR", "")),
                    "DESC1": attrs.get("DESC1", ""),
                    "DESC2": attrs.get("DESC2", ""),
                    "WIRENO": attrs.get("WIRENO", ""),
                })
            except Exception:
                continue

        base = _ensure_report_dir(output_path)
        filepath = output_path or str(base.parent / f"{base.name}_PLC_IO_List.csv")
        _write_csv(
            io_points,
            ["HANDLE", "BLOCK", "TAG1", "RACK", "SLOT", "ADDRESS", "DESC1", "DESC2", "WIRENO"],
            Path(filepath),
        )

        return {
            "success": True,
            "report_type": "PLC I/O List",
            "file": str(filepath),
            "io_count": len(io_points),
            "drawing": doc.Name,
        }
    except AutoCADConnectionError as exc:
        return {"success": False, "error": str(exc)}
    except Exception as exc:
        logger.exception("generate_plc_io_list failed")
        return {"success": False, "error": str(exc)}


def get_project_summary() -> dict[str, Any]:
    """Return a summary of the active AutoCAD project.

    Counts drawings, total components, wires, and terminals currently loaded.

    Returns
    -------
    dict
        Summary statistics dict.
    """
    try:
        conn = _get_conn()
        app = conn.get_application()
        docs = app.Documents

        summary: dict[str, Any] = {
            "open_drawings": [],
            "total_open": docs.Count,
        }

        total_components = 0
        total_wires = 0

        for d in range(docs.Count):
            try:
                doc = docs.Item(d)
                ms = doc.ModelSpace
                components = 0
                wires = 0
                for i in range(ms.Count):
                    try:
                        obj = ms.Item(i)
                        oname = obj.ObjectName
                        if oname == "AcDbBlockReference":
                            components += 1
                        elif oname == "AcDbLine" and "WIRE" in obj.Layer.upper():
                            wires += 1
                    except Exception:
                        pass
                total_components += components
                total_wires += wires
                summary["open_drawings"].append({
                    "name": doc.Name,
                    "path": doc.FullName,
                    "saved": doc.Saved,
                    "components": components,
                    "wires": wires,
                })
            except Exception:
                pass

        summary["total_components"] = total_components
        summary["total_wires"] = total_wires
        summary["success"] = True
        return summary
    except AutoCADConnectionError as exc:
        return {"success": False, "error": str(exc)}
    except Exception as exc:
        logger.exception("get_project_summary failed")
        return {"success": False, "error": str(exc)}
