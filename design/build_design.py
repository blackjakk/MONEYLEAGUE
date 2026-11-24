"""Generate the design-system artifacts from design/tokens.json.

    python3 design/build_design.py               # regenerate ml.css + tokens.py
    python3 design/build_design.py --sync-fonts  # refresh fonts.faces payloads
                                                 # in tokens.json from
                                                 # data/fonts/*.woff2, then build

Emits (commit all of these together):
  design/ml.css    — component library + CSS custom properties (dark + light)
                     + base64 @font-face for the self-hosted Exchange faces
  design/tokens.py — Python constants + report_base_css() + mpl_style()

Both files carry DO-NOT-EDIT headers; they are build products.

Font embedding: the latin woff2 payloads are stored base64 inside
tokens.json (fonts.faces) rather than read from data/fonts at build time,
so the DRIFT check — which regenerates from tokens.json + this file alone
in a temp dir — reproduces ml.css byte-identically. `--sync-fonts` is the
one sanctioned way to refresh those payloads from data/fonts.

Accessibility invariants baked in (see docs/DESIGN_SYSTEM.md for measured
WCAG ratios — do not change these without re-measuring):
  - every on-color text pairing (badges, filters, clock states) is emitted
    per-theme so both themes meet 4.5:1;
  - the gold closing-bell / blue-chip chips use the measured dark-on-gold
    polarity (chip_text on chip_bg) in BOTH themes;
  - interactive controls (.ml-btn/.ml-input/.ml-filter) use the
    border_strong token (>=3:1 boundary, WCAG 1.4.11); decorative panels
    keep the subtle border (documented exemption);
  - global :focus-visible ring from the focus token;
  - font sizes are rem so browser text-size settings work;
  - prefers-reduced-motion kills the ml-pulse animation;
  - (pointer: coarse) enforces >=40px touch targets;
  - .ml-tape is static by construction — no animation, ever (motion means
    urgency, DESIGN.md).
"""
from __future__ import annotations

import base64
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
TOKENS_PATH = HERE / "tokens.json"
T = json.loads(TOKENS_PATH.read_text())

POS = T["color"]["position"]
POS_TEXT = T["color"]["position_text"]  # on-badge text overrides; default #fff
SEM = T["color"]["semantic"]
GOLD = SEM["gold"]
DARK = T["color"]["surface"]["dark"]
LIGHT = T["color"]["surface"]["light"]
STRAIT = T["color"]["surface"]["strait"]   # toll-ticket sub-theme only
STRAIT_ACC = {k: v for k, v in T["color"]["strait"].items()
              if not k.startswith("_")}
HL = T["color"]["highlight"]
BAN = T["color"]["banner"]
CHART = T["color"]["chart"]
BRAND = T["color"]["brand"]
TYPE = T["typography"]
RAD = T["radius"]
FONTS = T.get("fonts", {}).get("faces", [])

# (family, css font-weight [range for variable files], filename in data/fonts)
FONT_FILES = [
    ("IBM Plex Mono", "400", "IBMPlexMono-Regular-latin.woff2"),
    ("IBM Plex Mono", "700", "IBMPlexMono-Bold-latin.woff2"),
    ("Cinzel", "700", "Cinzel-700-latin.woff2"),
    ("Archivo", "600 800", "Archivo-600-800-latin.woff2"),
]


def _pos_fg(k: str) -> str:
    """Text color on a position badge/filter chip (C20 polarity table)."""
    return POS_TEXT.get(k, "#fff")


def _rgba(hex_color: str, alpha: float) -> str:
    h = hex_color.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    return f"rgba({r},{g},{b},{alpha:g})"


def build_font_faces() -> str:
    """@font-face rules from the base64 payloads stored in tokens.json."""
    rules = []
    for face in FONTS:
        rules.append(
            f"@font-face {{ font-family: '{face['family']}'; "
            f"font-style: normal; font-weight: {face['weight']}; "
            f"font-display: swap; "
            f"src: url(data:font/woff2;base64,{face['data']}) "
            f"format('woff2'); }}")
    return "\n".join(rules)


def build_css() -> str:
    pos_vars_dark = "\n".join(f"  --ml-pos-{k.lower()}: {v};" for k, v in POS.items())
    sem_dark = "\n".join(f"  --ml-{k}: {v['dark']};" for k, v in SEM.items())
    sem_light = "\n".join(f"  --ml-{k}: {v['light']};" for k, v in SEM.items())
    surf = lambda s: "\n".join(
        f"  --ml-{k.replace('_', '-')}: {v};" for k, v in s.items())
    hl = lambda theme: "\n".join(
        f"  --ml-{k}-tint: {v[theme]};" for k, v in HL.items())

    pos_badges = "\n".join(
        f'.ml-badge--{k.lower()} {{ background: var(--ml-pos-{k.lower()});'
        f' color: {_pos_fg(k)}; }}'
        for k in POS)
    pos_text = "\n".join(
        f'.ml-pos-{k.lower()} {{ color: var(--ml-pos-{k.lower()}); }}' for k in POS)
    pos_filters = "\n".join(
        f'.ml-filter--{k.lower()}.active {{ background: var(--ml-pos-{k.lower()});'
        f' border-color: var(--ml-pos-{k.lower()}); color: {_pos_fg(k)}; }}'
        for k in POS)

    seal_tint_hi = _rgba(GOLD["chip_bg"], 0.35)
    seal_tint_lo = _rgba(GOLD["chip_bg"], 0.08)

    return f"""/* ============================================================
   MONEYLEAGUE design system — GENERATED from design/tokens.json.
   DO NOT EDIT BY HAND: run  python3 design/build_design.py
   ============================================================ */

/* ---------- self-hosted faces (latin subsets, OFL — data/fonts/OFL_NOTICE.md) ---------- */
{build_font_faces()}

:root, [data-theme="dark"] {{
{surf(DARK)}
{pos_vars_dark}
{sem_dark}
{hl('dark')}
  --ml-gold-chip: {GOLD['chip_bg']};
  --ml-gold-chip-text: {GOLD['chip_text']};
  --ml-banner-warn-bg: #2a2115;
  --ml-banner-warn-border: #7c5a2b;
  --ml-banner-error-bg: {BAN['error_bg_dark']};
  --ml-banner-error-border: {BAN['error_border_dark']};
  --ml-font-display: {TYPE['display']};
  --ml-font-body: {TYPE['body']};
  --ml-font-data: {TYPE['data']};
  --ml-font-engraving: {TYPE['engraving']};
  --ml-r-sm: {RAD['sm']}; --ml-r-md: {RAD['md']}; --ml-r-lg: {RAD['lg']};
  --ml-brand-a: {BRAND['header_a']}; --ml-brand-b: {BRAND['header_b']};
  --ml-on-brand: {BRAND['on_brand']};
}}
[data-theme="light"] {{
{surf(LIGHT)}
{sem_light}
{hl('light')}
  --ml-banner-warn-bg: {BAN['warn_bg']};
  --ml-banner-warn-border: {BAN['warn_border']};
  --ml-banner-error-bg: {BAN['error_bg']};
  --ml-banner-error-border: {BAN['error_border']};
}}
/* STRAIT sub-theme — the Bab al-Mandab toll ticket ONLY (DESIGN.md
   "Sub-theme: The Strait"). Sand chart paper + navy ink; semantics reuse
   the light values (gated in scripts/check_a11y.py). */
[data-theme="strait"] {{
{surf(STRAIT)}
{sem_light}
{hl('light')}
  --ml-banner-warn-bg: {BAN['warn_bg']};
  --ml-banner-warn-border: {BAN['warn_border']};
  --ml-banner-error-bg: {BAN['error_bg']};
  --ml-banner-error-border: {BAN['error_border']};
  --ml-strait-route: {STRAIT_ACC['route']};
}}

/* ---------- a11y utilities ---------- */
:focus-visible {{ outline: 2px solid var(--ml-focus); outline-offset: 1px; }}
.ml-visually-hidden {{ position: absolute; width: 1px; height: 1px;
  padding: 0; margin: -1px; overflow: hidden; clip: rect(0 0 0 0);
  clip-path: inset(50%); white-space: nowrap; border: 0; }}
.ml-btn--bare {{ background: none; border: 0; padding: 0; color: inherit;
  font: inherit; text-align: left; cursor: pointer; }}

/* ---------- primitives ---------- */
/* .ml-panel/.ml-card borders are decorative container outlines — exempt
   from WCAG 1.4.11 (structure is conveyed by headings/spacing). Interactive
   controls below use --ml-border-strong instead. */
.ml-panel {{ background: var(--ml-panel); border: 1px solid var(--ml-border);
  border-radius: var(--ml-r-lg); padding: 10px; }}
.ml-panel > h2, .ml-h-label {{ margin: 0 0 8px; font-size: 0.75rem; font-weight: 700;
  text-transform: uppercase; letter-spacing: 1px; color: var(--ml-muted); }}
.ml-card {{ border: 1px solid var(--ml-border); border-radius: var(--ml-r-md);
  padding: 4px 7px; background: var(--ml-panel); break-inside: avoid; }}
.ml-display {{ font-family: var(--ml-font-display); letter-spacing: .5px; }}

/* ---------- exchange primitives ---------- */
.ml-num {{ font-family: var(--ml-font-data); font-variant-numeric: tabular-nums;
  text-align: right; }}
/* .ml-tape is STATIC by doctrine (DESIGN.md: motion means urgency) —
   never animate it; overflow simply clips. */
.ml-tape {{ display: flex; gap: 18px; padding: 4px 10px; overflow: hidden;
  white-space: nowrap; font-family: var(--ml-font-data); font-size: 0.6875rem;
  color: var(--ml-muted); border-bottom: 1px solid var(--ml-border); }}
.ml-tape b, .ml-tape strong {{ color: var(--ml-text); font-weight: 700; }}
.ml-serial {{ font-family: var(--ml-font-data); color: var(--ml-danger);
  font-size: 0.625rem; font-weight: 700; letter-spacing: 1px; }}
.ml-seal {{ font-family: var(--ml-font-engraving); font-weight: 700;
  font-size: 0.8125rem; width: 34px; height: 34px; border-radius: 50%;
  border: 1.5px solid currentColor; display: inline-grid; place-items: center;
  background: radial-gradient(circle at 50% 50%, {seal_tint_hi},
    {seal_tint_lo} 70%); }}
.ml-fineprint {{ color: var(--ml-muted); font-size: 0.65rem; line-height: 1.5; }}

/* ---------- badges & chips ---------- */
.ml-badge {{ display: inline-block; padding: 1px 5px; border-radius: var(--ml-r-sm);
  font-size: 0.625rem; font-weight: 700; color: #fff; min-width: 24px; text-align: center; }}
{pos_badges}
.ml-badge--dst {{ background: var(--ml-pos-def); color: {_pos_fg('DEF')}; }}
.ml-badge--keeper {{ background: var(--ml-keeper); color: #000; padding: 1px 4px;
  font-size: 0.5625rem; min-width: 0; }}
.ml-badge--rookie {{ background: var(--ml-warn); color: #000; padding: 1px 4px;
  font-size: 0.5625rem; min-width: 0; }}
.ml-badge--injury {{ background: var(--ml-danger); color: #000; padding: 1px 4px;
  font-size: 0.5625rem; min-width: 0; }}
/* gold chip polarity: dark text on gold, BOTH themes (measured 7.84) */
.ml-badge--bluechip {{ background: var(--ml-gold-chip);
  color: var(--ml-gold-chip-text); padding: 1px 4px; font-size: 0.5625rem;
  min-width: 0; letter-spacing: .5px; }}
[data-theme="light"] .ml-badge--keeper {{ color: #fff; }}
[data-theme="light"] .ml-badge--rookie {{ color: #fff; }}
[data-theme="light"] .ml-badge--injury {{ color: #fff; }}
{pos_text}
.ml-stat {{ background: var(--ml-panel2); padding: 3px 8px; border-radius: 4px;
  font-size: 0.6875rem; color: var(--ml-muted); }}
.ml-stat strong {{ color: var(--ml-text); }}

/* ---------- buttons & inputs ---------- */
.ml-btn {{ background: var(--ml-panel2); border: 1px solid var(--ml-border-strong);
  color: var(--ml-text); padding: 4px 10px; border-radius: var(--ml-r-md);
  cursor: pointer; font-size: 0.75rem; }}
.ml-btn:hover {{ filter: brightness(1.2); }}
.ml-btn--hdr {{ background: rgba(0,0,0,0.35); border: 1px solid rgba(255,255,255,0.65);
  color: var(--ml-on-brand); padding: 6px 12px; font-weight: 700; letter-spacing: .5px; }}
.ml-btn--on {{ background: var(--ml-danger); border-color: var(--ml-danger);
  color: #000; animation: ml-pulse 1.4s infinite; }}
[data-theme="light"] .ml-btn--on {{ color: #fff; }}
.ml-input {{ background: var(--ml-panel2); border: 1px solid var(--ml-border-strong);
  color: var(--ml-text); padding: 6px 10px; border-radius: var(--ml-r-md);
  font-size: 0.875rem; }}
.ml-filter {{ background: var(--ml-panel2); border: 1px solid var(--ml-border-strong);
  color: var(--ml-text); padding: 4px 9px; border-radius: var(--ml-r-md);
  cursor: pointer; font-size: 0.75rem; font-weight: 700; }}
.ml-filter.active {{ background: var(--ml-success); color: #000;
  border-color: var(--ml-success); }}
[data-theme="light"] .ml-filter.active {{ color: #fff; }}
{pos_filters}

/* ---------- status / clock ---------- */
@keyframes ml-pulse {{ 0%,100% {{ box-shadow: 0 0 0 0 rgba(74,222,128,.6); }}
  50% {{ box-shadow: 0 0 0 8px rgba(74,222,128,0); }} }}
.ml-clock {{ font-weight: 700; font-size: 0.8125rem; padding: 6px 10px;
  border-radius: 6px; background: rgba(0,0,0,0.35); color: var(--ml-on-brand); }}
/* closing bell: gold chip polarity (dark text on gold), BOTH themes */
.ml-clock--me {{ background: var(--ml-gold-chip); color: var(--ml-gold-chip-text);
  animation: ml-pulse 1.4s infinite; }}
.ml-clock--soon {{ background: var(--ml-warn); color: #000;
  animation: ml-pulse 1.4s infinite; }}
[data-theme="light"] .ml-clock--soon {{ color: #fff; }}
.ml-sv-hi {{ color: var(--ml-success); font-weight: 700; }}
.ml-sv-mid {{ color: var(--ml-warn); font-weight: 700; }}
.ml-sv-lo {{ color: var(--ml-danger); font-weight: 700; }}

/* ---------- tables ---------- */
.ml-table {{ width: 100%; border-collapse: collapse; font-size: 0.8125rem; }}
.ml-table th {{ text-align: left; padding: 4px 6px; color: var(--ml-muted);
  font-size: 0.6875rem; text-transform: uppercase; letter-spacing: .5px;
  border-bottom: 1px solid var(--ml-border); position: sticky; top: 0;
  background: var(--ml-panel); z-index: 1; }}
.ml-table td {{ padding: 6px; border-bottom: 1px solid var(--ml-row); }}
.ml-table--compact {{ font-size: 7.6pt; }}
.ml-table--compact td {{ padding: 1px 2px; }}

/* ---------- banners & notes ---------- */
.ml-banner {{ background: var(--ml-panel2); border-radius: var(--ml-r-md);
  padding: 4px 8px; }}
.ml-banner--warn {{ background: var(--ml-banner-warn-bg);
  border: 1px solid var(--ml-banner-warn-border); border-radius: var(--ml-r-md);
  padding: 4px 8px; }}
.ml-banner--error {{ background: var(--ml-banner-error-bg);
  border: 1px solid var(--ml-banner-error-border); border-radius: var(--ml-r-md);
  padding: 8px 10px; }}
.ml-banner--error strong {{ color: var(--ml-danger); }}
.ml-note {{ color: var(--ml-muted); font-size: .85em; }}
.ml-urgent {{ color: var(--ml-danger); font-weight: 700; }}

/* ---------- interaction states ---------- */
/* Loading placeholder: STATIC block (no shimmer — motion doctrine). Mark
   the containing region aria-hidden; real content replaces it wholesale. */
.ml-skeleton {{ display: inline-block; width: 100%; height: 0.8125rem;
  border-radius: var(--ml-r-sm); background: var(--ml-panel2); }}
/* Empty state: context text set by the caller ("no matches", "no fills"). */
.ml-empty {{ padding: 14px 10px; text-align: center; color: var(--ml-muted);
  font-size: 0.75rem; }}
/* Disabled controls: aria-disabled (kept focusable + announced) or the
   disabled attribute both render the same. Muted text stays readable —
   never opacity-ghosting (the C15 lesson). */
.ml-btn[disabled], .ml-btn[aria-disabled="true"] {{ color: var(--ml-muted);
  border-color: var(--ml-border); cursor: not-allowed; }}
.ml-btn[disabled]:hover, .ml-btn[aria-disabled="true"]:hover {{ filter: none; }}
.ml-btn--hdr[aria-disabled="true"] {{ color: rgba(255,255,255,0.55);
  border-color: rgba(255,255,255,0.3); cursor: not-allowed; }}
.ml-filter:hover {{ filter: brightness(1.15); }}
/* Action receipt: a single-fire background fade acknowledging a user
   action (fill/undo). Sanctioned by the motion doctrine alongside
   ml-pulse; one-shot, <=900ms, killed under reduced motion. */
@keyframes ml-receipt {{ from {{ background-color: var(--ml-mine-tint); }}
  to {{ background-color: transparent; }} }}
.ml-flash {{ animation: ml-receipt 900ms ease-out 1; }}

/* ---------- media adaptations ---------- */
@media (prefers-reduced-motion: reduce) {{
  .ml-btn--on, .ml-clock--me, .ml-clock--soon, .ml-flash {{ animation: none; }}
}}
@media (pointer: coarse) {{
  .ml-btn, .ml-filter {{ min-height: 40px; padding: 8px 12px; }}
  .ml-input {{ min-height: 40px; }}
  .ml-table td {{ padding-top: 10px; padding-bottom: 10px; }}
}}
"""


def build_py() -> str:
    return f'''"""GENERATED from design/tokens.json — DO NOT EDIT BY HAND.
Regenerate with:  python3 design/build_design.py

Single import point for every Python UI surface:
    from design.tokens import POS_COLORS, MANAGER_COLORS, PALETTE
    from design.tokens import report_base_css, mpl_style
"""
from __future__ import annotations

POS_COLORS = {json.dumps(POS, indent=4)}
POS_COLORS["DST"] = POS_COLORS["DEF"]

MANAGER_COLORS = {json.dumps(T["color"]["manager"], indent=4)}

PALETTE = {json.dumps(T["color"]["palette"], indent=4)}

SEMANTIC_LIGHT = {json.dumps({k: v["light"] for k, v in SEM.items()}, indent=4)}
SEMANTIC_DARK = {json.dumps({k: v["dark"] for k, v in SEM.items()}, indent=4)}

# The Exchange gold chip (closing bell / blue chip): dark-on-gold polarity,
# measured safe in BOTH themes — see docs/DESIGN_SYSTEM.md.
GOLD_CHIP = {json.dumps({"bg": GOLD["chip_bg"], "text": GOLD["chip_text"]}, indent=4)}

SURFACE_LIGHT = {json.dumps(LIGHT, indent=4)}
SURFACE_DARK = {json.dumps(DARK, indent=4)}

# STRAIT sub-theme (toll ticket only): surfaces + the sea-lane route ink.
SURFACE_STRAIT = {json.dumps(STRAIT, indent=4)}
STRAIT = {json.dumps(STRAIT_ACC, indent=4)}

HIGHLIGHT = {json.dumps(HL, indent=4)}

BANNER = {json.dumps(BAN, indent=4)}
CHART = {json.dumps(CHART, indent=4)}
BRAND = {json.dumps(BRAND, indent=4)}

FONT_DISPLAY = {json.dumps(TYPE["display"])}
FONT_BODY = {json.dumps(TYPE["body"])}
FONT_DATA = {json.dumps(TYPE["data"])}
FONT_ENGRAVING = {json.dumps(TYPE["engraving"])}
FONT_DIR = {json.dumps(TYPE["font_dir"])}


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
body {{ font-family: var(--ml-font-body); color: var(--ml-text); }}
h1, h2, h3 {{ font-family: var(--ml-font-display); letter-spacing: .5px; }}
.page-break {{ page-break-after: always; }}
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
    plt.rcParams.update({{
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
    }})
'''


def sync_fonts() -> None:
    """Refresh tokens.json fonts.faces from data/fonts/*.woff2 (FONT_FILES).
    The payloads live in tokens.json so the DRIFT check's temp-dir
    regeneration (tokens.json + build_design.py only) stays byte-identical."""
    font_dir = HERE.parent / TYPE["font_dir"]
    faces = []
    for family, weight, fname in FONT_FILES:
        p = font_dir / fname
        if not p.exists():
            sys.exit(f"--sync-fonts: missing {p}")
        faces.append({
            "family": family,
            "weight": weight,
            "file": fname,
            "data": base64.b64encode(p.read_bytes()).decode("ascii"),
        })
    T["fonts"]["faces"] = faces
    TOKENS_PATH.write_text(json.dumps(T, indent=2) + "\n")
    total = sum(len(f["data"]) for f in faces)
    print(f"Synced {len(faces)} font payload(s) into tokens.json "
          f"({total:,} base64 chars)")


def main() -> None:
    if "--sync-fonts" in sys.argv[1:]:
        sync_fonts()
        # re-read so the build below uses the fresh payloads
        global FONTS
        FONTS = json.loads(TOKENS_PATH.read_text())["fonts"]["faces"]
    css = build_css()
    py = build_py()
    (HERE / "ml.css").write_text(css)
    (HERE / "tokens.py").write_text(py)
    (HERE / "__init__.py").write_text(
        '"""MONEYLEAGUE design system (generated artifacts inside)."""\n')
    print(f"Wrote design/ml.css ({len(css):,} bytes), design/tokens.py "
          f"({len(py):,} bytes)")


if __name__ == "__main__":
    main()
