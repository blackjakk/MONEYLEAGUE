# MONEYLEAGUE design system

One design system for every UI surface in this repo: the draft helper SPA,
the four PDF report builders, and every matplotlib chart. Single source of
truth, generated artifacts, automated enforcement. Since July 2026 the
system ships **The Exchange** theme (see DESIGN.md): trading-terminal dark,
engraved-banknote light.

```
design/tokens.json          <- THE single source (edit this, nothing else)
design/build_design.py      <- generator
        |-> design/ml.css   <- component library + CSS vars (dark + light)
        |                      + base64 @font-face (self-hosted faces)
        `-> design/tokens.py<- Python constants + report_base_css() + mpl_style()
design/guilloche.py         <- deterministic banknote texture (SVG strings)
```

**The rule: ALL new UI goes through this library.** No inline hex colors, no
local palette dicts, no bespoke style blocks that duplicate a component.
`scripts/check_design_system.py` (wired into `scripts/verify_outputs.py`)
fails the build on violations, and the `design-review` skill
(`.claude/skills/design-review/SKILL.md`) blocks non-compliant UI diffs.

## Edit workflow

1. Edit `design/tokens.json` (the ONLY hand-edited file here — except the
   `fonts.faces` payloads, which are written by `--sync-fonts`, below).
2. Run `python3 design/build_design.py` — regenerates `ml.css` + `tokens.py`.
3. Copy `design/ml.css` → `docs/draft_helper/ml.css` (the helper serves its
   own copy on Pages).
4. Commit **all together**: `tokens.json`, `ml.css` (both copies), `tokens.py`.

Never hand-edit `ml.css` or `tokens.py` — both carry DO-NOT-EDIT headers and
the checker's DRIFT rule diffs them against a fresh regeneration on every
verify run.

## Consumer map

| Surface | How it consumes the system |
| --- | --- |
| `docs/draft_helper/index.html` | `<link rel="stylesheet" href="ml.css">` + `data-theme="dark"`; markup uses `ml-*` classes; page CSS is layout-only |
| `docs/draft_helper/standalone.html` | `scripts/build_standalone_helper.py` inlines `ml.css` at build time |
| `scripts/build_power_rankings.py` | `from design.tokens import ...` + `report_base_css()` (light theme) + `mpl_style()` |
| `scripts/build_preseason_2026.py` | same |
| `scripts/build_mock_draft_report.py` | same |
| `scripts/build_round_menu.py` | same (+ `design.guilloche` for banknote texture) |
| matplotlib charts (all builders) | `design.tokens.mpl_style()` registers league fonts and applies the standard chart rcParams — replaces per-script `_setup_mpl()` copies |

## Token catalog (`design/tokens.json`)

All color values below are **WCAG 2.1 AA verified** (July 2026 a11y audit,
re-measured July 2026 for The Exchange retune — the light theme is cream,
not white, so every historical white-surface ratio was re-derived). Don't
change a value without re-measuring; `scripts/check_a11y.py --only contrast
--ratios` prints every gated pair.

### color.position — one color per position, everywhere
`QB #dc2626 · RB #0e7490 · WR #15803d · TE #f59e0b · K #9a3412 · DEF #6b6b6b`
CSS: `--ml-pos-qb` ... `--ml-pos-def`. Python: `POS_COLORS` (includes a
`DST` alias for `DEF`). Unchanged by the Exchange retune — position hue
identity survives every theme.

### color.position_text — on-badge text polarity overrides
Text color used on a position badge/filter chip when white fails AA.
Currently only `TE: #000` (white on `#f59e0b` = 2.15 ✗, black = 9.78 ✓).
The builder defaults every other position to `#fff`.

### color.semantic — meaning colors, themed light/dark
| token | light | dark | CSS var |
| --- | --- | --- | --- |
| success | `#147339` | `#4ade80` | `--ml-success` |
| warn | `#a54c06` | `#f59e0b` | `--ml-warn` |
| danger | `#c81e1e` | `#f87171` | `--ml-danger` |
| info | `#0369a1` | `#60a5fa` | `--ml-info` |
| keeper | `#0369a1` | `#60a5fa` | `--ml-keeper` |
| focus | `#0369a1` | `#7dd3fc` | `--ml-focus` |
| **gold** | `#7d6010` | `#e8c76a` | `--ml-gold` |

All semantic *text* colors are ≥4.5:1 on every surface they appear on,
including `panel2`. Light success/warn were darkened for the cream
surfaces (from `#15803d`/`#b45309`, which fell to 4.02 on cream `panel2`);
danger/info/keeper/focus pass unchanged. Measured on light `bg`/`panel2`:
success 5.39/4.75 · warn 5.25/4.63 · danger 5.21/4.60 · info 5.39/4.75 ·
gold 5.37/4.74. On dark `bg`/`panel2`: success 10.52/8.16 · warn 8.53/6.62
· danger 6.63/5.14 · info 7.21/5.60 · gold 11.18/8.68. `focus` drives the
global `:focus-visible` ring (≥3:1 against bg/panel2 in both themes:
dark 10.99/8.53, light 5.39/4.75).

**gold** is The Exchange's market accent (DESIGN.md gold doctrine: market
state + blue-chip tier ONLY). It also carries the fixed **chip form** —
`semantic.gold.chip_bg #d4a017` + `semantic.gold.chip_text #14130a` →
`--ml-gold-chip` / `--ml-gold-chip-text` — used by `.ml-clock--me` (the
closing bell) and `.ml-badge--bluechip` with the same dark-on-gold polarity
in BOTH themes (measured 7.84; white on gold is 2.38 ✗, never use it).

### color.surface — page scaffolding, themed
`bg`, `panel`, `panel2`, `border`, `border_strong`, `row`, `text`, `muted`
for both `dark` (the terminal) and `light` (the banknote). CSS vars:
`--ml-bg`, `--ml-panel`, `--ml-panel2`, `--ml-border`, `--ml-border-strong`,
`--ml-row`, `--ml-text`, `--ml-muted` — values switch automatically with
`data-theme`. Python: `SURFACE_LIGHT`, `SURFACE_DARK`.

| key | dark (vault green) | light (banknote cream) |
| --- | --- | --- |
| bg | `#0c1710` | `#f7f4ea` |
| panel | `#12211a` | `#f7f4ea` |
| panel2 | `#1a2f24` | `#ece6d3` |
| row | `#16281e` | `#f1ecdd` |
| border | `#24382c` | `#d9d2ba` |
| border_strong | `#6b8672` | `#6e755f` |
| text | `#dfe7df` | `#1f3d2b` (engraving ink) |
| muted | `#8fae97` | `#52604f` |

- `text` measured on bg/panel/panel2/row: dark 14.52/13.22/11.27/12.26,
  light 10.84/10.84/9.56/10.10. `muted`: dark 7.57/6.89/5.87/6.39, light
  6.07/6.07/5.35/5.65 — all ≥4.5.
- `border_strong` is the **interactive control boundary** — WCAG 1.4.11
  needs ≥3:1 for UI component boundaries (measured: dark 4.20 vs panel /
  3.58 vs panel2; light 4.36 vs bg / 3.85 vs panel2). Used by `.ml-input`,
  `.ml-btn`, `.ml-filter`.
- `border` (subtle) stays on `.ml-panel` / `.ml-card` — **decorative
  container outlines are exempt from 1.4.11** (audit C22): panel structure
  is conveyed by headings and spacing, the border is aesthetic only. Do not
  "fix" panel borders to `border_strong`; do not use plain `border` on
  anything a user must locate to operate.
- The vault greens are surfaces, never signals (DESIGN.md "three greens").

### color.highlight — row-tint overlays, themed
| token | dark | light | CSS var |
| --- | --- | --- | --- |
| target | `rgba(74,222,128,.16)` | `rgba(20,115,57,.10)` | `--ml-target-tint` |
| mine | `rgba(74,222,128,.18)` | `rgba(20,115,57,.12)` | `--ml-mine-tint` |

Used by the helper for Brian-target rows and "my pick" history rows.
Tints are intentionally subtle and therefore **must never be the only
signal** — pair with a non-color cue (the helper uses a ★ glyph / the
manager name). Python: `HIGHLIGHT`.

### color.banner / color.brand / color.chart
- banner: `warn_bg #f9efda`, `warn_border #dfc38f` (cream-warm light
  values; dark equivalents are baked into the dark block) →
  `--ml-banner-warn-bg`, `--ml-banner-warn-border`.
- brand: `header_a #0e2417`, `header_b #123020` → `--ml-brand-a`,
  `--ml-brand-b` (deep vault-green masthead gradient), plus
  `on_brand #ffffff` → `--ml-on-brand` — the ONLY text color allowed on
  the brand gradient, both themes (measured 16.36 / 14.29). Never put
  `--ml-text` on the gradient (light theme renders dark-on-dark).
- chart: `grid #ddd8c6`, `grid_strong #cbc5ae` — warm grid lines on the
  cream figure background via `mpl_style()`.

### color.palette — general-purpose named colors (Python `PALETTE`)
`gold, navy, teal, emerald, orange, crimson, slate, cream, ink, gray` — for
report accents and chart series that aren't position/manager-keyed.
`ink` is now the engraving ink `#1f3d2b` (matches `surface.light.text`);
`cream #f7f4ea` is the banknote paper (matches `surface.light.bg`);
`palette.gold #d4a017` equals the gold chip fill.

### color.manager — one stable brand color per franchise
17 manager ids (e.g. `brian_bigguap #1e40af`, `kyle_figgy #f59e0b`, ...).
Python: `MANAGER_COLORS`, or `mgr_color(mid)` which falls back to
`PALETTE["gray"]` for unknown/None ids. Use `mgr_color` so every chart and
report colors a franchise identically.

### typography / radius / space
Four roles (DESIGN.md "Type" has the usage doctrine):

| token | face | CSS var / Python |
| --- | --- | --- |
| `typography.display` | Archivo 600/800 (Bebas Neue retired July 2026; var name unchanged) | `--ml-font-display` / `FONT_DISPLAY` |
| `typography.body` | Inter | `--ml-font-body` / `FONT_BODY` |
| `typography.data` | IBM Plex Mono 400/700 | `--ml-font-data` / `FONT_DATA` |
| `typography.engraving` | Cinzel 700 | `--ml-font-engraving` / `FONT_ENGRAVING` |

- `typography.font_dir` → TTFs registered by `mpl_style()`.
- `radius.sm/md/lg` → `--ml-r-sm/--ml-r-md/--ml-r-lg` (3/5/8px).
- `space.xs..xl` (2/4/8/12/18px) — spacing scale; use these values when a
  component needs new padding/gaps (add emission to `build_design.py` if you
  need them as CSS vars).

### fonts — self-hosted embedded faces
`fonts.faces` holds base64 **latin woff2 subsets** (fetched from the Google
Fonts css2 API; all OFL — `data/fonts/OFL_NOTICE.md`) that the builder
emits as `@font-face` rules at the top of `ml.css` (~106 KB base64 total),
so the helper, standalone.html, and the Playwright-rendered PDFs get
identical faces with **zero network at runtime**:

- IBM Plex Mono 400 + 700 (two static subsets)
- Cinzel 700
- Archivo — Google serves one *variable* latin file for wght 600–800;
  it is declared once with `font-weight: 600 800`, so `document.fonts`
  shows 4 FontFace entries covering all 5 weights (verify with
  `document.fonts.check('600 12px Archivo')` etc.)

The payloads live **inside tokens.json** (not read from `data/fonts/` at
build time) so the DRIFT check — which regenerates from tokens.json + the
builder alone in a temp dir — stays byte-identical. Refresh them from
`data/fonts/*.woff2` with `python3 design/build_design.py --sync-fonts`.
Matching TTFs live in `data/fonts/` for matplotlib (`mpl_style()`).

### Strait sub-theme (toll ticket only, Nov 2026)

`color.surface.strait` (bg = chart sea, panel = ticket paper, panel2 =
alt row, border, border_strong, row, text = navy ink, muted) +
`color.strait` (signal, band, band_text, route, land, land_edge,
contour), emitted as the `[data-theme="strait"]` block in `ml.css`
(`--ml-strait-*` vars; semantics reuse the light values) and as
`SURFACE_STRAIT` / `STRAIT` in `tokens.py`. Sole consumer:
`scripts/build_tax_tape.py`. Measured at introduction: navy text 12.6:1
on sea / 15.3 on paper / 14.1 on panel2; muted 5.7 / 6.8 / 6.3; navy on
signal orange 5.3; band_text on navy band 15.3; navy on land 11.9, muted
on land 5.3; danger 5.4 / success 5.6 / info 5.6 / warn 5.4 on paper
(semantic text is never placed on the sea, where danger falls to 4.5);
border_strong 4.8 on sea; route line 4.5 on sea. All gated in
`scripts/check_a11y.py`. Ornament: `design.guilloche.compass_svg`. Intent
and scope rules: DESIGN.md "Sub-theme: The Strait".

## Guilloché (`design/guilloche.py`)

Deterministic banknote line texture — no randomness, no files, no external
requests. Both functions return complete inline-`<svg>` strings:

```python
from design.guilloche import lattice_svg, rosette_svg
lattice = lattice_svg(400, 80, SURFACE_LIGHT["text"], 0.11)  # 24-line engraving lattice
corner  = rosette_svg(34, SURFACE_LIGHT["text"], 0.20)       # spirograph rosette
```

Doctrine: engraving opacity only (~0.11 lattice / ~0.20 rosettes), print
surfaces and banknote-styled cards only, data always wins. Smoke test:
`python3 design/guilloche.py`.

## Component catalog (`design/ml.css`)

Every class, with a usage snippet. All of them theme automatically.

### A11y utilities

```html
<span class="ml-visually-hidden">Draft </span>      <!-- SR-only text -->
<button class="ml-btn--bare">Bijan Robinson</button> <!-- text-look button -->
```

- **Global focus ring** — ml.css ships
  `:focus-visible { outline: 2px solid var(--ml-focus); outline-offset: 1px; }`.
  Never suppress it (`outline: none`) and never add per-component focus
  styles; every interactive element gets a visible ring for free.
- `.ml-visually-hidden` — standard clip pattern; text readable by screen
  readers, invisible on screen. Use it for SR-only labels, live-region
  text, and expanding abbreviations.
- `.ml-btn--bare` — resets a `<button>` to inherit surrounding text style
  (background/border/padding stripped, `font: inherit`, `cursor: pointer`).
  Use it to make table-row / card content a real focusable button without
  changing its look (draft-a-player rows, rec cards).

### Media adaptations (baked into ml.css — no page CSS needed)

- `@media (prefers-reduced-motion: reduce)` — kills the `ml-pulse`
  animation on `.ml-btn--on`, `.ml-clock--me`, `.ml-clock--soon`; the solid
  background-color state still conveys the status.
- `@media (pointer: coarse)` — touch targets: `.ml-btn`/`.ml-filter` and
  `.ml-input` get `min-height: 40px` (+ `8px 12px` padding on buttons);
  `.ml-table td` gains vertical padding so rows are tappable (~40px).
- Font sizes are **rem** (root-16px equivalents:
  0.875/0.8125/0.75/0.6875/0.65/0.625/0.5625rem) so browser/OS text-size
  settings actually scale the UI. Exception: `.ml-table--compact` keeps
  `7.6pt` — print/PDF density is a physical-unit context.

### On-color text polarity (measured — pick from this table, never guess)

Whether text on a colored chip is white or black is decided by measured
contrast, per theme. The builder emits these; light-theme flips are
`[data-theme="light"]` overrides. Re-measured July 2026 for The Exchange
(chip fills are theme-independent, so position-badge ratios carry over;
light semantic fills changed where the semantic value was darkened).

| Surface | dark theme | light theme | measured (dark / light) |
| --- | --- | --- | --- |
| QB `#dc2626` | white | white | 4.83 (black fails 4.35) |
| RB `#0e7490`, WR `#15803d`, K `#9a3412`, DEF `#6b6b6b` | white | white | 5.36 / 5.02 / 7.31 / 5.33 |
| TE `#f59e0b` (badge + filter) | **black** | **black** | 9.78 (white fails 2.15) |
| keeper (`#60a5fa` / `#0369a1`) | **black** | **white** | 8.26 (white fails 2.54) / 5.93 (black fails 3.54) |
| rookie (warn: `#f59e0b` / `#a54c06`) | **black** | **white** | 9.78 / 5.78 |
| injury + `.ml-btn--on` (danger: `#f87171` / `#c81e1e`) | **black** | **white** | 7.59 / 5.74 |
| `.ml-filter.active` (success: `#4ade80` / `#147339`) | **black** | **white** | 12.05 / 5.93 |
| `.ml-clock--me` + `.ml-badge--bluechip` (gold chip `#d4a017`) | **`--ml-gold-chip-text`** | **`--ml-gold-chip-text`** (same — no flip) | 7.84 / 7.84 (white fails 2.38) |
| `.ml-clock--soon` (warn) | **black** | **white** | 9.78 / 5.78 |
| brand gradient (header, `.ml-clock`, `.ml-btn--hdr`) | `--ml-on-brand` (white) | `--ml-on-brand` (white) | 16.36 / 14.29 |

Adding a new badge/chip? Compute both polarities against its background in
BOTH themes (4.5:1 for the ≤16px badge text) and add a
`color.position_text` entry or a light-theme override in the builder
accordingly. Remember the light surfaces are cream — anything measured
against "white" historically must be re-measured against
`surface.light.bg`/`panel2`.

### Layout primitives
```html
<section class="ml-panel">
  <h2>Available players</h2>        <!-- panel h2 auto-styles as a label -->
  ...
</section>
<span class="ml-h-label">Round 3</span>   <!-- same label style, anywhere -->
<div class="ml-card">Pick 3.07 — Brian</div>  <!-- compact bordered card -->
<h1 class="ml-display">MONEYLEAGUE</h1>   <!-- display font (Archivo) + tracking -->
```

### Exchange primitives (July 2026)
```html
<td class="ml-num">+135</td>              <!-- data numerals: Plex Mono, tabular, right-aligned -->
<div class="ml-tape">                     <!-- STATIC ticker strip — never animated -->
  <span>WK MOVERS:</span> <span>GIBBS <b>▲2 rds</b></span> <span>HALL ▼1.1</span>
</div>
<span class="ml-badge ml-badge--bluechip">◆ BLUE CHIP</span> <!-- gold chip; top market tier ONLY -->
<span class="ml-serial">NO. B06-R3-030</span>  <!-- red mono provenance id -->
<span class="ml-seal" aria-hidden="true">ML</span> <!-- engraved circular seal (Cinzel, gold tint) -->
<p class="ml-fineprint">Past performance (2025: 12th of 12) is not
indicative of future results.</p>       <!-- disclosures only -->
```

- `.ml-num` — put it on every numeric table cell so columns never wobble.
- `.ml-tape` — muted mono facts strip with `--ml-text` for `<b>`/`<strong>`
  emphasis; overflow clips. **No animation, ever** (DESIGN.md motion rule).
- `.ml-badge--bluechip` — `--ml-gold-chip` fill + `--ml-gold-chip-text`
  in both themes; gold doctrine limits it to the top market tier.
- `.ml-serial` — `--ml-danger` colored, letterspaced mono; content must be
  a real id (week/build/slot-round-pick), not decoration.
- `.ml-seal` — the system's only circle; `currentColor` border so it takes
  its ink from the surrounding text; gold radial tint is baked in (the one
  sanctioned gradient outside the masthead). Ornament, never a control.
- `.ml-fineprint` — 0.65rem muted disclosures; never interactive text.

### Badges & chips
```html
<span class="ml-badge ml-badge--qb">QB</span>   <!-- --rb --wr --te --k --def --dst -->
<span class="ml-badge ml-badge--keeper">KEEPER</span>
<span class="ml-badge ml-badge--rookie">R</span>
<span class="ml-badge ml-badge--injury">Q</span>
<span class="ml-badge ml-badge--bluechip">◆</span>
<span class="ml-pos-wr">Ja'Marr Chase</span>    <!-- position-colored text: ml-pos-{qb,rb,wr,te,k,def} -->
<span class="ml-stat">ADP <strong>12.4</strong></span>  <!-- muted stat chip -->
```

### Buttons & inputs
```html
<button class="ml-btn">Undo</button>
<button class="ml-btn ml-btn--hdr">Practice</button>   <!-- on-gradient header button -->
<button class="ml-btn ml-btn--on">REC ON</button>      <!-- danger + pulse -->
<input class="ml-input" type="search" placeholder="Search players">
<button class="ml-filter active">ALL</button>          <!-- filter chip; .active = success -->
<button class="ml-filter ml-filter--qb active">QB</button>  <!-- position-colored active state: ml-filter--{qb,rb,wr,te,k,def} -->
```

### Status & clock
```html
<div class="ml-clock">Pick 3.07</div>
<div class="ml-clock ml-clock--me">CLOSING BELL — YOU'RE UP</div> <!-- gold chip + pulse -->
<div class="ml-clock ml-clock--soon">2 away</div>      <!-- amber + pulse -->
<td class="ml-sv-hi">92%</td>  <!-- survival tiers: ml-sv-hi / ml-sv-mid / ml-sv-lo -->
```
(`ml-pulse` is the shared keyframe animation behind `--on`, `--me`, `--soon`.
`--me` is the gold closing bell — dark text on gold, both themes, no flip.)

### Tables
```html
<table class="ml-table"> ... </table>              <!-- sticky headers, row rules -->
<table class="ml-table ml-table--compact"> ... </table>  <!-- 7.6pt print density -->
```
Numeric columns get `class="ml-num"` per cell (or via a column rule in
page layout CSS — alignment/font only, no colors).

### Banners & notes
```html
<div class="ml-banner">Ceiling mode uses 85th-percentile projections.</div>
<div class="ml-banner ml-banner--warn">3 keepers still unconfirmed.</div>
<div class="ml-banner--error" role="alert">
  <strong>MARKET DATA UNAVAILABLE</strong> — data.json didn't load.
  <button class="ml-btn">Retry</button></div>
<p class="ml-note">Values as of July 11.</p>
<span class="ml-urgent">On the clock!</span>
```

### Interaction states (DESIGN.md doctrine: every control earns all five)

```html
<!-- loading: static placeholder (no shimmer), region hidden from SR -->
<tr aria-hidden="true"><td colspan="9">
  <span class="ml-skeleton" style="width:72%"></span></td></tr>
<main aria-busy="true">…</main>   <!-- until the data bundle lands -->

<!-- empty: contextual — name the cause AND the way out -->
<div class="ml-empty">No assets match “jones” — press Esc to clear</div>

<!-- disabled: aria-disabled keeps it focusable + announced; activating it
     explains itself via the status region. Muted text, never opacity. -->
<button class="ml-btn" aria-disabled="true" title="Nothing to undo yet">undo last</button>

<!-- feedback: one-shot receipt flash on the affected row (<=900ms
     background fade via the ml-receipt keyframe; reduced-motion kills it),
     paired with a receipt line in a role="status" region -->
<div class="history-row ml-flash">#6 BRIAN … Bijan Robinson</div>
```

- `.ml-skeleton` — static block, `--ml-panel2` fill; never animated.
- `.ml-empty` — centered muted 0.75rem block for zero-result regions.
- `.ml-banner--error` — `--ml-banner-error-bg/border` (both themes measured:
  danger text 6.16 dark / 4.64 light); always `role="alert"` + one action.
- `.ml-btn[disabled]` / `[aria-disabled="true"]` — muted text, subtle
  border, `cursor: not-allowed`, hover filter off (both button variants).
- `.ml-flash` / `@keyframes ml-receipt` — the sanctioned action receipt;
  in the `prefers-reduced-motion` kill list alongside `ml-pulse`.
- `check_a11y.py` enforces all of the above (CSS group + error-banner
  contrast pairs + `role="alert"` / `aria-busy` ARIA rules).

## Python API (`design/tokens.py`, generated)

```python
from design.tokens import (
    POS_COLORS, MANAGER_COLORS, PALETTE,          # dicts of hex strings
    SEMANTIC_LIGHT, SEMANTIC_DARK,                 # themed meaning colors (incl. "gold")
    GOLD_CHIP,                                     # {"bg", "text"} — the gold chip pairing
    SURFACE_LIGHT, SURFACE_DARK, HIGHLIGHT, BANNER, BRAND, CHART,
    FONT_DISPLAY, FONT_BODY, FONT_DATA, FONT_ENGRAVING, FONT_DIR,
    mgr_color,          # mgr_color(manager_id) -> stable hex, gray fallback
    report_base_css,    # ml.css + light report defaults; append layout-only rules
    mpl_style,          # fonts + standard chart rcParams; call before plotting
)
```

Report builders: `html = f"<style>{report_base_css()}{PAGE_CSS}</style>..."`
where `PAGE_CSS` contains layout only. Charts: call `mpl_style()` once before
creating figures (idempotent). Banknote texture: `from design.guilloche
import lattice_svg, rosette_svg`.

## Enforcement

`python3 scripts/check_design_system.py` (also run by
`scripts/verify_outputs.py` as the "design system compliance" check):

- **RAW HEX** — no `#rgb`/`#rrggbb` literals in DESIGN.md, the helper, or
  the 4 report builders. Only `var(--ml-x, #hex)` fallbacks, quoted SVG
  data-URI favicons, and comments are exempt.
- **DUPLICATE PALETTES** — no `POS_COLORS` / `MANAGER_COLORS` / `PALETTE`
  dict literals in any `scripts/*.py`; import from `design.tokens`.
- **DRIFT** — `ml.css` / `tokens.py` must equal a fresh regeneration from
  `tokens.json` (catches hand-edits and forgotten regens; the font payloads
  living in tokens.json is what keeps this reproducible).
- **HELPER LINK** — `index.html` must link `ml.css` and carry `data-theme`.

`python3 scripts/check_a11y.py --only contrast` gates every fg/bg pair in
this document, including the gold pairs (gold text on every surface, the
gold chip polarity, `.ml-badge--bluechip`/`.ml-clock--me` as shipped in
ml.css). `--ratios` dumps the measured table.

`--fixture-selftest` validates the scanner itself; `--only <rule>` runs one
rule. The `design-review` skill applies the human-judgment half (component
usage, both themes, contrast, Playwright coverage) and blocks on any checker
failure.

## Adding a new component (checklist for strangers)

1. New color/radius/spacing? Add it to `design/tokens.json` first.
2. Add the component's CSS to `build_css()` in `design/build_design.py`
   using only `var(--ml-*)` references (name it `ml-<thing>`, modifiers as
   `ml-<thing>--<variant>`).
3. `python3 design/build_design.py`; commit tokens.json + ml.css + tokens.py
   (and the `docs/draft_helper/ml.css` copy).
4. Document it here (catalog snippet above) and check it against DESIGN.md
   (gold doctrine, motion rule, type roles).
5. If it renders text on a colored fill: measure both polarities in both
   themes and extend the contrast pair list in `scripts/check_a11y.py`.
6. If interactive: add Playwright coverage.
7. `python3 scripts/check_design_system.py` must pass — if you needed a raw
   hex anywhere outside `design/`, you skipped step 1.
