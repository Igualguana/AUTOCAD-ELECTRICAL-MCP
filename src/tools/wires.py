"""Wire management tools for AutoCAD Electrical MCP Server.

Provides MCP tools for drawing wires, running wire-numbering, querying wire
numbers, modifying wire attributes, and routing wires between components.
"""

from __future__ import annotations

import logging
from typing import Any

from src.autocad.connection import get_connection, AutoCADConnectionError
from src.autocad.utils import point3d, ensure_layer, get_block_attributes, set_block_attributes

logger = logging.getLogger(__name__)

# Default layer for wires in AutoCAD Electrical projects
_DEFAULT_WIRE_LAYER = "WIRES"


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

def draw_wire(
    x1: float,
    y1: float,
    x2: float,
    y2: float,
    wire_layer: str = _DEFAULT_WIRE_LAYER,
) -> dict[str, Any]:
    """Draw a wire segment from (x1, y1) to (x2, y2) on the WIRES layer.

    In AutoCAD Electrical the wire layer is typically ``WIRES`` (or a
    voltage-specific variant).  The entity is a plain LINE but placed on the
    correct layer so Electrical recognises it during wire-numbering and
    annotation.

    Parameters
    ----------
    x1, y1 : float
        Wire start coordinates.
    x2, y2 : float
        Wire end coordinates.
    wire_layer : str
        Target layer name (default ``"WIRES"``).

    Returns
    -------
    dict
        Success/error dict with entity handle.
    """
    try:
        conn = _get_conn()
        doc = conn.get_active_document()
        ms = conn.get_model_space()

        ensure_layer(doc, wire_layer, color=2)  # color 2 = yellow (standard for wires)

        line = ms.AddLine(point3d(x1, y1), point3d(x2, y2))
        line.Layer = wire_layer
        handle = line.Handle

        logger.debug("draw_wire: (%s,%s)->(%s,%s) layer=%s handle=%s",
                     x1, y1, x2, y2, wire_layer, handle)
        return {
            "success": True,
            "handle": handle,
            "entity": "Wire (Line)",
            "start": [x1, y1],
            "end": [x2, y2],
            "layer": wire_layer,
        }
    except AutoCADConnectionError as exc:
        return {"success": False, "error": str(exc)}
    except Exception as exc:
        logger.exception("draw_wire failed")
        return {"success": False, "error": str(exc)}


def number_wires(
    sheet: str | None = None,
    project: str | None = None,
) -> dict[str, Any]:
    """Run AutoCAD Electrical's wire-numbering command (WDANNO).

    Executes the WDANNO command which re-numbers all wires in the current
    drawing (or project-wide if *project* is specified) according to the
    project's wire-numbering format.

    Parameters
    ----------
    sheet : str or None
        Sheet identifier to limit numbering scope.  When ``None`` the active
        drawing is used.
    project : str or None
        When provided, run project-wide wire numbering via ``WDANNO`` with
        the project scope option.

    Returns
    -------
    dict
        Success/error dict.
    """
    try:
        conn = _get_conn()
        if project:
            # Project-wide numbering: select "Project" scope in WDANNO dialog
            cmd = "WDANNO\nP\n\n"
        else:
            # Drawing-only numbering
            cmd = "WDANNO\nD\n\n"
        conn.send_command(cmd)
        return {
            "success": True,
            "scope": "project" if project else "drawing",
            "sheet": sheet,
        }
    except AutoCADConnectionError as exc:
        return {"success": False, "error": str(exc)}
    except Exception as exc:
        logger.exception("number_wires failed")
        return {"success": False, "error": str(exc)}


def get_wire_numbers(
    sheet: str | None = None,
) -> dict[str, Any]:
    """Return all wire number tags present in the current drawing.

    Searches ModelSpace for block references on the ``WIRENO`` layer (the
    standard AutoCAD Electrical wire-number layer) and collects their tag
    values.

    Parameters
    ----------
    sheet : str or None
        Unused in the current implementation (operates on the active drawing).

    Returns
    -------
    dict
        ``{"success": True, "wire_numbers": [...], "count": N}``
    """
    try:
        conn = _get_conn()
        doc = conn.get_active_document()
        ms = conn.get_model_space()

        wire_numbers: list[dict[str, Any]] = []
        wire_number_layers = {"WIRENO", "WIRENUMBER", "WIRE_NUMBERS"}

        for i in range(ms.Count):
            try:
                obj = ms.Item(i)
                if obj.ObjectName != "AcDbBlockReference":
                    continue
                if obj.Layer.upper() not in wire_number_layers:
                    continue
                attrs = get_block_attributes(obj)
                wn = attrs.get("WIRENO", attrs.get("WIRENUMBER", attrs.get("TAG", "")))
                if wn:
                    pt = obj.InsertionPoint
                    wire_numbers.append({
                        "wire_number": wn,
                        "position": [round(pt[0], 4), round(pt[1], 4)],
                        "handle": obj.Handle,
                        "attributes": attrs,
                    })
            except Exception:
                continue

        return {
            "success": True,
            "wire_numbers": wire_numbers,
            "count": len(wire_numbers),
            "drawing": doc.Name,
        }
    except AutoCADConnectionError as exc:
        return {"success": False, "error": str(exc)}
    except Exception as exc:
        logger.exception("get_wire_numbers failed")
        return {"success": False, "error": str(exc)}


def set_wire_attributes(
    tag: str,
    attributes: dict[str, str],
) -> dict[str, Any]:
    """Modify attributes on a wire entity identified by its wire-number tag.

    Parameters
    ----------
    tag : str
        Wire number / tag to locate (e.g. ``"101"``).
    attributes : dict[str, str]
        Attribute tag → new value mapping.

    Returns
    -------
    dict
        Success/error dict.
    """
    try:
        conn = _get_conn()
        doc = conn.get_active_document()
        ms = conn.get_model_space()

        target = None
        wire_number_layers = {"WIRENO", "WIRENUMBER", "WIRE_NUMBERS"}

        for i in range(ms.Count):
            try:
                obj = ms.Item(i)
                if obj.ObjectName != "AcDbBlockReference":
                    continue
                if obj.Layer.upper() not in wire_number_layers:
                    continue
                attrs = get_block_attributes(obj)
                existing_tag = attrs.get("WIRENO", attrs.get("WIRENUMBER", attrs.get("TAG", "")))
                if existing_tag == tag:
                    target = obj
                    break
            except Exception:
                continue

        if target is None:
            return {
                "success": False,
                "error": f"Wire tag '{tag}' not found in current drawing.",
            }

        updated = set_block_attributes(target, attributes)
        return {
            "success": True,
            "tag": tag,
            "attributes_updated": updated,
            "handle": target.Handle,
        }
    except AutoCADConnectionError as exc:
        return {"success": False, "error": str(exc)}
    except Exception as exc:
        logger.exception("set_wire_attributes failed")
        return {"success": False, "error": str(exc)}


def create_wire_from_to(
    from_component: str,
    to_component: str,
) -> dict[str, Any]:
    """Route a wire between two components identified by TAG1.

    Locates both components in ModelSpace, identifies their nearest connection
    terminals (insertion points), and draws a wire line between them.

    Parameters
    ----------
    from_component : str
        TAG1 of the source component.
    to_component : str
        TAG1 of the destination component.

    Returns
    -------
    dict
        Success/error dict with wire handle and endpoint coordinates.
    """
    try:
        conn = _get_conn()
        doc = conn.get_active_document()
        ms = conn.get_model_space()

        def _find_component(tag: str):
            for i in range(ms.Count):
                try:
                    obj = ms.Item(i)
                    if obj.ObjectName != "AcDbBlockReference":
                        continue
                    attrs = get_block_attributes(obj)
                    if attrs.get("TAG1", "").upper() == tag.upper():
                        return obj
                except Exception:
                    continue
            return None

        from_obj = _find_component(from_component)
        to_obj = _find_component(to_component)

        if from_obj is None:
            return {
                "success": False,
                "error": f"Component '{from_component}' not found.",
            }
        if to_obj is None:
            return {
                "success": False,
                "error": f"Component '{to_component}' not found.",
            }

        # Use insertion points as connection points
        from_pt = from_obj.InsertionPoint
        to_pt = to_obj.InsertionPoint

        # Draw the wire
        ensure_layer(doc, _DEFAULT_WIRE_LAYER, color=2)
        line = ms.AddLine(
            point3d(from_pt[0], from_pt[1]),
            point3d(to_pt[0], to_pt[1]),
        )
        line.Layer = _DEFAULT_WIRE_LAYER
        handle = line.Handle

        return {
            "success": True,
            "wire_handle": handle,
            "from_component": from_component,
            "from_point": [round(from_pt[0], 4), round(from_pt[1], 4)],
            "to_component": to_component,
            "to_point": [round(to_pt[0], 4), round(to_pt[1], 4)],
            "layer": _DEFAULT_WIRE_LAYER,
        }
    except AutoCADConnectionError as exc:
        return {"success": False, "error": str(exc)}
    except Exception as exc:
        logger.exception("create_wire_from_to failed")
        return {"success": False, "error": str(exc)}
