"""Guilloché engraving generator for The Exchange banknote surfaces.

Deterministic spirograph math ported from the approved pitch's canvas JS
(artifact "exchange-pitch-v3"). Two primitives, both returning inline
``<svg>`` strings with no external references, no randomness, no files —
safe to drop straight into report HTML (Playwright/PDF) or the helper.

API (frozen by docs/GOAL_EXCHANGE.md — D3 imports these names):

    lattice_svg(width, height, stroke, opacity) -> str
        24-line engraving lattice, edge-tapered like real intaglio
        (amplitude envelope sin(x/W * pi) so lines flatten at the edges).

    rosette_svg(size, stroke, opacity) -> str
        (R - r)/r spirograph corner rosette (r = S*0.36, d = S*0.62,
        t over 18*pi), scaled to fit a size x size viewBox.

Doctrine (DESIGN.md): guilloché is print texture, keep opacity low
(the pitch ships the lattice at ~0.11 and rosettes at ~0.20) so data
always wins. Stroke color should be the engraving ink token value.
"""
from __future__ import annotations

import math

_STROKE_WIDTH = 0.5
_LATTICE_LINES = 24
_LATTICE_STEP = 2  # px between sampled points, as in the pitch canvas


def _fmt(v: float) -> str:
    """Fixed 2-decimal coordinate formatting => byte-stable output."""
    return f"{v:.2f}"


def _path(points: list[tuple[float, float]]) -> str:
    d = f"M{_fmt(points[0][0])} {_fmt(points[0][1])}"
    d += "".join(f"L{_fmt(x)} {_fmt(y)}" for x, y in points[1:])
    return d


def lattice_svg(width: int, height: int, stroke: str, opacity: float) -> str:
    """Edge-tapered 24-line engraving lattice as an inline <svg> string."""
    w, h = float(width), float(height)
    paths = []
    for k in range(_LATTICE_LINES):
        pts = []
        x = 0.0
        while x <= w:
            env = math.sin(x / w * math.pi)  # taper at the edges
            y = (h / 2.0
                 + (k - 11.5) * (h / 26.0)
                 + math.sin(x / 24.0 + k * 1.9) * 6.0 * env
                 + math.sin(x / 61.0 - k) * 3.0 * env)
            pts.append((x, y))
            x += _LATTICE_STEP
        paths.append(f'<path d="{_path(pts)}"/>')
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" '
        f'height="{height}" viewBox="0 0 {width} {height}" '
        f'aria-hidden="true" role="presentation">'
        f'<g fill="none" stroke="{stroke}" stroke-opacity="{opacity:g}" '
        f'stroke-width="{_STROKE_WIDTH}">'
        + "".join(paths)
        + "</g></svg>"
    )


def rosette_svg(size: int, stroke: str, opacity: float) -> str:
    """Spirograph rosette fitted to a size x size viewBox, inline <svg>."""
    c = size / 2.0
    # Curve extent from center is (R - r) + d = S*(0.64 + 0.62) = 1.26*S;
    # leave a hair of margin so the stroke never clips.
    big_s = (size / 2.0 - _STROKE_WIDTH) / 1.26
    big_r, small_r, d = big_s, big_s * 0.36, big_s * 0.62
    ratio = (big_r - small_r) / small_r
    pts = []
    steps = int(math.pi * 18.01 / 0.02) + 1
    for i in range(steps):
        t = i * 0.02
        x = c + (big_r - small_r) * math.cos(t) + d * math.cos(ratio * t)
        y = c + (big_r - small_r) * math.sin(t) - d * math.sin(ratio * t)
        pts.append((x, y))
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{size}" '
        f'height="{size}" viewBox="0 0 {size} {size}" '
        f'aria-hidden="true" role="presentation">'
        f'<path d="{_path(pts)}" fill="none" stroke="{stroke}" '
        f'stroke-opacity="{opacity:g}" stroke-width="{_STROKE_WIDTH}"/>'
        "</svg>"
    )


# ---- STRAIT sub-theme engravings (toll ticket only, Nov 2026) ----

def wave_svg(width: int, height: int, stroke: str, opacity: float) -> str:
    """Sea-chart swell lines: 14 edge-tapered sine bands, inline <svg>."""
    w, h = float(width), float(height)
    n = 14
    paths = []
    for k in range(n):
        pts = []
        x = 0.0
        while x <= w:
            env = math.sin(x / w * math.pi)
            y = (h * (k + 0.5) / n
                 + math.sin(x / 38.0 + k * 0.7) * 4.0 * env
                 + math.sin(x / 9.0 + k) * 0.8 * env)
            pts.append((x, y))
            x += _LATTICE_STEP * 2
        paths.append(f'<path d="{_path(pts)}"/>')
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" '
        f'height="{height}" viewBox="0 0 {width} {height}" '
        f'aria-hidden="true" role="presentation">'
        f'<g fill="none" stroke="{stroke}" stroke-opacity="{opacity:g}" '
        f'stroke-width="{_STROKE_WIDTH}">'
        + "".join(paths)
        + "</g></svg>"
    )


def compass_svg(size: int, stroke: str, opacity: float) -> str:
    """Engraved compass rose: two rings, 32 rhumb lines, 8-point star."""
    c = size / 2.0
    r_out = c - _STROKE_WIDTH
    r_in = r_out * 0.82
    parts = [
        f'<circle cx="{_fmt(c)}" cy="{_fmt(c)}" r="{_fmt(r_out)}"/>',
        f'<circle cx="{_fmt(c)}" cy="{_fmt(c)}" r="{_fmt(r_in)}"/>',
    ]
    for i in range(32):
        a = i * math.pi / 16
        parts.append('<path d="' + _path([
            (c, c), (c + r_in * math.cos(a), c + r_in * math.sin(a))]) + '"/>')
    star = []
    for i in range(16):
        a = i * math.pi / 8 - math.pi / 2
        rr = r_in if i % 4 == 0 else (r_in * 0.55 if i % 2 == 0 else r_in * 0.18)
        star.append((c + rr * math.cos(a), c + rr * math.sin(a)))
    star.append(star[0])
    parts.append(f'<path d="{_path(star)}" stroke-width="{_STROKE_WIDTH * 2:g}"/>')
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{size}" '
        f'height="{size}" viewBox="0 0 {size} {size}" '
        f'aria-hidden="true" role="presentation">'
        f'<g fill="none" stroke="{stroke}" stroke-opacity="{opacity:g}" '
        f'stroke-width="{_STROKE_WIDTH}">' + "".join(parts) + "</g></svg>"
    )


if __name__ == "__main__":
    import tempfile
    from pathlib import Path

    lat = lattice_svg(400, 80, "#000", 0.12)
    ros = rosette_svg(34, "#000", 0.2)

    assert lat.startswith("<svg") and lat.endswith("</svg>"), "lattice: not svg"
    assert ros.startswith("<svg") and ros.endswith("</svg>"), "rosette: not svg"
    assert "nan" not in lat.lower() and "nan" not in ros.lower(), "NaN coords"
    assert lat.count("<path") == _LATTICE_LINES, "lattice: expected 24 lines"
    assert lat == lattice_svg(400, 80, "#000", 0.12), "lattice: nondeterministic"
    assert ros == rosette_svg(34, "#000", 0.2), "rosette: nondeterministic"
    # every rosette coordinate stays inside the viewBox
    import re
    coords = [float(v) for v in re.findall(r"[ML]?(-?\d+\.\d+)", ros)]
    assert all(-0.01 <= v <= 34.01 for v in coords), "rosette: clipped"

    out = Path(tempfile.gettempdir()) / "guilloche_sample.svg"
    out.write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" width="400" height="140">'
        "<g>" + lat + "</g>"
        '<g transform="translate(10,90)">' + ros + "</g></svg>")
    print(f"guilloche smoke test OK — lattice {len(lat):,} B, "
          f"rosette {len(ros):,} B, sample written to {out}")
