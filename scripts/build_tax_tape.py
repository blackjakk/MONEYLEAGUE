"""THE TAX TAPE — the weekly low-score tax, collected (rendered as the
Bab al-Mandab toll ticket since Nov 2026; filename unchanged).

A one-page Tuesday card: last week's high scorer and low scorer, the
fine that changed hands, and the season-to-date ledger. Reads live
2026 matchups straight from the Sleeper league dir (refetched every
Tuesday by fetch_sleeper.sh, so this always reflects the latest
completed week with zero manual upkeep).

Rule (truth #10, CLAUDE.md — 2022+ era, the current form): each
REGULAR-SEASON week, the low scorer pays the high scorer $15, +$5 for
every additional low week that manager has already had this season
(2nd low week = $20, 3rd = $25, ...). Playoff weeks (playoff_week_start
onward) don't tax. A week only counts once every roster in it has
actually scored (guards against a partially-played week showing as a
0.0 "low score").

Output: data/MONEYLEAGUE_TAX_TAPE.pdf (Letter portrait, one page).
"""
from __future__ import annotations

import glob
import html as _html
import json
from collections import defaultdict
from datetime import date
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from design.tokens import STRAIT, SURFACE_STRAIT, report_base_css  # noqa: E402
from design.guilloche import compass_svg  # noqa: E402
from scripts import build_power_rankings as bpr  # noqa: E402
from scripts.build_almanac import SHORT  # noqa: E402
from fantasy_draft.team_identity import load_identity  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
PDF_OUT = ROOT / "data" / "MONEYLEAGUE_TAX_TAPE.pdf"
JSON_OUT = ROOT / "data" / "research" / "tax_tape_2026.json"
SEASON = 2026
BASE_FINE = 15
ESCALATOR = 5


def esc(s) -> str:
    return _html.escape(str(s), quote=False)


def label(mid: str | None) -> str:
    return SHORT.get(mid, (mid or "?")[:4].upper())


SCHEDULE_URL = "https://api.sleeper.app/schedule/nfl/regular/{season}"


def finished_nfl_weeks(season: int = SEASON) -> set[int] | None:
    """NFL weeks whose EVERY game Sleeper marks 'complete', or None if the
    schedule can't be fetched. Guards the Monday-night trap: once every
    roster has some points the week LOOKS done, but MNF can still flip
    the low/high scorer (it did in Week 11, 2026: Trevor showed low on
    Sunday night, Donnie was low after Monday)."""
    import urllib.request
    try:
        with urllib.request.urlopen(SCHEDULE_URL.format(season=season),
                                    timeout=30) as r:
            games = json.loads(r.read().decode())
    except Exception as e:                               # noqa: BLE001
        print(f"[warn] NFL schedule unavailable ({e}); falling back to the "
              "all-rosters-scored guard only")
        return None
    by_week: dict[int, list[str]] = defaultdict(list)
    for g in games:
        by_week[int(g.get("week") or 0)].append(g.get("status") or "")
    return {w for w, sts in by_week.items()
            if sts and all(s == "complete" for s in sts)}


def load_weeks() -> dict[int, dict[int, float]]:
    """week -> {roster_id: points}, only for weeks that are OVER: every NFL
    game final (finished_nfl_weeks) and every roster has scored."""
    cfg = json.loads((ROOT / "configs/season_2026.json").read_text())
    mdir = ROOT / cfg["league_dir"] / "matchups"
    n_teams = 12
    done = finished_nfl_weeks()
    out: dict[int, dict[int, float]] = {}
    for f in sorted(glob.glob(str(mdir / "week_*.json")),
                    key=lambda p: int(Path(p).stem.split("_")[1])):
        wk = int(Path(f).stem.split("_")[1])
        rows = json.loads(Path(f).read_text())
        pts = {r["roster_id"]: float(r.get("points") or 0.0) for r in rows}
        if len(pts) < n_teams or any(v == 0.0 for v in pts.values()):
            continue        # not yet played (or only partially played)
        if done is not None and wk not in done:
            continue        # a game (usually MNF) is still to be played
        out[wk] = pts
    return out


NAVY = SURFACE_STRAIT["text"]        # all chart/ticket colors from tokens
SEA = SURFACE_STRAIT["bg"]


def _pts(points) -> str:
    return " ".join(f"{x},{y}" for x, y in points)


def strait_chart_svg(vessel: str) -> str:
    """Stylised sea chart of the Bab al-Mandab: Red Sea in from the
    north-west, the Gate between Yemen and Djibouti, out to the Gulf of
    Aden in the east. Decorative geography, not navigation."""
    w, h = 1000, 250
    yemen = [(500, 0), (1000, 0), (1000, 108), (860, 104), (720, 110),
             (610, 122), (566, 134), (552, 120), (536, 86), (516, 40)]
    africa = [(0, 0), (372, 0), (412, 46), (458, 92), (500, 124),
              (530, 150), (548, 170), (600, 176), (700, 184), (820, 188),
              (1000, 196), (1000, h), (0, h)]
    contours = []
    for k in range(9):
        y0 = 18 + k * 26
        d = "M0 %d " % y0 + " ".join(
            f"L{x} {y0 + 5 * ((x // 40) % 2)}" for x in range(40, w + 1, 40))
        contours.append(f'<path d="{d}"/>')
    route = [(392, 6), (430, 48), (474, 92), (520, 128), (556, 150),
             (640, 156), (760, 158), (900, 162), (990, 166)]
    rose = compass_svg(64, NAVY, 0.55)
    lbl = (f'font-family="IBM Plex Mono, monospace" font-size="11" '
           f'letter-spacing="3" fill="{SURFACE_STRAIT["muted"]}"')
    land_lbl = (f'font-family="IBM Plex Mono, monospace" font-size="10" '
                f'letter-spacing="4" fill="{SURFACE_STRAIT["muted"]}"')
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" '
        f'width="100%" '
        'role="img" aria-label="Chart of the Bab al-Mandab strait with the '
        f'vessel {vessel} in the Gate">'
        f'<rect width="{w}" height="{h}" fill="{SEA}"/>'
        f'<g fill="none" stroke="{STRAIT["contour"]}" stroke-width="0.8" '
        f'stroke-dasharray="2 4">{"".join(contours)}</g>'
        f'<polygon points="{_pts(yemen)}" fill="{STRAIT["land"]}" '
        f'stroke="{STRAIT["land_edge"]}" stroke-width="1.2"/>'
        f'<polygon points="{_pts(africa)}" fill="{STRAIT["land"]}" '
        f'stroke="{STRAIT["land_edge"]}" stroke-width="1.2"/>'
        f'<ellipse cx="551" cy="140" rx="5" ry="3" fill="{STRAIT["land"]}" '
        f'stroke="{STRAIT["land_edge"]}"/>'
        f'<polyline points="{_pts(route)}" fill="none" '
        f'stroke="{STRAIT["route"]}" stroke-width="2.2" '
        'stroke-dasharray="8 5"/>'
        f'<g transform="translate(540,140)"><polygon points="-9,-5 9,0 -9,5" '
        f'fill="{STRAIT["signal"]}" stroke="{NAVY}" stroke-width="1"/></g>'
        f'<text x="568" y="164" font-family="Archivo, sans-serif" '
        f'font-weight="800" font-size="15" fill="{NAVY}">{vessel}</text>'
        f'<text x="452" y="30" {lbl} transform="rotate(42 452 30)">RED SEA</text>'
        f'<text x="760" y="146" {lbl}>GULF OF ADEN</text>'
        f'<text x="800" y="52" {land_lbl}>YEMEN</text>'
        f'<text x="640" y="222" {land_lbl}>DJIBOUTI</text>'
        f'<text x="250" y="40" {land_lbl}>ERITREA</text>'
        f'<g transform="translate(900,170)">{rose}</g>'
        "</svg>")


def barcode_svg(code: str, width: int = 260, height: int = 34) -> str:
    """Deterministic decorative barcode from the ticket serial."""
    bars, x = [], 0.0
    seq = [int(c, 36) % 4 + 1 for c in code if c.isalnum()] * 3
    unit = width / (sum(seq) * 2)
    for i, n in enumerate(seq):
        if i % 2 == 0:
            bars.append(f'<rect x="{x:.1f}" y="0" width="{n * unit:.1f}" '
                        f'height="{height}"/>')
        x += n * unit * 2
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" '
            f'height="{height}" viewBox="0 0 {width} {height}" '
            f'aria-hidden="true"><g fill="{NAVY}">{"".join(bars)}</g></svg>')


def status(lows: int) -> str:
    if lows >= 3:
        return "aground"
    return "clear passage" if lows == 0 else "paid passage"


def main() -> None:
    lg = json.loads((ROOT / "configs/season_2026.json").read_text())
    league_meta = json.loads(
        (ROOT / lg["league_dir"] / "league.json").read_text())
    playoff_start = int(league_meta.get("settings", {})
                        .get("playoff_week_start") or 15)

    ident = load_identity(ROOT / "data/team_identity.json")
    rid_mid = {rec["sleeper_roster_id"]: mid
               for mid, rec in ident["managers"].items()
               if rec.get("sleeper_roster_id")}

    weeks = load_weeks()
    reg_weeks = {w: pts for w, pts in weeks.items() if w < playoff_start}

    prior_lows: dict[str, int] = defaultdict(int)
    ledger: dict[str, dict] = defaultdict(
        lambda: {"lows": 0, "paid": 0, "tops": 0, "collected": 0})
    tape: list[dict] = []
    for wk in sorted(reg_weeks):
        pts = reg_weeks[wk]
        rows = sorted(((rid_mid.get(rid, str(rid)), p)
                      for rid, p in pts.items()), key=lambda r: r[1])
        low_m, low_p = rows[0]
        top_m, top_p = rows[-1]
        fine = BASE_FINE + ESCALATOR * prior_lows[low_m]
        ledger[low_m]["lows"] += 1
        ledger[low_m]["paid"] += fine
        ledger[top_m]["tops"] += 1
        ledger[top_m]["collected"] += fine
        tape.append({"week": wk, "low": low_m, "low_pts": round(low_p, 2),
                    "top": top_m, "top_pts": round(top_p, 2),
                    "fine": fine, "low_week_no": prior_lows[low_m] + 1})
        prior_lows[low_m] += 1

    # every manager gets a row, even at 0-0 — this reads as a season
    # standings table, not just a log of who's been touched so far
    for mid in rid_mid.values():
        ledger[mid]  # noqa: B018 — touch to materialize the defaultdict row

    JSON_OUT.parent.mkdir(parents=True, exist_ok=True)
    JSON_OUT.write_text(json.dumps(
        {"season": SEASON, "generated": str(date.today()),
         "playoff_week_start": playoff_start, "tape": tape,
         "ledger": dict(ledger)}, indent=2))

    # ---------------- render: the Bab al-Mandab toll ticket ----------------
    # Theme (user, Nov 2026): the low scorer is a vessel forced through
    # the Gate of Tears and pays passage; the high scorer is that week's
    # harbor master and collects it. The "Strait Authority" is a league
    # joke, not a real port or government body (said so in fine print).
    latest = tape[-1] if tape else None
    ord_word = {1: "1st", 2: "2nd", 3: "3rd"}

    def ord_(n):
        return ord_word.get(n, f"{n}th")

    last_reg = playoff_start - 1
    done = max(reg_weeks) if reg_weeks else 0
    left = max(0, last_reg - done)

    def toll(n_prior: int) -> int:
        return BASE_FINE + ESCALATOR * n_prior

    if latest:
        no = f"BM-{SEASON}-W{latest['week']:02d}-{latest['low_week_no']:02d}"
        nxt = toll(latest["low_week_no"])
        vessel, payee = label(latest["low"]), label(latest["top"])
        chart = strait_chart_svg(esc(vessel))

        def field(k, v):
            return (f'<div class="f"><span class="k">{k}</span>'
                    f'<span class="dots"></span><span class="v">{v}</span></div>')

        ticket = (
            '<section class="tk" aria-label="Toll ticket">'
            '<div class="tk-main">'
            '<div class="tk-band"><span>MONEYLEAGUE STRAIT AUTHORITY</span>'
            f'<span>TRANSIT TOLL · WEEK {latest["week"]}</span></div>'
            '<div class="tk-body"><div class="tk-fields">'
            + field("VESSEL", f'<b class="xl">{esc(vessel)}</b>')
            + field("CARGO DECLARED", f'{latest["low_pts"]:.2f} PTS · '
                    'LOWEST IN FLEET')
            + field("PASSAGE CLASS", f'{ord_(latest["low_week_no"]).upper()} '
                    'TRANSIT THIS SEASON')
            + field("PAYABLE TO", f'{esc(payee)} · HARBOR MASTER · '
                    f'{latest["top_pts"]:.2f} PTS')
            + field("NEXT TRANSIT", f'${nxt}')
            + '</div><div class="tk-due"><span class="k">TOLL DUE</span>'
            f'<span class="amt">${latest["fine"]}</span>'
            '<span class="stamp">ASSESSED</span></div></div>'
            f'<div class="tk-foot">{barcode_svg(no)}'
            f'<span class="ser">No. {no}</span></div>'
            '</div>'
            '<div class="tk-stub"><div class="stub-band">STUB</div>'
            '<div class="stub-body">'
            '<span class="k">ADMIT ONE VESSEL</span>'
            f'<span class="route">{esc(vessel)}<br>↓<br>{esc(payee)}</span>'
            f'<span class="amt">${latest["fine"]}</span>'
            f'<span class="ser">{no}</span></div></div>'
            '</section>')
    else:
        chart = strait_chart_svg("—")
        ticket = ('<section class="tk"><div class="tk-main"><p class="pad">'
                  "The strait opens once Week 1 is fully scored. No tolls "
                  "assessed yet.</p></div></section>")

    max_n = max([v["lows"] for v in ledger.values()] + [0]) + left
    max_n = max(4, min(max_n, 8))
    cur = latest["low_week_no"] + 1 if latest else 1
    board = "".join(
        f'<div class="cell{" cur" if n == cur else ""}">'
        f'<span class="k">{ord_(n).upper()}</span>'
        f'<span class="v">${toll(n - 1)}</span></div>'
        for n in range(1, max_n + 1))

    def net_cell(v: int) -> str:
        cls = "gain" if v > 0 else ("loss" if v < 0 else "")
        return f'<td class="ml-num {cls}">{v:+d}</td>'

    ledger_rows = "".join(
        f'<tr><td>{esc(label(m))}</td>'
        f'<td class="ml-num">{v["lows"]}</td>'
        f'<td class="ml-num">${v["paid"]}</td>'
        f'<td class="ml-num">{v["tops"]}</td>'
        f'<td class="ml-num">${v["collected"]}</td>'
        + net_cell(v["collected"] - v["paid"])
        + (f'<td class="ml-num">${toll(v["lows"])}</td>' if left else
           '<td class="ml-num">—</td>')
        + f'<td class="st">{status(v["lows"]).upper()}</td></tr>'
        for m, v in sorted(ledger.items(),
                           key=lambda kv: (-(kv[1]["collected"] - kv[1]["paid"]),
                                           label(kv[0]))))

    log_rows = "".join(
        f'<tr><td class="ml-num">{t["week"]:02d}</td>'
        f'<td>{esc(label(t["low"]))}</td>'
        f'<td class="ml-num">{t["low_pts"]:.2f}</td>'
        f'<td>{esc(label(t["top"]))}</td>'
        f'<td class="ml-num">{t["top_pts"]:.2f}</td>'
        f'<td class="ml-num">${t["fine"]}</td></tr>'
        for t in reversed(tape))

    h = ['<html data-theme="strait"><head><meta charset="utf-8"><style>'
         + report_base_css() + """
    * { box-sizing: border-box; margin: 0; }
    html, body { background: var(--ml-bg); }
    body { font-family: var(--ml-font-data); font-size: 8.6pt;
           color: var(--ml-text); padding: 0 0 18px; }
    .chart { position: relative; line-height: 0;
             border-bottom: 3px solid var(--ml-strait-band); }
    .cartouche { position: absolute; left: 30px; bottom: 18px; line-height: 1.2;
                 background: var(--ml-strait-band);
                 color: var(--ml-strait-band-text); padding: 10px 16px 11px;
                 border-left: 6px solid var(--ml-strait-signal); }
    .cartouche .small { font-size: 6.5pt; letter-spacing: 2px; }
    .cartouche h1 { font-family: var(--ml-font-display); font-weight: 800;
                    font-size: 21pt; letter-spacing: 1px; margin: 2px 0;
                    color: var(--ml-strait-band-text); }
    .wrap { padding: 14px 30px 0; }
    .tk { position: relative; display: grid;
          grid-template-columns: 1fr 150px; background: var(--ml-panel);
          border: 1.5px solid var(--ml-strait-band); }
    .tk::before, .tk::after { content: ""; position: absolute;
          right: 142px; width: 16px; height: 16px; border-radius: 50%;
          background: var(--ml-bg); border: 1.5px solid var(--ml-strait-band); }
    .tk::before { top: -9px; } .tk::after { bottom: -9px; }
    .tk-band { display: flex; justify-content: space-between;
               background: var(--ml-strait-signal); color: var(--ml-text);
               font-weight: 700; letter-spacing: 2px; font-size: 7.5pt;
               padding: 5px 14px; }
    .tk-body { display: grid; grid-template-columns: 1fr 170px; gap: 14px;
               padding: 10px 14px 4px; }
    .f { display: flex; align-items: baseline; gap: 6px; margin: 4px 0; }
    .f .k, .tk-due .k, .stub-body .k { font-size: 7pt; letter-spacing: 2px;
                                       color: var(--ml-muted); }
    .f .dots { flex: 1; border-bottom: 1px dotted var(--ml-border-strong); }
    .f .v { font-weight: 700; }
    .xl { font-family: var(--ml-font-display); font-size: 16pt;
          letter-spacing: 1px; }
    .tk-due { position: relative; border: 1.5px solid var(--ml-strait-band);
              display: flex; flex-direction: column; align-items: center;
              justify-content: center; padding: 8px; }
    .amt { font-family: var(--ml-font-display); font-weight: 800;
           font-size: 30pt; color: var(--ml-danger); line-height: 1.05; }
    .stamp { position: absolute; bottom: -8px; right: -10px;
             transform: rotate(-9deg); border: 2px solid var(--ml-danger);
             color: var(--ml-danger); background: var(--ml-panel);
             font-weight: 700; letter-spacing: 3px; font-size: 8pt;
             padding: 1px 7px; }
    .tk-foot { display: flex; align-items: center; gap: 14px;
               padding: 6px 14px 10px; }
    .ser { font-size: 7.5pt; letter-spacing: 2px; color: var(--ml-muted); }
    .tk-stub { border-left: 2px dashed var(--ml-strait-band);
               display: flex; flex-direction: column; }
    .stub-band { background: var(--ml-strait-band);
                 color: var(--ml-strait-band-text); text-align: center;
                 letter-spacing: 4px; font-weight: 700; font-size: 7.5pt;
                 padding: 5px; }
    .stub-body { flex: 1; display: flex; flex-direction: column;
                 align-items: center; justify-content: space-around;
                 padding: 8px; text-align: center; }
    .stub-body .route { font-family: var(--ml-font-display); font-weight: 800;
                        font-size: 12pt; line-height: 1.15; }
    .stub-body .amt { font-size: 18pt; }
    .sec { font-family: var(--ml-font-display); font-weight: 800;
           letter-spacing: 2px; font-size: 9pt; margin: 14px 0 5px;
           display: flex; gap: 8px; align-items: center; }
    .sec::before { content: ""; width: 14px; height: 6px;
                   background: var(--ml-strait-signal); }
    .board { display: flex; gap: 6px; }
    .board .cell { flex: 1; background: var(--ml-panel);
                   border: 1px solid var(--ml-border-strong);
                   display: flex; justify-content: space-between;
                   padding: 4px 8px; }
    .board .cell .k { font-size: 7pt; letter-spacing: 2px;
                      color: var(--ml-muted); }
    .board .cell .v { font-weight: 700; }
    .board .cell.cur { background: var(--ml-strait-signal);
                       border-color: var(--ml-strait-band); }
    .board .cell.cur .k { color: var(--ml-text); }
    .cols { display: grid; grid-template-columns: 1.32fr 1fr; gap: 12px; }
    table.mf { width: 100%; border-collapse: collapse;
               background: var(--ml-panel);
               border: 1px solid var(--ml-strait-band); }
    table.mf th { background: var(--ml-strait-band);
                  color: var(--ml-strait-band-text); font-weight: 700;
                  font-size: 6.8pt; letter-spacing: 1.5px; text-align: left;
                  padding: 4px 5px; }
    table.mf th.ml-num { text-align: right; }
    table.mf td { padding: 3px 5px; font-size: 7.8pt;
                  border-top: 1px solid var(--ml-border); white-space: nowrap; }
    table.mf tr:nth-child(even) td { background: var(--ml-panel2); }
    td.gain { color: var(--ml-success); font-weight: 700; }
    td.loss { color: var(--ml-danger); font-weight: 700; }
    td.st { font-size: 6.8pt; letter-spacing: 1px; color: var(--ml-muted); }
    .rule { margin-top: 12px; font-size: 7.5pt; color: var(--ml-muted);
            line-height: 1.45; }
    .foot { margin-top: 8px; padding-top: 6px; font-size: 6.8pt;
            color: var(--ml-muted); border-top: 1px solid var(--ml-border-strong);
            display: flex; justify-content: space-between; }
    .pad { padding: 14px; }
    </style></head><body>"""]
    h.append('<div class="chart">' + chart
             + '<div class="cartouche"><div class="small">MONEYLEAGUE '
             'STRAIT AUTHORITY · 2026</div><h1>BAB AL-MANDAB</h1>'
             '<div class="small">TOLL TICKET · THE GATE OF TEARS · '
             f'{date.today():%d %b %Y}'.upper() + '</div></div></div>')
    h.append('<div class="wrap">')
    h.append(ticket)
    nxt_note = (f' · ORANGE = {esc(label(latest["low"]))}\'S NEXT TRANSIT'
                if latest else "")
    h.append('<div class="sec">TOLL BOARD · BY TRANSIT NUMBER THIS SEASON'
             f'{nxt_note}</div><div class="board">{board}</div>')
    ledger_body = (ledger_rows
                   or '<tr><td colspan="8">no weeks scored yet</td></tr>')
    log_body = log_rows or '<tr><td colspan="6">—</td></tr>'
    h.append('<div class="cols"><div><div class="sec">PORT MANIFEST · '
             'SEASON TO DATE</div><table class="mf"><thead><tr>'
             '<th>VESSEL</th><th class="ml-num">TRANSITS</th>'
             '<th class="ml-num">PAID</th><th class="ml-num">HARBOR</th>'
             '<th class="ml-num">COLLECTED</th><th class="ml-num">NET</th>'
             '<th class="ml-num">NEXT</th><th>STATUS</th></tr></thead>'
             f'<tbody>{ledger_body}</tbody></table></div>'
             '<div><div class="sec">TRANSIT LOG</div><table class="mf">'
             '<thead><tr><th class="ml-num">WK</th><th>PAID PASSAGE</th>'
             '<th class="ml-num">PTS</th><th>HARBOR MASTER</th>'
             '<th class="ml-num">PTS</th><th class="ml-num">TOLL</th>'
             f'</tr></thead><tbody>{log_body}</tbody></table></div></div>')
    h.append('<p class="rule">TARIFF · 2022+ RULE: each regular-season week '
             "the low scorer pays the high scorer $15, +$5 for every earlier "
             f"low week that manager has had this season. {left} regular-"
             f"season week{'s' if left != 1 else ''} left (through Week "
             f"{last_reg}); playoffs (Week {playoff_start}+) sail toll-free. A "
             "week is assessed only after its last NFL game (Monday night "
             "included) is final. Full rule "
             "history and the all-time purse: the Almanac.</p>")
    h.append('<div class="foot"><span>The MONEYLEAGUE Strait Authority is a '
             "league joke, not a port, government or shipping body. Chart "
             "is decorative, not for navigation.</span><span>Source: live "
             "Sleeper matchups, refetched every Tuesday.</span></div>")
    h.append("</div></body></html>")

    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch(executable_path=bpr.CHROMIUM_EXEC,
                              args=["--no-sandbox",
                                    "--disable-dev-shm-usage"])
        page = b.new_context(viewport={"width": 1000, "height": 1200}).new_page()
        page.set_content("\n".join(h), wait_until="networkidle")
        page.evaluate("document.fonts.ready")
        page.pdf(path=str(PDF_OUT), format="Letter",
                 margin={"top": "0", "bottom": "0", "left": "0", "right": "0"},
                 print_background=True)
        b.close()
    print(f"Wrote {PDF_OUT.relative_to(ROOT)} "
          f"({PDF_OUT.stat().st_size / 1024:.0f} KB); "
          f"{len(tape)} week(s) on the tape")


if __name__ == "__main__":
    main()
