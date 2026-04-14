"""3D drawing tools for AutoCAD MCP Server.

Provides MCP-registered tools for 3D geometric entities:
  - draw_line_3d       — line between two 3-D points
  - draw_polyline_3d   — open or closed 3-D polyline
  - draw_3d_face       — planar 3- or 4-vertex face
  - draw_box           — 3-D solid box (ACIS — requires full AutoCAD license)
  - draw_sphere        — 3-D solid sphere (ACIS)
  - draw_cylinder      — 3-D solid cylinder (ACIS)
  - draw_cone          — 3-D solid cone (ACIS)
  - set_ucs            — change User Coordinate System origin and orientation
  - zoom_3d_view       — switch to isometric / perspective view preset

All geometry is added to ModelSpace of the active document.
ACIS-based primitives (box, sphere, cylinder, cone) require a full AutoCAD
license with the 3-D Modeling workset.  If the COM call fails (e.g. the
``add*`` method is not present or the license is insufficient), the tool
returns ``{"success": False, "error": "...", "note": "ACIS_NOT_AVAILABLE"}``.

COM coordinate note:
  All coordinate arrays must be passed as
  ``win32com.client.VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_R8, [...])``.
  Plain Python tuples cause E_INVALIDARG on AutoCAD 2025.
"""

from __future__ import annotations

import logging
import math
from typing import Any, List

from src.autocad.connection import get_connection, AutoCADConnectionError
from src.autocad.utils import point3d, ensure_layer

logger = logging.getLogger(__name__)

try:
    import win32com.client as _w32
    import pythoncom as _pc
    _WIN32 = True
except ImportError:
    _WIN32 = False


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _conn():
    c = get_connection(auto_connect=False)
    if not c.is_connected():
        c.connect()
    return c


def _ms():
    """Return (conn, doc, model_space) or raise."""
    c = _conn()
    doc = c.get_active_document()
    ms = c.get_model_space()
    return c, doc, ms


def _var(values: list) -> Any:
    """Wrap a list of floats as a COM SAFEARRAY VARIANT."""
    if _WIN32:
        return _w32.VARIANT(_pc.VT_ARRAY | _pc.VT_R8, [float(v) for v in values])
    return tuple(float(v) for v in values)


def _with_layer(doc, layer: str):
    try:
        ensure_layer(doc, layer)
        prev = doc.ActiveLayer.Name
        doc.ActiveLayer = doc.Layers.Item(layer)
        return prev
    except Exception:
        return None


def _restore_layer(doc, prev):
    if prev:
        try:
            doc.ActiveLayer = doc.Layers.Item(prev)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Tool: draw_line_3d
# ---------------------------------------------------------------------------

def draw_line_3d(
    x1: float, y1: float, z1: float,
    x2: float, y2: float, z2: float,
    layer: str = "0",
) -> dict[str, Any]:
    """Draw a 3-D line between two points with full Z coordinates.

    Parameters
    ----------
    x1, y1, z1 : float   Start point (3-D).
    x2, y2, z2 : float   End point (3-D).
    layer : str          Target layer (created if absent).

    Returns
    -------
    dict  ``{"success": True, "handle": "...", "entity": "Line3D", ...}``
    """
    try:
        _, doc, ms = _ms()
        prev = _with_layer(doc, layer)
        try:
            line = ms.AddLine(point3d(x1, y1, z1), point3d(x2, y2, z2))
            line.Layer = layer
            handle = line.Handle
        finally:
            _restore_layer(doc, prev)
        return {
            "success": True, "handle": handle, "entity": "Line3D",
            "start": [x1, y1, z1], "end": [x2, y2, z2], "layer": layer,
        }
    except AutoCADConnectionError as exc:
        return {"success": False, "error": str(exc)}
    except Exception as exc:
        logger.exception("draw_line_3d failed")
        return {"success": False, "error": str(exc)}


# ---------------------------------------------------------------------------
# Tool: draw_polyline_3d
# ---------------------------------------------------------------------------

def draw_polyline_3d(
    points: List[List[float]],
    closed: bool = False,
    layer: str = "0",
) -> dict[str, Any]:
    """Draw a 3-D polyline through a sequence of XYZ points.

    Parameters
    ----------
    points : list of [x, y, z]
        At least 2 points required.
    closed : bool
        If True, close the polyline back to the first point.
    layer : str
        Target layer.

    Returns
    -------
    dict  ``{"success": True, "handle": "...", "entity": "3DPolyline", ...}``
    """
    if len(points) < 2:
        return {"success": False, "error": "At least 2 points required for a polyline."}
    try:
        _, doc, ms = _ms()
        # Flatten to [x0,y0,z0, x1,y1,z1, ...]
        flat = []
        for p in points:
            flat.extend([float(p[0]), float(p[1]), float(p[2]) if len(p) > 2 else 0.0])
        pts_var = _var(flat)
        prev = _with_layer(doc, layer)
        try:
            pline = ms.Add3DPoly(pts_var)
            pline.Closed = closed
            pline.Layer = layer
            handle = pline.Handle
        finally:
            _restore_layer(doc, prev)
        return {
            "success": True, "handle": handle, "entity": "3DPolyline",
            "points": points, "closed": closed, "layer": layer,
        }
    except AutoCADConnectionError as exc:
        return {"success": False, "error": str(exc)}
    except Exception as exc:
        logger.exception("draw_polyline_3d failed")
        return {"success": False, "error": str(exc)}


# ---------------------------------------------------------------------------
# Tool: draw_3d_face
# ---------------------------------------------------------------------------

def draw_3d_face(
    x1: float, y1: float, z1: float,
    x2: float, y2: float, z2: float,
    x3: float, y3: float, z3: float,
    x4: float = None, y4: float = None, z4: float = None,
    layer: str = "0",
) -> dict[str, Any]:
    """Draw a 3DFACE entity (triangle or quad in 3-D space).

    AutoCAD's 3DFACE requires 4 corner points; for a triangle the 3rd and 4th
    points are the same.

    Parameters
    ----------
    x1-z3 : float   First three corners.
    x4-z4 : float   Optional fourth corner (defaults to third corner → triangle).
    layer : str

    Returns
    -------
    dict
    """
    if x4 is None:
        x4, y4, z4 = x3, y3, z3   # triangle
    try:
        _, doc, ms = _ms()
        prev = _with_layer(doc, layer)
        try:
            face = ms.Add3DFace(
                point3d(x1, y1, z1),
                point3d(x2, y2, z2),
                point3d(x3, y3, z3),
                point3d(x4, y4, z4),
            )
            face.Layer = layer
            handle = face.Handle
        finally:
            _restore_layer(doc, prev)
        corners = [[x1,y1,z1],[x2,y2,z2],[x3,y3,z3],[x4,y4,z4]]
        return {
            "success": True, "handle": handle, "entity": "3DFace",
            "corners": corners, "layer": layer,
        }
    except AutoCADConnectionError as exc:
        return {"success": False, "error": str(exc)}
    except Exception as exc:
        logger.exception("draw_3d_face failed")
        return {"success": False, "error": str(exc)}


# ---------------------------------------------------------------------------
# Tool: draw_box  (ACIS 3D solid)
# ---------------------------------------------------------------------------

def draw_box(
    origin_x: float, origin_y: float, origin_z: float,
    length: float, width: float, height: float,
    layer: str = "0",
) -> dict[str, Any]:
    """Draw a 3-D solid box (ACIS).

    Requires full AutoCAD with 3D Modeling workset.
    Returns ``{"success": False, "note": "ACIS_NOT_AVAILABLE", ...}`` if ACIS
    is not licensed.

    Parameters
    ----------
    origin_x, origin_y, origin_z : float  Corner of the box.
    length, width, height : float          Dimensions.
    layer : str
    """
    try:
        _, doc, ms = _ms()
        prev = _with_layer(doc, layer)
        try:
            box = ms.AddBox(
                point3d(origin_x, origin_y, origin_z),
                float(length), float(width), float(height),
            )
            box.Layer = layer
            handle = box.Handle
        finally:
            _restore_layer(doc, prev)
        return {
            "success": True, "handle": handle, "entity": "Box3D",
            "origin": [origin_x, origin_y, origin_z],
            "dimensions": {"length": length, "width": width, "height": height},
            "layer": layer,
        }
    except AutoCADConnectionError as exc:
        return {"success": False, "error": str(exc)}
    except Exception as exc:
        err = str(exc)
        logger.warning("draw_box failed (ACIS may not be available): %s", err)
        return {"success": False, "error": err, "note": "ACIS_NOT_AVAILABLE"}


# ---------------------------------------------------------------------------
# Tool: draw_sphere (ACIS 3D solid)
# ---------------------------------------------------------------------------

def draw_sphere(
    cx: float, cy: float, cz: float,
    radius: float,
    layer: str = "0",
) -> dict[str, Any]:
    """Draw a 3-D solid sphere (ACIS).

    Parameters
    ----------
    cx, cy, cz : float  Centre of the sphere.
    radius : float      Radius.
    layer : str
    """
    try:
        _, doc, ms = _ms()
        prev = _with_layer(doc, layer)
        try:
            sphere = ms.AddSphere(point3d(cx, cy, cz), float(radius))
            sphere.Layer = layer
            handle = sphere.Handle
        finally:
            _restore_layer(doc, prev)
        return {
            "success": True, "handle": handle, "entity": "Sphere3D",
            "center": [cx, cy, cz], "radius": radius, "layer": layer,
        }
    except AutoCADConnectionError as exc:
        return {"success": False, "error": str(exc)}
    except Exception as exc:
        err = str(exc)
        logger.warning("draw_sphere failed (ACIS): %s", err)
        return {"success": False, "error": err, "note": "ACIS_NOT_AVAILABLE"}


# ---------------------------------------------------------------------------
# Tool: draw_cylinder (ACIS 3D solid)
# ---------------------------------------------------------------------------

def draw_cylinder(
    cx: float, cy: float, cz: float,
    radius: float, height: float,
    layer: str = "0",
) -> dict[str, Any]:
    """Draw a 3-D solid cylinder (ACIS).

    Parameters
    ----------
    cx, cy, cz : float  Centre of the cylinder base.
    radius : float      Base radius.
    height : float      Height (positive = up along Z).
    layer : str
    """
    try:
        _, doc, ms = _ms()
        prev = _with_layer(doc, layer)
        try:
            cyl = ms.AddCylinder(
                point3d(cx, cy, cz), float(radius), float(height)
            )
            cyl.Layer = layer
            handle = cyl.Handle
        finally:
            _restore_layer(doc, prev)
        return {
            "success": True, "handle": handle, "entity": "Cylinder3D",
            "center": [cx, cy, cz], "radius": radius, "height": height,
            "layer": layer,
        }
    except AutoCADConnectionError as exc:
        return {"success": False, "error": str(exc)}
    except Exception as exc:
        err = str(exc)
        logger.warning("draw_cylinder failed (ACIS): %s", err)
        return {"success": False, "error": err, "note": "ACIS_NOT_AVAILABLE"}


# ---------------------------------------------------------------------------
# Tool: draw_cone (ACIS 3D solid)
# ---------------------------------------------------------------------------

def draw_cone(
    cx: float, cy: float, cz: float,
    base_radius: float, height: float,
    layer: str = "0",
) -> dict[str, Any]:
    """Draw a 3-D solid cone (ACIS).

    Parameters
    ----------
    cx, cy, cz : float   Centre of the cone base.
    base_radius : float  Radius of the base circle.
    height : float       Height of the cone.
    layer : str
    """
    try:
        _, doc, ms = _ms()
        prev = _with_layer(doc, layer)
        try:
            cone = ms.AddCone(
                point3d(cx, cy, cz), float(base_radius), float(height)
            )
            cone.Layer = layer
            handle = cone.Handle
        finally:
            _restore_layer(doc, prev)
        return {
            "success": True, "handle": handle, "entity": "Cone3D",
            "center": [cx, cy, cz], "base_radius": base_radius,
            "height": height, "layer": layer,
        }
    except AutoCADConnectionError as exc:
        return {"success": False, "error": str(exc)}
    except Exception as exc:
        err = str(exc)
        logger.warning("draw_cone failed (ACIS): %s", err)
        return {"success": False, "error": err, "note": "ACIS_NOT_AVAILABLE"}


# ---------------------------------------------------------------------------
# Tool: set_ucs
# ---------------------------------------------------------------------------

def set_ucs(
    origin_x: float = 0.0, origin_y: float = 0.0, origin_z: float = 0.0,
    x_axis_x: float = 1.0, x_axis_y: float = 0.0, x_axis_z: float = 0.0,
    y_axis_x: float = 0.0, y_axis_y: float = 1.0, y_axis_z: float = 0.0,
    name: str = "MCP_UCS",
) -> dict[str, Any]:
    """Define and activate a named User Coordinate System.

    Sending the UCS back to World (0,0,0 / 1,0,0 / 0,1,0) resets to WCS.

    Parameters
    ----------
    origin_x, origin_y, origin_z : float   UCS origin.
    x_axis_x/y/z : float                   X-axis direction vector.
    y_axis_x/y/z : float                   Y-axis direction vector.
    name : str                              Name for the UCS entry.
    """
    try:
        c = _conn()
        doc = c.get_active_document()
        ucs = doc.UserCoordinateSystems.Add(
            point3d(origin_x, origin_y, origin_z),
            point3d(x_axis_x, x_axis_y, x_axis_z),
            point3d(y_axis_x, y_axis_y, y_axis_z),
            name,
        )
        doc.ActiveUCS = ucs
        return {
            "success": True,
            "ucs_name": name,
            "origin": [origin_x, origin_y, origin_z],
            "x_axis": [x_axis_x, x_axis_y, x_axis_z],
            "y_axis": [y_axis_x, y_axis_y, y_axis_z],
        }
    except AutoCADConnectionError as exc:
        return {"success": False, "error": str(exc)}
    except Exception as exc:
        logger.exception("set_ucs failed")
        return {"success": False, "error": str(exc)}


# ---------------------------------------------------------------------------
# Tool: zoom_3d_view
# ---------------------------------------------------------------------------

def zoom_3d_view(
    view_type: str = "SE_ISOMETRIC",
) -> dict[str, Any]:
    """Set the viewport to a 3-D view preset and zoom to extents.

    Parameters
    ----------
    view_type : str
        One of:
        ``"SE_ISOMETRIC"`` (default), ``"SW_ISOMETRIC"``,
        ``"NE_ISOMETRIC"``, ``"NW_ISOMETRIC"``,
        ``"TOP"``, ``"FRONT"``, ``"RIGHT"``, ``"LEFT"``, ``"BACK"``,
        ``"BOTTOM"``, ``"PERSPECTIVE"``.

    Returns
    -------
    dict
    """
    _VIEW_COMMANDS = {
        "SE_ISOMETRIC": "-VIEW SE ",
        "SW_ISOMETRIC": "-VIEW SW ",
        "NE_ISOMETRIC": "-VIEW NE ",
        "NW_ISOMETRIC": "-VIEW NW ",
        "TOP":          "-VIEW TOP ",
        "FRONT":        "-VIEW FRONT ",
        "RIGHT":        "-VIEW RIGHT ",
        "LEFT":         "-VIEW LEFT ",
        "BACK":         "-VIEW BACK ",
        "BOTTOM":       "-VIEW BOTTOM ",
        "PERSPECTIVE":  "-VIEW SE \nDVIEW \n\nTW 0 \nD 200 \n ",
    }
    vt = view_type.upper()
    cmd = _VIEW_COMMANDS.get(vt)
    if cmd is None:
        return {
            "success": False,
            "error": f"Unknown view_type '{view_type}'. "
                     f"Valid: {list(_VIEW_COMMANDS.keys())}",
        }
    try:
        c = _conn()
        c.send_command(cmd)
        c.send_command("ZOOM E ")
        return {"success": True, "view": vt, "command_sent": cmd.strip()}
    except AutoCADConnectionError as exc:
        return {"success": False, "error": str(exc)}
    except Exception as exc:
        logger.exception("zoom_3d_view failed")
        return {"success": False, "error": str(exc)}
