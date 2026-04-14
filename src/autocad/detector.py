"""AutoCAD installation detector.

Determines which AutoCAD variant is installed and running, enabling the server
to conditionally activate/deactivate tools.

Supported variants:
  - ``"electrical"``  — AutoCAD Electrical (all 34+ tools including wires,
                        ladders, symbols, cross-refs, PLCs, BOM, etc.)
  - ``"standard"``    — AutoCAD standard (drawing + project + 2D/3D geometry)
  - ``"unknown"``     — could not determine (fallback to standard tools)
  - ``"none"``        — AutoCAD not found / not running

Detection order (Windows, most-reliable first):
  1. Registry product ID under HKLM\\SOFTWARE\\Autodesk\\AutoCAD\\R*
  2. Running process window title (contains "Electrical")
  3. File-system: ACAOE folder and AcEw.dll presence
  4. COM property query (app.Name / Description)

macOS note:
  AutoCAD is not available natively on macOS. This module always returns
  ``("none", [])`` on non-Windows platforms so the rest of the code can
  import it safely. A future macOS variant (e.g. AutoCAD web / LT) may add
  its own detection branch here.
"""

from __future__ import annotations

import logging
import os
import sys
from dataclasses import dataclass, field
from functools import lru_cache
from typing import List, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# AutoCAD Registry product-ID → variant
# Source: Autodesk Registry Guide / ARX SDK
_ELECTRICAL_PRODUCT_IDS = {"8107", "8108", "8109"}  # Electrical 2025/2024/2023
_STANDARD_PRODUCT_IDS = {"8101", "8102", "8103", "ACAD"}

# Known install paths per major release (R prefix = internal version)
_AUTOCAD_REGISTRY_ROOTS = [
    r"SOFTWARE\Autodesk\AutoCAD\R25.0",  # 2025
    r"SOFTWARE\Autodesk\AutoCAD\R24.0",  # 2024 (24.3)
    r"SOFTWARE\Autodesk\AutoCAD\R23.0",  # 2023
    r"SOFTWARE\Autodesk\AutoCAD\R22.0",  # 2022
]

_STANDARD_INSTALL_PATHS = [
    r"C:\Program Files\Autodesk\AutoCAD 2025",
    r"C:\Program Files\Autodesk\AutoCAD 2024",
    r"C:\Program Files\Autodesk\AutoCAD 2023",
]
_ELECTRICAL_INSTALL_PATHS = [
    r"C:\Program Files\Autodesk\AutoCAD Electrical 2025",
    r"C:\Program Files\Autodesk\AutoCAD Electrical 2024",
    r"C:\Program Files\Autodesk\AutoCAD Electrical 2023",
]


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------

@dataclass
class AutoCADInfo:
    """Describes the detected AutoCAD installation."""

    variant: str = "none"
    """One of ``"electrical"``, ``"standard"``, ``"unknown"``, ``"none"``."""

    version: str = ""
    """Human-readable version string, e.g. ``"AutoCAD 2025 (25.0)"``."""

    install_path: str = ""
    """Absolute path to the AutoCAD install directory."""

    product_id: str = ""
    """Registry product ID, e.g. ``"8107"`` for Electrical."""

    running: bool = False
    """``True`` if AutoCAD is currently running (process detected)."""

    features: List[str] = field(default_factory=list)
    """List of enabled feature groups for this variant."""

    detection_method: str = ""
    """How the variant was determined (registry / process / filesystem / com)."""

    platform: str = sys.platform
    """``"win32"`` on Windows, ``"darwin"`` on macOS, etc."""

    @property
    def is_electrical(self) -> bool:
        return self.variant == "electrical"

    @property
    def is_standard(self) -> bool:
        return self.variant in ("standard", "electrical")  # Electrical ⊇ Standard

    @property
    def available(self) -> bool:
        return self.variant not in ("none",)

    def to_dict(self) -> dict:
        return {
            "variant": self.variant,
            "version": self.version,
            "install_path": self.install_path,
            "product_id": self.product_id,
            "running": self.running,
            "features": self.features,
            "detection_method": self.detection_method,
            "platform": self.platform,
            "is_electrical": self.is_electrical,
        }


# ---------------------------------------------------------------------------
# Feature map
# ---------------------------------------------------------------------------

_FEATURES_STANDARD = [
    "drawing_2d",    # lines, circles, arcs, text, rectangles, polylines
    "drawing_3d",    # 3D lines, polylines, faces, meshes, solids (if license)
    "layers",        # layer creation and management
    "zoom_pan",      # zoom extents, pan, views
    "model_space",   # model-space entity access
    "project_info",  # drawing name, path, entity count
]

_FEATURES_ELECTRICAL = _FEATURES_STANDARD + [
    "electrical_symbols",   # WDINSYM - insert symbols
    "ladder_diagrams",      # WDLADDER
    "wire_numbering",       # WDAUTO
    "cross_references",     # WDXREF
    "plc_modules",          # WDPLC
    "component_database",   # WD data
    "bom_reports",          # BOM / BOC
    "wire_list_reports",
    "terminal_plans",
    "plc_io_reports",
]


# ---------------------------------------------------------------------------
# Core detection
# ---------------------------------------------------------------------------

def detect(force: bool = False) -> AutoCADInfo:
    """Detect the installed and/or running AutoCAD variant.

    Results are cached after the first call. Pass ``force=True`` to re-run.

    Returns
    -------
    AutoCADInfo
        Detection result with variant, version, features, and running state.
    """
    if not force:
        return _cached_detect()
    _cached_detect.cache_clear()
    return _cached_detect()


@lru_cache(maxsize=1)
def _cached_detect() -> AutoCADInfo:
    """Internal cached implementation of :func:`detect`."""
    if sys.platform != "win32":
        logger.info(
            "Platform is '%s' — AutoCAD COM not available. "
            "Returning placeholder for future macOS support.",
            sys.platform,
        )
        return AutoCADInfo(
            variant="none",
            version="",
            platform=sys.platform,
            features=[],
            detection_method="platform_check",
        )

    info = AutoCADInfo(platform="win32")

    # ── Step 1: Registry ────────────────────────────────────────────────────
    try:
        _detect_via_registry(info)
    except Exception as exc:
        logger.debug("Registry detection failed: %s", exc)

    # ── Step 2: Running process ─────────────────────────────────────────────
    _detect_running_process(info)

    # ── Step 3: File system ─────────────────────────────────────────────────
    if info.variant == "none":
        _detect_via_filesystem(info)

    # ── Step 4: COM query (only if process is running) ──────────────────────
    if info.running and info.variant in ("none", "unknown"):
        try:
            _detect_via_com(info)
        except Exception as exc:
            logger.debug("COM detection failed: %s", exc)

    # ── Assign features ─────────────────────────────────────────────────────
    if info.variant == "electrical":
        info.features = _FEATURES_ELECTRICAL.copy()
    elif info.variant in ("standard", "unknown"):
        info.features = _FEATURES_STANDARD.copy()
    else:
        info.features = []

    logger.info(
        "AutoCAD detected: variant=%s version=%r running=%s method=%s",
        info.variant, info.version, info.running, info.detection_method,
    )
    return info


def _detect_via_registry(info: AutoCADInfo) -> None:
    """Populate *info* from the Windows registry."""
    import winreg

    for root_path in _AUTOCAD_REGISTRY_ROOTS:
        try:
            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, root_path)
        except FileNotFoundError:
            continue

        # Enumerate sub-keys like ACAD-8107:409
        idx = 0
        while True:
            try:
                subkey_name = winreg.EnumKey(key, idx)
                idx += 1
            except OSError:
                break

            try:
                subkey = winreg.OpenKey(key, subkey_name)
                prod_id = _reg_value(subkey, "ProductID")
                if prod_id:
                    info.product_id = prod_id
                    # Determine variant from product ID
                    if prod_id in _ELECTRICAL_PRODUCT_IDS:
                        info.variant = "electrical"
                        info.detection_method = "registry"
                    elif prod_id in _STANDARD_PRODUCT_IDS:
                        if info.variant != "electrical":
                            info.variant = "standard"
                            info.detection_method = "registry"

                    install = _reg_value(subkey, "InstallDir") or _reg_value(subkey, "Location")
                    if install and not info.install_path:
                        info.install_path = install.rstrip("\\")

                    ver = _reg_value(subkey, "ProductVersion") or _reg_value(subkey, "Release")
                    if ver and not info.version:
                        info.version = f"AutoCAD {ver}"
                winreg.CloseKey(subkey)
            except Exception:
                pass

        winreg.CloseKey(key)

        if info.variant in ("electrical", "standard"):
            break


def _detect_running_process(info: AutoCADInfo) -> None:
    """Check for running AutoCAD process via WMI or tasklist."""
    try:
        import subprocess
        result = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq acad.exe", "/FO", "CSV"],
            capture_output=True, text=True, timeout=5,
        )
        if "acad.exe" in result.stdout:
            info.running = True
    except Exception:
        pass

    if not info.running:
        return

    # Try to read window title for "Electrical"
    try:
        import subprocess
        result = subprocess.run(
            [
                "powershell", "-NoProfile", "-Command",
                "(Get-Process acad | Where-Object {$_.MainWindowTitle} | "
                "Select-Object -First 1 -ExpandProperty MainWindowTitle)"
            ],
            capture_output=True, text=True, timeout=5,
        )
        title = result.stdout.strip()
        if title:
            info.version = title.split(" - ")[0].strip() if " - " in title else title
            if "electrical" in title.lower():
                if info.variant == "none":
                    info.variant = "electrical"
                    info.detection_method = "process_title"
            elif "autocad" in title.lower():
                if info.variant == "none":
                    info.variant = "standard"
                    info.detection_method = "process_title"
    except Exception as exc:
        logger.debug("Process title check failed: %s", exc)


def _detect_via_filesystem(info: AutoCADInfo) -> None:
    """Fall back to checking install directories."""
    for path in _ELECTRICAL_INSTALL_PATHS:
        if os.path.isdir(path):
            info.variant = "electrical"
            info.install_path = path
            info.detection_method = "filesystem"
            return

    for path in _STANDARD_INSTALL_PATHS:
        if os.path.isdir(path):
            # Standard path might still have ACAOE (Electrical installed there)
            acaoe = os.path.join(path, "ACAOE")
            acew = os.path.join(path, "AcEw.dll")
            if os.path.isdir(acaoe) or os.path.isfile(acew):
                info.variant = "electrical"
            else:
                info.variant = "standard"
            info.install_path = path
            info.detection_method = "filesystem"
            return


def _detect_via_com(info: AutoCADInfo) -> None:
    """Query the live AutoCAD COM object for product info."""
    try:
        import win32com.client
        app = win32com.client.GetActiveObject("AutoCAD.Application")
        name = str(app.Name)
        ver = str(app.Version)
        if not info.version:
            info.version = f"{name} {ver}"
        desc = getattr(app, "Description", "") or ""
        if "electrical" in (name + desc).lower():
            info.variant = "electrical"
        else:
            info.variant = "standard"
        info.detection_method = "com"
    except Exception as exc:
        logger.debug("COM variant query failed: %s", exc)


def _reg_value(key, name: str) -> Optional[str]:
    """Read a string value from an open registry key; return None on failure."""
    try:
        import winreg
        val, _ = winreg.QueryValueEx(key, name)
        return str(val)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Convenience helpers
# ---------------------------------------------------------------------------

def get_variant() -> str:
    """Return the variant string: ``"electrical"``, ``"standard"``, ``"unknown"``, ``"none"``."""
    return detect().variant


def has_feature(feature: str) -> bool:
    """Return True if the detected AutoCAD installation supports *feature*."""
    return feature in detect().features


def is_electrical() -> bool:
    """Return True if AutoCAD Electrical is detected."""
    return detect().is_electrical


def is_standard_or_better() -> bool:
    """Return True if at least AutoCAD standard is detected."""
    return detect().is_standard
