"""AutoCAD COM utility helpers.

These functions sit on top of :class:`~src.autocad.connection.AutoCADConnection`
and provide convenient, reusable building blocks for the tool modules.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

try:
    import win32com.client
    import pywintypes
    _WIN32_AVAILABLE = True
except ImportError:
    _WIN32_AVAILABLE = False


# ---------------------------------------------------------------------------
# Geometry helpers
# ---------------------------------------------------------------------------

def point3d(x: float, y: float, z: float = 0.0) -> Any:
    """Create a COM-compatible 3-element array representing an AcGePoint3d.

    AutoCAD COM methods expect coordinates as an explicit VARIANT SAFEARRAY of
    doubles. Plain Python tuples do not marshal correctly with AutoCAD 2025+.

    Parameters
    ----------
    x, y, z:
        Coordinates (z defaults to 0 for 2-D drawings).

    Returns
    -------
    VARIANT or tuple[float, float, float]
        A SAFEARRAY VARIANT that AutoCAD COM can consume, falling back to a
        plain tuple if win32com is not available.
    """
    if _WIN32_AVAILABLE:
        try:
            import pythoncom
            return win32com.client.VARIANT(
                pythoncom.VT_ARRAY | pythoncom.VT_R8,
                [float(x), float(y), float(z)],
            )
        except Exception:
            pass
    return (float(x), float(y), float(z))


# ---------------------------------------------------------------------------
# Layer helpers
# ---------------------------------------------------------------------------

def layer_exists(acad_doc: Any, name: str) -> bool:
    """Return ``True`` if a layer named *name* exists in *acad_doc*.

    Parameters
    ----------
    acad_doc:
        An AutoCAD Document COM object (e.g. ``conn.get_active_document()``).
    name:
        Layer name to check (case-insensitive).
    """
    try:
        layers = acad_doc.Layers
        for i in range(layers.Count):
            if layers.Item(i).Name.upper() == name.upper():
                return True
        return False
    except Exception as exc:
        logger.warning("layer_exists check failed: %s", exc)
        return False


def ensure_layer(
    acad_doc: Any,
    name: str,
    color: int = 7,
    linetype: str = "Continuous",
) -> Any:
    """Return the layer COM object, creating it if it does not already exist.

    Parameters
    ----------
    acad_doc:
        An AutoCAD Document COM object.
    name:
        Layer name.
    color:
        AutoCAD Color Index (ACI) – default 7 is white/black.
    linetype:
        Linetype name; default ``"Continuous"``.

    Returns
    -------
    Any
        The AutoCAD Layer COM object.
    """
    try:
        if layer_exists(acad_doc, name):
            return acad_doc.Layers.Item(name)
        layer = acad_doc.Layers.Add(name)
        layer.Color = color
        # Try to load / set linetype (non-fatal if it fails)
        try:
            acad_doc.Linetypes.Load(linetype, "acad.lin")
        except Exception:
            pass
        try:
            layer.Linetype = linetype
        except Exception:
            pass
        logger.debug("Created layer '%s' (color=%d).", name, color)
        return layer
    except Exception as exc:
        logger.warning("ensure_layer failed for '%s': %s", name, exc)
        raise


# ---------------------------------------------------------------------------
# Selection set helpers
# ---------------------------------------------------------------------------

def select_by_filter(
    acad_doc: Any,
    filter_dict: dict[int, Any],
    selection_name: str = "_MCP_FILTER",
) -> Any:
    """Build and return an AutoCAD SelectionSet filtered by DXF group codes.

    Parameters
    ----------
    acad_doc:
        An AutoCAD Document COM object.
    filter_dict:
        Dictionary mapping DXF group codes (int) to their expected values.
        Example: ``{0: "INSERT", 8: "WIRES"}`` selects all INSERT entities
        on layer ``WIRES``.
    selection_name:
        Internal name for the selection set (will be deleted/re-created).

    Returns
    -------
    Any
        The AutoCAD SelectionSet COM object (iterable).
    """
    import array as _array

    try:
        # Remove an existing selection set of the same name
        try:
            existing = acad_doc.SelectionSets.Item(selection_name)
            existing.Delete()
        except Exception:
            pass

        ss = acad_doc.SelectionSets.Add(selection_name)

        if filter_dict:
            group_codes = list(filter_dict.keys())
            group_values = list(filter_dict.values())

            # COM expects VARIANT arrays – use win32com.client.VARIANT
            if _WIN32_AVAILABLE:
                import pythoncom
                filter_type = win32com.client.VARIANT(
                    pythoncom.VT_ARRAY | pythoncom.VT_I2,
                    group_codes,
                )
                filter_data = win32com.client.VARIANT(
                    pythoncom.VT_ARRAY | pythoncom.VT_VARIANT,
                    group_values,
                )
                ss.SelectOnScreen()  # fallback; real filter below
                ss.Clear()
                ss.Select(
                    5,  # acSelectionSetAll
                    None,
                    None,
                    filter_type,
                    filter_data,
                )
            else:
                # Non-Windows: return empty selection set
                pass
        else:
            ss.Select(5)  # acSelectionSetAll – no filter

        return ss
    except Exception as exc:
        logger.warning("select_by_filter failed: %s", exc)
        raise


# ---------------------------------------------------------------------------
# Attribute helpers
# ---------------------------------------------------------------------------

def get_block_attributes(block_ref: Any) -> dict[str, str]:
    """Extract attribute tag→value pairs from an AutoCAD block reference.

    Parameters
    ----------
    block_ref:
        An AutoCAD ``AcDbBlockReference`` COM object.

    Returns
    -------
    dict[str, str]
        Mapping of attribute tag (uppercase) to text value.
    """
    attrs: dict[str, str] = {}
    try:
        attribs = block_ref.GetAttributes()
        for attr in attribs:
            try:
                attrs[attr.TagString.upper()] = attr.TextString
            except Exception:
                pass
    except Exception as exc:
        logger.debug("get_block_attributes failed: %s", exc)
    return attrs


def set_block_attributes(block_ref: Any, attributes: dict[str, str]) -> int:
    """Set attribute values on an AutoCAD block reference.

    Parameters
    ----------
    block_ref:
        An AutoCAD ``AcDbBlockReference`` COM object.
    attributes:
        Dictionary of tag→value pairs (tag matching is case-insensitive).

    Returns
    -------
    int
        Number of attributes that were actually updated.
    """
    updated = 0
    try:
        attribs = block_ref.GetAttributes()
        upper_attrs = {k.upper(): v for k, v in attributes.items()}
        for attr in attribs:
            tag = attr.TagString.upper()
            if tag in upper_attrs:
                attr.TextString = str(upper_attrs[tag])
                attr.Update()
                updated += 1
    except Exception as exc:
        logger.warning("set_block_attributes failed: %s", exc)
    return updated


# ---------------------------------------------------------------------------
# Miscellaneous
# ---------------------------------------------------------------------------

def acad_object_to_dict(obj: Any) -> dict[str, Any]:
    """Attempt to serialise a COM object's common properties to a dict.

    This is a best-effort helper used for returning component info to MCP tool
    callers without exposing raw COM objects.
    """
    result: dict[str, Any] = {}
    candidate_props = [
        "Name", "Handle", "Layer", "ObjectName",
        "InsertionPoint", "Rotation", "XScaleFactor",
        "YScaleFactor", "ZScaleFactor",
    ]
    for prop in candidate_props:
        try:
            val = getattr(obj, prop)
            # Convert COM arrays / tuples to plain Python lists
            if hasattr(val, "__iter__") and not isinstance(val, str):
                val = list(val)
            result[prop] = val
        except Exception:
            pass
    return result
