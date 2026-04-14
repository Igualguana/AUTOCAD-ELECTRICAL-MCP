"""Main MCP server entry point for AutoCAD (Electrical and Standard).

Supports both AutoCAD Electrical (full 34+ tools) and AutoCAD Standard
(drawing + 2D/3D geometry tools).  The active variant is auto-detected at
startup via :mod:`src.autocad.detector`.

Uses FastMCP from the ``mcp`` library to register tools and serve them over
stdio transport so that Claude Code (and other MCP clients) can invoke them.

Usage
-----
Run as a module::

    python -m src.server

Or via the installed script::

    autocad-mcp
"""

from __future__ import annotations

import logging
import sys
from typing import Any

# ---------------------------------------------------------------------------
# Logging configuration (before any other imports that log)
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stderr)],
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# MCP server bootstrap
# ---------------------------------------------------------------------------
try:
    from mcp.server.fastmcp import FastMCP
except ImportError as _exc:
    logger.critical(
        "The 'mcp' package is not installed.  Run: pip install mcp>=1.0.0\n%s",
        _exc,
    )
    sys.exit(1)

from src.config import get_config
from src.autocad.connection import get_connection, AutoCADConnectionError
from src.autocad.detector import detect as _detect_autocad

# Load config early so tools can use it
_cfg = get_config()
_mcp_cfg = _cfg.mcp

# Detect AutoCAD variant (Electrical / Standard / none)
_acad_info = _detect_autocad()
logger.info(
    "AutoCAD variant: %s | running: %s | method: %s",
    _acad_info.variant, _acad_info.running, _acad_info.detection_method,
)

# Initialise FastMCP (mcp>=1.2 removed the 'version' parameter)
mcp = FastMCP(
    name=_mcp_cfg.get("server_name", "autocad-mcp"),
)

# ---------------------------------------------------------------------------
# Lazy AutoCAD connection (attempt at startup but don't fail if not running)
# ---------------------------------------------------------------------------

def _attempt_autocad_connect() -> None:
    """Try to connect to AutoCAD; log a warning if unavailable."""
    ac_cfg = _cfg.autocad
    com_obj = ac_cfg.get("com_object", "AutoCAD.Application")
    timeout = int(ac_cfg.get("timeout", 30))
    try:
        conn = get_connection(com_object=com_obj, timeout=timeout, auto_connect=True)
        logger.info("AutoCAD connection established: %s", conn._get_version_string())
    except AutoCADConnectionError as exc:
        logger.warning(
            "AutoCAD is not running at startup – tools will return an error "
            "until AutoCAD Electrical 2025 is launched.\n  %s",
            exc,
        )
    except Exception as exc:
        logger.warning("AutoCAD connection attempt failed: %s", exc)


# ---------------------------------------------------------------------------
# Import tool modules
# ---------------------------------------------------------------------------
from src.tools import drawing, electrical, wires, components, reports, project
from src.tools import drawing3d


# ===========================================================================
# Drawing tools  (2D — available for both Standard and Electrical)
# ===========================================================================

@mcp.tool()
def draw_line(
    x1: float,
    y1: float,
    x2: float,
    y2: float,
    layer: str = "0",
) -> dict[str, Any]:
    """Draw a line from (x1, y1) to (x2, y2) on the specified layer.

    Returns a dict with success status and the entity handle on success.
    """
    return drawing.draw_line(x1, y1, x2, y2, layer)


@mcp.tool()
def draw_circle(
    cx: float,
    cy: float,
    radius: float,
    layer: str = "0",
) -> dict[str, Any]:
    """Draw a circle at centre (cx, cy) with the given radius."""
    return drawing.draw_circle(cx, cy, radius, layer)


@mcp.tool()
def draw_arc(
    cx: float,
    cy: float,
    radius: float,
    start_angle: float,
    end_angle: float,
    layer: str = "0",
) -> dict[str, Any]:
    """Draw an arc centred at (cx, cy).

    Angles are in degrees; 0° = East, counter-clockwise positive.
    """
    return drawing.draw_arc(cx, cy, radius, start_angle, end_angle, layer)


@mcp.tool()
def draw_text(
    x: float,
    y: float,
    text: str,
    height: float = 2.5,
    layer: str = "0",
) -> dict[str, Any]:
    """Place a single-line text entity at (x, y) with the given height."""
    return drawing.draw_text(x, y, text, height, layer)


@mcp.tool()
def draw_rectangle(
    x1: float,
    y1: float,
    x2: float,
    y2: float,
    layer: str = "0",
) -> dict[str, Any]:
    """Draw a closed rectangular polyline from corner (x1, y1) to (x2, y2)."""
    return drawing.draw_rectangle(x1, y1, x2, y2, layer)


@mcp.tool()
def draw_polyline(
    points: list,
    closed: bool = False,
    layer: str = "0",
) -> dict[str, Any]:
    """Draw a 2-D lightweight polyline through a list of [x, y] points.

    Parameters
    ----------
    points : list of [x, y]   At least 2 vertices.
    closed : bool             Close the polyline (last → first vertex).
    layer : str               Target layer.
    """
    return drawing.draw_polyline(points, closed, layer)


@mcp.tool()
def zoom_extents() -> dict[str, Any]:
    """Zoom the active viewport to fit all entities (ZOOM E)."""
    return drawing.zoom_extents()


@mcp.tool()
def set_layer(
    layer_name: str,
    color: int = 7,
    linetype: str = "Continuous",
    make_active: bool = True,
) -> dict[str, Any]:
    """Create or configure a layer and optionally make it active.

    Parameters
    ----------
    layer_name : str    Layer name.
    color : int         ACI color (1=Red, 2=Yellow, 3=Green, 5=Blue, 7=White).
    linetype : str      Linetype (e.g. 'Continuous', 'DASHED').
    make_active : bool  Set as the active layer.
    """
    return drawing.set_layer(layer_name, color, linetype, make_active)


# ===========================================================================
# 3D Drawing tools  (Standard and Electrical)
# ===========================================================================

@mcp.tool()
def draw_line_3d(
    x1: float, y1: float, z1: float,
    x2: float, y2: float, z2: float,
    layer: str = "0",
) -> dict[str, Any]:
    """Draw a 3-D line between two XYZ points.

    Parameters
    ----------
    x1, y1, z1 : float   Start point.
    x2, y2, z2 : float   End point.
    layer : str           Target layer.
    """
    return drawing3d.draw_line_3d(x1, y1, z1, x2, y2, z2, layer)


@mcp.tool()
def draw_polyline_3d(
    points: list,
    closed: bool = False,
    layer: str = "0",
) -> dict[str, Any]:
    """Draw a 3-D polyline through a list of [x, y, z] points.

    Parameters
    ----------
    points : list of [x, y, z]   At least 2 vertices.
    closed : bool                Close the polyline.
    layer : str                  Target layer.
    """
    return drawing3d.draw_polyline_3d(points, closed, layer)


@mcp.tool()
def draw_3d_face(
    x1: float, y1: float, z1: float,
    x2: float, y2: float, z2: float,
    x3: float, y3: float, z3: float,
    x4: float = None, y4: float = None, z4: float = None,
    layer: str = "0",
) -> dict[str, Any]:
    """Draw a 3DFACE (triangle or quad) in 3-D space.

    For a triangle, leave x4/y4/z4 as None (third point is duplicated).
    """
    return drawing3d.draw_3d_face(x1, y1, z1, x2, y2, z2, x3, y3, z3,
                                   x4, y4, z4, layer)


@mcp.tool()
def draw_box(
    origin_x: float, origin_y: float, origin_z: float,
    length: float, width: float, height: float,
    layer: str = "0",
) -> dict[str, Any]:
    """Draw a 3-D solid box (ACIS — requires full AutoCAD with 3D Modeling).

    Returns ``{"note": "ACIS_NOT_AVAILABLE"}`` if the license doesn't permit it.
    """
    return drawing3d.draw_box(origin_x, origin_y, origin_z,
                               length, width, height, layer)


@mcp.tool()
def draw_sphere(
    cx: float, cy: float, cz: float,
    radius: float,
    layer: str = "0",
) -> dict[str, Any]:
    """Draw a 3-D solid sphere (ACIS)."""
    return drawing3d.draw_sphere(cx, cy, cz, radius, layer)


@mcp.tool()
def draw_cylinder(
    cx: float, cy: float, cz: float,
    radius: float, height: float,
    layer: str = "0",
) -> dict[str, Any]:
    """Draw a 3-D solid cylinder (ACIS)."""
    return drawing3d.draw_cylinder(cx, cy, cz, radius, height, layer)


@mcp.tool()
def draw_cone(
    cx: float, cy: float, cz: float,
    base_radius: float, height: float,
    layer: str = "0",
) -> dict[str, Any]:
    """Draw a 3-D solid cone (ACIS)."""
    return drawing3d.draw_cone(cx, cy, cz, base_radius, height, layer)


@mcp.tool()
def zoom_3d_view(view_type: str = "SE_ISOMETRIC") -> dict[str, Any]:
    """Switch to a 3-D view preset and zoom to extents.

    view_type options: SE_ISOMETRIC, SW_ISOMETRIC, NE_ISOMETRIC, NW_ISOMETRIC,
    TOP, FRONT, RIGHT, LEFT, BACK, BOTTOM, PERSPECTIVE.
    """
    return drawing3d.zoom_3d_view(view_type)


@mcp.tool()
def set_ucs(
    origin_x: float = 0.0, origin_y: float = 0.0, origin_z: float = 0.0,
    x_axis_x: float = 1.0, x_axis_y: float = 0.0, x_axis_z: float = 0.0,
    y_axis_x: float = 0.0, y_axis_y: float = 1.0, y_axis_z: float = 0.0,
    name: str = "MCP_UCS",
) -> dict[str, Any]:
    """Define and activate a named User Coordinate System for 3-D work."""
    return drawing3d.set_ucs(
        origin_x, origin_y, origin_z,
        x_axis_x, x_axis_y, x_axis_z,
        y_axis_x, y_axis_y, y_axis_z,
        name,
    )


@mcp.tool()
def get_autocad_info() -> dict[str, Any]:
    """Return detected AutoCAD variant, version, features, and running state.

    Useful for discovering whether AutoCAD Electrical or Standard is active
    and which feature groups are enabled.
    """
    return _acad_info.to_dict()


# ===========================================================================
# Electrical tools  (AutoCAD Electrical only)
# ===========================================================================

@mcp.tool()
def insert_electrical_symbol(
    symbol_name: str,
    x: float,
    y: float,
    rotation: float = 0.0,
    attributes: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Insert an AutoCAD Electrical symbol from the WD symbol library.

    Parameters
    ----------
    symbol_name : str
        Block name as it appears in the Electrical symbol library
        (e.g. "WD_NOPEN", "WD_COIL").
    x, y : float
        Insertion point coordinates.
    rotation : float
        Rotation angle in degrees.
    attributes : dict or None
        Optional attribute overrides, e.g. {"TAG1": "101CR", "DESC1": "Motor Contactor"}.
    """
    return electrical.insert_electrical_symbol(symbol_name, x, y, rotation, attributes)


@mcp.tool()
def insert_ladder(
    x_start: float,
    y_start: float,
    rung_spacing: float = 25.4,
    rung_count: int = 10,
    voltage: str = "120V",
    phase: str = "1P",
) -> dict[str, Any]:
    """Create a ladder diagram using AutoCAD Electrical's WDLADDER command.

    Parameters
    ----------
    x_start, y_start : float
        Origin of the ladder (top-left).
    rung_spacing : float
        Vertical distance between rungs in drawing units (25.4 = 1 inch).
    rung_count : int
        Number of rungs.
    voltage : str
        Voltage label (e.g. "120V", "24VDC").
    phase : str
        "1P" for single-phase or "3P" for three-phase.
    """
    return electrical.insert_ladder(x_start, y_start, rung_spacing, rung_count, voltage, phase)


@mcp.tool()
def get_symbol_list(category: str = "") -> dict[str, Any]:
    """Return available AutoCAD Electrical symbol names.

    Parameters
    ----------
    category : str
        Filter by category: "contacts", "coils", "plc", "terminals",
        "transformers", "misc", or "" for all.
    """
    return electrical.get_symbol_list(category)


@mcp.tool()
def set_wire_number(
    wire_number: str,
    x: float,
    y: float,
) -> dict[str, Any]:
    """Place a wire number tag at the given coordinates using WDWNUM."""
    return electrical.set_wire_number(wire_number, x, y)


@mcp.tool()
def insert_plc_module(
    module_type: str,
    rack: int,
    slot: int,
    x: float,
    y: float,
) -> dict[str, Any]:
    """Insert a PLC I/O module symbol.

    Parameters
    ----------
    module_type : str
        "input", "output", "analog_input", or "analog_output".
    rack : int
        PLC rack number (0-based).
    slot : int
        Slot number within the rack (0-based).
    x, y : float
        Insertion point.
    """
    return electrical.insert_plc_module(module_type, rack, slot, x, y)


@mcp.tool()
def create_cross_reference(
    source_tag: str,
    dest_sheet: str,
    dest_ref: str,
) -> dict[str, Any]:
    """Create a cross-reference link between a source component and a destination.

    Parameters
    ----------
    source_tag : str
        TAG1 of the source component (e.g. "101CR").
    dest_sheet : str
        Destination drawing sheet number (e.g. "3").
    dest_ref : str
        Reference designation on the destination sheet (e.g. "B12").
    """
    return electrical.create_cross_reference(source_tag, dest_sheet, dest_ref)


@mcp.tool()
def edit_component_attributes(
    tag1: str,
    attributes_dict: dict[str, str],
) -> dict[str, Any]:
    """Update attribute values on a component identified by TAG1.

    Parameters
    ----------
    tag1 : str
        The component's TAG1 identifier.
    attributes_dict : dict[str, str]
        Attribute tag → new value mapping.
    """
    return electrical.edit_component_attributes(tag1, attributes_dict)


# ===========================================================================
# Wire tools
# ===========================================================================

@mcp.tool()
def draw_wire(
    x1: float,
    y1: float,
    x2: float,
    y2: float,
    wire_layer: str = "WIRES",
) -> dict[str, Any]:
    """Draw a wire segment on the WIRES layer (or custom layer).

    Parameters
    ----------
    x1, y1 : float
        Wire start point.
    x2, y2 : float
        Wire end point.
    wire_layer : str
        Target layer (default "WIRES").
    """
    return wires.draw_wire(x1, y1, x2, y2, wire_layer)


@mcp.tool()
def number_wires(
    sheet: str | None = None,
    project: str | None = None,
) -> dict[str, Any]:
    """Run AutoCAD Electrical's WDANNO wire-numbering command.

    Parameters
    ----------
    sheet : str or None
        Sheet to limit scope; None uses the active drawing.
    project : str or None
        When provided, triggers project-wide numbering.
    """
    return wires.number_wires(sheet, project)


@mcp.tool()
def get_wire_numbers(sheet: str | None = None) -> dict[str, Any]:
    """Return all wire number tags in the active drawing."""
    return wires.get_wire_numbers(sheet)


@mcp.tool()
def set_wire_attributes(
    tag: str,
    attributes: dict[str, str],
) -> dict[str, Any]:
    """Modify attributes on a wire entity identified by its wire-number tag.

    Parameters
    ----------
    tag : str
        Wire number / tag to locate.
    attributes : dict[str, str]
        Attribute tag → new value mapping.
    """
    return wires.set_wire_attributes(tag, attributes)


@mcp.tool()
def create_wire_from_to(
    from_component: str,
    to_component: str,
) -> dict[str, Any]:
    """Route a wire between two components identified by their TAG1 values.

    Parameters
    ----------
    from_component : str
        TAG1 of the source component.
    to_component : str
        TAG1 of the destination component.
    """
    return wires.create_wire_from_to(from_component, to_component)


# ===========================================================================
# Component tools
# ===========================================================================

@mcp.tool()
def get_component_list(drawing: str | None = None) -> dict[str, Any]:
    """List all AutoCAD Electrical components in the active drawing."""
    return components.get_component_list(drawing)


@mcp.tool()
def get_component_info(tag1: str) -> dict[str, Any]:
    """Return full attribute information for the component with the given TAG1."""
    return components.get_component_info(tag1)


@mcp.tool()
def update_component(
    tag1: str,
    attributes: dict[str, str],
) -> dict[str, Any]:
    """Update attribute values on the component identified by TAG1.

    Parameters
    ----------
    tag1 : str
        TAG1 of the target component.
    attributes : dict[str, str]
        Attribute tag → new value pairs.
    """
    return components.update_component(tag1, attributes)


@mcp.tool()
def delete_component(tag1: str) -> dict[str, Any]:
    """Remove the component identified by TAG1 from the current drawing."""
    return components.delete_component(tag1)


@mcp.tool()
def move_component(
    tag1: str,
    new_x: float,
    new_y: float,
) -> dict[str, Any]:
    """Move a component identified by TAG1 to new coordinates (new_x, new_y)."""
    return components.move_component(tag1, new_x, new_y)


@mcp.tool()
def search_components(filter_criteria: dict[str, str]) -> dict[str, Any]:
    """Search for components matching one or more attribute criteria.

    Parameters
    ----------
    filter_criteria : dict[str, str]
        Attribute tag → expected value.  Use a trailing ``*`` for prefix
        matching, e.g. ``{"TAG1": "CR*", "MFG": "ALLEN-BRADLEY"}``.
    """
    return components.search_components(filter_criteria)


# ===========================================================================
# Report tools
# ===========================================================================

@mcp.tool()
def generate_bom(
    output_format: str = "csv",
    output_path: str | None = None,
) -> dict[str, Any]:
    """Generate a Bill of Materials for the active drawing.

    Parameters
    ----------
    output_format : str
        "csv" (default) or "wdreport" to use AutoCAD Electrical's WDREPORT.
    output_path : str or None
        Output file path; defaults to a timestamped file in Documents.
    """
    return reports.generate_bom(output_format, output_path)


@mcp.tool()
def generate_wire_list(output_path: str | None = None) -> dict[str, Any]:
    """Generate a wire connection list (from-to report) as a CSV file."""
    return reports.generate_wire_list(output_path)


@mcp.tool()
def generate_terminal_plan(output_path: str | None = None) -> dict[str, Any]:
    """Generate a terminal strip report as a CSV file."""
    return reports.generate_terminal_plan(output_path)


@mcp.tool()
def generate_plc_io_list(output_path: str | None = None) -> dict[str, Any]:
    """Generate a PLC I/O list as a CSV file."""
    return reports.generate_plc_io_list(output_path)


@mcp.tool()
def get_project_summary() -> dict[str, Any]:
    """Return a summary of open drawings, total components, and wire counts."""
    return reports.get_project_summary()


# ===========================================================================
# Project tools
# ===========================================================================

@mcp.tool()
def get_project_info() -> dict[str, Any]:
    """Return information about the current AutoCAD Electrical project."""
    return project.get_project_info()


@mcp.tool()
def list_drawings() -> dict[str, Any]:
    """List all drawings currently open in AutoCAD."""
    return project.list_drawings()


@mcp.tool()
def open_drawing(sheet_number_or_name: str) -> dict[str, Any]:
    """Switch to or open a drawing by sheet number or filename.

    Parameters
    ----------
    sheet_number_or_name : str
        Sheet number (e.g. "3") or drawing filename (e.g. "Sheet_03.dwg").
    """
    return project.open_drawing(sheet_number_or_name)


@mcp.tool()
def close_drawing(save: bool = True) -> dict[str, Any]:
    """Close the currently active drawing.

    Parameters
    ----------
    save : bool
        Save the drawing before closing (default True).
    """
    return project.close_drawing(save)


@mcp.tool()
def sync_project() -> dict[str, Any]:
    """Run a project-wide update via AutoCAD Electrical's WDSYNCH command."""
    return project.sync_project()


@mcp.tool()
def get_active_drawing() -> dict[str, Any]:
    """Return information about the currently active drawing."""
    return project.get_active_drawing()


# ===========================================================================
# Entry point
# ===========================================================================

def main() -> None:
    """Start the MCP server (stdio transport)."""
    logger.info(
        "Starting %s v%s",
        _mcp_cfg.get("server_name", "autocad-electrical-mcp"),
        _mcp_cfg.get("server_version", "1.0.0"),
    )
    logger.info("Active AI provider: %s", _cfg.get_active_provider())

    # Attempt AutoCAD connection at startup (non-fatal)
    _attempt_autocad_connect()

    # Run the MCP server (blocks until the client disconnects)
    mcp.run()


if __name__ == "__main__":
    main()
