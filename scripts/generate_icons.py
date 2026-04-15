#!/usr/bin/env python3
"""Generate PWA icons for AutoCAD Electrical MCP — no external dependencies.

Creates:
  web/frontend/icons/icon-192.png         (192×192, standard)
  web/frontend/icons/icon-512.png         (512×512, standard)
  web/frontend/icons/icon-512-maskable.png (512×512, maskable — safe zone)
  web/frontend/icons/favicon.png          ( 32×32,  tab favicon)

Run from the project root:
    python scripts/generate_icons.py
"""

from __future__ import annotations

import math
import os
import struct
import zlib
from pathlib import Path

# ---------------------------------------------------------------------------
# Brand colours (matches CSS variables in style.css)
# ---------------------------------------------------------------------------
BG_BASE   = ( 8,  12,  20)   # --bg-base      #080c14
ACCENT    = (88, 166, 255)   # --accent        #58a6ff
ACCENT_D  = (31,  66, 128)   # --accent-dim    #1f4280
ORANGE    = (240, 136,  62)  # --cat-electrical #f0883e
WHITE     = (230, 237, 243)  # --text-primary   #e6edf3

# ---------------------------------------------------------------------------
# Minimal PNG encoder (pure stdlib — no Pillow needed)
# ---------------------------------------------------------------------------

def _chunk(tag: bytes, data: bytes) -> bytes:
    crc = zlib.crc32(tag + data) & 0xFFFF_FFFF
    return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", crc)


def encode_png(pixels: list[list[tuple]], w: int, h: int) -> bytes:
    raw = bytearray()
    for row in pixels:
        raw += b"\x00"
        for r, g, b in row:
            raw += bytes([r & 0xFF, g & 0xFF, b & 0xFF])
    sig   = b"\x89PNG\r\n\x1a\n"
    ihdr  = _chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
    idat  = _chunk(b"IDAT", zlib.compress(bytes(raw), 9))
    iend  = _chunk(b"IEND", b"")
    return sig + ihdr + idat + iend


# ---------------------------------------------------------------------------
# Drawing primitives
# ---------------------------------------------------------------------------

def _canvas(size: int, bg: tuple = BG_BASE) -> list[list[tuple]]:
    return [[bg] * size for _ in range(size)]


def _clamp(v: float) -> int:
    return max(0, min(255, int(v)))


def _blend(bg: tuple, fg: tuple, a: float) -> tuple:
    return (_clamp(bg[0] + (fg[0] - bg[0]) * a),
            _clamp(bg[1] + (fg[1] - bg[1]) * a),
            _clamp(bg[2] + (fg[2] - bg[2]) * a))


def _put(px, x: int, y: int, col: tuple, a: float = 1.0):
    if 0 <= x < len(px[0]) and 0 <= y < len(px):
        px[y][x] = _blend(px[y][x], col, min(1.0, max(0.0, a)))


def _circle(px, cx: float, cy: float, r: float, col: tuple, thick: float):
    """Anti-aliased circle outline."""
    for y in range(max(0, int(cy - r - 2)), min(len(px), int(cy + r + 3))):
        for x in range(max(0, int(cx - r - 2)), min(len(px[0]), int(cx + r + 3))):
            d = math.dist((x, y), (cx, cy))
            dd = abs(d - r)
            if dd < thick + 1.0:
                _put(px, x, y, col, 1.0 - max(0.0, dd - thick))


def _line(px, x0: float, y0: float, x1: float, y1: float, col: tuple, thick: float):
    """Anti-aliased thick line (Xiaolin Wu style via distance)."""
    dx, dy = x1 - x0, y1 - y0
    length = math.hypot(dx, dy)
    if length < 0.5:
        return
    steps = int(length) + 1
    for i in range(steps + 1):
        t  = i / steps
        sx = x0 + t * dx
        sy = y0 + t * dy
        pad = int(thick) + 2
        for y in range(max(0, int(sy) - pad), min(len(px), int(sy) + pad + 1)):
            for x in range(max(0, int(sx) - pad), min(len(px[0]), int(sx) + pad + 1)):
                d = math.dist((x, y), (sx, sy))
                if d < thick + 1.0:
                    _put(px, x, y, col, 1.0 - max(0.0, d - thick))


def _fill_poly(px, pts: list[tuple], col: tuple, alpha: float = 1.0):
    """Scanline fill for a convex/concave polygon."""
    if not pts:
        return
    min_y = int(min(p[1] for p in pts))
    max_y = int(max(p[1] for p in pts)) + 1
    n = len(pts)
    for sy in range(min_y, max_y):
        xs: list[float] = []
        for i in range(n):
            ax, ay = pts[i]
            bx, by = pts[(i + 1) % n]
            if (ay <= sy < by) or (by <= sy < ay):
                xs.append(ax + (sy - ay) * (bx - ax) / (by - ay))
        xs.sort()
        for j in range(0, len(xs) - 1, 2):
            for x in range(int(xs[j]), int(xs[j + 1]) + 1):
                _put(px, x, sy, col, alpha)


# ---------------------------------------------------------------------------
# Icon renderer
# ---------------------------------------------------------------------------
# Lightning bolt shape (normalised — fits in ±1 × ±1 box)
_BOLT = [
    ( 0.28, -1.00),
    ( 1.00, -0.10),
    ( 0.05,  0.10),
    ( 0.72,  1.00),
    (-0.28,  0.10),
    (-0.05, -0.10),
]


def _render_graphic(px, cx: float, cy: float, R: float):
    """Draw the icon graphic centred at (cx,cy) within a half-radius of R."""

    # ── Outer ring ────────────────────────────────────────────────────────
    _circle(px, cx, cy, R * 0.82, ACCENT_D, max(2.0, R * 0.046))

    # ── Crosshair ─────────────────────────────────────────────────────────
    gap   = R * 0.17
    reach = R * 0.80
    lt    = max(2.0, R * 0.032)
    _line(px, cx - reach, cy, cx - gap, cy, ACCENT, lt)
    _line(px, cx + gap,   cy, cx + reach, cy, ACCENT, lt)
    _line(px, cx, cy - reach, cx, cy - gap, ACCENT, lt)
    _line(px, cx, cy + gap,   cx, cy + reach, ACCENT, lt)

    # ── Tick marks at N/S/E/W ─────────────────────────────────────────────
    for deg in (0, 90, 180, 270):
        a  = math.radians(deg)
        r1 = R * 0.56
        r2 = R * 0.70
        _line(px,
              cx + r1 * math.cos(a), cy + r1 * math.sin(a),
              cx + r2 * math.cos(a), cy + r2 * math.sin(a),
              ACCENT, max(2.0, R * 0.026))

    # ── Diagonal connector lines to nodes ─────────────────────────────────
    for deg in (45, 135, 225, 315):
        a  = math.radians(deg)
        r1 = R * 0.21
        r2 = R * 0.53
        _line(px,
              cx + r1 * math.cos(a), cy + r1 * math.sin(a),
              cx + r2 * math.cos(a), cy + r2 * math.sin(a),
              ACCENT_D, max(1.5, R * 0.018))

    # ── Circuit nodes at 45° diagonals ────────────────────────────────────
    nr = max(2.5, R * 0.062)
    for deg in (45, 135, 225, 315):
        a  = math.radians(deg)
        nx = cx + R * 0.56 * math.cos(a)
        ny = cy + R * 0.56 * math.sin(a)
        _circle(px, nx, ny, nr, ACCENT, max(1.5, nr * 0.55))

    # ── Lightning bolt (centre) ────────────────────────────────────────────
    bs   = R * 0.25
    bpts = [(cx + bx * bs, cy + by * bs) for bx, by in _BOLT]
    _fill_poly(px, bpts, ORANGE, 0.96)
    for i in range(len(bpts)):
        ax, ay = bpts[i]
        bx, by = bpts[(i + 1) % len(bpts)]
        _line(px, ax, ay, bx, by, ORANGE, max(1.5, R * 0.030))


def render_icon(size: int) -> list[list[tuple]]:
    """Standard icon (no safe-zone padding)."""
    px = _canvas(size)
    _render_graphic(px, size / 2, size / 2, size / 2)
    return px


def render_maskable(size: int) -> list[list[tuple]]:
    """Maskable icon — graphic scaled to 72 % so it fits the safe zone."""
    px = _canvas(size)
    inner = size * 0.72
    _render_graphic(px, size / 2, size / 2, inner / 2)
    return px


def render_favicon(size: int = 32) -> list[list[tuple]]:
    """Simplified favicon: bolt + accent ring (readable at small sizes)."""
    px = _canvas(size)
    cx = cy = size / 2
    R  = size / 2

    # Accent ring
    _circle(px, cx, cy, R * 0.85, ACCENT, max(1.0, R * 0.12))

    # Lightning bolt (larger, fills the icon)
    bs   = R * 0.58
    bpts = [(cx + bx * bs, cy + by * bs) for bx, by in _BOLT]
    _fill_poly(px, bpts, ORANGE, 1.0)
    for i in range(len(bpts)):
        ax, ay = bpts[i]
        bx, by = bpts[(i + 1) % len(bpts)]
        _line(px, ax, ay, bx, by, ORANGE, max(1.0, R * 0.10))

    return px


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    project_root = Path(__file__).resolve().parent.parent
    out_dir = project_root / "web" / "frontend" / "icons"
    out_dir.mkdir(parents=True, exist_ok=True)

    tasks = [
        ("icon-192.png",          lambda: render_icon(192)),
        ("icon-512.png",          lambda: render_icon(512)),
        ("icon-512-maskable.png", lambda: render_maskable(512)),
        ("favicon.png",           lambda: render_favicon(32)),
    ]

    for filename, render_fn in tasks:
        path = out_dir / filename
        size_hint = filename.split("-")[1].split(".")[0] if "-" in filename else "32"
        print(f"  Generating {filename} …", end=" ", flush=True)
        pixels = render_fn()
        h = len(pixels)
        w = len(pixels[0])
        png_bytes = encode_png(pixels, w, h)
        path.write_bytes(png_bytes)
        print(f"saved ({w}×{h}, {len(png_bytes):,} bytes)")

    print(f"\nIcons written to: {out_dir}")


if __name__ == "__main__":
    main()
