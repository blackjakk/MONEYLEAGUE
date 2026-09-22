"""THE SKILLBAR — the season as a leveling bar.

A one-page Tuesday card, updated every week alongside the Tax Tape:
each manager's bar fills with cumulative points-for through the just-
completed week (the "level"), scaled to the current league leader.
Each week's new points render as a distinct segment — green if that
week's score beat the league median, red if it didn't — so growth AND
form are both visible in the same bar. A separate LINEUP SKILL column
carries the season's cumulative bench-leak (optimal lineup minus
actual starters, MONEYLEAGUE start shape) — the one genuine skill
signal in the card, reusing the exact method from the 2025 Autopsy
(build_autopsy_2025.py's optimal_points()) so the two never disagree.

Unlike the Post-Draft Shift (graded against a frozen draft-night
snapshot), this card has no fixed baseline — it's a running leaderboard
that simply grows every week. "Last week" IS the baseline for "this
week's segment", by construction.

Output: data/MONEYLEAGUE_SKILLBAR.pdf (Letter portrait, one page).
"""
from __future__ import annotations

import glob
import html as _html
import json
import statistics
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
PDF_OUT = ROOT / "data" / "MONEYLEAGUE_SKILLBAR.pdf"
JSON_OUT = ROOT / "data" / "research" / "skillbar_2026.json"
MY_RID = 9

# MONEYLEAGUE start shape (league.json roster_positions, bench excluded) —
# identical to build_autopsy_2025.py so the two scripts never disagree.
SLOT_ELIG = {
    "QB": {"QB"}, "RB": {"RB"}, "WR": {"WR"}, "TE": {"TE"},
    "K": {"K"}, "DEF": {"DEF"},
    "FLEX": {"RB", "WR", "TE"},
    "SUPER_FLEX": {"QB", "RB", "WR", "TE"},
}


def esc(s) -> str:
    return _html.escape(str(s), quote=False)


def label(mid: str | None) -> str:
    return SHORT.get(mid, (mid or "?")[:4].upper())


def optimal_points(players_points: dict, pos: dict[str, str]) -> float:
    """Best legal MONEYLEAGUE lineup from one week's players_points."""
    by_pos: dict[str, list[tuple[float, str]]] = {}
    for pid, pts in players_points.items():
        p = pos.get(pid)
        if p in ("QB", "RB", "WR", "TE", "K", "DEF"):
            by_pos.setdefault(p, []).append((float(pts or 0.0), pid))
    for lst in by_pos.values():
        lst.sort(reverse=True)
    used: set[str] = set()
    total = 0.0
    for p, k in (("QB", 1), ("RB", 2), ("WR", 3), ("TE", 1),
                ("K", 1), ("DEF", 1)):
        for pts, pid in by_pos.get(p, [])[:k]:
            total += pts
            used.add(pid)
    for elig in (SLOT_ELIG["FLEX"], SLOT_ELIG["SUPER_FLEX"]):
        best = None
        for p in elig:
            for pts, pid in by_pos.get(p, []):
                if pid not in used:
                    if best is None or pts > best[0]:
                        best = (pts, pid)
                    break              # sorted: first unused is that pos's best
        if best:
            total += best[0]
            used.add(best[1])
    return total


def load_played_weeks() -> list[tuple[int, list[dict]]]:
    """[(week, matchup_rows)] for weeks every roster has actually scored."""
    cfg = json.loads((ROOT / "configs/season_2026.json").read_text())
    mdir = ROOT / cfg["league_dir"] / "matchups"
    out = []
    for f in sorted(glob.glob(str(mdir / "week_*.json")),
                    key=lambda p: int(Path(p).stem.split("_")[1])):
        wk = int(Path(f).stem.split("_")[1])
        rows = json.loads(Path(f).read_text())
        if len(rows) < 12 or any((r.get("points") or 0.0) == 0.0
                                 for r in rows):
            continue
        out.append((wk, rows))
    return out


def main() -> None:
    cat = json.loads((ROOT / "data/sleeper/players_nfl.json").read_text())
    pos = {pid: (p.get("position")
                or (p.get("fantasy_positions") or [None])[0])
           for pid, p in cat.items()}

    ident = load_identity(ROOT / "data/team_identity.json")
    rid_mid = {rec["sleeper_roster_id"]: mid
               for mid, rec in ident["managers"].items()
               if rec.get("sleeper_roster_id")}

    weeks = load_played_weeks()
    cum_pf: dict[int, float] = defaultdict(float)
    cum_opt: dict[int, float] = defaultdict(float)
    wins: dict[int, int] = defaultdict(int)
    losses: dict[int, int] = defaultdict(int)
    last_week_pf: dict[int, float] = defaultdict(float)
    weekly_scores: dict[int, list[float]] = defaultdict(list)
    history: list[dict] = []

    for wk, rows in weeks:
        actual = {r["roster_id"]: float(r.get("points") or 0.0) for r in rows}
        median = statistics.median(actual.values())
        bym = defaultdict(list)
        for r in rows:
            if r.get("matchup_id") is not None:
                bym[r["matchup_id"]].append(r)
        for g in bym.values():
            if len(g) == 2:
                a, b = g
                if actual[a["roster_id"]] > actual[b["roster_id"]]:
                    wins[a["roster_id"]] += 1
                    losses[b["roster_id"]] += 1
                else:
                    wins[b["roster_id"]] += 1
                    losses[a["roster_id"]] += 1
        for r in rows:
            rid = r["roster_id"]
            opt = optimal_points(r.get("players_points") or {}, pos)
            cum_pf[rid] += actual[rid]
            cum_opt[rid] += opt
            weekly_scores[rid].append(actual[rid])
            history.append({
                "week": wk, "roster_id": rid,
                "manager": rid_mid.get(rid, str(rid)),
                "actual": round(actual[rid], 2), "optimal": round(opt, 2),
                "leak": round(opt - actual[rid], 2),
                "above_median": actual[rid] >= median,
            })

    rows_out = []
    for rid, mid in rid_mid.items():
        rows_out.append({
            "rid": rid, "mid": mid,
            "cum_pf": cum_pf.get(rid, 0.0),
            "cum_opt": cum_opt.get(rid, 0.0),
            "wins": wins.get(rid, 0), "losses": losses.get(rid, 0),
            "scores": weekly_scores.get(rid, []),
        })

    JSON_OUT.parent.mkdir(parents=True, exist_ok=True)
    JSON_OUT.write_text(json.dumps(
        {"season": 2026, "generated": str(date.today()),
         "weeks_played": [w for w, _ in weeks],
         "standings": [{k: v for k, v in r.items() if k != "scores"}
                      for r in rows_out],
         "history": history}, indent=2))

    if not weeks:
        print("[skillbar] no weeks played yet — nothing to render")
        # still render an empty-state card below, matching the other
        # week-1-before-kickoff cards' behavior
    n_played = len(weeks)
    maxv = max((r["cum_pf"] for r in rows_out), default=0.0) or 1.0
    rows_out.sort(key=lambda r: -r["cum_pf"])
    # rank a week ago, for the movement arrow
    prior_rank = {r["rid"]: i for i, r in enumerate(
        sorted(rows_out,
              key=lambda r: -(r["cum_pf"] - (r["scores"][-1]
                                             if r["scores"] else 0.0))), 1)}

    bars = []
    for i, r in enumerate(rows_out, 1):
        this_wk = r["scores"][-1] if r["scores"] else 0.0
        prior_pf = r["cum_pf"] - this_wk
        base_w = prior_pf / maxv * 100
        seg_w = this_wk / maxv * 100
        good_week = (n_played > 0 and this_wk >= statistics.median(
            [x["scores"][-1] for x in rows_out if x["scores"]] or [0]))
        move = prior_rank.get(r["rid"], i) - i
        arrow = (f'<span class="up">▲{move}</span>' if move > 0 else
                 f'<span class="dn">▼{-move}</span>' if move < 0 else
                 '<span class="fl">■</span>')
        me = " me" if r["rid"] == MY_RID else ""
        lvl = ('<span class="lvl gold">1</span>' if i == 1
               else f'<span class="lvl">{i}</span>')
        leak = r["cum_opt"] - r["cum_pf"]
        bars.append(f"""
<div class="row{me}">
  <div class="who">{lvl} <b>{esc(label(r["mid"]))}</b></div>
  <div class="track">
    <div class="fill base" style="left:0;width:{base_w:.1f}%"></div>
    <div class="fill {'gain' if good_week else 'loss'}"
         style="left:{base_w:.1f}%;width:{seg_w:.1f}%"></div>
  </div>
  <div class="num">{r["cum_pf"]:,.1f}</div>
  <div class="num wk">{this_wk:.1f}</div>
  <div class="num rec">{r["wins"]}-{r["losses"]}</div>
  <div class="num leak {'dn' if leak > 5 else ''}">−{leak:.0f}</div>
  <div class="mv">{arrow}</div>
</div>""")

    bars_html = ("".join(bars) if rows_out else
                '<p class="rule">No games have finished yet — the '
                "skillbar starts filling once Week 1 is fully scored."
                "</p>")

    awards_html = ""
    if n_played:
        best_wk = max(history, key=lambda h: h["actual"])
        worst_leak = max(rows_out, key=lambda r: r["cum_opt"] - r["cum_pf"])
        best_leak = min(rows_out, key=lambda r: r["cum_opt"] - r["cum_pf"])
        climber = max(rows_out, key=lambda r: prior_rank.get(r["rid"], 0)
                      - (rows_out.index(r) + 1))
        climb_delta = (prior_rank.get(climber["rid"], 0)
                      - (rows_out.index(climber) + 1))
        me_row = next(r for r in rows_out if r["rid"] == MY_RID)
        me_leak = me_row["cum_opt"] - me_row["cum_pf"]
        awards_html = (
            '<div class="ml-h-label" style="margin-top:14px">TABLE AWARDS'
            '</div><table class="story awards"><tbody>'
            f'<tr><td class="sl">BEST WEEK</td><td>'
            f'<b>{esc(label(best_wk["manager"]))}</b> '
            f'{best_wk["actual"]:.1f} (Week {best_wk["week"]})</td></tr>'
            f'<tr><td class="sl">CLIMBING</td><td>'
            f'<b>{esc(label(climber["mid"]))}</b> up '
            f'{climb_delta} spot{"s" if climb_delta != 1 else ""} this '
            'week</td></tr>'
            f'<tr><td class="sl">BIGGEST LINEUP LEAK</td><td>'
            f'<b>{esc(label(worst_leak["mid"]))}</b> '
            f'−{worst_leak["cum_opt"] - worst_leak["cum_pf"]:.0f} pts left '
            'on the bench this season</td></tr>'
            f'<tr><td class="sl">SHARPEST LINEUP</td><td>'
            f'<b>{esc(label(best_leak["mid"]))}</b> '
            f'only −{best_leak["cum_opt"] - best_leak["cum_pf"]:.0f} pts '
            'left on the bench — the season\'s best lineup-setter'
            '</td></tr>'
            f'<tr><td class="sl">THE DESK\'S SEAT</td><td><b>BRIAN</b> '
            f'{me_row["cum_pf"]:.1f} PF, {me_row["wins"]}-{me_row["losses"]}'
            f', −{me_leak:.0f} lineup leak this season</td></tr>'
            '</tbody></table>')

    h = ['<html data-theme="light"><head><meta charset="utf-8"><style>'
         + report_base_css() + bpr.banknote_css() + """
    * { box-sizing: border-box; margin: 0; }
    body { font-size: 10pt; padding: 20px 26px; }
    .legend { margin: 10px 0 16px; font-size: 8.5pt;
              color: var(--ml-muted); }
    .legend .chip { display: inline-block; width: 22px; height: 8px;
                    vertical-align: middle; margin: 0 4px 0 10px; }
    .chip.base { background: var(--ml-border-strong); }
    .chip.gain { background: var(--ml-success); }
    .chip.loss { background: var(--ml-danger); }
    .row { display: grid;
           grid-template-columns: 82px 1fr 52px 44px 44px 48px 30px;
           gap: 7px; align-items: center; padding: 9px 4px;
           border-bottom: 1px solid var(--ml-border); }
    .row.me { border-left: 3px solid var(--ml-gold-chip);
              padding-left: 6px; }
    .who { font-family: var(--ml-font-mono); font-size: 9.5pt; }
    .lvl { display: inline-block; min-width: 18px; text-align: center;
           border: 1px solid var(--ml-border-strong); font-size: 8pt;
           padding: 1px 2px; }
    .lvl.gold { background: var(--ml-gold-chip);
                color: var(--ml-gold-chip-text);
                border-color: var(--ml-gold-chip); }
    .track { position: relative; height: 13px;
             border: 1px solid var(--ml-border-strong);
             background: var(--ml-bg); }
    .fill { position: absolute; top: 0; bottom: 0; }
    .fill.base { background: var(--ml-border-strong); }
    .fill.gain { background: var(--ml-success); }
    .fill.loss { background: var(--ml-danger); }
    .num { text-align: right; font-family: var(--ml-font-mono);
           font-size: 9.5pt; }
    .num.wk, .num.rec, .num.leak { font-size: 8.6pt; color: var(--ml-muted); }
    .num.leak.dn { color: var(--ml-danger); }
    .mv { text-align: center; font-size: 9pt; }
    .up { color: var(--ml-success); }
    .dn { color: var(--ml-danger); }
    .fl { color: var(--ml-muted); }
    .hdr { font-size: 6.6pt; letter-spacing: .4px;
           color: var(--ml-muted); border-bottom: 1px solid
           var(--ml-border-strong); padding: 2px 4px; }
    .hdr div { text-align: right; }
    .hdr .l { text-align: left; }
    .story { border-collapse: collapse; width: 100%; max-width: 62em; }
    .story td { padding: 3px 6px 3px 0; font-size: 9pt; }
    .story td.sl { color: var(--ml-muted); font-weight: 700;
                   font-size: 7.5pt; letter-spacing: .4px;
                   white-space: nowrap; padding-right: 10px; }
    .rule { margin-top: 14px; font-size: 8.5pt; color: var(--ml-muted);
            max-width: 60em; }
    </style></head><body>"""]
    h.append(bpr.banknote_masthead(
        "THE SKILLBAR",
        "the season, leveling up — cumulative points-for vs the league "
        f"leader · updated {date.today():%b %d, %Y}"))
    h.append('<div class="legend">READING THE BARS — '
             '<span class="chip base"></span> banked through last week '
             '<span class="chip gain"></span> this week, above league '
             'median <span class="chip loss"></span> this week, below '
             'median · bar length = cumulative points-for vs the current '
             "league leader (the bar that reaches the far right is #1). "
             "LINEUP SKILL = optimal lineup minus actual starters, "
             "season-to-date (the 2025 Autopsy's method) — the genuine "
             "skill signal here, independent of raw scoring.</div>")
    h.append('<div class="row hdr"><div class="l">LVL · TEAM</div>'
             '<div class="l">SEASON BAR</div><div>PF</div>'
             '<div>WK</div><div>REC</div><div>LEAK</div><div></div></div>')
    h.append(bars_html)
    h.append(awards_html)
    h.append('<p class="rule">Reads live 2026 Sleeper matchups (refetched '
             "every Tuesday morning by the weekly refresh); a week counts "
             "only once every roster has actually scored. Lineup leak = "
             "the exact optimal_points() method from the 2025 Autopsy "
             "(MONEYLEAGUE start shape: 1QB/2RB/3WR/1TE/1FLEX/1SF/1K/1DEF) "
             "— the two will never disagree.</p>")
    h.append(bpr.banknote_fineprint(
        "One page, one story: who's leveling up, and who's leaving points "
        "on the bench while they do it."))
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
          f"{n_played} week(s) on the bar")


if __name__ == "__main__":
    main()
