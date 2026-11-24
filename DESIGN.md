# DESIGN.md — how MONEYLEAGUE should look

Read this BEFORE building or changing any UI (helper, PDF builders, charts).
It is the intent layer of the design system:

| Layer | File | Question it answers |
|---|---|---|
| Values | `design/tokens.json` (→ generated `ml.css`/`tokens.py`) | what exact color/size |
| Catalog | `docs/DESIGN_SYSTEM.md` | what components/API exist |
| **Intent** | **this file** | which to choose, and why |
| Law | `scripts/check_design_system.py` + `check_a11y.py` | what gets blocked |
| Review | `design-review` + `a11y-review` skills | the judgment pass |

**This file never states a color value.** Reference tokens by name
(`--ml-danger`, `position.TE`); the RAW HEX check scans this file and fails
the build on any hex literal here. If intent and tokens seem to disagree,
tokens win — then fix whichever is wrong in its own layer.

## The aesthetic: The Exchange

The league is literally named for money, and drafting under a clock *is*
trading under a closing bell. Every surface reads money through one of two
materials — never through dollar-sign clip-art:

- **The trading terminal** (dark theme, the live tool): vault-green
  surfaces (`surface.dark`), monospaced tabular numerals, a static ticker
  tape, a gold closing bell. A Bloomberg terminal for a 12-team keeper
  league — screens read under clock pressure, at a desk or on a phone.
- **The engraved banknote** (light theme, the printed reports): banknote
  cream paper (`surface.light`), engraving-ink text, guilloché line
  texture (`design/guilloche.py`), serial numbers, seals, fine print.
  Currency engraving is a print-native idiom; the PDFs inherit it
  automatically through `report_base_css()`.

The theme is *display and language only*: it renames labels and dresses
surfaces, it never changes what a number means or hides one.

1. **Data is the interface.** Numbers and names are the heroes; chrome
   recedes. If a decoration competes with a fact, the decoration loses.
   Guilloché stays at engraving opacity (the generator defaults are tuned
   for this) — texture must disappear the moment you read the table.
2. **Color is meaning, never decoration.** Every hue on screen encodes
   something (position, urgency, ownership, market state). A color with no
   meaning is visual noise — leave it out. The vault greens are *surfaces*,
   not signals: they carry no meaning beyond "this is The Exchange".
3. **Flat.** Separation comes from surface steps (`bg → panel → panel2`)
   and 1px borders — never drop shadows, never glassmorphism. Banknote
   texture is line work, not depth.
4. **Motion is spent on exactly two things.** (a) *Urgency*: `ml-pulse`
   means "act now" (you're up / 2 away / live). (b) *Receipts*: `ml-flash`
   (`ml-receipt` keyframe) is a single-fire ≤900ms background fade that
   acknowledges a user action — a fill landing, an undo returning — and
   never loops. Nothing else moves, nothing ambient ever moves —
   **the tape is static, always** (`.ml-tape` never animates, never
   marquees; it is a strip of facts, not ambience). Loading skeletons
   (`.ml-skeleton`) are static blocks — no shimmer. Reduced-motion users
   get the same states via solid color (both animations are killed).
5. **Dense, with rhythm.** Draft decisions need many facts per screen-inch;
   density is a feature. Rhythm comes from the `space.*` tokens, not
   eyeballed padding.
6. **Accessibility is part of the look.** The focus ring, 40px touch
   targets, text-carrying-meaning — these are design, not compliance
   afterthoughts. docs/A11Y_AUDIT.md is part of this system's history.

## Color doctrine

- **Position hues are identity.** QB/RB/WR/TE/K/DEF each own their hue
  (`color.position`) everywhere — helper table, PDF cards, matplotlib
  series. Never reuse a position hue to mean anything else, and never
  introduce a second hue for the same position.
- **Traffic-light semantics are reserved for actionability.**
  `--ml-success` = safe / can wait / gain. `--ml-warn` = coin flip /
  2-away / rookie risk. `--ml-danger` = now-or-never / injury / LIVE /
  loss. Don't spend these on anything that isn't a call to judgment.
  Never green-tint data that isn't gain/loss; survival % keeps its own
  traffic-light scale.
- **Gold doctrine.** `--ml-gold` (text) and the `--ml-gold-chip` pairing
  are spent on exactly two meanings: **market state** (the closing bell —
  `.ml-clock--me`) and the **blue-chip tier** (`.ml-badge--bluechip`,
  top-of-market assets only, used sparingly). Gold on anything else is
  decoration and gets rejected. The one sanctioned ornament is the faint
  gold radial tint baked into `.ml-seal`.
- **Three greens, three jobs.** WR's position hue, `--ml-success`
  (gain/safe), and the vault-green surfaces coexist because the surfaces
  are very dark (dark theme) or ink-on-cream (light theme) — background
  material, never a signal. Never introduce a fourth green, and never use
  a surface green as text.
- `--ml-info` / `--ml-keeper` (blue) = factual annotation, never urgency.
- The brand gradient exists **only** on the app header / report mastheads,
  and the only text color on it is `--ml-on-brand`.
- `--ml-muted` is for secondary facts (team, ADP, round tags) and fine
  print; primary facts get `--ml-text`. If you're unsure, it's primary.
- Tint overlays (`--ml-target-tint`, `--ml-mine-tint`) are never the sole
  signal — always pair a glyph or text (★, "(your pick)").
- New on-color text? Use the measured polarity table in
  docs/DESIGN_SYSTEM.md; never guess white-vs-black. The gold chip is
  dark-text-on-gold in BOTH themes — never put white on gold.

## Language doctrine (GUAP & market terms)

- **Renames label, never replace.** Market language decorates the real
  stat; the number stays. VAL keeps its hidden VBD expansion; "contract:
  keep '27 @ R4" keeps the round math; BUY sits on a row that still shows
  the projection. If a themed term hides a number, the term loses.
- **GUAP is the denomination, not the data.** GUAP suffixes a real total
  ("2 081 GUAP") — it never substitutes for it, never rounds it, never
  becomes a made-up currency conversion.
- Serial numbers (`.ml-serial`) are real provenance — week + build ids,
  slot-round-pick — not decorative gibberish.
- Fine print (`.ml-fineprint`) is for true disclosures (data-as-of lines,
  the self-aware risk disclosure), not for burying facts someone needs.

## Interaction states (every control earns all five)

A control or region isn't done until its loading, empty, error, disabled,
and feedback states are all designed — the components exist, so "the happy
path only" is never a reason:

- **Loading**: static `.ml-skeleton` placeholders per region (aria-hidden,
  `aria-busy` on the container until data lands). No shimmer, ever.
- **Empty**: `.ml-empty` with a *contextual* sentence that names the cause
  and the way out ("No assets match 'jones' — press Esc to clear"), never
  a bare dash or a silent blank.
- **Error**: `.ml-banner--error` + `role="alert"`, stating what failed and
  offering exactly one action (Retry). Recoverable background failures
  (live poll) degrade to status text instead and keep retrying.
- **Disabled**: `aria-disabled="true"` — kept focusable and announced;
  activating it explains itself via the status region. Muted text, hover
  effects off; never opacity-ghosting.
- **Feedback**: every state-changing action produces a receipt — one line
  in the `role="status"` region ("FILLED — …", "UNDONE — …") plus an
  `ml-flash` on the affected row; search/filter changes announce a result
  count. Silent success is a bug.
- Hover ≠ focus: hover is a brightness step; focus is the global ring;
  neither ever substitutes for the other.

## Type

Four faces, four jobs — nothing else, no italic-as-brand:

| Role | Var | Face | Use |
|---|---|---|---|
| data | `--ml-font-data` | IBM Plex Mono 400/700 | every numeral column (`.ml-num`), tape, serials, BUY-style micro-actions — tabular by construction, the single most load-bearing "money" face |
| masthead/display | `--ml-font-display` | Archivo 600/800 | mastheads, PDF headlines, table headers that want the annual-report voice (Bebas Neue is retired) |
| engraving | `--ml-font-engraving` | Cinzel 700 | banknote denominations, league name on certificates, `.ml-seal` — the certificate voice, print surfaces only; never body text, never the helper table |
| body | `--ml-font-body` | Inter | everything else |

All four are OFL, self-hosted, and embedded into ml.css as base64 latin
subsets — zero network at runtime (licenses: `data/fonts/OFL_NOTICE.md`).
Numerals in any aligned column get `.ml-num` — columns must never wobble.

The scale is rem-based (root-16px equivalents), smallest to largest:

| Step | rem | Use |
|---|---|---|
| micro | 0.5625 | keeper/rookie/blue-chip/injury mini-badges — legacy floor, no new uses |
| serial | 0.625 | position badges, `.ml-serial` |
| fineprint | 0.65 | `.ml-fineprint` disclosures only — never interactive, never load-bearing facts |
| meta | 0.6875 | secondary facts, panel h2 labels, table headers, `.ml-tape` |
| control | 0.75 | buttons, filters, clock |
| table | 0.8125 | data rows, `.ml-seal` monogram |
| body | 0.875 | prose, inputs |

Rules: emphasis by **weight**, not size; panel headings are small
uppercase muted labels (the `ml-panel > h2` style), never large type — big
type is reserved for the one `<h1>`/masthead per page and for denomination
numbers in PDFs. Nothing new below the fineprint step, and fineprint is
reserved for disclosures.

## Space, radius, elevation

- Spacing only from `space.*`: `xs` hairline gaps, `sm` chip padding,
  `md` component padding, `lg` panel gaps/grid gutters, `xl` page margins.
- Radius: `--ml-r-sm` chips/badges, `--ml-r-md` controls/cards,
  `--ml-r-lg` panels. No pill buttons. The **only** circle is `.ml-seal`
  (an engraving ornament, never a control) — don't mint more.
- Elevation: none. Border hierarchy instead — `--ml-border` for decorative
  container outlines, `--ml-border-strong` for anything a user must locate
  to operate (inputs, buttons, filters). Never promote panel borders to
  strong "for looks", never demote a control border to subtle.
- Guilloché (`design/guilloche.py`) is the only texture: deterministic
  spirograph line work, engraving opacity, print surfaces (and the
  banknote-styled cards) only. No stock textures, no repeating tiles,
  no images.

## Component decision rules

- **Panel** (`ml-panel` + h2): a top-level region of the screen. **Card**
  (`ml-card`): one repeated record (a pick, a round). **Banner**: inline
  context line; `--warn` variant only when the reader should act.
  **Badge**: a categorical fact; never clickable (`--bluechip` marks the
  top market tier and nothing else). **Filter** (`ml-filter`):
  mutually exclusive chip set, `aria-pressed` required. **Table**
  (`ml-table`): anything with ≥3 aligned facts — no div-grids pretending;
  numeric cells get `.ml-num`. **Tape** (`ml-tape`): one static strip of
  market facts (weekly movers) per surface, at most.
- Every interactive element is a real `<button>`/`<input>`; text-look
  actions use `ml-btn--bare`. Click-only divs/rows are banned (a11y gate).
- New UI = existing components composed by page-level **layout** CSS.
  Page CSS never restyles a component and never contains a color. If a
  composition recurs on a second surface, promote it to a component
  (tokens → builder → catalog).

## Device & mode behavior

- Dark theme is the live terminal; light theme is the printed banknote
  (PDFs). Every change must hold in both (the theme toggle and
  `report_base_css()` share tokens) — and remember the light surfaces are
  cream, not white: re-measure any new pair on `surface.light.panel2`.
- Phone: collapse **facts** before shrinking **type** (the helper drops
  Team/Age/Proj columns at ≤480px rather than going below the meta step);
  the decision context (clock, recs) stays above the fold; the header
  sticks. Keep this pattern for any future dense view.
- Coarse pointers get 40px targets; reduced-motion kills the pulse — both
  baked into ml.css; don't reimplement per page.

## Sub-theme: The Strait (toll ticket only)

One sanctioned exception to "one look everywhere", added Nov 2026 at the
user's request ("I want it to be separate"): the weekly low-score tax card
renders as the **Bab al-Mandab toll ticket** (`scripts/build_tax_tape.py`)
in a look that deliberately does NOT read as The Exchange —
`data-theme="strait"`:

- **Object:** a ferry/port toll ticket on a sea chart, not a banknote.
  A drawn chart of the strait heads the page (decorative geography, the
  vessel's route through the Gate), with a navy title cartouche; below,
  the ticket itself — signal-orange band, dotted-leader fields, boxed
  TOLL DUE, ASSESSED stamp, barcode, punched notches at the perforation,
  tear-off stub — then manifest-style tables with navy header bands.
- **Palette:** chart-sea page, ticket-paper panels, navy ink, and an
  international-orange **signal** used only for the ticket band, section
  ticks and the "next toll" cell. No banknote cream, no vault green, no
  gold, no guilloché lattice or rosettes (the compass rose is its
  ornament).
- **Type:** monospace-first (the data face) with heavy Archivo titles;
  no Cinzel anywhere on this card.
- **Allowed here only:** the round notches and the compass rose (circles
  outside `.ml-seal`), and a full-bleed page (zero PDF margin).

Rules that still hold inside it: flat (no shadows or gradients), static,
numbers right-aligned in `.ml-num`, traffic-light semantics keep their
meaning (toll due and losses in danger, net gains in success; semantic
text only on ticket paper, never on the sea). Scope is this one card —
no other surface may set `data-theme="strait"` or use `--ml-strait-*`.
The "MONEYLEAGUE Strait Authority" is a league joke and the fine print
says so; never imitate a real port, government or shipping body's marks.
Colors live in `color.surface.strait` / `color.strait`; every text pair is
gated in `scripts/check_a11y.py`.

## Off-brand (reject on sight)

Drop shadows · gradients anywhere but the masthead and the baked-in seal
tint · pill buttons · circles that aren't `.ml-seal` · money emoji or
dollar-sign clip-art in chrome (emoji in *status text* is fine) · Monopoly
man, casino anything — luck is the wrong story for an edge tool · tickers
that move, marquees, ambient motion of any kind · gold spent on anything
but market state and blue chip · green-tinting data that isn't gain/loss ·
GUAP or market slang replacing a real number · a new hue for a new feature
(map it to existing semantics) · color-only meaning · centered numbers in
tables (left text, right numerics, `.ml-num`) · Cinzel in body text or the
helper · headings that outweigh the data · a hex value outside
`design/tokens.json`.
