"""Basic drawing tools for AutoCAD Electrical MCP Server.

Provides MCP-registered tools for inserting fundamental geometric entities:
lines, circles, arcs, text, and rectangles.  All functions communicate with
AutoCAD through the shared :class:`~src.autocad.connection.AutoCADConnection`
singleton.
"""

from __future__ import annotations

import logging
import math
from typing import Any

from src.autocad.connection import get_connection, AutoCADConnectionError
from src.autocad.utils import point3d, ensure_layer

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _get_conn():
    """Return a connected AutoCADConnection or raise a friendly error."""
    conn = get_connection(auto_connect=False)
    if not conn.is_connected():
        try:
            conn.connect()
        except AutoCADConnectionError as exc:
            raise AutoCADConnectionError(str(exc)) from exc
    return conn


def _with_layer(doc, layer: str):
    """Set the active layer on the document; return the previous layer name."""
    try:
        ensure_layer(doc, layer)
        prev = doc.ActiveLayer.Name
        doc.ActiveLayer = doc.Layers.Item(layer)
        return prev
    except Exception as exc:
        logger.warning("Could not set layer '%s': %s", layer, exc)
        return None


def _restore_layer(doc, prev_layer: str | None):
    if prev_layer:
        try:
            doc.ActiveLayer = doc.Layers.Item(prev_layer)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# MCP Tool functions
# ---------------------------------------------------------------------------

def draw_line(
    x1: float,
    y1: float,
    x2: float,
    y2: float,
    layer: str = "0",
) -> dict[str, Any]:
    """Draw a line from (x1, y1) to (x2, y2) on *layer*.

    Parameters
    ----------
    x1, y1 : float
        Start point coordinates.
    x2, y2 : float
        End point coordinates.
    layer : str
        Target layer name (created if it does not exist).

    Returns
    -------
    dict
        ``{"success": True, "handle": "<entity handle>"}`` or an error dict.
    """
    try:
        conn = _get_conn()
        doc = conn.get_active_document()
        ms = conn.get_model_space()
        prev = _with_layer(doc, layer)
        try:
            line = ms.AddLine(point3d(x1, y1), point3d(x2, y2))
            line.Layer = layer
            handle = line.Handle
        finally:
            _restore_layer(doc, prev)
        logger.debug("draw_line: (%s,%s)->(%s,%s) handle=%s", x1, y1, x2, y2, handle)
        return {"success": True, "handle": handle, "entity": "Line",
                "start": [x1, y1], "end": [x2, y2], "layer": layer}
    except AutoCADConnectionError as exc:
        return {"success": False, "error": str(exc)}
    except Exception as exc:
        logger.exception("draw_line failed")
        return {"success": False, "error": str(exc)}


def draw_circle(
    cx: float,
    cy: float,
    radius: float,
    layer: str = "0",
) -> dict[str, Any]:
    """Draw a circle at centre (cx, cy) with the given *radius*.

    Parameters
    ----------
    cx, cy : float
        Centre coordinates.
    radius : float
        Circle radius (in drawing units).
    layer : str
        Target layer name.

    Returns
    -------
    dict
        Success/error dict with entity handle.
    """
    try:
        conn = _get_conn()
        doc = conn.get_active_document()
        ms = conn.get_model_space()
        prev = _with_layer(doc, layer)
        try:
            circle = ms.AddCircle(point3d(cx, cy), float(radius))
            circle.Layer = layer
            handle = circle.Handle
        finally:
            _restore_layer(doc, prev)
        return {"success": True, "handle": handle, "entity": "Circle",
                "center": [cx, cy], "radius": radius, "layer": layer}
    except AutoCADConnectionError as exc:
        return {"success": False, "error": str(exc)}
    except Exception as exc:
        logger.exception("draw_circle failed")
        return {"success": False, "error": str(exc)}


def draw_arc(
    cx: float,
    cy: float,
    radius: float,
    start_angle: float,
    end_angle: float,
    layer: str = "0",
) -> dict[str, Any]:
    """Draw an arc centred at (cx, cy).

    Parameters
    ----------
    cx, cy : float
        Centre coordinates.
    radius : float
        Arc radius.
    start_angle : float
        Start angle in **degrees** (0 = East, counter-clockwise positive).
    end_angle : float
        End angle in degrees.
    layer : str
        Target layer name.

    Returns
    -------
    dict
        Success/error dict.
    """
    try:
        conn = _get_conn()
        doc = conn.get_active_document()
        ms = conn.get_model_space()
        start_rad = math.radians(start_angle)
        end_rad = math.radians(end_angle)
        prev = _with_layer(doc, layer)
        try:
            arc = ms.AddArc(
                point3d(cx, cy),
                float(radius),
                start_rad,
                end_rad,
            )
            arc.Layer = layer
            handle = arc.Handle
        finally:
            _restore_layer(doc, prev)
        return {
            "success": True,
            "handle": handle,
            "entity": "Arc",
            "center": [cx, cy],
            "radius": radius,
            "start_angle": start_angle,
            "end_angle": end_angle,
            "layer": layer,
        }
    except AutoCADConnectionError as exc:
        return {"success": False, "error": str(exc)}
    except Exception as exc:
        logger.exception("draw_arc failed")
        return {"success": False, "error": str(exc)}


def draw_text(
    x: float,
    y: float,
    text: str,
    height: float = 2.5,
    layer: str = "0",
) -> dict[str, Any]:
    """Place a single-line text entity at (x, y).

    Parameters
    ----------
    x, y : float
        Insertion point.
    text : str
        Text string content.
    height : float
        Text height in drawing units (default 2.5).
    layer : str
        Target layer name.

    Returns
    -------
    dict
        Success/error dict.
    """
    try:
        conn = _get_conn()
        doc = conn.get_active_document()
        ms = conn.get_model_space()
        prev = _with_layer(doc, layer)
        try:
            txt = ms.AddText(str(text), point3d(x, y), float(height))
            txt.Layer = layer
            handle = txt.Handle
        finally:
            _restore_layer(doc, prev)
        return {
            "success": True,
            "handle": handle,
            "entity": "Text",
            "insertion_point": [x, y],
            "text": text,
            "height": height,
            "layer": layer,
        }
    except AutoCADConnectionError as exc:
        return {"success": False, "error": str(exc)}
    except Exception as exc:
        logger.exception("draw_text failed")
        return {"success": False, "error": str(exc)}


def draw_rectangle(
    x1: float,
    y1: float,
    x2: float,
    y2: float,
    layer: str = "0",
) -> dict[str, Any]:
    """Draw a closed rectangular polyline from corner (x1, y1) to (x2, y2).

    Parameters
    ----------
    x1, y1 : float
        First corner.
    x2, y2 : float
        Opposite corner.
    layer : str
        Target layer name.

    Returns
    -------
    dict
        Success/error dict with handles of the created polyline.
    """
    try:
        conn = _get_conn()
        doc = conn.get_active_document()
        ms = conn.get_model_space()
        prev = _with_layer(doc, layer)
        try:
            import win32com.client as _w32
            import pythoncom as _pc
            # LWPolyline vertices: flat list of (x, y) pairs as SAFEARRAY
            pts = _w32.VARIANT(
                _pc.VT_ARRAY | _pc.VT_R8,
                [float(x1), float(y1), float(x2), float(y1),
                 float(x2), float(y2), float(x1), float(y2)],
            )
            pline = ms.AddLightWeightPolyline(pts)
            pline.Closed = True
            pline.Layer = layer
            handle = pline.Handle
        finally:
            _restore_layer(doc, prev)
        return {
            "success": True,
            "handle": handle,
            "entity": "LWPolyline",
            "corners": [[x1, y1], [x2, y2]],
            "layer": layer,
        }
    except AutoCADConnectionError as exc:
        return {"success": False, "error": str(exc)}
    except Exception as exc:
        logger.exception("draw_rectangle failed")
        return {"success": False, "error": str(exc)}


def draw_polyline(
    points: list,
    closed: bool = False,
    layer: str = "0",
) -> dict[str, Any]:
    """Draw a 2-D lightweight polyline through a list of (x, y) points.

    Parameters
    ----------
    points : list of [x, y]
        Sequence of 2-D vertices. Minimum 2 points.
    closed : bool
        If True, the last vertex connects back to the first.
    layer : str
        Target layer name (created if absent).

    Returns
    -------
    dict
        ``{"success": True, "handle": "...", "entity": "LWPolyline", ...}``
    """
    if len(points) < 2:
        return {"success": False, "error": "At least 2 points required."}
    try:
        import win32com.client as _w32
        import pythoncom as _pc
        conn = _get_conn()
        doc = conn.get_active_document()
        ms = conn.get_model_space()
        prev = _with_layer(doc, layer)
        try:
            flat = []
            for p in points:
                flat.extend([float(p[0]), float(p[1])])
            pts_var = _w32.VARIANT(_pc.VT_ARRAY | _pc.VT_R8, flat)
            pline = ms.AddLightWeightPolyline(pts_var)
            pline.Closed = bool(closed)
            pline.Layer = layer
            handle = pline.Handle
        finally:
            _restore_layer(doc, prev)
        return {
            "success": True, "handle": handle, "entity": "LWPolyline",
            "points": points, "closed": closed, "layer": layer,
        }
    except AutoCADConnectionError as exc:
        return {"success": False, "error": str(exc)}
    except Exception as exc:
        logger.exception("draw_polyline failed")
        return {"success": False, "error": str(exc)}


def zoom_extents() -> dict[str, Any]:
    """Zoom the active viewport to fit all entities in ModelSpace.

    Equivalent to typing ``ZOOM E`` on the AutoCAD command line.

    Returns
    -------
    dict  ``{"success": True}``
    """
    try:
        from src.autocad.connection import get_connection
        conn = get_connection(auto_connect=False)
        if not conn.is_connected():
            conn.connect()
        conn.send_command("ZOOM E ")
        return {"success": True, "command": "ZOOM E"}
    except AutoCADConnectionError as exc:
        return {"success": False, "error": str(exc)}
    except Exception as exc:
        logger.exception("zoom_extents failed")
        return {"success": False, "error": str(exc)}


def set_layer(
    layer_name: str,
    color: int = 7,
    linetype: str = "Continuous",
    make_active: bool = True,
) -> dict[str, Any]:
    """Create or configure a layer and optionally make it active.

    Parameters
    ----------
    layer_name : str
        Layer name (max 255 chars, no special characters).
    color : int
        AutoCAD Color Index (ACI): 1=Red, 2=Yellow, 3=Green, 4=Cyan,
        5=Blue, 6=Magenta, 7=White/Black.
    linetype : str
        Linetype name (e.g. ``"Continuous"``, ``"DASHED"``).
    make_active : bool
        If True, sets this as the active layer.

    Returns
    -------
    dict
    """
    try:
        from src.autocad.utils import ensure_layer
        conn = _get_conn()
        doc = conn.get_active_document()
        layer = ensure_layer(doc, layer_name, color=color, linetype=linetype)
        if make_active:
            doc.ActiveLayer = doc.Layers.Item(layer_name)
        return {
            "success": True, "layer": layer_name,
            "color": color, "linetype": linetype, "active": make_active,
        }
    except AutoCADConnectionError as exc:
        return {"success": False, "error": str(exc)}
    except Exception as exc:
        logger.exception("set_layer failed")
        return {"success": False, "error": str(exc)}
