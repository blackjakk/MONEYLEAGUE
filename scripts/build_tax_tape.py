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

from design.tokens import SURFACE_STRAIT, report_base_css  # noqa: E402
from design.guilloche import compass_svg, wave_svg  # noqa: E402
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


def load_weeks() -> dict[int, dict[int, float]]:
    """week -> {roster_id: points}, only for weeks every roster has
    actually scored (guards a live/partially-played week)."""
    cfg = json.loads((ROOT / "configs/season_2026.json").read_text())
    mdir = ROOT / cfg["league_dir"] / "matchups"
    n_teams = 12
    out: dict[int, dict[int, float]] = {}
    for f in sorted(glob.glob(str(mdir / "week_*.json")),
                    key=lambda p: int(Path(p).stem.split("_")[1])):
        wk = int(Path(f).stem.split("_")[1])
        rows = json.loads(Path(f).read_text())
        pts = {r["roster_id"]: float(r.get("points") or 0.0) for r in rows}
        if len(pts) < n_teams or any(v == 0.0 for v in pts.values()):
            continue        # not yet played (or only partially played)
        out[wk] = pts
    return out


STRAIT_INK = SURFACE_STRAIT["text"]   # engraving ink, from tokens


def strait_masthead(title: str, subtitle: str) -> str:
    """The toll ticket's own masthead: sea-chart swell lines + compass
    roses (STRAIT sub-theme), same bn-* layout as the banknote chrome."""
    waves = wave_svg(1400, 150, STRAIT_INK, 0.12)
    rose = compass_svg(56, STRAIT_INK, 0.30)
    return (
        '<header class="bn-mast">'
        f'<div class="bn-lattice" aria-hidden="true">{waves}</div>'
        f'<div class="bn-corner bn-corner--tl" aria-hidden="true">{rose}</div>'
        f'<div class="bn-corner bn-corner--br" aria-hidden="true">{rose}</div>'
        '<div class="bn-mast-top">'
        '<span class="bn-league">✦ MONEYLEAGUE STRAIT AUTHORITY ✦</span>'
        f'<span class="ml-serial">{bpr.banknote_serial()}</span></div>'
        f'<h1>{title}</h1><p class="bn-sub">{subtitle}</p></header>')


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
        ticket = (
            '<section class="tk" aria-label="Toll ticket">'
            '<div class="tk-main">'
            '<div class="tk-head"><span class="ml-h-label">TRANSIT TOLL '
            f'— WEEK {latest["week"]}</span>'
            f'<span class="ml-serial">No. {no}</span></div>'
            '<div class="tk-route-strip" aria-label="Route: Red Sea, '
            'through Bab al-Mandab, to the Gulf of Aden">'
            '<span>RED SEA</span><span class="lane"></span>'
            f'<span class="gate">⟩ {esc(label(latest["low"]))} ⟨'
            '<small>BAB AL-MANDAB</small></span>'
            '<span class="lane"></span><span>GULF OF ADEN</span></div>'
            '<dl class="tk-grid">'
            f'<dt>Vessel</dt><dd class="tk-big">{esc(label(latest["low"]))}</dd>'
            '<dt>Cargo declared</dt><dd><span class="ml-num">'
            f'{latest["low_pts"]:.2f}</span> pts · lowest in the fleet</dd>'
            '<dt>Passage class</dt><dd>'
            f'{ord_(latest["low_week_no"])} transit this season</dd>'
            '<dt>Payable to</dt><dd><b>'
            f'{esc(label(latest["top"]))}</b>, harbor master · '
            f'<span class="ml-num">{latest["top_pts"]:.2f}</span> pts, '
            'high score</dd>'
            '<dt>Toll due</dt><dd class="tk-big tk-due">'
            f'${latest["fine"]}</dd>'
            '</dl>'
            '<div class="tk-stamp" aria-hidden="true">ASSESSED</div>'
            '</div>'
            '<div class="tk-stub">'
            '<div class="ml-h-label">STUB · RETAIN</div>'
            f'<div class="ml-serial">{no}</div>'
            f'<p class="tk-route">{esc(label(latest["low"]))} → '
            f'{esc(label(latest["top"]))}</p>'
            f'<p class="tk-big tk-due">${latest["fine"]}</p>'
            f'<p class="tk-small">Next transit for '
            f'{esc(label(latest["low"]))}: <b>${nxt}</b></p>'
            '</div></section>')
    else:
        ticket = ('<section class="tk"><div class="tk-main"><p>The strait '
                  "opens once Week 1 is fully scored — no tolls assessed "
                  "yet.</p></div></section>")

    # tariff: one cell per passage number, through the most anyone could
    # still reach this season
    max_n = max([v["lows"] for v in ledger.values()] + [0]) + left
    max_n = max(4, min(max_n, 8))
    tariff = "".join(
        f'<td class="ml-num">${toll(n - 1)}</td>' for n in range(1, max_n + 1))
    tariff_head = "".join(
        f'<th class="ml-num">{ord_(n)}</th>' for n in range(1, max_n + 1))

    def net_cell(v: int) -> str:
        cls = "tk-gain" if v > 0 else ("tk-loss" if v < 0 else "")
        return f'<td class="ml-num {cls}"><b>{v:+d}</b></td>'

    ledger_rows = "".join(
        f'<tr><td class="ml-num">{i}</td><td>{esc(label(m))}</td>'
        f'<td class="ml-num">{v["lows"]}</td>'
        f'<td class="ml-num">${v["paid"]}</td>'
        f'<td class="ml-num">{v["tops"]}</td>'
        f'<td class="ml-num">${v["collected"]}</td>'
        + net_cell(v["collected"] - v["paid"])
        + (f'<td class="ml-num">${toll(v["lows"])}</td>' if left else
           '<td class="ml-num">—</td>')
        + f'<td class="st">{status(v["lows"])}</td>'
        + '</tr>'
        for i, (m, v) in enumerate(
            sorted(ledger.items(),
                  key=lambda kv: (-(kv[1]["collected"] - kv[1]["paid"]),
                                 label(kv[0]))), 1))

    log_rows = "".join(
        f'<tr><td class="ml-num">{t["week"]}</td>'
        f'<td>{esc(label(t["low"]))} <span class="own ml-num">'
        f'{t["low_pts"]:.2f}</span></td>'
        f'<td>{esc(label(t["top"]))} <span class="own ml-num">'
        f'{t["top_pts"]:.2f}</span></td>'
        f'<td class="ml-num">${t["fine"]} '
        f'<span class="own">({ord_(t["low_week_no"])})</span></td>'
        '</tr>'
        for t in reversed(tape))

    h = ['<html data-theme="strait"><head><meta charset="utf-8"><style>'
         + report_base_css() + bpr.banknote_css() + """
    * { box-sizing: border-box; margin: 0; }
    body { font-size: 10pt; padding: 20px 26px; }
    .tk { display: grid; grid-template-columns: 1fr 170px; margin: 4px 0 14px;
          border: 2px solid var(--ml-text); border-radius: var(--ml-r-md);
          background: var(--ml-panel); }
    .tk-main { position: relative; padding: 12px 16px; }
    .tk-head { display: flex; justify-content: space-between;
               align-items: baseline; margin-bottom: 8px; }
    .tk-grid { display: grid; grid-template-columns: 130px 1fr;
               row-gap: 5px; column-gap: 10px; align-items: baseline; }
    .tk-grid dt { color: var(--ml-muted); font-size: 8pt;
                  text-transform: uppercase; letter-spacing: 1px; }
    .tk-big { font-family: var(--ml-font-engraving, var(--ml-font-display));
              font-size: 18pt; font-weight: 700; line-height: 1.1; }
    .tk-due { color: var(--ml-danger); }
    .tk-stamp { position: absolute; right: 18px; bottom: 14px;
                transform: rotate(-8deg); border: 2px solid var(--ml-danger);
                color: var(--ml-danger); padding: 2px 10px;
                border-radius: var(--ml-r-sm); font-weight: 700;
                letter-spacing: 3px; font-size: 11pt; opacity: .8; }
    .tk-stub { border-left: 2px dashed var(--ml-border-strong);
               padding: 12px 14px; display: flex; flex-direction: column;
               gap: 5px; }
    .tk-route { font-weight: 700; font-size: 11pt; }
    .tk-small { font-size: 8pt; color: var(--ml-muted); }
    .tk-route-strip { display: flex; align-items: center; gap: 8px;
                      margin: 0 0 10px; font-size: 7.5pt; letter-spacing: 2px;
                      color: var(--ml-muted); }
    .tk-route-strip .lane { flex: 1; border-top: 2px dashed
                            var(--ml-strait-route); }
    .tk-route-strip .gate { display: flex; flex-direction: column;
                            align-items: center; color: var(--ml-text);
                            font-weight: 700; letter-spacing: 1px;
                            font-size: 9pt; }
    .tk-route-strip .gate small { font-size: 6.5pt; letter-spacing: 2px;
                                  color: var(--ml-muted); font-weight: 400; }
    td.st { font-size: 7.5pt; color: var(--ml-muted); white-space: nowrap; }
    .tk-gain { color: var(--ml-success); }
    .tk-loss { color: var(--ml-danger); }
    .tariff { margin-bottom: 14px; }
    .tariff td, .tariff th { padding: 3px 8px; }
    .cols { display: grid; grid-template-columns: 1.25fr 1fr; gap: 12px; }
    .own { color: var(--ml-muted); font-size: 8pt; }
    table.log td, table.log th { font-size: 8pt; padding: 3px 4px;
                                 white-space: nowrap; }
    .rule { margin-top: 14px; font-size: 8.5pt; color: var(--ml-muted);
            max-width: 62em; }
    </style></head><body>"""]
    h.append(strait_masthead(
        "BAB AL-MANDAB TOLL TICKET",
        "the Gate of Tears: low scorer pays passage, high scorer holds "
        f"the harbor · {date.today():%b %d, %Y}"))
    h.append(ticket)
    h.append('<div class="ml-h-label">TARIFF SCHEDULE · toll by transit '
             'number this season</div>'
             '<table class="ml-table ml-table--compact tariff"><thead><tr>'
             f'<th>Transit</th>{tariff_head}</tr></thead><tbody><tr>'
             f'<td>Toll</td>{tariff}</tr></tbody></table>')
    ledger_body = (ledger_rows
                   or '<tr><td colspan="9">no weeks scored yet</td></tr>')
    log_body = log_rows or '<tr><td colspan="4">—</td></tr>'
    h.append('<div class="cols"><div>'
             '<div class="ml-h-label">PORT LEDGER · season to date</div>'
             '<table class="ml-table ml-table--compact">'
             '<thead><tr><th></th><th>Vessel</th>'
             '<th class="ml-num">Transits</th><th class="ml-num">Tolls paid'
             '</th><th class="ml-num">Harbor wks</th>'
             '<th class="ml-num">Collected</th><th class="ml-num">Net</th>'
             '<th class="ml-num">Next toll</th><th>Status</th></tr></thead>'
             f'<tbody>{ledger_body}</tbody></table></div>'
             '<div><div class="ml-h-label">TRANSIT LOG</div>'
             '<table class="ml-table ml-table--compact log">'
             '<thead><tr><th class="ml-num">Wk</th><th>Paid passage</th>'
             '<th>Harbor master</th><th class="ml-num">Toll</th></tr></thead>'
             f'<tbody>{log_body}</tbody></table></div></div>')
    h.append('<p class="rule">Tariff (2022+ era rule): each regular-season '
             "week the low scorer pays the high scorer $15, +$5 for every "
             "earlier low week that manager has had this season. "
             f"{left} regular-season week{'s' if left != 1 else ''} left "
             f"(through Week {last_reg}); playoffs (Week {playoff_start}+) "
             "sail toll-free. A week is assessed only once every roster has "
             "scored, so a live week never shows a false $0.0 low. "
             "Full rule history and all-time purse: the Almanac.</p>")
    h.append(bpr.banknote_fineprint(
        "The MONEYLEAGUE Strait Authority is a league joke, not a port, "
        "government or shipping body. Source: live Sleeper matchups, "
        "refetched every Tuesday."))
    h.append("</body></html>")

    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch(executable_path=bpr.CHROMIUM_EXEC,
                              args=["--no-sandbox",
                                    "--disable-dev-shm-usage"])
        page = b.new_context(viewport={"width": 1000, "height": 1200}).new_page()
        page.set_content("\n".join(h), wait_until="networkidle")
        page.evaluate("document.fonts.ready")
        page.pdf(path=str(PDF_OUT), format="Letter",
                 margin={"top": "0.3in", "bottom": "0.3in",
                         "left": "0.3in", "right": "0.3in"},
                 print_background=True)
        b.close()
    print(f"Wrote {PDF_OUT.relative_to(ROOT)} "
          f"({PDF_OUT.stat().st_size / 1024:.0f} KB); "
          f"{len(tape)} week(s) on the tape")


if __name__ == "__main__":
    main()
