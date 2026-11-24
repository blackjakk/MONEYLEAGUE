"""GENERATED from design/tokens.json — DO NOT EDIT BY HAND.
Regenerate with:  python3 design/build_design.py

Single import point for every Python UI surface:
    from design.tokens import POS_COLORS, MANAGER_COLORS, PALETTE
    from design.tokens import report_base_css, mpl_style
"""
from __future__ import annotations

POS_COLORS = {
    "QB": "#dc2626",
    "RB": "#0e7490",
    "WR": "#15803d",
    "TE": "#f59e0b",
    "K": "#9a3412",
    "DEF": "#6b6b6b"
}
POS_COLORS["DST"] = POS_COLORS["DEF"]

MANAGER_COLORS = {
    "trevor_bergerboy": "#2d6a4f",
    "coop": "#1f3a5f",
    "dave_aka_wang": "#8b1e3f",
    "kyle_figgy": "#f59e0b",
    "brower_barry": "#0891b2",
    "ankur_patel": "#7c3aed",
    "eric_m": "#dc2626",
    "troy_mullings": "#15803d",
    "brian_bigguap": "#1e40af",
    "lem": "#65a30d",
    "donnie": "#9a3412",
    "tim_breswick": "#0f172a",
    "josh_wildboy": "#a855f7",
    "nark": "#78716c",
    "jp_former": "#525252",
    "nick_lewis_left": "#737373",
    "notebooks_left": "#a3a3a3"
}

PALETTE = {
    "gold": "#d4a017",
    "navy": "#0a3d62",
    "teal": "#1f7a8c",
    "emerald": "#2d6a4f",
    "orange": "#dd6e42",
    "crimson": "#a23737",
    "slate": "#3d405b",
    "cream": "#f7f4ea",
    "ink": "#1f3d2b",
    "gray": "#6b7280"
}

SEMANTIC_LIGHT = {
    "success": "#147339",
    "warn": "#a54c06",
    "danger": "#c81e1e",
    "info": "#0369a1",
    "keeper": "#0369a1",
    "focus": "#0369a1",
    "gold": "#7d6010"
}
SEMANTIC_DARK = {
    "success": "#4ade80",
    "warn": "#f59e0b",
    "danger": "#f87171",
    "info": "#60a5fa",
    "keeper": "#60a5fa",
    "focus": "#7dd3fc",
    "gold": "#e8c76a"
}

# The Exchange gold chip (closing bell / blue chip): dark-on-gold polarity,
# measured safe in BOTH themes — see docs/DESIGN_SYSTEM.md.
GOLD_CHIP = {
    "bg": "#d4a017",
    "text": "#14130a"
}

SURFACE_LIGHT = {
    "bg": "#f7f4ea",
    "panel": "#f7f4ea",
    "panel2": "#ece6d3",
    "border": "#d9d2ba",
    "border_strong": "#6e755f",
    "row": "#f1ecdd",
    "text": "#1f3d2b",
    "muted": "#52604f"
}
SURFACE_DARK = {
    "bg": "#0c1710",
    "panel": "#12211a",
    "panel2": "#1a2f24",
    "border": "#24382c",
    "border_strong": "#6b8672",
    "row": "#16281e",
    "text": "#dfe7df",
    "muted": "#8fae97"
}

# STRAIT sub-theme (toll ticket only): surfaces + the sea-lane route ink.
SURFACE_STRAIT = {
    "bg": "#f2ecdc",
    "panel": "#f2ecdc",
    "panel2": "#e3dbc3",
    "border": "#cdc3a5",
    "border_strong": "#5f7480",
    "row": "#ebe4cf",
    "text": "#0f2f45",
    "muted": "#455a66"
}
STRAIT = {
    "route": "#1d6a85"
}

HIGHLIGHT = {
    "target": {
        "dark": "rgba(74,222,128,.16)",
        "light": "rgba(20,115,57,.10)"
    },
    "mine": {
        "dark": "rgba(74,222,128,.18)",
        "light": "rgba(20,115,57,.12)"
    }
}

BANNER = {
    "warn_bg": "#f9efda",
    "warn_border": "#dfc38f",
    "error_bg": "#f7e3dc",
    "error_border": "#c98d7e",
    "error_bg_dark": "#2c1614",
    "error_border_dark": "#8a4a40"
}
CHART = {
    "grid": "#ddd8c6",
    "grid_strong": "#cbc5ae"
}
BRAND = {
    "header_a": "#0e2417",
    "header_b": "#123020",
    "on_brand": "#ffffff"
}

FONT_DISPLAY = "'Archivo', 'Arial Narrow', sans-serif"
FONT_BODY = "'Inter', -apple-system, 'Segoe UI', sans-serif"
FONT_DATA = "'IBM Plex Mono', ui-monospace, Menlo, Consolas, monospace"
FONT_ENGRAVING = "'Cinzel', Georgia, 'Times New Roman', serif"
FONT_DIR = "data/fonts"


def mgr_color(mid: str | None) -> str:
    """Manager brand color (stable across every chart and report)."""
    return MANAGER_COLORS.get(mid or "", PALETTE["gray"])


def report_base_css() -> str:
    """Shared CSS base for the PDF report builders (light theme). Report
    scripts append only page-specific rules after this."""
    from pathlib import Path
    css = (Path(__file__).parent / "ml.css").read_text()
    return (
        css
        + """
/* report defaults (light) */
body { font-family: var(--ml-font-body); color: var(--ml-text); }
h1, h2, h3 { font-family: var(--ml-font-display); letter-spacing: .5px; }
.page-break { page-break-after: always; }
"""
    )


_MPL_DONE = False


def mpl_style() -> None:
    """Register league fonts + apply the standard chart style. Replaces the
    per-script _setup_mpl() copies. Safe to call repeatedly."""
    global _MPL_DONE
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.font_manager as fm
    import matplotlib.pyplot as plt
    from pathlib import Path
    if not _MPL_DONE:
        root = Path(__file__).resolve().parent.parent
        for f in (root / FONT_DIR).glob("*.ttf"):
            try:
                fm.fontManager.addfont(str(f))
            except Exception:
                pass
        _MPL_DONE = True
    plt.rcParams.update({
        "font.family": ["Inter", "DejaVu Sans"],
        "font.size": 10,
        "axes.facecolor": SURFACE_LIGHT["bg"],
        "figure.facecolor": SURFACE_LIGHT["bg"],
        "axes.edgecolor": PALETTE["gray"],
        "axes.labelcolor": PALETTE["ink"],
        "axes.titleweight": "bold",
        "axes.titlesize": 13,
        "axes.titlecolor": PALETTE["ink"],
        "axes.spines.top": False,
        "axes.spines.right": False,
        "xtick.color": PALETTE["gray"],
        "ytick.color": PALETTE["gray"],
        "grid.color": CHART["grid"],
        "grid.alpha": 0.7,
    })
