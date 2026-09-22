"""THE TAX TAPE — the weekly low-score tax, collected.

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

from design.tokens import report_base_css  # noqa: E402
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

    # ---------------- render ----------------
    latest = tape[-1] if tape else None
    ord_word = {1: "1st", 2: "2nd", 3: "3rd"}

    def ord_(n):
        return ord_word.get(n, f"{n}th")

    banner = ""
    if latest:
        streak_note = (f" — his {ord_(latest['low_week_no'])} low week "
                       "this season" if latest["low_week_no"] > 1
                       else " — his first low week this season")
        banner = (
            '<div class="ml-banner">'
            f'<div class="ml-h-label">WEEK {latest["week"]} — TAX '
            'COLLECTED</div>'
            f'<p class="big"><b>{esc(label(latest["top"]))}</b> '
            f'{latest["top_pts"]:.2f} (high score) collects '
            f'<b>${latest["fine"]}</b> from '
            f'<b>{esc(label(latest["low"]))}</b> '
            f'{latest["low_pts"]:.2f} (low score){esc(streak_note)}.</p>'
            "</div>")
    else:
        banner = ('<div class="ml-banner"><p class="big">No regular-season '
                  "week has finished yet — the tape starts once Week 1 is "
                  "fully scored.</p></div>")

    rows = "".join(
        f'<tr><td class="ml-num">{i}</td><td>{esc(label(m))}</td>'
        f'<td class="ml-num">{v["lows"]}</td>'
        f'<td class="ml-num">${v["paid"]}</td>'
        f'<td class="ml-num">{v["tops"]}</td>'
        f'<td class="ml-num">${v["collected"]}</td>'
        f'<td class="ml-num"><b>{v["collected"] - v["paid"]:+d}</b></td>'
        '</tr>'
        for i, (m, v) in enumerate(
            sorted(ledger.items(),
                  key=lambda kv: (-(kv[1]["collected"] - kv[1]["paid"]),
                                 label(kv[0]))), 1))

    tape_rows = "".join(
        f'<tr><td class="ml-num">{t["week"]}</td>'
        f'<td>{esc(label(t["top"]))} <span class="ml-num">'
        f'{t["top_pts"]:.2f}</span></td>'
        f'<td>{esc(label(t["low"]))} <span class="ml-num">'
        f'{t["low_pts"]:.2f}</span></td>'
        f'<td class="ml-num">${t["fine"]} '
        f'<span class="own">({ord_(t["low_week_no"])} low)</span></td>'
        '</tr>'
        for t in reversed(tape))

    h = ['<html data-theme="light"><head><meta charset="utf-8"><style>'
         + report_base_css() + bpr.banknote_css() + """
    * { box-sizing: border-box; margin: 0; }
    body { font-size: 10pt; padding: 20px 26px; }
    .ml-banner { margin: 12px 0 16px; padding: 10px 14px; }
    .ml-banner p.big { font-size: 12pt; margin-top: 4px; }
    .cols { display: grid; grid-template-columns: 1fr 1fr; gap: 18px;
            margin-top: 6px; }
    .own { color: var(--ml-muted); font-size: 8pt; }
    table.tape td, table.tape th { font-size: 8.6pt; padding: 3px 6px; }
    .rule { margin-top: 14px; font-size: 8.5pt; color: var(--ml-muted);
            max-width: 60em; }
    </style></head><body>"""]
    ledger_body = rows or '<tr><td colspan="7">no weeks scored yet</td></tr>'
    tape_body = tape_rows or '<tr><td colspan="4">—</td></tr>'
    h.append(bpr.banknote_masthead(
        "THE TAX TAPE",
        "the low-score tax, collected — every regular-season week · "
        f"updated {date.today():%b %d, %Y}"))
    h.append(banner)
    h.append('<div class="cols"><div>'
             '<div class="ml-h-label">SEASON LEDGER</div>'
             '<table class="ml-table ml-table--compact">'
             '<thead><tr><th></th><th>Manager</th>'
             '<th class="ml-num">Lows</th><th class="ml-num">Paid</th>'
             '<th class="ml-num">Tops</th><th class="ml-num">Collected'
             '</th><th class="ml-num">Net</th></tr></thead>'
             f'<tbody>{ledger_body}</tbody></table></div>'
             '<div><div class="ml-h-label">WEEK BY WEEK</div>'
             '<table class="ml-table ml-table--compact tape">'
             '<thead><tr><th class="ml-num">Wk</th><th>High</th>'
             '<th>Low</th><th class="ml-num">Fine</th></tr></thead>'
             f'<tbody>{tape_body}</tbody></table></div></div>')
    h.append('<p class="rule">Rule (2022+ era): the low scorer each '
             "regular-season week pays the high scorer $15, +$5 for every "
             "additional low week that manager has already had this "
             f"season (2nd low = $20, 3rd = $25...). Playoffs (week "
             f"{playoff_start}+) don't tax. A week counts only once every "
             "roster has actually scored, so a live/partial week never "
             "shows a false $0.0 low. Full rule history + all-time purse: "
             "the Almanac.</p>")
    h.append(bpr.banknote_fineprint(
        "Source: live Sleeper matchups, refetched every Tuesday morning "
        "by the weekly refresh. One page, one story: who paid whom this "
        "week."))
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
