"""AI orchestration: natural language → tool selection → AutoCAD execution.

Flow
----
1. User sends a natural language message with an optional drawing mode.
2. A mode-aware system prompt (Electrical / 3D / 2D / Auto) is built from the
   TOOL_REGISTRY, exposing only the relevant subset of tools to the model.
3. The configured AI provider (default: Ollama) receives the prompt.
4. On TimeoutError or any provider failure, a smart fallback to the smallest
   installed Ollama model is attempted automatically.
5. The provider response is stripped of Qwen3 <think> blocks, then JSON-parsed.
6. If a tool call: the corresponding src/tools/* function is invoked directly.
7. The result is returned to the caller (FastAPI endpoint).
"""

from __future__ import annotations

import json
import logging
import re
import time
import traceback
from typing import Any

from src.config import get_config
from src.providers import get_provider
from src.tools import drawing, drawing3d, electrical, wires, components, reports
from src.tools import project as proj
from web.backend.state import add_log, add_history

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Tool registry — maps tool name → {func, description, params, category}
# ---------------------------------------------------------------------------

TOOL_REGISTRY: dict[str, dict[str, Any]] = {
    # ── Drawing ─────────────────────────────────────────────────────────
    "draw_line": {
        "func": drawing.draw_line,
        "description": "Draw a straight line from (x1,y1) to (x2,y2) on the specified layer.",
        "params": {"x1": "float", "y1": "float", "x2": "float", "y2": "float", "layer": "str (default '0')"},
        "category": "Drawing",
    },
    "draw_circle": {
        "func": drawing.draw_circle,
        "description": "Draw a circle at centre (cx,cy) with the given radius.",
        "params": {"cx": "float", "cy": "float", "radius": "float", "layer": "str (default '0')"},
        "category": "Drawing",
    },
    "draw_arc": {
        "func": drawing.draw_arc,
        "description": "Draw an arc. Angles in degrees, 0=East, counter-clockwise positive.",
        "params": {"cx": "float", "cy": "float", "radius": "float", "start_angle": "float", "end_angle": "float", "layer": "str (default '0')"},
        "category": "Drawing",
    },
    "draw_text": {
        "func": drawing.draw_text,
        "description": "Place a single-line text entity at (x,y).",
        "params": {"x": "float", "y": "float", "text": "str", "height": "float (default 2.5)", "layer": "str (default '0')"},
        "category": "Drawing",
    },
    "draw_rectangle": {
        "func": drawing.draw_rectangle,
        "description": "Draw a closed rectangle from corner (x1,y1) to opposite corner (x2,y2).",
        "params": {"x1": "float", "y1": "float", "x2": "float", "y2": "float", "layer": "str (default '0')"},
        "category": "Drawing",
    },
    "draw_polyline": {
        "func": drawing.draw_polyline,
        "description": "Draw a 2-D polyline through a list of [x,y] points. closed=True closes the shape.",
        "params": {"points": "list of [x,y]", "closed": "bool (default False)", "layer": "str (default '0')"},
        "category": "Drawing",
    },
    "zoom_extents": {
        "func": drawing.zoom_extents,
        "description": "Zoom the active viewport to fit all ModelSpace entities (ZOOM E).",
        "params": {},
        "category": "Drawing",
    },
    "set_layer": {
        "func": drawing.set_layer,
        "description": "Create or configure a layer (name, ACI color, linetype) and optionally make it active.",
        "params": {"layer_name": "str", "color": "int (ACI, default 7)", "linetype": "str (default 'Continuous')", "make_active": "bool (default True)"},
        "category": "Drawing",
    },
    # ── Drawing 3D ──────────────────────────────────────────────────────
    "draw_line_3d": {
        "func": drawing3d.draw_line_3d,
        "description": "Draw a 3-D line between two XYZ points.",
        "params": {"x1": "float", "y1": "float", "z1": "float", "x2": "float", "y2": "float", "z2": "float", "layer": "str (default '0')"},
        "category": "Drawing3D",
    },
    "draw_polyline_3d": {
        "func": drawing3d.draw_polyline_3d,
        "description": "Draw a 3-D polyline through a list of [x,y,z] points.",
        "params": {"points": "list of [x,y,z]", "closed": "bool (default False)", "layer": "str (default '0')"},
        "category": "Drawing3D",
    },
    "draw_3d_face": {
        "func": drawing3d.draw_3d_face,
        "description": "Draw a 3DFACE (triangle or quad) in 3-D space.",
        "params": {"x1..z3": "float (3 corners required)", "x4/y4/z4": "float optional (4th corner)", "layer": "str (default '0')"},
        "category": "Drawing3D",
    },
    "draw_box": {
        "func": drawing3d.draw_box,
        "description": "Draw a 3-D solid box (ACIS — full AutoCAD with 3D Modeling required).",
        "params": {"origin_x": "float", "origin_y": "float", "origin_z": "float", "length": "float", "width": "float", "height": "float", "layer": "str (default '0')"},
        "category": "Drawing3D",
    },
    "draw_sphere": {
        "func": drawing3d.draw_sphere,
        "description": "Draw a 3-D solid sphere (ACIS).",
        "params": {"cx": "float", "cy": "float", "cz": "float", "radius": "float", "layer": "str (default '0')"},
        "category": "Drawing3D",
    },
    "draw_cylinder": {
        "func": drawing3d.draw_cylinder,
        "description": "Draw a 3-D solid cylinder (ACIS).",
        "params": {"cx": "float", "cy": "float", "cz": "float", "radius": "float", "height": "float", "layer": "str (default '0')"},
        "category": "Drawing3D",
    },
    "draw_cone": {
        "func": drawing3d.draw_cone,
        "description": "Draw a 3-D solid cone (ACIS).",
        "params": {"cx": "float", "cy": "float", "cz": "float", "base_radius": "float", "height": "float", "layer": "str (default '0')"},
        "category": "Drawing3D",
    },
    "zoom_3d_view": {
        "func": drawing3d.zoom_3d_view,
        "description": "Set a 3-D view preset (SE_ISOMETRIC, TOP, FRONT, etc.) and zoom to extents.",
        "params": {"view_type": "str (default 'SE_ISOMETRIC')"},
        "category": "Drawing3D",
    },
    "set_ucs": {
        "func": drawing3d.set_ucs,
        "description": "Define and activate a UCS by origin and X/Y axis vectors.",
        "params": {"origin_x/y/z": "float", "x_axis_x/y/z": "float", "y_axis_x/y/z": "float", "name": "str (default 'MCP_UCS')"},
        "category": "Drawing3D",
    },
    # ── Electrical ──────────────────────────────────────────────────────
    "insert_electrical_symbol": {
        "func": electrical.insert_electrical_symbol,
        "description": "Insert an AutoCAD Electrical symbol from the WD library (e.g. 'WD_NOPEN', 'WD_COIL').",
        "params": {"symbol_name": "str", "x": "float", "y": "float", "rotation": "float (default 0.0)", "attributes": "dict or null"},
        "category": "Electrical",
    },
    "insert_ladder": {
        "func": electrical.insert_ladder,
        "description": "Insert a rung ladder with specified spacing, rung count, voltage and phase.",
        "params": {"x_start": "float", "y_start": "float", "rung_spacing": "float", "rung_count": "int", "voltage": "str", "phase": "str"},
        "category": "Electrical",
    },
    "get_symbol_list": {
        "func": electrical.get_symbol_list,
        "description": "Return the list of available WD electrical symbols, optionally filtered by category.",
        "params": {"category": "str or null"},
        "category": "Electrical",
    },
    "set_wire_number": {
        "func": electrical.set_wire_number,
        "description": "Place a wire number tag at coordinates (x,y).",
        "params": {"wire_number": "str", "x": "float", "y": "float"},
        "category": "Electrical",
    },
    "insert_plc_module": {
        "func": electrical.insert_plc_module,
        "description": "Insert a PLC module symbol at a rack/slot position.",
        "params": {"module_type": "str", "rack": "int", "slot": "int", "x": "float", "y": "float"},
        "category": "Electrical",
    },
    "create_cross_reference": {
        "func": electrical.create_cross_reference,
        "description": "Create a cross-reference link between a source component (TAG1) and a destination sheet/ref.",
        "params": {"source_tag": "str", "dest_sheet": "str", "dest_ref": "str"},
        "category": "Electrical",
    },
    "edit_component_attributes": {
        "func": electrical.edit_component_attributes,
        "description": "Edit one or more attributes on a component identified by TAG1.",
        "params": {"tag1": "str", "attributes_dict": "dict"},
        "category": "Electrical",
    },
    # ── Wires ───────────────────────────────────────────────────────────
    "draw_wire": {
        "func": wires.draw_wire,
        "description": "Draw a wire (line on the WIRES layer) from (x1,y1) to (x2,y2).",
        "params": {"x1": "float", "y1": "float", "x2": "float", "y2": "float", "wire_layer": "str (default 'WIRES')"},
        "category": "Wires",
    },
    "number_wires": {
        "func": wires.number_wires,
        "description": "Run AutoCAD Electrical wire numbering (WDANNO) on the current sheet or entire project.",
        "params": {"sheet": "str or null", "project": "str or null"},
        "category": "Wires",
    },
    "get_wire_numbers": {
        "func": wires.get_wire_numbers,
        "description": "Return all wire numbers found on the specified sheet (or active sheet).",
        "params": {"sheet": "str or null"},
        "category": "Wires",
    },
    "set_wire_attributes": {
        "func": wires.set_wire_attributes,
        "description": "Set attributes on a wire entity identified by its tag.",
        "params": {"tag": "str", "attributes": "dict"},
        "category": "Wires",
    },
    "create_wire_from_to": {
        "func": wires.create_wire_from_to,
        "description": "Route a wire between two components identified by their TAG1 values.",
        "params": {"from_component": "str", "to_component": "str"},
        "category": "Wires",
    },
    # ── Components ──────────────────────────────────────────────────────
    "get_component_list": {
        "func": components.get_component_list,
        "description": "Return a list of all electrical components in the active (or specified) drawing.",
        "params": {"drawing": "str or null"},
        "category": "Components",
    },
    "get_component_info": {
        "func": components.get_component_info,
        "description": "Return full attributes and position for a single component by TAG1.",
        "params": {"tag1": "str"},
        "category": "Components",
    },
    "update_component": {
        "func": components.update_component,
        "description": "Update one or more attributes on a component identified by TAG1.",
        "params": {"tag1": "str", "attributes": "dict"},
        "category": "Components",
    },
    "delete_component": {
        "func": components.delete_component,
        "description": "Delete a component from the drawing by TAG1.",
        "params": {"tag1": "str"},
        "category": "Components",
    },
    "move_component": {
        "func": components.move_component,
        "description": "Move a component to new coordinates by TAG1.",
        "params": {"tag1": "str", "new_x": "float", "new_y": "float"},
        "category": "Components",
    },
    "search_components": {
        "func": components.search_components,
        "description": "Search components by attribute values. Supports wildcards (e.g. {'TAG1': 'CR*'}).",
        "params": {"filter_criteria": "dict"},
        "category": "Components",
    },
    # ── Reports ─────────────────────────────────────────────────────────
    "generate_bom": {
        "func": reports.generate_bom,
        "description": "Generate a Bill of Materials. format: 'csv' or 'wdreport'.",
        "params": {"output_format": "str (default 'csv')", "output_path": "str or null"},
        "category": "Reports",
    },
    "generate_wire_list": {
        "func": reports.generate_wire_list,
        "description": "Generate a wire from-to list as CSV.",
        "params": {"output_path": "str or null"},
        "category": "Reports",
    },
    "generate_terminal_plan": {
        "func": reports.generate_terminal_plan,
        "description": "Generate a terminal strip plan report as CSV.",
        "params": {"output_path": "str or null"},
        "category": "Reports",
    },
    "generate_plc_io_list": {
        "func": reports.generate_plc_io_list,
        "description": "Generate a PLC I/O mapping report as CSV.",
        "params": {"output_path": "str or null"},
        "category": "Reports",
    },
    "get_project_summary": {
        "func": reports.get_project_summary,
        "description": "Return a summary of the project: drawing count, component count, wire count.",
        "params": {},
        "category": "Reports",
    },
    # ── Project ─────────────────────────────────────────────────────────
    "get_project_info": {
        "func": proj.get_project_info,
        "description": "Return project name, path, and list of open drawings.",
        "params": {},
        "category": "Project",
    },
    "list_drawings": {
        "func": proj.list_drawings,
        "description": "List all open drawings with their sheet numbers and save state.",
        "params": {},
        "category": "Project",
    },
    "open_drawing": {
        "func": proj.open_drawing,
        "description": "Switch to a drawing by sheet number or filename.",
        "params": {"sheet_number_or_name": "str"},
        "category": "Project",
    },
    "close_drawing": {
        "func": proj.close_drawing,
        "description": "Close the active drawing, optionally saving first.",
        "params": {"save": "bool (default True)"},
        "category": "Project",
    },
    "sync_project": {
        "func": proj.sync_project,
        "description": "Run project-wide synchronization (WDSYNCH command).",
        "params": {},
        "category": "Project",
    },
    "get_active_drawing": {
        "func": proj.get_active_drawing,
        "description": "Return the name and path of the currently active drawing.",
        "params": {},
        "category": "Project",
    },
}

# ---------------------------------------------------------------------------
# Tool alias map — maps hallucinated / wrong names → real tool names
# Used both in LLM output validation AND the pre-router validator.
# ---------------------------------------------------------------------------
TOOL_ALIASES: dict[str, str] = {
    # 3-D solids
    "draw_cube":            "draw_box",
    "draw_cube_3d":         "draw_box",
    "draw_square_3d":       "draw_box",
    "draw_box_3d":          "draw_box",
    "draw_solid_box":       "draw_box",
    "draw_prism":           "draw_box",
    "draw_solid":           "draw_box",
    "draw_ball":            "draw_sphere",
    "draw_sphere_3d":       "draw_sphere",
    "draw_cylinder_3d":     "draw_cylinder",
    "draw_cone_3d":         "draw_cone",
    # 2-D
    "draw_ellipse":         "draw_circle",
    "draw_oval":            "draw_circle",
    "draw_square":          "draw_rectangle",
    "draw_rect":            "draw_rectangle",
    "draw_polygon":         "draw_polyline",
    "draw_pline":           "draw_polyline",
    # Views / layers
    "zoom_all":             "zoom_extents",
    "zoom_fit":             "zoom_extents",
    "zoom_to_fit":          "zoom_extents",
    "zoom_isometric":       "zoom_3d_view",
    "set_view":             "zoom_3d_view",
    "view_isometric":       "zoom_3d_view",
    "create_layer":         "set_layer",
    "make_layer":           "set_layer",
    "set_current_layer":    "set_layer",
    # Electrical / geometry fallbacks
    "draw_wire":            "draw_line",
    "draw_conductor":       "draw_line",
    "draw_bus":             "draw_polyline",
    "draw_motor":           "draw_circle",
    "draw_lamp":            "draw_circle",
    "draw_light":           "draw_circle",
    "draw_switch":          "draw_line",
    "draw_battery":         "draw_rectangle",
    "draw_resistor":        "draw_rectangle",
    "draw_capacitor":       "draw_line",
    "draw_inductor":        "draw_arc",
    "insert_symbol":        "draw_circle",
    "draw_symbol":          "draw_circle",
    "draw_component":       "draw_rectangle",
    "add_text":             "draw_text",
    "place_text":           "draw_text",
    # Project
    "get_drawing":          "get_active_drawing",
    "get_current_drawing":  "get_active_drawing",
    "current_drawing":      "get_active_drawing",
}


def _validate_tool_name(name: str) -> tuple[str, bool]:
    """Validate a tool name and apply aliases if needed.

    Returns
    -------
    (resolved_name, was_aliased)

    Raises ValueError if not resolvable.
    """
    if name in TOOL_REGISTRY:
        return name, False
    if name in TOOL_ALIASES:
        resolved = TOOL_ALIASES[name]
        if resolved in TOOL_REGISTRY:
            return resolved, True
    raise ValueError(
        f"Tool '{name}' not found. "
        f"Valid tools: {', '.join(sorted(TOOL_REGISTRY.keys()))}"
    )


# ---------------------------------------------------------------------------
# Compound drawing plans — multi-step drawings composed from basic tools
# ---------------------------------------------------------------------------

# Type alias for a single execution step
CompoundStep = dict   # {"tool": str, "params": dict, "label": str}


def _screw_steps(scale: float = 1.0) -> list[CompoundStep]:
    """Generate steps to draw a 3-D screw/bolt (tornillo)."""
    r  = round(5.0 * scale, 1)      # shaft radius
    h  = round(30.0 * scale, 1)     # shaft height
    hr = round(9.0 * scale, 1)      # head radius
    hh = round(5.0 * scale, 1)      # head height
    th = round(8.0 * scale, 1)      # tip (cone) height
    return [
        {"tool": "set_layer",
         "params": {"layer_name": "SCREW", "color": 3, "make_active": True},
         "label": "Capa SCREW (verde)"},
        {"tool": "draw_cylinder",
         "params": {"cx": 0.0, "cy": 0.0, "cz": 0.0,
                    "radius": r, "height": h, "layer": "SCREW"},
         "label": f"Cuerpo del tornillo (r={r}, h={h})"},
        {"tool": "draw_cone",
         "params": {"cx": 0.0, "cy": 0.0, "cz": -th,
                    "base_radius": r, "height": th, "layer": "SCREW"},
         "label": f"Punta del tornillo (h={th})"},
        {"tool": "draw_cylinder",
         "params": {"cx": 0.0, "cy": 0.0, "cz": h,
                    "radius": hr, "height": hh, "layer": "SCREW"},
         "label": f"Cabeza del tornillo (r={hr}, h={hh})"},
        {"tool": "zoom_3d_view",
         "params": {"view_type": "SE_ISOMETRIC"},
         "label": "Vista isométrica SE"},
    ]


# Electrical ladder schematic: L1 rail | SW1–EL1 (rung1) | SW2–M1 (rung2) | L2 rail
_ELEC_SCHEMATIC_STEPS: list[CompoundStep] = [
    # ── Power rails ────────────────────────────────────────────────────────
    {"tool": "set_layer",   "params": {"layer_name": "RAILS",     "color": 7, "make_active": True}, "label": "Capa RAILS"},
    {"tool": "draw_line",   "params": {"x1":   0, "y1": 120, "x2":   0, "y2":   0, "layer": "RAILS"}, "label": "Riel L1 vertical izq"},
    {"tool": "draw_line",   "params": {"x1": 210, "y1": 120, "x2": 210, "y2":   0, "layer": "RAILS"}, "label": "Riel L2/N vertical der"},
    {"tool": "draw_text",   "params": {"x":   3, "y": 122, "text": "L1",   "height": 6, "layer": "RAILS"}, "label": "Label L1"},
    {"tool": "draw_text",   "params": {"x": 195, "y": 122, "text": "L2/N", "height": 6, "layer": "RAILS"}, "label": "Label L2/N"},
    # ── Cables rung 1 (y=90): SW1 → EL1 ───────────────────────────────────
    {"tool": "set_layer",   "params": {"layer_name": "CABLES",    "color": 1, "make_active": True}, "label": "Capa CABLES (rojo)"},
    {"tool": "draw_line",   "params": {"x1":   0, "y1":  90, "x2":  45, "y2":  90, "layer": "CABLES"}, "label": "Cable L1→SW1"},
    {"tool": "draw_line",   "params": {"x1":  85, "y1":  90, "x2": 130, "y2":  90, "layer": "CABLES"}, "label": "Cable SW1→EL1"},
    {"tool": "draw_line",   "params": {"x1": 170, "y1":  90, "x2": 210, "y2":  90, "layer": "CABLES"}, "label": "Cable EL1→L2"},
    # ── Cables rung 2 (y=40): SW2 → M1 ────────────────────────────────────
    {"tool": "draw_line",   "params": {"x1":   0, "y1":  40, "x2":  45, "y2":  40, "layer": "CABLES"}, "label": "Cable L1→SW2"},
    {"tool": "draw_line",   "params": {"x1":  85, "y1":  40, "x2": 130, "y2":  40, "layer": "CABLES"}, "label": "Cable SW2→M1"},
    {"tool": "draw_line",   "params": {"x1": 170, "y1":  40, "x2": 210, "y2":  40, "layer": "CABLES"}, "label": "Cable M1→L2"},
    # ── Switch SW1 symbol (rung 1) ─────────────────────────────────────────
    {"tool": "set_layer",   "params": {"layer_name": "SYMBOLS",   "color": 3, "make_active": True}, "label": "Capa SYMBOLS (verde)"},
    {"tool": "draw_line",   "params": {"x1":  45, "y1":  90, "x2":  55, "y2":  90, "layer": "SYMBOLS"}, "label": "SW1 terminal izq"},
    {"tool": "draw_line",   "params": {"x1":  55, "y1":  90, "x2":  75, "y2": 104, "layer": "SYMBOLS"}, "label": "SW1 palanca (abierto)"},
    {"tool": "draw_line",   "params": {"x1":  75, "y1":  90, "x2":  85, "y2":  90, "layer": "SYMBOLS"}, "label": "SW1 terminal der"},
    # ── Switch SW2 symbol (rung 2) ─────────────────────────────────────────
    {"tool": "draw_line",   "params": {"x1":  45, "y1":  40, "x2":  55, "y2":  40, "layer": "SYMBOLS"}, "label": "SW2 terminal izq"},
    {"tool": "draw_line",   "params": {"x1":  55, "y1":  40, "x2":  75, "y2":  54, "layer": "SYMBOLS"}, "label": "SW2 palanca (abierto)"},
    {"tool": "draw_line",   "params": {"x1":  75, "y1":  40, "x2":  85, "y2":  40, "layer": "SYMBOLS"}, "label": "SW2 terminal der"},
    # ── Lamp EL1 symbol: circle + X ────────────────────────────────────────
    {"tool": "draw_circle", "params": {"cx": 150, "cy":  90, "radius": 20, "layer": "SYMBOLS"}, "label": "EL1 cuerpo (círculo)"},
    {"tool": "draw_line",   "params": {"x1": 136, "y1":  76, "x2": 164, "y2": 104, "layer": "SYMBOLS"}, "label": "EL1 diagonal / (X)"},
    {"tool": "draw_line",   "params": {"x1": 164, "y1":  76, "x2": 136, "y2": 104, "layer": "SYMBOLS"}, "label": "EL1 diagonal \\ (X)"},
    # ── Motor M1 symbol: circle + 'M' ──────────────────────────────────────
    {"tool": "draw_circle", "params": {"cx": 150, "cy":  40, "radius": 20, "layer": "SYMBOLS"}, "label": "M1 cuerpo (círculo)"},
    {"tool": "draw_text",   "params": {"x": 145, "y":  37, "text": "M",  "height":  9, "layer": "SYMBOLS"}, "label": "M1 letra M"},
    # ── Text labels ────────────────────────────────────────────────────────
    {"tool": "set_layer",   "params": {"layer_name": "TEXT_ELEC", "color": 2, "make_active": True}, "label": "Capa TEXT_ELEC (amarillo)"},
    {"tool": "draw_text",   "params": {"x":  52, "y": 106, "text": "SW1",  "height": 5, "layer": "TEXT_ELEC"}, "label": "Label SW1"},
    {"tool": "draw_text",   "params": {"x":  52, "y":  55, "text": "SW2",  "height": 5, "layer": "TEXT_ELEC"}, "label": "Label SW2"},
    {"tool": "draw_text",   "params": {"x": 142, "y":  68, "text": "EL1",  "height": 5, "layer": "TEXT_ELEC"}, "label": "Label EL1"},
    {"tool": "draw_text",   "params": {"x": 143, "y":  18, "text": "M1",   "height": 5, "layer": "TEXT_ELEC"}, "label": "Label M1"},
    {"tool": "draw_text",   "params": {"x":  95, "y":   2, "text": "ESQUEMA CONTROL BASICO", "height": 4, "layer": "TEXT_ELEC"}, "label": "Título del esquema"},
    # ── Final zoom ─────────────────────────────────────────────────────────
    {"tool": "zoom_extents", "params": {}, "label": "Zoom extents"},
]


def _compound_keyword_route(msg: str, mode: str) -> list[CompoundStep] | None:
    """Return a compound step list if the message maps to a multi-tool drawing.

    Returns None to fall through to single-tool keyword router or LLM.
    """
    low = msg.lower()
    nums = _extract_numbers(msg)
    scale = (nums[0] / 100.0) if nums else 1.0
    scale = max(0.1, min(scale, 10.0))   # clamp to sensible range

    # ── Screw / tornillo / bolt ───────────────────────────────────────────
    if _re.search(r"tornillo|screw|bolt|perno", low):
        return _screw_steps(1.0)

    # ── Electrical schematic / ladder diagram ─────────────────────────────
    if _re.search(
        r"esquema\s+electr|esquema\s+de\s+control|control\s+circuit|ladder\s+diagram"
        r"|circuito\s+electr|circuito\s+(con|de)\s+(bater|switch|lamp|motor|interruptor)"
        r"|bateria.*switch|switch.*lamp|lamp.*motor|motor.*circuit"
        r"|dibujo\s+esquem|electric(al)?\s+schem",
        low,
    ):
        return _ELEC_SCHEMATIC_STEPS

    return None


async def _execute_compound(
    steps: list[CompoundStep],
    intent: str,
) -> dict[str, Any]:
    """Execute a compound multi-step drawing and return a structured result."""
    step_results: list[dict] = []
    handles: list[str] = []
    failed: list[str] = []

    add_log("INFO",
            f"🔨 Compound '{intent}': {len(steps)} pasos programados",
            "chat")

    for i, step in enumerate(steps, start=1):
        raw_tool = step["tool"]
        params   = step.get("params", {})
        label    = step.get("label", raw_tool)

        # ── Validate / alias tool name ────────────────────────────────────
        tool_exists = raw_tool in TOOL_REGISTRY
        fallback_tool = TOOL_ALIASES.get(raw_tool) if not tool_exists else None
        resolved_tool = fallback_tool if (fallback_tool and fallback_tool in TOOL_REGISTRY) else raw_tool

        add_log("INFO",
                f"  [{i}/{len(steps)}] requested_intent={raw_tool} "
                f"tool_exists={tool_exists} "
                f"fallback_tool={fallback_tool or 'none'} "
                f"→ {resolved_tool}({json.dumps(params)}) — {label}",
                "autocad")

        if resolved_tool not in TOOL_REGISTRY:
            msg = f"SKIP: '{raw_tool}' no existe y no tiene alias"
            add_log("WARN", f"  [{i}] {msg}", "autocad")
            failed.append(label)
            step_results.append({"step": i, "tool": raw_tool, "label": label,
                                  "tool_exists": False, "success": False, "error": msg})
            continue

        # ── Execute ───────────────────────────────────────────────────────
        try:
            try:
                import pythoncom
                pythoncom.CoInitialize()
            except Exception:
                pass

            result: dict = TOOL_REGISTRY[resolved_tool]["func"](**params)
            ok = result.get("success", False)
            handle = result.get("handle")
            err = result.get("error")

            if ok and handle:
                handles.append(str(handle))
            if not ok:
                failed.append(label)

            execution_result = "OK" if ok else f"FAIL:{err}"
            add_log(
                "INFO" if ok else "WARN",
                f"  [{i}] execution_result={execution_result} handle={handle or '—'}",
                "autocad",
            )
            step_results.append({
                "step": i, "tool": resolved_tool, "label": label,
                "tool_exists": True, "success": ok,
                "handle": handle, "error": err,
            })
        except Exception as exc:
            err = str(exc)
            add_log("ERROR", f"  [{i}] exception: {err}\n{traceback.format_exc()}", "autocad")
            failed.append(label)
            step_results.append({"step": i, "tool": resolved_tool, "label": label,
                                  "tool_exists": True, "success": False, "error": err})

    ok_count = sum(1 for s in step_results if s["success"])
    total    = len(steps)

    lines = [f"Dibujo compuesto **{intent}** — {ok_count}/{total} pasos OK"]
    if handles:
        lines.append(f"Handles AutoCAD: `{', '.join(handles)}`")
    if failed:
        lines.append(f"⚠️ Fallaron: {', '.join(failed)}")
    summary = "\n".join(lines)

    add_log("INFO",
            f"🔨 Compound '{intent}' terminado: {ok_count}/{total} OK — "
            f"handles={handles}",
            "chat")
    add_history("tool", summary, {"compound": intent, "handles": handles})

    return {
        "success":    ok_count > 0,
        "action":     "compound",
        "intent":     intent,
        "text":       summary,
        "tool":       None,
        "params":     None,
        "tool_result": {"intent": intent, "handles": handles, "steps": step_results},
        "model_used": "compound",
    }


# ---------------------------------------------------------------------------
# Mode → allowed tool categories mapping
# ---------------------------------------------------------------------------
# "auto" / "electrical" → all categories (None means unrestricted)
# "2d"   → only 2-D drawing and project management
# "3d"   → 2-D + 3-D drawing and project management
_MODE_CATEGORIES: dict[str, set[str] | None] = {
    "auto":       None,
    "electrical": None,
    "3d":         {"Drawing", "Drawing3D", "Project"},
    "2d":         {"Drawing", "Project"},
}

# ---------------------------------------------------------------------------
# System prompt template
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT_TEMPLATE = """\
{header} You control AutoCAD by calling tools.

Respond with ONLY a JSON object — no markdown fences, no explanation, no preamble:

  {{"action": "tool_call", "tool": "<tool_name>", "params": {{...}}}}

When the user asks a question (not an AutoCAD action), respond with:

  {{"action": "response", "text": "<your answer>"}}

CRITICAL RULES:
- Use EXACT tool names from the list below. Do not invent tool names.
- Coordinates are floating-point numbers in AutoCAD drawing units.
- If coordinates are not given, use sensible defaults: origin (0,0) and size 100.
- Output ONLY valid JSON — nothing else, no explanation, no markdown.
{mode_examples}
Available tools ({count} total):
{tools_list}
"""

_MODE_EXAMPLES = {
    "2d": """\
EXAMPLES for 2D mode:
  "draw a line"           → {{"action":"tool_call","tool":"draw_line","params":{{"x1":0,"y1":0,"x2":100,"y2":0}}}}
  "draw a rectangle"      → {{"action":"tool_call","tool":"draw_rectangle","params":{{"x1":0,"y1":0,"x2":100,"y2":100}}}}
  "draw a circle r=50"    → {{"action":"tool_call","tool":"draw_circle","params":{{"cx":0,"cy":0,"radius":50}}}}
  "draw a square 80x80"   → {{"action":"tool_call","tool":"draw_rectangle","params":{{"x1":0,"y1":0,"x2":80,"y2":80}}}}
  "zoom extents"          → {{"action":"tool_call","tool":"zoom_extents","params":{{}}}}
""",
    "3d": """\
EXAMPLES for 3D mode:
  "draw a 3D box 100x100x100"    → {{"action":"tool_call","tool":"draw_box","params":{{"origin_x":0,"origin_y":0,"origin_z":0,"length":100,"width":100,"height":100}}}}
  "draw a cube"                  → {{"action":"tool_call","tool":"draw_box","params":{{"origin_x":0,"origin_y":0,"origin_z":0,"length":100,"width":100,"height":100}}}}
  "cuadrado 3D" / "caja 3D"     → {{"action":"tool_call","tool":"draw_box","params":{{"origin_x":0,"origin_y":0,"origin_z":0,"length":100,"width":100,"height":100}}}}
  "draw a sphere r=50"           → {{"action":"tool_call","tool":"draw_sphere","params":{{"cx":0,"cy":0,"cz":0,"radius":50}}}}
  "draw a cylinder"              → {{"action":"tool_call","tool":"draw_cylinder","params":{{"cx":0,"cy":0,"cz":0,"radius":50,"height":100}}}}
  "3D line from 0,0,0 to 100,100,100" → {{"action":"tool_call","tool":"draw_line_3d","params":{{"x1":0,"y1":0,"z1":0,"x2":100,"y2":100,"z2":100}}}}
  "isometric view"               → {{"action":"tool_call","tool":"zoom_3d_view","params":{{"view_type":"SE_ISOMETRIC"}}}}
""",
    "electrical": """\
EXAMPLES for Electrical mode:
  "insert NO contact at 50,100"  → {{"action":"tool_call","tool":"insert_electrical_symbol","params":{{"symbol_name":"WD_NOPEN","x":50,"y":100}}}}
  "insert coil at 50,80"         → {{"action":"tool_call","tool":"insert_electrical_symbol","params":{{"symbol_name":"WD_COIL","x":50,"y":80}}}}
  "draw wire from 0,100 to 50,100" → {{"action":"tool_call","tool":"draw_wire","params":{{"x1":0,"y1":100,"x2":50,"y2":100}}}}
  "generate BOM"                 → {{"action":"tool_call","tool":"generate_bom","params":{{}}}}
""",
    "auto": """\
EXAMPLES:
  "draw a line"          → {{"action":"tool_call","tool":"draw_line","params":{{"x1":0,"y1":0,"x2":100,"y2":0}}}}
  "draw a 3D box"        → {{"action":"tool_call","tool":"draw_box","params":{{"origin_x":0,"origin_y":0,"origin_z":0,"length":100,"width":100,"height":100}}}}
  "draw a rectangle"     → {{"action":"tool_call","tool":"draw_rectangle","params":{{"x1":0,"y1":0,"x2":100,"y2":100}}}}
  "isometric view"       → {{"action":"tool_call","tool":"zoom_3d_view","params":{{"view_type":"SE_ISOMETRIC"}}}}
""",
}

_MODE_HEADERS = {
    "auto":       "You are an AutoCAD AI assistant.",
    "electrical": "You are an AutoCAD Electrical 2025 assistant.",
    "2d":         "You are an AutoCAD 2D drawing assistant.",
    "3d":         "You are an AutoCAD 3D drawing assistant.",
}


def _build_system_prompt(mode: str = "auto") -> str:
    mode_key = mode.lower() if mode else "auto"
    if mode_key not in _MODE_CATEGORIES:
        mode_key = "auto"

    allowed_cats = _MODE_CATEGORIES[mode_key]
    header = _MODE_HEADERS.get(mode_key, _MODE_HEADERS["auto"])
    examples = _MODE_EXAMPLES.get(mode_key, _MODE_EXAMPLES["auto"])

    lines: list[str] = []
    current_cat = ""
    tool_count = 0
    for name, info in TOOL_REGISTRY.items():
        cat = info.get("category", "Other")
        if allowed_cats is not None and cat not in allowed_cats:
            continue
        tool_count += 1
        if cat != current_cat:
            lines.append(f"\n[{cat}]")
            current_cat = cat
        params_str = (
            ", ".join(f"{k}: {v}" for k, v in info["params"].items())
            if info["params"] else "none"
        )
        lines.append(f"  {name}({params_str})  — {info['description']}")

    return _SYSTEM_PROMPT_TEMPLATE.format(
        header=header,
        count=tool_count,
        mode_examples=examples,
        tools_list="\n".join(lines),
    )


# Build prompts for each mode at import time
_SYSTEM_PROMPTS: dict[str, str] = {
    mode: _build_system_prompt(mode)
    for mode in _MODE_CATEGORIES
}


def get_system_prompt(mode: str | None) -> str:
    """Return the system prompt for the given drawing mode."""
    key = (mode or "auto").lower()
    return _SYSTEM_PROMPTS.get(key, _SYSTEM_PROMPTS["auto"])


# ---------------------------------------------------------------------------
# Fallback model selection
# ---------------------------------------------------------------------------
# Ordered preference for fallback when the primary model fails
_FALLBACK_PREFERENCE = [
    "qwen2.5:0.5b",
    "qwen2.5:1.5b",
    "gemma3:1b",
    "llama3.2:1b",
    "tinyllama:1.1b",
    "phi3.5:3.8b",
]


def _pick_fallback_model(current_model: str, installed_names: list[str]) -> str | None:
    """Return the best fallback model from the installed list."""
    for preferred in _FALLBACK_PREFERENCE:
        if preferred in installed_names and preferred != current_model:
            return preferred
    # Any installed model that isn't the current one
    for name in installed_names:
        if name != current_model:
            return name
    return None


async def _complete_with_fallback(
    provider: Any,
    messages: list[dict],
    cfg: Any,
) -> tuple[str, str]:
    """Call provider.complete(); on failure, try a smaller installed model.

    Returns
    -------
    (raw_text, model_used)
    """
    model_used = provider.get_model_name() if hasattr(provider, "get_model_name") else "unknown"
    t0 = time.monotonic()
    try:
        raw = await provider.complete(messages)
        elapsed = time.monotonic() - t0
        logger.debug("AI response from '%s' in %.1fs (%.0f chars)", model_used, elapsed, len(raw))
        return raw, model_used
    except Exception as primary_exc:
        elapsed = time.monotonic() - t0
        exc_type = type(primary_exc).__name__
        logger.error(
            "Provider '%s' model '%s' failed after %.1fs — [%s] %s\n%s",
            getattr(provider, "name", "?"),
            model_used,
            elapsed,
            exc_type,
            primary_exc,
            traceback.format_exc(),
        )

        # ── Attempt fallback to a smaller/different installed model ──────
        fallback_model: str | None = None
        if hasattr(provider, "list_models"):
            try:
                installed = await provider.list_models()
                installed_names = [m["name"] for m in installed]
                fallback_model = _pick_fallback_model(model_used, installed_names)
            except Exception as list_exc:
                logger.warning("Could not list Ollama models for fallback: %s", list_exc)

        if fallback_model:
            from src.providers.ollama import OllamaProvider
            fb_provider = OllamaProvider(
                base_url=getattr(provider, "_base_url", "http://localhost:11434"),
                model=fallback_model,
                timeout=60,
            )
            add_log("WARN",
                    f"Primary model '{model_used}' failed [{exc_type}]. "
                    f"Retrying with fallback model '{fallback_model}'…",
                    "chat")
            try:
                t1 = time.monotonic()
                raw = await fb_provider.complete(messages)
                elapsed2 = time.monotonic() - t1
                logger.info("Fallback '%s' succeeded in %.1fs", fallback_model, elapsed2)
                add_log("INFO",
                        f"Fallback '{fallback_model}' responded in {elapsed2:.1f}s",
                        "chat")
                return raw, fallback_model
            except Exception as fb_exc:
                logger.error("Fallback model '%s' also failed: [%s] %s",
                             fallback_model, type(fb_exc).__name__, fb_exc)
                # Re-raise the original error with extra context
                raise RuntimeError(
                    f"Both primary model '{model_used}' and fallback '{fallback_model}' failed.\n"
                    f"Primary error ({exc_type}): {primary_exc}\n"
                    f"Fallback error ({type(fb_exc).__name__}): {fb_exc}"
                ) from primary_exc

        # No fallback available — re-raise with a descriptive message
        raise RuntimeError(
            f"AI provider error — model '{model_used}' failed [{exc_type}]: {primary_exc}"
        ) from primary_exc


# ---------------------------------------------------------------------------
# Keyword pre-router — reliable fast path that doesn't depend on LLM quality
# Maps common Spanish/English phrases to (tool_name, params) without AI.
# The AI is only called when no keyword rule matches.
# ---------------------------------------------------------------------------

import re as _re

def _extract_numbers(text: str) -> list[float]:
    """Extract all numbers from a string, skipping '2D'/'3D' dimension tags."""
    results = []
    for m in _re.finditer(r"-?\d+(?:\.\d+)?", text):
        # Skip numbers that are part of a dimension tag like '2D', '3D', '4D'
        end = m.end()
        if end < len(text) and text[end].upper() == 'D':
            continue
        results.append(float(m.group()))
    return results


def _keyword_route(msg: str, mode: str) -> dict | None:
    """Return a pre-routed {tool, params} dict, or None to fall through to LLM.

    Handles the most common Spanish/English drawing phrases reliably so that
    small LLMs don't need to guess tool names.
    """
    low = msg.lower()
    nums = _extract_numbers(msg)

    # ── Helpers ──────────────────────────────────────────────────────────
    def n(i: float, default: float) -> float:
        return nums[i] if len(nums) > i else default

    # ── 3D shapes ────────────────────────────────────────────────────────
    is_3d = (
        "3d" in low or "3 d" in low or "tres" in low or mode == "3d"
        or any(w in low for w in ["box","caja","cubo","cuadrado 3","cono","esfera","sphere","cylinder","cilindro"])
    )

    # Box / cube
    if any(w in low for w in ["box","caja","cubo","cube","draw_box","dado","cuboid"]) or (
        is_3d and any(w in low for w in ["cuadrado","square","rectangulo","rectangle","rect"])
    ):
        l = n(0, 100); w = n(1, l); h = n(2, l)
        return {"tool": "draw_box", "params": {
            "origin_x": 0.0, "origin_y": 0.0, "origin_z": 0.0,
            "length": l, "width": w, "height": h,
        }}

    # Sphere
    if any(w in low for w in ["sphere","esfera","spher"]):
        r = n(0, 50.0)
        return {"tool": "draw_sphere", "params": {"cx": 0.0, "cy": 0.0, "cz": 0.0, "radius": r}}

    # Cylinder
    if any(w in low for w in ["cylinder","cilindro"]):
        r = n(0, 30.0); h = n(1, 100.0)
        return {"tool": "draw_cylinder", "params": {"cx": 0.0, "cy": 0.0, "cz": 0.0, "radius": r, "height": h}}

    # Cone
    if any(w in low for w in ["cone","cono"]):
        r = n(0, 30.0); h = n(1, 100.0)
        return {"tool": "draw_cone", "params": {"cx": 0.0, "cy": 0.0, "cz": 0.0, "base_radius": r, "height": h}}

    # 3D line
    if is_3d and any(w in low for w in ["line","linea","línea"]):
        if len(nums) >= 6:
            return {"tool": "draw_line_3d", "params": {
                "x1": nums[0], "y1": nums[1], "z1": nums[2],
                "x2": nums[3], "y2": nums[4], "z2": nums[5],
            }}
        return {"tool": "draw_line_3d", "params": {
            "x1": 0.0, "y1": 0.0, "z1": 0.0, "x2": 100.0, "y2": 100.0, "z2": 100.0,
        }}

    # Isometric / 3D view
    if any(w in low for w in ["isomet","isométric","3d view","vista 3d","vista iso","se iso","top view","front view"]):
        vt = "SE_ISOMETRIC"
        if "top" in low or "superior" in low: vt = "TOP"
        elif "front" in low or "frontal" in low: vt = "FRONT"
        elif "left" in low or "izquier" in low: vt = "LEFT"
        elif "right" in low or "derech" in low: vt = "RIGHT"
        return {"tool": "zoom_3d_view", "params": {"view_type": vt}}

    # ── 2D shapes ────────────────────────────────────────────────────────

    # Zoom extents
    if any(w in low for w in ["zoom extent","zoom e","zoom all","ver todo","ajustar vista"]):
        return {"tool": "zoom_extents", "params": {}}

    # Rectangle / square (2D)
    if any(w in low for w in ["rectangle","rectangulo","rectángulo"]) or (
        not is_3d and any(w in low for w in ["cuadrado","square"]) and "3d" not in low
    ):
        x1, y1 = 0.0, 0.0
        if len(nums) >= 4:
            x1, y1, x2, y2 = nums[0], nums[1], nums[2], nums[3]
        elif len(nums) >= 2:
            x2, y2 = nums[0], nums[1]
        else:
            side = n(0, 100.0); x2, y2 = side, side
        return {"tool": "draw_rectangle", "params": {"x1": x1, "y1": y1, "x2": x2, "y2": y2}}

    # Circle
    if any(w in low for w in ["circle","círculo","circulo"]):
        r = n(0, 50.0)
        return {"tool": "draw_circle", "params": {"cx": 0.0, "cy": 0.0, "radius": r}}

    # Line (2D)
    if not is_3d and any(w in low for w in ["line","linea","línea"]):
        if len(nums) >= 4:
            return {"tool": "draw_line", "params": {
                "x1": nums[0], "y1": nums[1], "x2": nums[2], "y2": nums[3],
            }}
        size = n(0, 100.0)
        return {"tool": "draw_line", "params": {"x1": 0.0, "y1": 0.0, "x2": size, "y2": 0.0}}

    # Active drawing / status
    if any(w in low for w in ["active drawing","dibujo activo","dibujo actual","cual es el dibujo","cuál es el dibujo"]):
        return {"tool": "get_active_drawing", "params": {}}

    return None  # Fall through to LLM


# ---------------------------------------------------------------------------
# Core processing function
# ---------------------------------------------------------------------------

async def process_message(
    user_message: str,
    provider_name: str | None = None,
    mode: str | None = None,
) -> dict[str, Any]:
    """Process a natural language message and execute the appropriate AutoCAD tool.

    Parameters
    ----------
    user_message : str
        The natural language instruction from the user.
    provider_name : str | None
        Override the active provider for this request only.
    mode : str | None
        Drawing mode: "auto" | "electrical" | "2d" | "3d".
        Controls which subset of tools is exposed to the AI model.

    Returns
    -------
    dict with keys:
        success (bool), action (str), text (str), tool (str|None),
        params (dict|None), tool_result (dict|None), model_used (str|None)
    """
    cfg = get_config()

    # ── Resolve provider ─────────────────────────────────────────────────
    if provider_name and provider_name != cfg.active_provider:
        original = cfg._data.get("active_provider")
        cfg._data["active_provider"] = provider_name
        try:
            provider = get_provider(cfg)
        finally:
            cfg._data["active_provider"] = original
    else:
        provider = get_provider(cfg)

    effective_mode = (mode or "auto").lower()
    model_label = (
        provider.get_model_name() if hasattr(provider, "get_model_name") else "unknown"
    )

    add_log("INFO",
            f"Chat [{effective_mode}] via {provider.name}/{model_label}: "
            f"{user_message[:120]}",
            "chat")
    add_history("user", user_message)

    # ── Compound pre-router: multi-step drawings (tornillo, schematic…) ─────
    compound_steps = _compound_keyword_route(user_message, effective_mode)
    if compound_steps:
        # Extract a short intent label from the message
        intent_label = user_message[:60].strip()
        return await _execute_compound(compound_steps, intent_label)

    # ── Single keyword pre-router: fast path, no LLM needed ───────────────
    kw_route = _keyword_route(user_message, effective_mode)
    if kw_route:
        tool_name = kw_route["tool"]
        params = kw_route["params"]
        add_log("INFO", f"⚡ [keyword] {tool_name}({json.dumps(params)})", "autocad")
        try:
            try:
                import pythoncom
                pythoncom.CoInitialize()
            except Exception:
                pass
            func = TOOL_REGISTRY[tool_name]["func"]
            result: dict = func(**params)
        except Exception as exc:
            msg = f"Excepción al ejecutar {tool_name}: {exc}"
            add_log("ERROR", msg + "\n" + traceback.format_exc(), "autocad")
            add_history("tool_error", msg, {"tool": tool_name})
            return {"success": False, "action": "error", "text": msg,
                    "tool": tool_name, "params": params, "tool_result": None, "model_used": "keyword"}
        if result.get("success"):
            add_log("INFO", f"✓ [keyword] {tool_name} OK — handle={result.get('handle','?')}", "autocad")
            text = f"Ejecutado **{tool_name}** exitosamente (enrutamiento directo).\n```json\n{json.dumps(result, indent=2)}\n```"
        else:
            err = result.get("error", "Unknown error")
            add_log("WARN", f"✗ [keyword] {tool_name} falló: {err}", "autocad")
            text = f"⚠️ Herramienta **{tool_name}** falló: {err}"
        add_history("tool", text, {"tool": tool_name, "params": params, "result": result})
        return {"success": result.get("success", False), "action": "tool_call",
                "text": text, "tool": tool_name, "params": params,
                "tool_result": result, "model_used": "keyword"}

    system_prompt = get_system_prompt(effective_mode)
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message},
    ]

    # ── Call AI with fallback ─────────────────────────────────────────────
    model_used: str | None = None
    try:
        raw, model_used = await _complete_with_fallback(provider, messages, cfg)
    except Exception as exc:
        exc_type = type(exc).__name__
        msg = str(exc) or f"Unknown {exc_type}"
        # Friendly categorisation of common errors
        if "Cannot connect" in msg or "ConnectError" in exc_type:
            friendly = (
                "❌ No se puede conectar a Ollama. "
                "Inicia Ollama con: ollama serve"
            )
        elif "timed out" in msg.lower() or "Timeout" in exc_type:
            friendly = (
                f"⏱️ El modelo '{model_label}' tardó demasiado en responder. "
                "Puede ser que no tenga suficiente RAM, o que el modelo esté descargando. "
                "Intenta usar un modelo más pequeño como qwen2.5:0.5b."
            )
        elif "not found" in msg.lower() or "404" in msg:
            friendly = (
                f"🔍 Modelo '{model_label}' no encontrado en Ollama. "
                f"Descárgalo con: ollama pull {model_label}"
            )
        else:
            friendly = f"⚠️ Error del proveedor AI [{exc_type}]: {msg}"

        add_log("ERROR", f"AI provider failed [{exc_type}]: {msg}", "chat")
        add_history("error", friendly)
        return {
            "success": False, "action": "error", "text": friendly,
            "tool": None, "params": None, "tool_result": None,
            "model_used": model_used or model_label,
        }

    add_log("INFO", f"AI raw ({len(raw)} chars): {raw[:300]}", "chat")

    # ── Strip Qwen3 <think> blocks and clean up response ─────────────────
    cleaned = re.sub(r"<think>[\s\S]*?</think>", "", raw).strip()

    # ── Parse JSON ────────────────────────────────────────────────────────
    parsed: dict | None = None
    json_match = re.search(r"\{[\s\S]*\}", cleaned)
    if json_match:
        try:
            parsed = json.loads(json_match.group())
        except json.JSONDecodeError as jde:
            logger.warning("JSON parse error: %s — raw: %s", jde, cleaned[:200])

    if parsed is None:
        # No valid JSON — treat whole response as plain text
        add_history("assistant", cleaned or raw)
        return {
            "success": True, "action": "response",
            "text": cleaned or raw,
            "tool": None, "params": None, "tool_result": None,
            "model_used": model_used,
        }

    action = parsed.get("action", "response")

    # ── Tool call path ────────────────────────────────────────────────────
    if action == "tool_call":
        original_tool: str = parsed.get("tool", "")
        params: dict = parsed.get("params", {})

        # ── Validate + alias resolution ───────────────────────────────────
        tool_exists_raw = original_tool in TOOL_REGISTRY
        fallback_tool: str | None = None
        tool_name = original_tool

        if not tool_exists_raw:
            alias = TOOL_ALIASES.get(original_tool)
            if alias and alias in TOOL_REGISTRY:
                fallback_tool = alias
                tool_name = alias
                add_log("WARN",
                        f"requested_intent={original_tool} "
                        f"attempted_tool={original_tool} "
                        f"tool_exists=False "
                        f"fallback_tool={fallback_tool} → aliased OK",
                        "chat")
            else:
                # No alias — try compound route for this specific shape
                compound = _compound_keyword_route(original_tool, effective_mode)
                if compound:
                    add_log("INFO",
                            f"LLM requested '{original_tool}' → compound fallback",
                            "chat")
                    return await _execute_compound(compound, original_tool)

                msg = (
                    f"⚠️ La IA solicitó '{original_tool}' (tool_exists=False, "
                    f"fallback_tool=none). "
                    f"Herramientas válidas: "
                    + ", ".join(sorted(TOOL_REGISTRY.keys()))
                )
                add_log("WARN",
                        f"requested_intent={original_tool} tool_exists=False fallback_tool=none",
                        "chat")
                return {
                    "success": False, "action": "error", "text": msg,
                    "tool": original_tool, "params": params,
                    "tool_result": None, "model_used": model_used,
                }
        else:
            add_log("INFO",
                    f"requested_intent={original_tool} tool_exists=True fallback_tool=none",
                    "chat")

        add_log("INFO",
                f"⚡ Executing {tool_name}({json.dumps(params)}) "
                f"[execution_result=pending]",
                "autocad")

        try:
            try:
                import pythoncom
                pythoncom.CoInitialize()
            except Exception:
                pass

            func = TOOL_REGISTRY[tool_name]["func"]
            result: dict = func(**params)
        except Exception as exc:
            msg = f"Excepción al ejecutar {tool_name}: {exc}"
            add_log("ERROR", msg + "\n" + traceback.format_exc(), "autocad")
            add_history("tool_error", msg, {"tool": tool_name})
            return {
                "success": False, "action": "error", "text": msg,
                "tool": tool_name, "params": params, "tool_result": None,
                "model_used": model_used,
            }

        if result.get("success"):
            handle = result.get("handle", "?")
            add_log("INFO",
                    f"execution_result=OK handle={handle} tool={tool_name}",
                    "autocad")
            text = (
                f"Ejecutado **{tool_name}** exitosamente"
                + (f" (alias de `{original_tool}`)" if fallback_tool else "")
                + f".\n```json\n{json.dumps(result, indent=2)}\n```"
            )
        else:
            err = result.get("error", "Unknown error")
            add_log("WARN",
                    f"execution_result=FAIL error={err} tool={tool_name}",
                    "autocad")
            text = f"⚠️ Herramienta **{tool_name}** falló: {err}"

        add_history("tool", text, {"tool": tool_name, "params": params, "result": result})
        return {
            "success": result.get("success", False),
            "action": "tool_call",
            "text": text,
            "tool": tool_name,
            "params": params,
            "tool_result": result,
            "model_used": model_used,
        }

    # ── Plain response path ───────────────────────────────────────────────
    text = parsed.get("text", cleaned or raw)
    add_history("assistant", text)
    return {
        "success": True, "action": "response", "text": text,
        "tool": None, "params": None, "tool_result": None,
        "model_used": model_used,
    }
