"""Component management tools for AutoCAD Electrical MCP Server.

Provides MCP tools for listing, querying, updating, deleting, moving, and
searching electrical components in the current AutoCAD Electrical drawing.

Components are AutoCAD block references that carry AutoCAD Electrical
attributes such as TAG1, TAG2, DESC1, DESC2, MFG, CAT, etc.
"""

from __future__ import annotations

import logging
from typing import Any

from src.autocad.connection import get_connection, AutoCADConnectionError
from src.autocad.utils import get_block_attributes, set_block_attributes, point3d

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


def _is_electrical_component(obj: Any) -> bool:
    """Return True if *obj* looks like an AutoCAD Electrical component."""
    if obj.ObjectName != "AcDbBlockReference":
        return False
    try:
        attrs = obj.GetAttributes()
        if len(attrs) == 0:
            return False
        tags = {a.TagString.upper() for a in attrs}
        # Must have at least one of the canonical Electrical attribute tags
        return bool(tags & {"TAG1", "TAG2", "INST", "LOC", "DESC1", "MFG", "CAT"})
    except Exception:
        return False


def _component_to_dict(obj: Any) -> dict[str, Any]:
    """Serialise an AutoCAD Electrical component to a plain dict."""
    try:
        pt = obj.InsertionPoint
        return {
            "handle": obj.Handle,
            "block_name": obj.Name,
            "layer": obj.Layer,
            "insertion_point": [round(pt[0], 4), round(pt[1], 4)],
            "rotation": round(obj.Rotation, 6),
            "attributes": get_block_attributes(obj),
        }
    except Exception as exc:
        return {"handle": "?", "error": str(exc)}


# ---------------------------------------------------------------------------
# MCP Tool functions
# ---------------------------------------------------------------------------

def get_component_list(
    drawing: str | None = None,
) -> dict[str, Any]:
    """List all AutoCAD Electrical components in the current drawing.

    Parameters
    ----------
    drawing : str or None
        Unused in this implementation – operates on the active drawing.

    Returns
    -------
    dict
        ``{"success": True, "components": [...], "count": N}``
        Each component entry contains its handle, block name, layer,
        insertion point, rotation, and a dict of attribute values.
    """
    try:
        conn = _get_conn()
        doc = conn.get_active_document()
        ms = conn.get_model_space()

        components: list[dict[str, Any]] = []
        for i in range(ms.Count):
            try:
                obj = ms.Item(i)
                if _is_electrical_component(obj):
                    components.append(_component_to_dict(obj))
            except Exception:
                continue

        return {
            "success": True,
            "drawing": doc.Name,
            "components": components,
            "count": len(components),
        }
    except AutoCADConnectionError as exc:
        return {"success": False, "error": str(exc)}
    except Exception as exc:
        logger.exception("get_component_list failed")
        return {"success": False, "error": str(exc)}


def get_component_info(tag1: str) -> dict[str, Any]:
    """Return full attribute information for the component with the given TAG1.

    Parameters
    ----------
    tag1 : str
        The component's TAG1 value (case-insensitive match).

    Returns
    -------
    dict
        Component information dict, or an error dict if not found.
    """
    try:
        conn = _get_conn()
        doc = conn.get_active_document()
        ms = conn.get_model_space()

        for i in range(ms.Count):
            try:
                obj = ms.Item(i)
                if obj.ObjectName != "AcDbBlockReference":
                    continue
                attrs = get_block_attributes(obj)
                if attrs.get("TAG1", "").upper() == tag1.upper():
                    info = _component_to_dict(obj)
                    info["drawing"] = doc.Name
                    return {"success": True, "component": info}
            except Exception:
                continue

        return {
            "success": False,
            "error": f"Component with TAG1='{tag1}' not found in '{doc.Name}'.",
        }
    except AutoCADConnectionError as exc:
        return {"success": False, "error": str(exc)}
    except Exception as exc:
        logger.exception("get_component_info failed")
        return {"success": False, "error": str(exc)}


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
        Attribute tag → new value pairs to apply.

    Returns
    -------
    dict
        Success/error dict with updated attribute count.
    """
    try:
        conn = _get_conn()
        doc = conn.get_active_document()
        ms = conn.get_model_space()

        for i in range(ms.Count):
            try:
                obj = ms.Item(i)
                if obj.ObjectName != "AcDbBlockReference":
                    continue
                existing = get_block_attributes(obj)
                if existing.get("TAG1", "").upper() == tag1.upper():
                    n = set_block_attributes(obj, attributes)
                    doc.Regen(1)
                    return {
                        "success": True,
                        "tag1": tag1,
                        "attributes_updated": n,
                        "handle": obj.Handle,
                    }
            except Exception:
                continue

        return {
            "success": False,
            "error": f"Component '{tag1}' not found.",
        }
    except AutoCADConnectionError as exc:
        return {"success": False, "error": str(exc)}
    except Exception as exc:
        logger.exception("update_component failed")
        return {"success": False, "error": str(exc)}


def delete_component(tag1: str) -> dict[str, Any]:
    """Remove the component identified by TAG1 from the drawing.

    Parameters
    ----------
    tag1 : str
        TAG1 of the component to delete.

    Returns
    -------
    dict
        Success/error dict.
    """
    try:
        conn = _get_conn()
        doc = conn.get_active_document()
        ms = conn.get_model_space()

        for i in range(ms.Count):
            try:
                obj = ms.Item(i)
                if obj.ObjectName != "AcDbBlockReference":
                    continue
                attrs = get_block_attributes(obj)
                if attrs.get("TAG1", "").upper() == tag1.upper():
                    handle = obj.Handle
                    obj.Delete()
                    doc.Regen(1)
                    return {
                        "success": True,
                        "tag1": tag1,
                        "handle": handle,
                        "message": f"Component '{tag1}' deleted.",
                    }
            except Exception:
                continue

        return {
            "success": False,
            "error": f"Component '{tag1}' not found.",
        }
    except AutoCADConnectionError as exc:
        return {"success": False, "error": str(exc)}
    except Exception as exc:
        logger.exception("delete_component failed")
        return {"success": False, "error": str(exc)}


def move_component(
    tag1: str,
    new_x: float,
    new_y: float,
) -> dict[str, Any]:
    """Move the component identified by TAG1 to a new location.

    Parameters
    ----------
    tag1 : str
        TAG1 of the component to move.
    new_x, new_y : float
        New insertion point coordinates.

    Returns
    -------
    dict
        Success/error dict with old and new positions.
    """
    try:
        conn = _get_conn()
        doc = conn.get_active_document()
        ms = conn.get_model_space()

        for i in range(ms.Count):
            try:
                obj = ms.Item(i)
                if obj.ObjectName != "AcDbBlockReference":
                    continue
                attrs = get_block_attributes(obj)
                if attrs.get("TAG1", "").upper() == tag1.upper():
                    old_pt = list(obj.InsertionPoint)
                    obj.InsertionPoint = point3d(new_x, new_y)
                    obj.Update()
                    return {
                        "success": True,
                        "tag1": tag1,
                        "old_position": [round(old_pt[0], 4), round(old_pt[1], 4)],
                        "new_position": [new_x, new_y],
                        "handle": obj.Handle,
                    }
            except Exception:
                continue

        return {
            "success": False,
            "error": f"Component '{tag1}' not found.",
        }
    except AutoCADConnectionError as exc:
        return {"success": False, "error": str(exc)}
    except Exception as exc:
        logger.exception("move_component failed")
        return {"success": False, "error": str(exc)}


def search_components(
    filter_criteria: dict[str, str],
) -> dict[str, Any]:
    """Search for components matching one or more attribute criteria.

    All criteria must match (AND logic).  Matching is case-insensitive and
    supports substring matching when the criterion value ends with ``"*"``.

    Parameters
    ----------
    filter_criteria : dict[str, str]
        Attribute tag → value to match.  Examples::

            {"MFG": "ALLEN-BRADLEY"}
            {"CAT": "100-C09", "DESC1": "Motor"}
            {"TAG1": "CR*"}    # TAG1 starting with "CR"

    Returns
    -------
    dict
        ``{"success": True, "components": [...], "count": N}``
    """
    try:
        conn = _get_conn()
        doc = conn.get_active_document()
        ms = conn.get_model_space()

        def _matches(attrs: dict[str, str]) -> bool:
            for tag, pattern in filter_criteria.items():
                value = attrs.get(tag.upper(), "")
                pattern_u = pattern.upper()
                value_u = value.upper()
                if pattern_u.endswith("*"):
                    if not value_u.startswith(pattern_u[:-1]):
                        return False
                else:
                    if value_u != pattern_u:
                        return False
            return True

        # Normalise filter keys to uppercase
        filter_criteria = {k.upper(): v for k, v in filter_criteria.items()}

        results: list[dict[str, Any]] = []
        for i in range(ms.Count):
            try:
                obj = ms.Item(i)
                if obj.ObjectName != "AcDbBlockReference":
                    continue
                attrs = get_block_attributes(obj)
                if attrs and _matches(attrs):
                    results.append(_component_to_dict(obj))
            except Exception:
                continue

        return {
            "success": True,
            "filter": filter_criteria,
            "components": results,
            "count": len(results),
            "drawing": doc.Name,
        }
    except AutoCADConnectionError as exc:
        return {"success": False, "error": str(exc)}
    except Exception as exc:
        logger.exception("search_components failed")
        return {"success": False, "error": str(exc)}
