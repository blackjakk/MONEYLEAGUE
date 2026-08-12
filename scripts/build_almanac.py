"""THE ALMANAC — the MONEY_LEAGUE.xlsx use case as a living PDF.

The xlsx is the league's bible: every draft board with TRUE pick
ownership (cell colors), plus who won. This report recreates that
record beautifully and keeps itself current: seasons are DISCOVERED
from the data (xlsx boards 2015+, yahoo_era standings 2011+, Sleeper
brackets for champions) — when the 2026 draft lands in the xlsx or the
Sleeper archive, it folds in on the next weekly run with zero edits.

Pages: honor-roll cover (champions by year, title counts, era growth),
a standings-only spread for the pre-board years (2011-2014), then one
page per season: champion banner, final standings, and the full draft
board (round x slot, players position-colored, owner tag per pick —
the xlsx cell-color truth, typeset). Champion picks are bold.

Output: data/MONEYLEAGUE_ALMANAC.pdf (multi-page, Letter landscape).
"""
from __future__ import annotations

import html as _html
import json
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from design.tokens import report_base_css  # noqa: E402
from scripts import build_power_rankings as bpr  # noqa: E402
from scripts.build_history_charts import KNOWN_CHAMPIONS  # noqa: E402
from fantasy_draft.xlsx_drafts import load_xlsx_drafts  # noqa: E402
from fantasy_draft.team_identity import (load_identity,  # noqa: E402
                                         manager_for_xlsx_nickname)

ROOT = Path(__file__).resolve().parent.parent
PDF_OUT = ROOT / "data" / "MONEYLEAGUE_ALMANAC.pdf"
XLSX = ROOT / "data" / "historical" / "MONEY_LEAGUE.xlsx"

SHORT = {"brian_bigguap": "BRI", "trevor_bergerboy": "TREV", "coop": "COOP",
         "lem": "LEM", "kyle_figgy": "FIG", "troy_mullings": "TROY",
         "donnie": "DON", "eric_m": "ERIC", "tim_breswick": "TIM",
         "brower_barry": "BROW", "ankur_patel": "ANK",
         "josh_wildboy": "JOSH", "dave_aka_wang": "DAVE", "nark": "NARK",
         "jp_former": "JP", "nick_lewis_left": "NICK",
         "notebooks_left": "NTBK"}

POS_CLASS = {"QB": "ml-pos-qb", "RB": "ml-pos-rb", "WR": "ml-pos-wr",
             "TE": "ml-pos-te", "K": "ml-pos-k", "DEF": "ml-pos-def"}


def esc(s) -> str:
    return _html.escape(str(s), quote=False)


def player_positions() -> dict[str, str]:
    """name(normalized) -> pos, best-effort from the Sleeper catalog."""
    cat = json.loads((ROOT / "data/sleeper/players_nfl.json").read_text())
    out = {}
    for p in cat.values():
        nm = f"{p.get('first_name', '')} {p.get('last_name', '')}".strip().lower()
        pos = p.get("position")
        if nm and pos in POS_CLASS:
            out.setdefault(nm, pos)
    return out


def sleeper_standings() -> dict[int, list[dict]]:
    """Regular-season standings for Sleeper seasons, from matchups."""
    import glob
    ident = load_identity(ROOT / "data/team_identity.json")
    rid_mid = {rec["sleeper_roster_id"]: mid
               for mid, rec in ident["managers"].items()
               if rec.get("sleeper_roster_id")}
    out = {}
    seasons = sorted({int(f.split("/")[-1].split("_")[0])
                      for f in glob.glob(str(ROOT / "data/league_history/*_matchups_w1.json"))})
    for season in seasons:
        rmap = dict(rid_mid)
        rmap[10] = "josh_wildboy" if season >= 2025 else "dave_aka_wang"
        w, l, pf = defaultdict(int), defaultdict(int), defaultdict(float)
        for wf in glob.glob(str(ROOT / f"data/league_history/{season}_matchups_w*.json")):
            wk = int(wf.split("_w")[1].split(".")[0])
            if wk > 14:
                continue
            bym = defaultdict(list)
            for r in json.loads(open(wf).read()):
                pf[r["roster_id"]] += r["points"]
                if r["matchup_id"] is not None:
                    bym[r["matchup_id"]].append(r)
            for g in bym.values():
                if len(g) == 2:
                    a, b = g
                    if a["points"] > b["points"]:
                        w[a["roster_id"]] += 1
                        l[b["roster_id"]] += 1
                    else:
                        w[b["roster_id"]] += 1
                        l[a["roster_id"]] += 1
        rows = [{"manager": rmap.get(rid, str(rid)), "wins": w[rid],
                 "losses": l[rid], "pf": round(pf[rid], 1)}
                for rid in pf]
        rows.sort(key=lambda r: (-r["wins"], -r["pf"]))
        for i, r in enumerate(rows, 1):
            r["rank"] = i
        out[season] = rows
    return out


def sleeper_champions() -> dict[int, tuple[str | None, str | None]]:
    import glob
    ident = load_identity(ROOT / "data/team_identity.json")
    rid_mid = {rec["sleeper_roster_id"]: mid
               for mid, rec in ident["managers"].items()
               if rec.get("sleeper_roster_id")}
    out = {}
    for d in glob.glob(str(ROOT / "data/sleeper/league_*")):
        lg = json.loads(open(d + "/league.json").read())
        season = int(lg["season"])
        wb_f = Path(d) / "winners_bracket.json"
        if not wb_f.exists():
            continue
        wb = json.loads(wb_f.read_text())
        final = next((g for g in wb if g.get("p") == 1 and g.get("w")), None)
        if not final:
            continue                              # season not decided
        rmap = dict(rid_mid)
        rmap[10] = "josh_wildboy" if season >= 2025 else "dave_aka_wang"
        out[season] = (rmap.get(final["w"]), rmap.get(final["l"]))
    return out


def build_html() -> str:
    era = {int(k): v for k, v in json.loads(
        (ROOT / "data/league_history/yahoo_era.json").read_text()).items()}
    sl_stand = sleeper_standings()
    sl_champ = sleeper_champions()
    champs: dict[int, str | None] = dict(KNOWN_CHAMPIONS)
    runners: dict[int, str | None] = {}
    for s, sd in era.items():
        runners[s] = next((t["manager"] for t in sd["teams"]
                           if t["rank"] == 2), None)
    for s, (c, r) in sl_champ.items():
        champs[s] = c
        runners[s] = r
    boards = load_xlsx_drafts(str(XLSX))
    pos_of = player_positions()

    def label(mid) -> str:
        return SHORT.get(mid, (mid or "?")[:4].upper())

    def standings_rows(season: int) -> list[dict]:
        if season in era:
            return [{"rank": t["rank"], "manager": t["manager"],
                     "wins": t["wins"], "losses": t["losses"], "pf": t["pf"]}
                    for t in sorted(era[season]["teams"],
                                    key=lambda t: t["rank"])]
        return sl_stand.get(season, [])

    def standings_table(season: int, compact=False) -> str:
        rows = standings_rows(season)
        if not rows:
            return '<p class="ml-note">standings unavailable</p>'
        body = "".join(
            f'<tr><td class="ml-num">{r["rank"]}</td>'
            f'<td>{esc(label(r["manager"]))}'
            + (" 🏆" if r["manager"] == champs.get(season) else "")
            + f'</td><td class="ml-num">{r["wins"]}-{r["losses"]}</td>'
            f'<td class="ml-num">{r["pf"]:.0f}</td></tr>'
            for r in rows)
        return ('<table class="ml-table ml-table--compact st">'
                '<thead><tr><th></th><th>Team</th><th class="ml-num">W-L</th>'
                '<th class="ml-num">PF</th></tr></thead>'
                f"<tbody>{body}</tbody></table>")

    def board_grid(season: int) -> str:
        picks = boards.get(season) or []
        if not picks:
            return ""
        by = {}
        max_r = 0
        slots = sorted({p.slot for p in picks})
        for p in picks:
            by[(p.round, p.slot)] = p
            max_r = max(max_r, p.round)
        champ = champs.get(season)
        head = "".join(f'<th class="ml-num">{s}</th>' for s in slots)
        rows_html = []
        for r in range(1, max_r + 1):
            cells = []
            for s in slots:
                p = by.get((r, s))
                if not p:
                    cells.append("<td></td>")
                    continue
                m = manager_for_xlsx_nickname(p.manager_nickname)
                mid = m["id"] if m else None
                pos = pos_of.get((p.player_name or "").strip().lower())
                cls = POS_CLASS.get(pos, "")
                bold = ' class="champ"' if mid and mid == champ else ""
                cells.append(
                    f'<td{bold}><span class="{cls}">{esc(p.player_name)}'
                    f'</span> <span class="own">{esc(label(mid))}</span></td>')
            rows_html.append(f'<tr><td class="ml-num rnd">{r}</td>'
                             + "".join(cells) + "</tr>")
        return ('<table class="board"><thead><tr><th></th>' + head
                + "</tr></thead><tbody>" + "".join(rows_html)
                + "</tbody></table>")

    all_seasons = sorted(set(era) | set(sl_stand) | set(boards))
    board_seasons = [s for s in all_seasons if s in boards]
    # ---------------- cover: honor roll ----------------
    counts = Counter(v for v in champs.values() if v)
    roll = "".join(
        f'<tr><td class="ml-num">{s}</td>'
        f'<td>{esc(label(champs.get(s)))} 🏆</td>'
        f'<td>{esc(label(runners.get(s)))}</td>'
        f'<td class="ml-num">{era.get(s, {}).get("num_teams") or 12}</td></tr>'
        for s in all_seasons if champs.get(s))
    titles = " · ".join(f"{esc(label(m))} ×{n}"
                        for m, n in counts.most_common())

    h = ['<html data-theme="light"><head><meta charset="utf-8"><style>'
         + report_base_css() + bpr.banknote_css() + """
    * { box-sizing: border-box; margin: 0; }
    body { font-size: 8pt; line-height: 1.3; padding: 16px 22px; }
    .season { page-break-before: always; }
    .season h2 { font-family: var(--ml-font-engraving); font-size: 13pt;
                 letter-spacing: 1px; border-bottom: 1px solid
                 var(--ml-border-strong); padding-bottom: 3px;
                 margin-bottom: 6px; }
    .cols { display: grid; grid-template-columns: 170px 1fr; gap: 10px;
            align-items: start; }
    .cover-cols { display: grid; grid-template-columns: 340px 1fr;
                  gap: 24px; align-items: start; }
    .cover-cols p { max-width: 52em; margin-bottom: 6px; }
    .st td, .st th { padding: 1px 5px; font-size: 7pt; }
    .board { border-collapse: collapse; width: 100%; }
    .board td, .board th { border: 1px solid var(--ml-border);
        padding: 0 2px; font-size: 5.6pt; white-space: nowrap;
        overflow: hidden; text-overflow: ellipsis; max-width: 5.8em; }
    .board th { font-size: 6pt; }
    .rnd { font-weight: 700; }
    .own { color: var(--ml-muted); font-size: 4.8pt; letter-spacing: .3px; }
    .champ { font-weight: 700; }
    .banner { margin: 2px 0 8px; }
    .roll td, .roll th { padding: 2px 8px; }
    .fourup { display: grid; grid-template-columns: repeat(4, 1fr);
              gap: 10px; align-items: start; }
    .bn-foot { margin-top: 8px; font-size: 6.2pt; }
    </style></head><body>"""]

    h.append(bpr.banknote_masthead(
        "THE ALMANAC",
        "the league record · every draft board, every champion · "
        f"compiled {date.today():%b %d, %Y} · extends itself each season"))
    h.append('<div class="cover-cols"><div>'
             '<div class="ml-h-label">HONOR ROLL</div>'
             '<table class="ml-table ml-table--compact roll">'
             '<thead><tr><th>Year</th><th>Champion</th><th>Runner-up</th>'
             '<th class="ml-num">Teams</th></tr></thead>'
             f'<tbody>{roll}</tbody></table></div><div>'
             '<div class="ml-h-label">TITLES</div>'
             f'<p>{titles}</p>'
             '<div class="ml-h-label" style="margin-top:8px">THE RECORD</div>'
             '<p>Founded 2011 at 8 teams; grew to 10 (2013) and 12 (2019). '
             'Draft boards preserved from 2015 onward — every pick below '
             'carries its TRUE owner (the xlsx cell-color record, typeset), '
             'with the champion\'s picks in bold. Keepers entered as '
             'ordinary picks before 2025 appear at their cost round. '
             'Standings are regular-season; the trophy follows the '
             'bracket.</p></div></div>')

    # pre-board years, four-up
    pre = [s for s in all_seasons if s not in boards]
    if pre:
        h.append('<div class="season"><h2>THE EARLY YEARS — '
                 f'{pre[0]}–{pre[-1]} (standings only)</h2>'
                 '<div class="fourup">')
        for s in pre:
            h.append(f'<div><div class="ml-h-label">{s} · '
                     f'{esc(label(champs.get(s)))} 🏆</div>'
                     + standings_table(s, compact=True) + "</div>")
        h.append("</div></div>")

    for s in board_seasons:
        c, ru = champs.get(s), runners.get(s)
        h.append(f'<div class="season"><h2>{s}</h2>'
                 f'<p class="banner"><b>🏆 {esc(label(c))}</b>'
                 + (f' over {esc(label(ru))}' if ru else "")
                 + '</p><div class="cols"><div>'
                 + standings_table(s) + "</div><div>"
                 + board_grid(s) + "</div></div></div>")

    h.append(bpr.banknote_fineprint(
        f"Compiled {date.today():%b %d, %Y} · sources: MONEY_LEAGUE.xlsx "
        "(boards + pick ownership), Yahoo archive standings 2011-2022, "
        "Sleeper archive 2023+ · new seasons fold in automatically once "
        "their board and bracket exist"))
    h.append("</body></html>")
    return "\n".join(h)


def main() -> None:
    from playwright.sync_api import sync_playwright
    html = build_html()
    with sync_playwright() as p:
        b = p.chromium.launch(executable_path=bpr.CHROMIUM_EXEC,
                              args=["--no-sandbox", "--disable-dev-shm-usage"])
        page = b.new_context(viewport={"width": 1400, "height": 1000}).new_page()
        page.set_content(html, wait_until="networkidle")
        page.evaluate("document.fonts.ready")
        page.pdf(path=str(PDF_OUT), format="Letter", landscape=True,
                 margin={"top": "0.3in", "bottom": "0.3in",
                         "left": "0.3in", "right": "0.3in"},
                 print_background=True)
        b.close()
    try:
        from pypdf import PdfReader
        n = len(PdfReader(str(PDF_OUT)).pages)
    except Exception:                       # noqa: BLE001 — count is optional
        n = "?"
    print(f"Wrote {PDF_OUT.relative_to(ROOT)} ({n} pages, "
          f"{PDF_OUT.stat().st_size / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
