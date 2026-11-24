"""MONEYLEAGUE accessibility enforcement. Run standalone or via verify_outputs.

Static regression guard for the July 2026 a11y hardening (docs/GOAL_A11Y.md,
audits A/B/C). It asserts the POST-FIX end-state of the draft helper and the
design system, so it FAILS on the pre-fix tree by design. Rules (each prints
per-violation detail; exit 1 on any violation):

  STRUCTURE   docs/draft_helper/index.html: exactly one <h1>; no <button>
              nested in any heading; <html lang=...>; a viewport meta tag.
  ARIA        index.html source (markup + JS templates): #search labelled;
              aria-pressed on every .ml-filter and on #ceiling-btn;
              role="status" on #live-status, #next-pick and a #sr-clock
              element; player rows and Top Recommendations rendered as real
              <button>s (row-draft / rec); .player-list-scroll is a named
              focusable region; rookie/keeper/injury badges carry aria-labels
              (injury = the FULL injury string, not injury[0]).
  RESPONSIVE  index.html page CSS: (max-width: 480px) column collapse hiding
              .player-list nth-child(3|4|5); a `min-width: 0` grid guard;
              overflow-x: auto on .player-list-scroll; (max-width: 900px)
              sticky header.
  CSS         design/ml.css: :focus-visible rule using --ml-focus;
              prefers-reduced-motion and pointer:coarse media blocks;
              .ml-visually-hidden and .ml-btn--bare utilities.
  CONTRAST    design/tokens.json + generated ml.css: WCAG 2.1 relative-
              luminance ratios for every fg/bg pair the helper renders as
              small text (>= 4.5) or UI boundary (>= 3.0). Badge/filter/clock
              text colors are read from the generated ml.css rules per theme,
              so the pairing checked is the pairing actually shipped.

Documented ARIA implementation choices (per audit K1/K2):
  * row-draft: pass if any <button> tag (markup or JS template literal) has a
    class containing "row-draft", OR createElement("button") appears together
    with the string row-draft (programmatic construction).
  * recs: the renderRecs() function body must create real buttons — it must
    contain `<button` or createElement("button"). If renderRecs was renamed,
    fall back to requiring a <button> whose class list contains "rec"
    anywhere in the source. Rec cards built as click-listener <div>s fail.

Usage:
    python3 scripts/check_a11y.py                     # full check
    python3 scripts/check_a11y.py --only contrast     # one rule group
    python3 scripts/check_a11y.py --only contrast --ratios   # dump all pairs
    python3 scripts/check_a11y.py --fixture-selftest
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HELPER = "docs/draft_helper/index.html"
ML_CSS = "design/ml.css"
TOKENS = "design/tokens.json"

HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)
CSS_COMMENT_RE = re.compile(r"/\*.*?\*/", re.DOTALL)
TAG_RE = re.compile(r"<[a-zA-Z][^<>]*>")
CREATE_BUTTON_RE = re.compile(r"createElement\(\s*[\"']button[\"']\s*\)")


# ---------------------------------------------------------------- helpers

def _blank(match: re.Match) -> str:
    """Replace a span with spaces, preserving newlines => line numbers."""
    return re.sub(r"[^\n]", " ", match.group(0))


def _line(text: str, pos: int) -> int:
    return text.count("\n", 0, pos) + 1


def _tags(html: str):
    """Yield (pos, tag_text) for every opening tag, attribute-order agnostic.
    Works inside JS template literals too (${...} interpolations are fine)."""
    for m in TAG_RE.finditer(html):
        yield m.start(), m.group(0)


def _attr(tag: str, name: str) -> str | None:
    """Value of an attribute inside one tag string, or None if absent."""
    m = re.search(rf"\b{re.escape(name)}\s*=\s*(\"([^\"]*)\"|'([^']*)')", tag)
    if m:
        return m.group(2) if m.group(2) is not None else m.group(3)
    m = re.search(rf"\b{re.escape(name)}\s*=\s*([^\s>\"']+)", tag)
    if m:
        return m.group(1)
    # bare boolean attribute (e.g. tabindex present with no value is invalid,
    # but `hidden`-style presence still counts as "present")
    if re.search(rf"\b{re.escape(name)}(?=[\s>])", tag):
        return ""
    return None


def _has_class_token(tag: str, cls: str) -> bool:
    v = _attr(tag, "class") or ""
    return re.search(rf"(^|\s){re.escape(cls)}($|\s)", v) is not None


def _tags_with_id(html: str, idval: str) -> list[tuple[int, str]]:
    return [(p, t) for p, t in _tags(html) if _attr(t, "id") == idval]


def _page_css(html: str) -> str:
    """Concatenated contents of all <style> blocks."""
    return "\n".join(m.group(1) for m in re.finditer(
        r"<style[^>]*>(.*?)</style>", html, re.DOTALL | re.IGNORECASE))


def _css_rules(css: str) -> list[tuple[str, str]]:
    """All leaf `selector { body }` pairs, including inside @media blocks."""
    css = CSS_COMMENT_RE.sub(_blank, css)
    return [(m.group(1).strip(), m.group(2))
            for m in re.finditer(r"([^{}]+)\{([^{}]*)\}", css)]


def _media_bodies(css: str, cond_re: str) -> list[str]:
    """Balanced-brace bodies of @media blocks whose condition matches."""
    css = CSS_COMMENT_RE.sub(_blank, css)
    out = []
    for m in re.finditer(r"@media\s*([^{]*)\{", css):
        if not re.search(cond_re, m.group(1)):
            continue
        depth, i = 1, m.end()
        while i < len(css) and depth:
            if css[i] == "{":
                depth += 1
            elif css[i] == "}":
                depth -= 1
            i += 1
        out.append(css[m.end():i - 1])
    return out


def _js_region(source: str, fname: str) -> str | None:
    """Body of `function fname(...)` up to the next top-level function."""
    m = re.search(rf"function\s+{re.escape(fname)}\s*\(", source)
    if not m:
        return None
    nxt = re.search(r"\nfunction\s+\w+\s*\(", source[m.end():])
    end = m.end() + (nxt.start() if nxt else len(source) - m.end())
    return source[m.start():end]


# ------------------------------------------------------------- STRUCTURE

def scan_structure(html: str, name: str) -> list[str]:
    out = []
    h = HTML_COMMENT_RE.sub(_blank, html)

    n_h1 = len(re.findall(r"<h1\b", h, re.IGNORECASE))
    if n_h1 != 1:
        out.append(f"STRUCTURE {name}: expected exactly one <h1>, "
                   f"found {n_h1}")

    for m in re.finditer(r"<h([1-6])\b[^>]*>(.*?)</h\1\s*>",
                         h, re.IGNORECASE | re.DOTALL):
        if re.search(r"<button\b", m.group(2), re.IGNORECASE):
            out.append(f"STRUCTURE {name}:{_line(h, m.start())}: <button> "
                       f"nested inside <h{m.group(1)}> (move it out of the "
                       f"heading, e.g. a .panel-head flex wrapper)")

    m = re.search(r"<html\b[^>]*>", h, re.IGNORECASE)
    if not m or _attr(m.group(0), "lang") in (None, ""):
        out.append(f"STRUCTURE {name}: <html> missing lang attribute")

    if not any(_attr(t, "name") == "viewport" for _, t in _tags(h)
               if t.lower().startswith("<meta")):
        out.append(f"STRUCTURE {name}: no <meta name=\"viewport\"> tag")
    return out


# ------------------------------------------------------------------ ARIA

def scan_aria(html: str, name: str) -> list[str]:
    out = []

    def need_attr(idval: str, attr: str, value: str | None = None) -> None:
        tags = _tags_with_id(html, idval)
        if not tags:
            out.append(f"ARIA {name}: no element with id=\"{idval}\"")
            return
        for pos, t in tags:
            v = _attr(t, attr)
            want = f'{attr}="{value}"' if value is not None else attr
            if v is None or (value is not None and v != value):
                out.append(f"ARIA {name}:{_line(html, pos)}: #{idval} "
                           f"missing {want}")

    # search labelled; toggle state exposed (audit K6/K7)
    need_attr("search", "aria-label")
    need_attr("ceiling-btn", "aria-pressed")
    # live regions (audit K3)
    need_attr("live-status", "role", "status")
    need_attr("next-pick", "role", "status")

    filters = [(p, t) for p, t in _tags(html)
               if t.lower().startswith("<button")
               and _has_class_token(t, "ml-filter")]
    if not filters:
        out.append(f"ARIA {name}: no .ml-filter buttons found")
    for pos, t in filters:
        if _attr(t, "aria-pressed") is None:
            out.append(f"ARIA {name}:{_line(html, pos)}: .ml-filter button "
                       f"({_attr(t, 'data-pos') or '?'}) missing "
                       f"aria-pressed")

    # visually-hidden SR clock announcer (audit K3)
    sr = _tags_with_id(html, "sr-clock")
    ok = any(_attr(t, "role") == "status" for _, t in sr)
    if not ok:
        m = re.search(r"sr-clock", html)
        ok = bool(m and re.search(
            r"setAttribute\(\s*[\"']role[\"']\s*,\s*[\"']status[\"']\s*\)",
            html[max(0, m.start() - 300):m.start() + 300]))
    if not ok:
        out.append(f"ARIA {name}: no element with id=\"sr-clock\" and "
                   f"role=\"status\" (SR on-the-clock announcer)")

    # player rows draftable via real buttons (audit K1)
    row_btn = any(t.lower().startswith("<button")
                  and "row-draft" in (_attr(t, "class") or "")
                  for _, t in _tags(html))
    if not row_btn:
        row_btn = bool(CREATE_BUTTON_RE.search(html)) and "row-draft" in html
    if not row_btn:
        out.append(f"ARIA {name}: no row-draft <button> in the player-row "
                   f"render (rows must be draftable by keyboard — "
                   f"<button class=\"ml-btn--bare row-draft\" ...>)")

    # rec cards are real buttons (audit K2)
    region = _js_region(html, "renderRecs")
    if region is not None:
        rec_ok = bool(re.search(r"<button\b", region)
                      or CREATE_BUTTON_RE.search(region))
    else:
        rec_ok = any(t.lower().startswith("<button")
                     and _has_class_token(t, "rec")
                     for _, t in _tags(html))
    if not rec_ok:
        out.append(f"ARIA {name}: Top Recommendations are not rendered as "
                   f"<button>s (renderRecs must build <button class=\"rec\"> "
                   f"or createElement(\"button\") — click-only divs fail)")

    # scroll container named + focusable (audit K11)
    pls = [(p, t) for p, t in _tags(html)
           if _has_class_token(t, "player-list-scroll")]
    if not pls:
        out.append(f"ARIA {name}: no .player-list-scroll element found")
    elif not any(_attr(t, "role") == "region"
                 and _attr(t, "tabindex") is not None for _, t in pls):
        out.append(f"ARIA {name}: .player-list-scroll needs role=\"region\" "
                   f"and tabindex (keyboard-scrollable outside Chromium)")

    # badge aria-labels (audit K9)
    for pos, t in _tags(html):
        if _has_class_token(t, "ml-badge--rookie") \
                and _attr(t, "aria-label") != "Rookie":
            out.append(f"ARIA {name}:{_line(html, pos)}: rookie badge "
                       f"missing aria-label=\"Rookie\"")
        if _has_class_token(t, "ml-badge--keeper") \
                and _attr(t, "aria-label") != "Keeper":
            out.append(f"ARIA {name}:{_line(html, pos)}: keeper badge "
                       f"missing aria-label=\"Keeper\"")
        if _has_class_token(t, "ml-badge--injury"):
            label = _attr(t, "aria-label")
            if label is None:
                out.append(f"ARIA {name}:{_line(html, pos)}: injury badge "
                           f"missing aria-label (full injury string)")
            elif "[0]" in label:
                out.append(f"ARIA {name}:{_line(html, pos)}: injury badge "
                           f"aria-label uses injury[0] — must be the FULL "
                           f"injury string (Questionable, not Q)")

    # interaction-states doctrine (DESIGN.md): boot failure must be an
    # announced alert with a retry, and the shell must expose its loading
    # state — silent blank screens are the pre-fix failure mode.
    if 'role="alert"' not in html:
        out.append(f"ARIA {name}: no role=\"alert\" boot-error surface "
                   f"(a data-load failure must be announced, not a blank "
                   f"screen)")
    if not re.search(r"<main\b[^>]*\baria-busy", html, re.IGNORECASE):
        out.append(f"ARIA {name}: <main> missing aria-busy loading state "
                   f"(skeletons render until the data bundle lands)")
    return out


# ------------------------------------------------------------ RESPONSIVE

def scan_responsive(css: str, name: str) -> list[str]:
    """Page CSS (contents of index.html <style>) — audits R1/R2/R4."""
    out = []

    m480 = _media_bodies(css, r"max-width\s*:\s*480px")
    if not m480:
        out.append(f"RESPONSIVE {name}: no @media (max-width: 480px) block "
                   f"(phone column collapse missing — audit R2)")
    else:
        body = "\n".join(m480)
        for n in (3, 4, 5):
            if not re.search(
                    rf"\.player-list[^{{}}]*nth-child\(\s*{n}\s*\)", body):
                out.append(f"RESPONSIVE {name}: 480px block does not hide "
                           f".player-list nth-child({n})")
        if not re.search(r"display\s*:\s*none", body):
            out.append(f"RESPONSIVE {name}: 480px block has no "
                       f"display: none (columns not actually hidden)")

    if not re.search(r"min-width\s*:\s*0", css):
        out.append(f"RESPONSIVE {name}: no `min-width: 0` grid guard "
                   f"(table min-content escapes the 1fr column — audit R1)")

    if not any(re.search(r"overflow-x\s*:\s*auto", body)
               for sel, body in _css_rules(css)
               if ".player-list-scroll" in sel):
        out.append(f"RESPONSIVE {name}: .player-list-scroll lacks "
                   f"overflow-x: auto (overflow must scroll inside the "
                   f"panel, never the page — audit R1)")

    m900 = _media_bodies(css, r"max-width\s*:\s*900px")
    sticky = any(
        "header" in sel and re.search(r"position\s*:\s*sticky", body)
        for b in m900 for sel, body in _css_rules(b))
    if not sticky:
        out.append(f"RESPONSIVE {name}: no (max-width: 900px) block with "
                   f"`position: sticky` for header (clock scrolls away "
                   f"during a live draft — audit R4)")
    return out


# ------------------------------------------------------------------- CSS

def scan_css(css: str, name: str) -> list[str]:
    """Generated design/ml.css — fix-contract components (audits K5/K15/R5/R8)."""
    out = []
    stripped = CSS_COMMENT_RE.sub(_blank, css)

    focus_rules = [body for sel, body in _css_rules(stripped)
                   if ":focus-visible" in sel]
    if not focus_rules:
        out.append(f"CSS {name}: no :focus-visible rule (visible focus "
                   f"contract — audit K5)")
    elif not any("--ml-focus" in b for b in focus_rules):
        out.append(f"CSS {name}: :focus-visible rule does not use "
                   f"var(--ml-focus)")
    if "--ml-focus" not in stripped:
        out.append(f"CSS {name}: --ml-focus token not defined")

    if not re.search(r"@media[^{]*prefers-reduced-motion\s*:\s*reduce",
                     stripped):
        out.append(f"CSS {name}: no @media (prefers-reduced-motion: reduce) "
                   f"block (ml-pulse must be killable — audits K15/R8)")
    if not re.search(r"@media[^{]*pointer\s*:\s*coarse", stripped):
        out.append(f"CSS {name}: no @media (pointer: coarse) block "
                   f"(40px touch targets — audit R5)")
    if ".ml-visually-hidden" not in stripped:
        out.append(f"CSS {name}: .ml-visually-hidden utility missing")
    if ".ml-btn--bare" not in stripped:
        out.append(f"CSS {name}: .ml-btn--bare reset missing (in-cell "
                   f"row-draft buttons depend on it)")

    # interaction-states component layer (DESIGN.md doctrine)
    for cls, why in ((".ml-skeleton", "loading skeletons"),
                     (".ml-empty", "empty states"),
                     (".ml-banner--error", "error banner"),
                     ('.ml-btn[aria-disabled="true"]',
                      "disabled-control styling")):
        if cls not in stripped:
            out.append(f"CSS {name}: {cls} missing ({why} — "
                       f"interaction-states doctrine)")
    # ml-flash (action receipt) exists => it must die under reduced motion
    if ".ml-flash" in stripped:
        rm = re.search(r"prefers-reduced-motion.*?(?=@media|\Z)",
                       stripped, re.DOTALL)
        if not rm or ".ml-flash" not in rm.group(0):
            out.append(f"CSS {name}: .ml-flash not inside the "
                       f"prefers-reduced-motion kill list")
    return out


# -------------------------------------------------------------- CONTRAST

def _parse_color(v: str) -> tuple[int, int, int] | None:
    v = v.strip().rstrip(";").strip()
    if v.lower() in ("white",):
        return (255, 255, 255)
    if v.lower() in ("black",):
        return (0, 0, 0)
    m = re.fullmatch(r"#([0-9a-fA-F]{3}|[0-9a-fA-F]{6})", v)
    if not m:
        return None
    h = m.group(1)
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))  # type: ignore


def _luminance(rgb: tuple[int, int, int]) -> float:
    def chan(c: int) -> float:
        c_ = c / 255.0
        return c_ / 12.92 if c_ <= 0.03928 else ((c_ + 0.055) / 1.055) ** 2.4
    r, g, b = rgb
    return 0.2126 * chan(r) + 0.7152 * chan(g) + 0.0722 * chan(b)


def contrast_ratio(fg: tuple[int, int, int], bg: tuple[int, int, int]) -> float:
    l1, l2 = sorted((_luminance(fg), _luminance(bg)), reverse=True)
    return (l1 + 0.05) / (l2 + 0.05)


def _tok(tokens: dict, path: str) -> str | None:
    node = tokens.get("color", {})
    for part in path.split("."):
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    return node if isinstance(node, str) else None


def _var_maps(css: str) -> tuple[dict, dict]:
    """--ml-* var -> raw value, per theme, scraped from ml.css blocks."""
    dark: dict[str, str] = {}
    light: dict[str, str] = {}
    for sel, body in _css_rules(css):
        decls = dict(re.findall(r"(--[\w-]+)\s*:\s*([^;}]+)", body))
        if not decls:
            continue
        if re.search(r"data-theme=[\"']light[\"']", sel):
            light.update(decls)
        elif ":root" in sel or re.search(r"data-theme=[\"']dark[\"']", sel):
            dark.update(decls)
    return dark, {**dark, **light}


def _resolve(value: str | None, varmap: dict,
             depth: int = 0) -> tuple[int, int, int] | None:
    if value is None or depth > 5:
        return None
    value = value.strip()
    m = re.match(r"var\(\s*(--[\w-]+)\s*(?:,([^)]*))?\)", value)
    if m:
        return _resolve(varmap.get(m.group(1), m.group(2)), varmap, depth + 1)
    return _parse_color(value)


def _component_fg_bg(rules: list[tuple[str, str]], cls: str, theme: str,
                     varmap: dict):
    """(found, fg_rgb, bg_rgb) for a component class in one theme.
    Base rules apply to both themes; [data-theme="light"] rules override
    for light. Later rules win, mirroring the cascade."""
    cls_re = re.compile(re.escape(cls) + r"(?![\w-])")
    fg_v = bg_v = None
    found = False
    passes = [False] if theme == "dark" else [False, True]
    for want_light in passes:
        for sel, body in rules:
            if not cls_re.search(sel):
                continue
            is_light = bool(re.search(r"data-theme=[\"']light[\"']", sel))
            if is_light != want_light:
                continue
            found = True
            m = re.search(r"(?:^|;)\s*color\s*:\s*([^;}]+)", body)
            if m:
                fg_v = m.group(1)
            m = re.search(r"(?:^|;)\s*background(?:-color)?\s*:\s*([^;}]+)",
                          body)
            if m:
                bg_v = m.group(1)
    if fg_v is None and cls.startswith(".ml-badge--"):
        for sel, body in rules:  # inherit base .ml-badge color
            if re.search(r"\.ml-badge(?![\w-])", sel):
                m = re.search(r"(?:^|;)\s*color\s*:\s*([^;}]+)", body)
                if m:
                    fg_v = m.group(1)
    return found, _resolve(fg_v, varmap), _resolve(bg_v, varmap)


# Small text (13px bold survival %, 10px badges) => 4.5. UI boundary => 3.0.
# (name suffix, fg token path, bg token path, minimum) — data-driven so a
# token retune needs no code change here.
def _token_pairs() -> list[tuple[str, str, str, float]]:
    pairs: list[tuple[str, str, str, float]] = []
    for theme in ("dark", "light"):
        s = f"surface.{theme}"
        for bgk in ("bg", "panel", "panel2", "row"):
            pairs.append((f"{theme} muted on {bgk}",
                          f"{s}.muted", f"{s}.{bgk}", 4.5))
            pairs.append((f"{theme} text on {bgk}",
                          f"{s}.text", f"{s}.{bgk}", 4.5))
        # "gold" joined the semantic text set with The Exchange theme
        # (July 2026): market-state/premium accent, themed like the others.
        for sem in ("success", "warn", "danger", "info", "gold"):
            for bgk in ("bg", "panel", "panel2"):
                pairs.append((f"{theme} {sem} text on {bgk}",
                              f"semantic.{sem}.{theme}", f"{s}.{bgk}", 4.5))
    # audit C1/C2: header foregrounds; C13: interactive control boundaries;
    # Exchange gold chip (closing bell / blue chip): dark-on-gold polarity,
    # one fixed pairing used in BOTH themes.
    pairs += [
        ("gold chip text on gold chip fill",
         "semantic.gold.chip_text", "semantic.gold.chip_bg", 4.5),
        ("on_brand on brand.header_a", "brand.on_brand", "brand.header_a", 4.5),
        ("on_brand on brand.header_b", "brand.on_brand", "brand.header_b", 4.5),
        ("dark border_strong vs panel",
         "surface.dark.border_strong", "surface.dark.panel", 3.0),
        ("dark border_strong vs panel2",
         "surface.dark.border_strong", "surface.dark.panel2", 3.0),
        ("light border_strong vs bg",
         "surface.light.border_strong", "surface.light.bg", 3.0),
        ("light border_strong vs panel2",
         "surface.light.border_strong", "surface.light.panel2", 3.0),
        # interaction-states doctrine: error banner text pairs, both themes
        ("dark danger text on error banner",
         "semantic.danger.dark", "banner.error_bg_dark", 4.5),
        ("dark text on error banner",
         "surface.dark.text", "banner.error_bg_dark", 4.5),
        ("light danger text on error banner",
         "semantic.danger.light", "banner.error_bg", 4.5),
        ("light text on error banner",
         "surface.light.text", "banner.error_bg", 4.5),
    ]
    # STRAIT sub-theme (toll ticket only, Nov 2026): its own surfaces with
    # the light semantics. Semantic (danger/success...) text only ever sits on
    # ticket paper (panel/panel2), never directly on the chart sea (bg).
    st = "surface.strait"
    for bgk in ("bg", "panel", "panel2", "row"):
        pairs.append((f"strait muted on {bgk}", f"{st}.muted", f"{st}.{bgk}", 4.5))
        pairs.append((f"strait text on {bgk}", f"{st}.text", f"{st}.{bgk}", 4.5))
    for sem in ("success", "danger", "info", "warn"):
        for bgk in ("panel", "panel2"):
            pairs.append((f"strait {sem} text on {bgk}",
                          f"semantic.{sem}.light", f"{st}.{bgk}", 4.5))
    pairs += [
        ("strait border_strong vs bg", f"{st}.border_strong", f"{st}.bg", 3.0),
        ("strait border_strong vs panel2",
         f"{st}.border_strong", f"{st}.panel2", 3.0),
        ("strait route line vs bg", "strait.route", f"{st}.bg", 3.0),
        ("strait text on signal band", f"{st}.text", "strait.signal", 4.5),
        ("strait band_text on band", "strait.band_text", "strait.band", 4.5),
        ("strait text on land", f"{st}.text", "strait.land", 4.5),
        ("strait muted on land", f"{st}.muted", "strait.land", 4.5),
    ]
    return pairs


# Component text-on-fill pairs; the ACTUAL text/fill colors are read from the
# generated ml.css rules (theme-aware), so whatever polarity the contrast fix
# chose (white vs black per badge, audit C20) is what gets verified.
COMPONENT_CLASSES = [
    ".ml-badge--qb", ".ml-badge--rb", ".ml-badge--wr", ".ml-badge--te",
    ".ml-badge--k", ".ml-badge--def",
    ".ml-badge--keeper", ".ml-badge--rookie", ".ml-badge--injury",
    ".ml-badge--bluechip",
    ".ml-filter.active",
    ".ml-filter--qb.active", ".ml-filter--rb.active", ".ml-filter--wr.active",
    ".ml-filter--te.active", ".ml-filter--k.active", ".ml-filter--def.active",
    ".ml-clock--me", ".ml-clock--soon", ".ml-btn--on",
]


def contrast_table(tokens: dict, css: str) -> list[tuple]:
    """[(pair name, ratio | None, minimum, note)] — ratio None = unresolvable."""
    rows: list[tuple] = []
    for pname, fg_path, bg_path, minimum in _token_pairs():
        fg, bg = _tok(tokens, fg_path), _tok(tokens, bg_path)
        if fg is None or bg is None:
            missing = fg_path if fg is None else bg_path
            rows.append((pname, None, minimum,
                         f"token color.{missing} missing (required by the "
                         f"a11y contract — audit C1/C13)"))
            continue
        fg_rgb, bg_rgb = _parse_color(fg), _parse_color(bg)
        if fg_rgb is None or bg_rgb is None:
            rows.append((pname, None, minimum, "non-hex token value"))
            continue
        rows.append((pname, contrast_ratio(fg_rgb, bg_rgb), minimum, ""))

    rules = _css_rules(css)
    dark_vars, light_vars = _var_maps(css)
    for cls in COMPONENT_CLASSES:
        for theme, varmap in (("dark", dark_vars), ("light", light_vars)):
            found, fg_rgb, bg_rgb = _component_fg_bg(rules, cls, theme, varmap)
            pname = f"{theme} {cls} text on fill"
            if not found:
                rows.append((pname, None, 4.5,
                             f"no {cls} rule in ml.css"))
                continue
            if fg_rgb is None or bg_rgb is None:
                which = "text color" if fg_rgb is None else "background"
                rows.append((pname, None, 4.5,
                             f"cannot resolve {which} for {cls} ({theme})"))
                continue
            rows.append((pname, contrast_ratio(fg_rgb, bg_rgb), 4.5, ""))
    return rows


def contrast_violations(rows: list[tuple], name: str) -> list[str]:
    out = []
    for pname, ratio, minimum, note in rows:
        if ratio is None:
            out.append(f"CONTRAST {name}: {pname}: {note}")
        elif ratio < minimum:
            out.append(f"CONTRAST {name}: {pname}: {ratio:.2f} < {minimum}")
    return out


# ---------------------------------------------------------- file wrappers

def _read(rel: str) -> str | None:
    p = ROOT / rel
    return p.read_text() if p.exists() else None


def check_structure() -> list[str]:
    text = _read(HELPER)
    if text is None:
        return [f"STRUCTURE {HELPER}: file missing"]
    return scan_structure(text, HELPER)


def check_aria() -> list[str]:
    text = _read(HELPER)
    if text is None:
        return [f"ARIA {HELPER}: file missing"]
    return scan_aria(text, HELPER)


def check_responsive() -> list[str]:
    text = _read(HELPER)
    if text is None:
        return [f"RESPONSIVE {HELPER}: file missing"]
    return scan_responsive(_page_css(text), HELPER)


def check_css() -> list[str]:
    text = _read(ML_CSS)
    if text is None:
        return [f"CSS {ML_CSS}: file missing"]
    return scan_css(text, ML_CSS)


def check_contrast() -> list[str]:
    tokens_text, css_text = _read(TOKENS), _read(ML_CSS)
    if tokens_text is None:
        return [f"CONTRAST {TOKENS}: file missing"]
    if css_text is None:
        return [f"CONTRAST {ML_CSS}: file missing"]
    return contrast_violations(
        contrast_table(json.loads(tokens_text), css_text),
        f"{TOKENS}+ml.css")


RULES = {
    "structure": ("STRUCTURE", check_structure),
    "aria": ("ARIA", check_aria),
    "responsive": ("RESPONSIVE", check_responsive),
    "css": ("CSS", check_css),
    "contrast": ("CONTRAST", check_contrast),
}


# --------------------------------------------------------------- selftest
# Fixtures model the FINAL (post-a11y-fix) and violating (pre-fix) states.

GOOD_HTML = """<!DOCTYPE html>
<html lang="en" data-theme="dark">
<head>
<meta charset="utf-8">
<meta content="width=device-width, initial-scale=1" name="viewport">
<title>helper</title>
<style>
  main { display: grid; grid-template-columns: 1fr 380px; }
  main > * { min-width: 0; }
  .player-list-scroll { max-height: 70vh; overflow-y: auto; overflow-x: auto; }
  @media (max-width: 900px) {
    main { grid-template-columns: 1fr; }
    header { position: sticky; top: 0; z-index: 10; }
  }
  @media (max-width: 480px) {
    .player-list th:nth-child(3), .player-list td:nth-child(3),
    .player-list th:nth-child(4), .player-list td:nth-child(4),
    .player-list th:nth-child(5), .player-list td:nth-child(5)
    { display: none; }
  }
</style>
</head>
<body>
<header>
  <h1 class="title">BRIAN'S 2026 DRAFT HELPER</h1>
  <button id="ceiling-btn" class="ml-btn" aria-pressed="false">CEILING</button>
  <span id="live-status" role="status" aria-live="polite"></span>
  <div id="sr-clock" class="ml-visually-hidden" role="status"></div>
</header>
<div id="boot-error" hidden><div class="ml-banner--error" role="alert">
  <strong>MARKET DATA UNAVAILABLE</strong>
  <button class="ml-btn" id="boot-retry">Retry</button></div></div>
<main aria-busy="true">
  <h2>Available Players</h2>
  <input id="search" class="ml-input" type="search"
         aria-label="Search players by name" placeholder="Search by name">
  <button class="ml-filter active" aria-pressed="true" data-pos="ALL">All</button>
  <button aria-pressed="false" class="ml-filter ml-filter--qb" data-pos="QB">QB</button>
  <div class="player-list-scroll" role="region" tabindex="0"
       aria-label="Available players table"></div>
  <div id="next-pick" role="status" class="next-pick-info">&mdash;</div>
  <div class="panel-head"><h2>Recent Picks</h2>
    <button class="ml-btn" id="undo">undo last</button></div>
</main>
<script>
function renderPlayerList() {
  const nameCell = `<button class="ml-btn--bare row-draft"
    aria-label="Draft ${p.player}">${p.player}</button>`;
  const rookieTag = ' <span class="ml-badge ml-badge--rookie" aria-label="Rookie">R</span>';
  const injTag = ` <span class="ml-badge ml-badge--injury" aria-label="${p.injury}">${p.injury[0]}</span>`;
  const keepTag = ' <span class="ml-badge ml-badge--keeper" aria-label="Keeper">K</span>';
}
function renderRecs() {
  const b = document.createElement("button");
  b.className = "rec";
}
</script>
</body></html>
"""

# Modeled on the real pre-fix helper: every rule group must fire.
BAD_HTML = """<html data-theme="dark">
<head><title>helper</title>
<style>
  main { display: grid; grid-template-columns: 1fr 380px; }
  .player-list-scroll { max-height: 70vh; overflow-y: auto; }
  @media (max-width: 900px) { main { grid-template-columns: 1fr; } }
</style>
</head>
<body>
<header>
  <div class="title">BRIAN'S 2026 DRAFT HELPER</div>
  <button id="ceiling-btn" class="ml-btn">CEILING</button>
  <span id="live-status"></span>
</header>
<main>
  <input id="search" class="ml-input" type="search" placeholder="Search">
  <button class="ml-filter active" data-pos="ALL">All</button>
  <button class="ml-filter" data-pos="QB">QB</button>
  <div class="player-list-scroll"></div>
  <div id="next-pick" class="next-pick-info">&mdash;</div>
  <h2>Recent Picks <button class="ml-btn" id="undo">undo last</button></h2>
</main>
<script>
function renderPlayerList() {
  const tr = document.createElement("tr");
  const rookieTag = ' <span class="ml-badge ml-badge--rookie">R</span>';
  const injTag = ` <span class="ml-badge ml-badge--injury" aria-label="${p.injury[0]}">${p.injury[0]}</span>`;
  const keepTag = ' <span class="ml-badge ml-badge--keeper">K</span>';
}
function renderRecs() {
  const div = document.createElement("div");
  div.className = "rec";
  div.addEventListener("click", () => draftPlayer(p));
}
</script>
</body></html>
"""

TWO_H1_HTML = """<html lang="en"><head>
<meta name="viewport" content="width=device-width"></head>
<body><h1>a</h1><h1>b</h1></body></html>"""

GOOD_CSS = """
:root, [data-theme="dark"] { --ml-focus: #7dd3fc; }
[data-theme="light"] { --ml-focus: #0369a1; }
:focus-visible { outline: 2px solid var(--ml-focus); outline-offset: 1px; }
.ml-visually-hidden { position: absolute; width: 1px; height: 1px;
  clip: rect(0 0 0 0); overflow: hidden; }
.ml-btn--bare { background: none; border: 0; color: inherit; font: inherit; }
.ml-skeleton { display: inline-block; background: var(--ml-panel2); }
.ml-empty { padding: 14px 10px; color: var(--ml-muted); }
.ml-banner--error { background: var(--ml-banner-error-bg);
  border: 1px solid var(--ml-banner-error-border); }
.ml-btn[disabled], .ml-btn[aria-disabled="true"] { color: var(--ml-muted);
  cursor: not-allowed; }
@keyframes ml-receipt { from { background-color: var(--ml-mine-tint); }
  to { background-color: transparent; } }
.ml-flash { animation: ml-receipt 900ms ease-out 1; }
@media (prefers-reduced-motion: reduce) {
  .ml-btn--on, .ml-clock--me, .ml-clock--soon, .ml-flash { animation: none; }
}
@media (pointer: coarse) { .ml-btn, .ml-filter { min-height: 40px; } }
"""

BAD_CSS = """
/* pre-fix ml.css: :focus-visible mentioned only in this comment */
.ml-btn { color: var(--ml-text); }
"""

# Post-fix token values from audit C's verified table.
GOOD_TOKENS = {"color": {
    "position": {"QB": "#dc2626", "RB": "#0e7490", "WR": "#15803d",
                 "TE": "#f59e0b", "K": "#9a3412", "DEF": "#525252"},
    "semantic": {"success": {"light": "#15803d", "dark": "#4ade80"},
                 "warn": {"light": "#b45309", "dark": "#f59e0b"},
                 "danger": {"light": "#c81e1e", "dark": "#f87171"},
                 "info": {"light": "#0369a1", "dark": "#60a5fa"},
                 "keeper": {"light": "#0369a1", "dark": "#60a5fa"},
                 "gold": {"light": "#7d6010", "dark": "#e8c76a",
                          "chip_bg": "#d4a017", "chip_text": "#14130a"}},
    "surface": {"dark": {"bg": "#0b0d10", "panel": "#14171c",
                         "panel2": "#1c2027", "border": "#262b33",
                         "border_strong": "#66707d", "row": "#1a1d22",
                         "text": "#e8eaee", "muted": "#8a93a0"},
                "light": {"bg": "#ffffff", "panel": "#ffffff",
                          "panel2": "#f1f5f9", "border": "#d8dce2",
                          "border_strong": "#767f8b", "row": "#f0f2f5",
                          "text": "#1a1d24", "muted": "#5d6673"}},
    "brand": {"header_a": "#0f766e", "header_b": "#0e7490",
              "on_brand": "#ffffff"},
    "banner": {"warn_bg": "#fff7ed", "warn_border": "#fed7aa",
               "error_bg": "#f7e3dc", "error_border": "#c98d7e",
               "error_bg_dark": "#2c1614", "error_border_dark": "#8a4a40"},
}}

GOOD_TOKENS_CSS = """
:root, [data-theme="dark"] {
  --ml-pos-qb: #dc2626; --ml-pos-rb: #0e7490; --ml-pos-wr: #15803d;
  --ml-pos-te: #f59e0b; --ml-pos-k: #9a3412; --ml-pos-def: #525252;
  --ml-success: #4ade80; --ml-warn: #f59e0b; --ml-danger: #f87171;
  --ml-keeper: #60a5fa;
  --ml-gold-chip: #d4a017; --ml-gold-chip-text: #14130a;
}
[data-theme="light"] {
  --ml-success: #15803d; --ml-warn: #b45309; --ml-danger: #c81e1e;
  --ml-keeper: #0369a1;
}
.ml-badge { color: #fff; }
.ml-badge--bluechip { background: var(--ml-gold-chip); color: var(--ml-gold-chip-text); }
.ml-badge--qb { background: var(--ml-pos-qb); color: #fff; }
.ml-badge--rb { background: var(--ml-pos-rb); color: #fff; }
.ml-badge--wr { background: var(--ml-pos-wr); color: #fff; }
.ml-badge--te { background: var(--ml-pos-te); color: #000; }
.ml-badge--k { background: var(--ml-pos-k); color: #fff; }
.ml-badge--def { background: var(--ml-pos-def); color: #fff; }
.ml-badge--keeper { background: var(--ml-keeper); color: #000; }
.ml-badge--rookie { background: var(--ml-warn); color: #000; }
.ml-badge--injury { background: var(--ml-danger); color: #000; }
[data-theme="light"] .ml-badge--keeper { color: #fff; }
[data-theme="light"] .ml-badge--rookie { color: #fff; }
[data-theme="light"] .ml-badge--injury { color: #fff; }
.ml-filter.active { background: var(--ml-success); color: #000; }
[data-theme="light"] .ml-filter.active { color: #fff; }
.ml-filter--qb.active { background: var(--ml-pos-qb); color: #fff; }
.ml-filter--rb.active { background: var(--ml-pos-rb); color: #fff; }
.ml-filter--wr.active { background: var(--ml-pos-wr); color: #fff; }
.ml-filter--te.active { background: var(--ml-pos-te); color: #000; }
.ml-filter--k.active { background: var(--ml-pos-k); color: #fff; }
.ml-filter--def.active { background: var(--ml-pos-def); color: #fff; }
.ml-clock--me { background: var(--ml-success); color: #000; }
.ml-clock--soon { background: var(--ml-warn); color: #000; }
[data-theme="light"] .ml-clock--me { color: #fff; }
[data-theme="light"] .ml-clock--soon { color: #fff; }
.ml-btn--on { background: var(--ml-danger); color: #000; }
[data-theme="light"] .ml-btn--on { color: #fff; }
"""

# Pre-fix values: light success/warn fail as text, TE/WR/RB badges fail,
# on_brand / border_strong tokens absent.
BAD_TOKENS = {"color": {
    "position": {"QB": "#dc2626", "RB": "#0891b2", "WR": "#16a34a",
                 "TE": "#f59e0b", "K": "#9a3412", "DEF": "#525252"},
    "semantic": {"success": {"light": "#16a34a", "dark": "#4ade80"},
                 "warn": {"light": "#d97706", "dark": "#f59e0b"},
                 "danger": {"light": "#dc2626", "dark": "#ef4444"},
                 "info": {"light": "#0369a1", "dark": "#60a5fa"},
                 "keeper": {"light": "#0369a1", "dark": "#60a5fa"},
                 "gold": {"light": "#d4a017", "dark": "#e8c76a",
                          "chip_bg": "#d4a017", "chip_text": "#ffffff"}},
    "surface": {"dark": {"bg": "#0b0d10", "panel": "#14171c",
                         "panel2": "#1c2027", "border": "#262b33",
                         "row": "#1a1d22",
                         "text": "#e8eaee", "muted": "#8a93a0"},
                "light": {"bg": "#ffffff", "panel": "#ffffff",
                          "panel2": "#f1f5f9", "border": "#d8dce2",
                          "row": "#f0f2f5",
                          "text": "#1a1d24", "muted": "#66707d"}},
    "brand": {"header_a": "#14b8a6", "header_b": "#0891b2"},
}}

BAD_TOKENS_CSS = """
:root, [data-theme="dark"] {
  --ml-pos-te: #f59e0b; --ml-danger: #ef4444; --ml-keeper: #60a5fa;
}
[data-theme="light"] { --ml-danger: #dc2626; --ml-keeper: #0369a1; }
.ml-badge--te { background: var(--ml-pos-te); color: #fff; }
.ml-badge--injury { background: var(--ml-danger); color: #fff; }
.ml-badge--keeper { background: var(--ml-keeper); color: #000; }
"""


def selftest() -> int:
    failures: list[str] = []

    def check(name: str, ok: bool, detail: str = "") -> None:
        print(f"  [{'ok ' if ok else 'FAIL'}] {name}"
              + (f" — {detail}" if detail and not ok else ""))
        if not ok:
            failures.append(name)

    def has(v: list[str], frag: str) -> bool:
        return any(frag in x for x in v)

    print("fixture selftest:")

    # STRUCTURE
    v = scan_structure(GOOD_HTML, "good.html")
    check("structure: good HTML passes", not v, str(v))
    v = scan_structure(BAD_HTML, "bad.html")
    check("structure: missing h1 fires", has(v, "exactly one <h1>, found 0"))
    check("structure: button-in-heading fires", has(v, "nested inside <h2>"))
    check("structure: missing lang fires", has(v, "missing lang"))
    check("structure: missing viewport fires", has(v, "viewport"))
    check("structure: bad HTML fires exactly 4", len(v) == 4, str(v))
    v = scan_structure(TWO_H1_HTML, "two_h1.html")
    check("structure: two h1s fire the exactly-one rule",
          has(v, "exactly one <h1>, found 2") and len(v) == 1, str(v))

    # ARIA
    v = scan_aria(GOOD_HTML, "good.html")
    check("aria: good HTML (attr order shuffled) passes", not v, str(v))
    v = scan_aria(BAD_HTML, "bad.html")
    check("aria: unlabelled #search fires", has(v, "#search missing aria-label"))
    check("aria: filter without aria-pressed fires (both filters)",
          sum(".ml-filter button" in x for x in v) == 2, str(v))
    check("aria: #ceiling-btn aria-pressed fires",
          has(v, "#ceiling-btn missing aria-pressed"))
    check("aria: #live-status role=status fires",
          has(v, '#live-status missing role="status"'))
    check("aria: #next-pick role=status fires",
          has(v, '#next-pick missing role="status"'))
    check("aria: missing sr-clock fires", has(v, "sr-clock"))
    check("aria: missing row-draft button fires", has(v, "row-draft"))
    check("aria: div-based recs fire", has(v, "Top Recommendations"))
    check("aria: scroll region role/tabindex fires",
          has(v, ".player-list-scroll needs"))
    check("aria: rookie badge label fires", has(v, "rookie badge"))
    check("aria: keeper badge label fires", has(v, "keeper badge"))
    check("aria: injury[0] aria-label fires", has(v, "FULL injury string"))
    check("aria: missing boot-error alert fires", has(v, 'role="alert"'))
    check("aria: missing main aria-busy fires", has(v, "aria-busy"))

    # RESPONSIVE
    v = scan_responsive(_page_css(GOOD_HTML), "good.html")
    check("responsive: good page CSS passes", not v, str(v))
    v = scan_responsive(_page_css(BAD_HTML), "bad.html")
    check("responsive: missing 480px collapse fires", has(v, "480px"))
    check("responsive: missing min-width 0 fires", has(v, "min-width: 0"))
    check("responsive: missing overflow-x fires", has(v, "overflow-x"))
    check("responsive: missing sticky header fires", has(v, "sticky"))
    partial = ("@media (max-width: 480px) { .player-list td:nth-child(3) "
               "{ display: none; } }")
    v = scan_responsive(partial, "partial.css")
    check("responsive: 480px block missing nth-child(4) and (5) fires",
          has(v, "nth-child(4)") and has(v, "nth-child(5)")
          and not has(v, "nth-child(3)"), str(v))

    # CSS
    v = scan_css(GOOD_CSS, "good.css")
    check("css: good ml.css passes", not v, str(v))
    v = scan_css(BAD_CSS, "bad.css")
    check("css: focus-visible in comments only still fires",
          has(v, ":focus-visible"))
    check("css: reduced-motion fires", has(v, "prefers-reduced-motion"))
    check("css: pointer coarse fires", has(v, "pointer: coarse"))
    check("css: visually-hidden fires", has(v, ".ml-visually-hidden"))
    check("css: btn--bare fires", has(v, ".ml-btn--bare"))
    check("css: skeleton fires", has(v, ".ml-skeleton"))
    check("css: empty-state fires", has(v, ".ml-empty"))
    check("css: error banner fires", has(v, ".ml-banner--error"))
    check("css: disabled styling fires", has(v, 'aria-disabled="true"'))
    v = scan_css(GOOD_CSS.replace(
        ".ml-btn--on, .ml-clock--me, .ml-clock--soon, .ml-flash "
        "{ animation: none; }",
        ".ml-btn--on, .ml-clock--me, .ml-clock--soon { animation: none; }"),
        "flashless.css")
    check("css: ml-flash outside reduced-motion kill fires",
          has(v, ".ml-flash not inside"), str(v))
    focus_no_token = ":focus-visible { outline: 2px solid red; }"
    v = scan_css(focus_no_token + GOOD_CSS.replace(
        ":focus-visible { outline: 2px solid var(--ml-focus); "
        "outline-offset: 1px; }", ""), "mixed.css")
    check("css: focus-visible without --ml-focus fires",
          has(v, "does not use"), str(v))

    # CONTRAST — math first (spot values from audit C appendix)
    r = contrast_ratio(_parse_color("#8a93a0"), _parse_color("#1c2027"))
    check("contrast math: dark muted/panel2 = 5.26 (audit C)",
          abs(r - 5.26) < 0.02, f"got {r:.3f}")
    r = contrast_ratio(_parse_color("#ffffff"), _parse_color("#f59e0b"))
    check("contrast math: white/TE = 2.15 (audit C4)",
          abs(r - 2.15) < 0.02, f"got {r:.3f}")
    r = contrast_ratio(_parse_color("#fff"), _parse_color("#0f766e"))
    check("contrast math: #rgb parse + on_brand/header_a = 5.47 (audit C1)",
          abs(r - 5.47) < 0.02, f"got {r:.3f}")

    v = contrast_violations(
        contrast_table(GOOD_TOKENS, GOOD_TOKENS_CSS), "good")
    check("contrast: post-fix tokens + polarity-fixed ml.css pass", not v,
          str(v))
    v = contrast_violations(contrast_table(BAD_TOKENS, BAD_TOKENS_CSS), "bad")
    check("contrast: light success text fires (3.30 < 4.5)",
          has(v, "light success text on bg"))
    check("contrast: light warn text fires", has(v, "light warn text on"))
    check("contrast: dark danger on panel2 fires (4.34)",
          has(v, "dark danger text on panel2"))
    check("contrast: missing on_brand token fires",
          has(v, "brand.on_brand missing"))
    check("contrast: missing border_strong token fires",
          has(v, "border_strong missing"))
    check("contrast: white-on-TE badge fires (reads ml.css polarity)",
          has(v, ".ml-badge--te"))
    check("contrast: dark injury badge white-on-danger fires (3.76)",
          has(v, "dark .ml-badge--injury"))
    check("contrast: light keeper badge black-on-info fires (3.54)",
          has(v, "light .ml-badge--keeper"))
    check("contrast: light injury (white on #dc2626 = 4.83) passes",
          not has(v, "light .ml-badge--injury"), str(v))
    check("contrast: dark keeper (black on #60a5fa = 8.26) passes",
          not has(v, "dark .ml-badge--keeper"), str(v))
    check("contrast: absent component rules reported, not crashed",
          has(v, "no .ml-clock--me rule"))
    # Exchange gold pairs (July 2026): raw gold as light-theme text fails,
    # white-on-gold chip fails — the measured pairings are #7d6010 text and
    # #14130a chip text, modeled in the GOOD fixtures.
    check("contrast: light gold text on white fires (2.38 < 4.5)",
          has(v, "light gold text on bg"))
    check("contrast: dark gold text passes on dark panels",
          not has(v, "dark gold text on"), str(v))
    check("contrast: white-on-gold chip fires (2.38 < 4.5)",
          has(v, "gold chip text on gold chip fill"))
    check("contrast: absent bluechip rule reported, not crashed",
          has(v, "no .ml-badge--bluechip rule"))

    print()
    if failures:
        print(f"selftest: {len(failures)} assertion(s) FAILED")
        return 1
    print("selftest: all assertions passed")
    return 0


# ------------------------------------------------------------------- main

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--fixture-selftest", action="store_true",
                    help="validate the checker against embedded fixtures")
    ap.add_argument("--only", action="append", choices=sorted(RULES),
                    help="run only the named rule group(s)")
    ap.add_argument("--ratios", action="store_true",
                    help="print every evaluated contrast pair with its ratio")
    args = ap.parse_args(argv)

    if args.fixture_selftest:
        return selftest()

    if args.ratios:
        tokens_text, css_text = _read(TOKENS), _read(ML_CSS)
        if tokens_text and css_text:
            for pname, ratio, minimum, note in contrast_table(
                    json.loads(tokens_text), css_text):
                if ratio is None:
                    print(f"  ?    {pname}: {note}")
                else:
                    mark = "ok  " if ratio >= minimum else "FAIL"
                    print(f"  {mark} {pname}: {ratio:.2f} (min {minimum})")
            print()

    selected = args.only or list(RULES)
    all_violations: list[str] = []
    for key in RULES:
        if key not in selected:
            continue
        label, fn = RULES[key]
        violations = fn()
        print(f"{label}: {len(violations)} violation(s)")
        for v in violations:
            print(f"  FAIL {v}")
        all_violations.extend(violations)

    print()
    if all_violations:
        print(f"✗ a11y check FAILED with {len(all_violations)} violation(s). "
              f"Fix per the ownership contract: page markup/CSS -> "
              f"docs/draft_helper/index.html; tokens/components -> "
              f"design/tokens.json + design/build_design.py (regenerate, "
              f"never hand-edit ml.css). See docs/GOAL_A11Y.md and the "
              f"a11y-review skill.")
        return 1
    print("✓ a11y check passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
