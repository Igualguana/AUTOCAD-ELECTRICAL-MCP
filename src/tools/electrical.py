"""AutoCAD Electrical-specific tools.

Provides MCP tools for electrical symbols, ladder diagrams, PLC modules,
cross-references, wire number tags, and component attributes.

AutoCAD Electrical 2025 commands are sent as AutoLISP expressions via
``SendCommand`` so that the Electrical-specific routines (WDLADDER, WDANNO,
acet-insert-block, etc.) are available without requiring the COM automation
API extensions.
"""

from __future__ import annotations

import logging
from typing import Any

from src.autocad.connection import get_connection, AutoCADConnectionError
from src.autocad.utils import point3d, ensure_layer, get_block_attributes, set_block_attributes

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


def _run_lisp(conn, expr: str) -> None:
    """Send a LISP expression to AutoCAD via SendCommand."""
    conn.send_command(f"{expr}\n")


# ---------------------------------------------------------------------------
# MCP Tool functions
# ---------------------------------------------------------------------------

def insert_electrical_symbol(
    symbol_name: str,
    x: float,
    y: float,
    rotation: float = 0.0,
    attributes: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Insert an AutoCAD Electrical symbol from the WD symbol library.

    The symbol is inserted using the Electrical-specific LISP function
    ``acet-insert-block``.  After insertion the provided *attributes* are
    applied via EATTEDIT-compatible attribute editing.

    Parameters
    ----------
    symbol_name : str
        Symbol block name as it appears in the WD symbol library
        (e.g. ``"WD_NOPEN"`` for a normally-open contact).
    x, y : float
        Insertion point coordinates.
    rotation : float
        Rotation angle in degrees (default 0).
    attributes : dict[str, str] or None
        Optional mapping of attribute tag to value
        (e.g. ``{"TAG1": "101CR", "DESC1": "Motor Contactor"}``).

    Returns
    -------
    dict
        Success/error dict with the inserted block's handle.
    """
    if attributes is None:
        attributes = {}
    try:
        conn = _get_conn()
        import math
        rot_rad = math.radians(rotation)

        # Use acet-insert-block for Electrical-aware symbol insertion
        lisp = (
            f'(acet-insert-block "{symbol_name}" '
            f'(list {x} {y} 0) '
            f'1.0 1.0 {rot_rad} '
            f'"" "")'
        )
        _run_lisp(conn, lisp)

        # Apply attributes if supplied
        if attributes:
            doc = conn.get_active_document()
            ms = conn.get_model_space()
            # Find the most-recently inserted block matching symbol_name
            target_block = None
            for i in range(ms.Count - 1, -1, -1):
                try:
                    obj = ms.Item(i)
                    if (
                        obj.ObjectName == "AcDbBlockReference"
                        and obj.Name.upper() == symbol_name.upper()
                    ):
                        target_block = obj
                        break
                except Exception:
                    continue

            if target_block is not None:
                updated = set_block_attributes(target_block, attributes)
                logger.debug(
                    "insert_electrical_symbol: set %d attribute(s) on '%s'",
                    updated,
                    symbol_name,
                )
                return {
                    "success": True,
                    "symbol": symbol_name,
                    "insertion_point": [x, y],
                    "rotation": rotation,
                    "handle": target_block.Handle,
                    "attributes_set": updated,
                }

        return {
            "success": True,
            "symbol": symbol_name,
            "insertion_point": [x, y],
            "rotation": rotation,
        }
    except AutoCADConnectionError as exc:
        return {"success": False, "error": str(exc)}
    except Exception as exc:
        logger.exception("insert_electrical_symbol failed")
        return {"success": False, "error": str(exc)}


def insert_ladder(
    x_start: float,
    y_start: float,
    rung_spacing: float = 25.4,
    rung_count: int = 10,
    voltage: str = "120V",
    phase: str = "1P",
) -> dict[str, Any]:
    """Create a ladder diagram via AutoCAD Electrical's WDLADDER command.

    The command is sent as a LISP string so it runs inside AutoCAD Electrical's
    own environment and respects the current project settings.

    Parameters
    ----------
    x_start, y_start : float
        Origin of the ladder (top-left corner of the first rung).
    rung_spacing : float
        Vertical distance between rungs in drawing units (default 25.4 mm / 1 inch).
    rung_count : int
        Number of rungs to create.
    voltage : str
        Voltage label for the ladder (e.g. ``"120V"``, ``"24VDC"``).
    phase : str
        Phase designation: ``"1P"`` (single) or ``"3P"`` (three-phase).

    Returns
    -------
    dict
        Success/error dict.
    """
    try:
        conn = _get_conn()
        # WDLADDER command syntax (AutoCAD Electrical):
        # Command: WDLADDER
        # Then prompts for: start point, rung spacing, number of rungs, etc.
        # We drive it programmatically via SendCommand with newline-separated answers.
        cmd = (
            f"WDLADDER\n"
            f"{x_start},{y_start}\n"  # insertion point
            f"{rung_spacing}\n"       # rung spacing
            f"{rung_count}\n"         # rung count
            f"{voltage}\n"            # voltage label
            f"{phase}\n"              # phase
            f"\n"                     # accept defaults / end
        )
        conn.send_command(cmd)
        return {
            "success": True,
            "start": [x_start, y_start],
            "rung_spacing": rung_spacing,
            "rung_count": rung_count,
            "voltage": voltage,
            "phase": phase,
        }
    except AutoCADConnectionError as exc:
        return {"success": False, "error": str(exc)}
    except Exception as exc:
        logger.exception("insert_ladder failed")
        return {"success": False, "error": str(exc)}


def get_symbol_list(category: str = "") -> dict[str, Any]:
    """Return a list of known AutoCAD Electrical symbol names.

    This function returns a curated catalogue of common WD symbol names.  A
    full dynamic list would require parsing the symbol library path configured
    in the project, which is file-system dependent.

    Parameters
    ----------
    category : str
        Optional filter: ``"contacts"``, ``"coils"``, ``"plc"``,
        ``"terminals"``, ``"transformers"``, or ``""`` for all.

    Returns
    -------
    dict
        ``{"success": True, "symbols": [...], "count": N}``
    """
    _SYMBOLS: dict[str, list[str]] = {
        "contacts": [
            "WD_NOPEN",    # Normally open contact
            "WD_NCLOSE",   # Normally closed contact
            "WD_NOENA",    # NO contact, push-button
            "WD_NCENA",    # NC contact, push-button
            "WD_TCON",     # Time delay contact (on-delay)
            "WD_TCOFF",    # Time delay contact (off-delay)
        ],
        "coils": [
            "WD_COIL",     # Standard coil / relay coil
            "WD_LATCH",    # Latching coil
            "WD_UNLATCH",  # Unlatching coil
            "WD_SOLENOID", # Solenoid coil
            "WD_MOTOR",    # Motor symbol
        ],
        "plc": [
            "WD_PLC_IN",   # PLC input module
            "WD_PLC_OUT",  # PLC output module
            "WD_PLC_AI",   # PLC analog input
            "WD_PLC_AO",   # PLC analog output
        ],
        "terminals": [
            "WD_TERM",     # Single terminal
            "WD_GROUND",   # Earth/ground
            "WD_CHASSIS",  # Chassis ground
            "WD_COM",      # Common terminal
        ],
        "transformers": [
            "WD_XFMR1",    # Single-phase transformer
            "WD_XFMR3",    # Three-phase transformer
            "WD_CT",        # Current transformer
            "WD_PT",        # Potential transformer
        ],
        "misc": [
            "WD_FUSE",     # Fuse
            "WD_CB",       # Circuit breaker
            "WD_DISCONNECT",# Disconnect switch
            "WD_PILOT_LT", # Pilot light
            "WD_SELECTOR", # Selector switch
            "WD_LIMIT_SW", # Limit switch
            "WD_PUSHBTN",  # Push button
            "WD_OVERLOAD", # Overload relay contact
        ],
    }

    cat_lower = category.lower()
    if cat_lower and cat_lower in _SYMBOLS:
        result = {cat_lower: _SYMBOLS[cat_lower]}
    elif cat_lower:
        # Partial match
        result = {k: v for k, v in _SYMBOLS.items() if cat_lower in k}
    else:
        result = _SYMBOLS

    all_symbols = [s for group in result.values() for s in group]
    return {
        "success": True,
        "category": category or "all",
        "symbols": all_symbols,
        "by_category": result,
        "count": len(all_symbols),
    }


def set_wire_number(
    wire_number: str,
    x: float,
    y: float,
) -> dict[str, Any]:
    """Place a wire number tag at the given coordinates.

    Uses the AutoCAD Electrical ``WDWNUM`` command to insert the tag so that
    it is properly associated with the wire it overlaps.

    Parameters
    ----------
    wire_number : str
        The wire number string (e.g. ``"101"``, ``"L1"``).
    x, y : float
        Insertion point for the wire number tag.

    Returns
    -------
    dict
        Success/error dict.
    """
    try:
        conn = _get_conn()
        # WDWNUM: Place wire number at a specific location
        cmd = f"WDWNUM\n{x},{y}\n{wire_number}\n\n"
        conn.send_command(cmd)
        return {
            "success": True,
            "wire_number": wire_number,
            "position": [x, y],
        }
    except AutoCADConnectionError as exc:
        return {"success": False, "error": str(exc)}
    except Exception as exc:
        logger.exception("set_wire_number failed")
        return {"success": False, "error": str(exc)}


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
        Module type: ``"input"``, ``"output"``, ``"analog_input"``,
        ``"analog_output"``.
    rack : int
        PLC rack number (0-based).
    slot : int
        Slot number within the rack (0-based).
    x, y : float
        Insertion point.

    Returns
    -------
    dict
        Success/error dict.
    """
    _TYPE_MAP = {
        "input": "WD_PLC_IN",
        "output": "WD_PLC_OUT",
        "analog_input": "WD_PLC_AI",
        "analog_output": "WD_PLC_AO",
    }
    symbol = _TYPE_MAP.get(module_type.lower(), "WD_PLC_IN")
    attrs = {
        "RACK": str(rack),
        "SLOT": str(slot),
        "TAG1": f"R{rack:02d}S{slot:02d}",
        "DESC1": f"PLC {module_type.replace('_', ' ').title()}",
    }
    result = insert_electrical_symbol(symbol, x, y, attributes=attrs)
    if result.get("success"):
        result.update({"module_type": module_type, "rack": rack, "slot": slot})
    return result


def create_cross_reference(
    source_tag: str,
    dest_sheet: str,
    dest_ref: str,
) -> dict[str, Any]:
    """Create a cross-reference link between a source component and a destination.

    Uses AutoCAD Electrical's ``WDXREF`` command.

    Parameters
    ----------
    source_tag : str
        TAG1 of the source component (e.g. ``"101CR"``).
    dest_sheet : str
        Destination drawing sheet number (e.g. ``"3"``).
    dest_ref : str
        Reference designation on the destination sheet (e.g. ``"B12"``).

    Returns
    -------
    dict
        Success/error dict.
    """
    try:
        conn = _get_conn()
        cmd = f"WDXREF\n{source_tag}\n{dest_sheet}\n{dest_ref}\n\n"
        conn.send_command(cmd)
        return {
            "success": True,
            "source_tag": source_tag,
            "dest_sheet": dest_sheet,
            "dest_ref": dest_ref,
        }
    except AutoCADConnectionError as exc:
        return {"success": False, "error": str(exc)}
    except Exception as exc:
        logger.exception("create_cross_reference failed")
        return {"success": False, "error": str(exc)}


def edit_component_attributes(
    tag1: str,
    attributes_dict: dict[str, str],
) -> dict[str, Any]:
    """Update attribute values on a component identified by TAG1.

    Searches ModelSpace for a block reference whose TAG1 attribute matches,
    then applies the provided attribute updates.

    Parameters
    ----------
    tag1 : str
        The component's TAG1 value (case-insensitive search).
    attributes_dict : dict[str, str]
        Attribute tag → new value mapping.

    Returns
    -------
    dict
        Success/error dict with the number of attributes updated.
    """
    try:
        conn = _get_conn()
        doc = conn.get_active_document()
        ms = conn.get_model_space()

        target = None
        for i in range(ms.Count):
            try:
                obj = ms.Item(i)
                if obj.ObjectName != "AcDbBlockReference":
                    continue
                attrs = get_block_attributes(obj)
                if attrs.get("TAG1", "").upper() == tag1.upper():
                    target = obj
                    break
            except Exception:
                continue

        if target is None:
            return {
                "success": False,
                "error": f"Component with TAG1='{tag1}' not found in current drawing.",
            }

        updated = set_block_attributes(target, attributes_dict)
        doc.Regen(1)  # acAllViewports
        return {
            "success": True,
            "tag1": tag1,
            "attributes_updated": updated,
            "handle": target.Handle,
        }
    except AutoCADConnectionError as exc:
        return {"success": False, "error": str(exc)}
    except Exception as exc:
        logger.exception("edit_component_attributes failed")
        return {"success": False, "error": str(exc)}
