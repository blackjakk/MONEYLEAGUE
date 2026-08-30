"""POST-DRAFT SHIFT — the table as an XP bar.

One page: every team ranked by its ACTUAL drafted starting lineup
(projected points, optimal starters incl. keepers), each rendered as
an MMO-style experience bar. The bar fills to what the pre-draft
simulation EXPECTED that team to leave the table with (same metric,
same units — data/draft_expectation_2026.json, the final pre-draft
mock frozen at keeper lock); a bright segment shows XP GAINED at the
table beyond expectation, a drained segment shows XP LOST. Rank
arrows show movement vs the expected order.

The expectation baseline is FROZEN — the weekly sim regenerates
mock_draft_picks.json, but this report always grades the real draft
against what the model believed the night before.

Output: data/MONEYLEAGUE_POSTDRAFT_SHIFT.pdf (Letter portrait).
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

ROOT = Path(__file__).resolve().parent.parent
PDF_OUT = ROOT / "data" / "MONEYLEAGUE_POSTDRAFT_SHIFT.pdf"
EXPECT = ROOT / "data" / "draft_expectation_2026.json"

SHORT = {1: "TIM", 2: "DON", 3: "ANK", 4: "TROY", 5: "FIG", 6: "LEM",
         7: "ERIC", 8: "BROW", 9: "BRIAN", 10: "JOSH", 11: "TREV",
         12: "COOP"}
MY_RID = 9


def esc(s) -> str:
    return _html.escape(str(s), quote=False)


def optimal_lineup(players: list[tuple[str, str, float]]) -> float:
    """1QB 2RB 3WR 1TE FLEX SF, greedy on projections."""
    by: dict[str, list[float]] = defaultdict(list)
    for _, pos, pr in players:
        by[pos].append(pr)
    for k in by:
        by[k].sort(reverse=True)
    total = 0.0

    def take(pos, cnt):
        nonlocal total
        for _ in range(cnt):
            if by[pos]:
                total += by[pos].pop(0)
    take("QB", 1), take("RB", 2), take("WR", 3), take("TE", 1)
    flex = sorted(by["RB"] + by["WR"] + by["TE"], reverse=True)
    if flex:
        total += flex[0]
        for k in ("RB", "WR", "TE"):
            if flex[0] in by[k]:
                by[k].remove(flex[0])
                break
    sf = sorted(by["QB"] + by["RB"] + by["WR"] + by["TE"], reverse=True)
    if sf:
        total += sf[0]
    return total


def main() -> None:
    helper = json.loads((ROOT / "docs/draft_helper/data.json").read_text())
    proj = {p["name"]: (p.get("proj") or 0.0, p["pos"])
            for p in helper["players"]}
    cat = json.loads((ROOT / "data/sleeper/players_nfl.json").read_text())

    def nm(pid):
        p = cat.get(str(pid), {})
        return f"{p.get('first_name', '')} {p.get('last_name', '')}".strip()

    # actual draft: newest completed draft in the live league dir
    cfg = json.loads((ROOT / "configs/season_2026.json").read_text())
    lg_dir = ROOT / cfg["league_dir"]
    picks_f = sorted(glob.glob(str(lg_dir / "draft_*_picks.json")))[-1]
    actual = defaultdict(list)
    for p in json.loads(Path(picks_f).read_text()):
        n = nm(p["player_id"])
        pr, pos = proj.get(n, (0.0, "?"))
        actual[p["roster_id"]].append((n, pos, pr))

    # expectation: the frozen pre-draft mock (slot team_idx -> rid)
    slot_rid = {int(k): v for k, v in cfg["slot_to_roster_id"].items()}
    expect = defaultdict(list)
    for m in json.loads(EXPECT.read_text()):
        rid = slot_rid[m["team_idx"] + 1]
        pr, pos = proj.get(m["player_name"], (0.0, m.get("position", "?")))
        expect[rid].append((m["player_name"], pos, pr))

    rows = []
    for rid in SHORT:
        a = optimal_lineup(actual.get(rid, []))
        e = optimal_lineup(expect.get(rid, []))
        rows.append({"rid": rid, "actual": a, "expected": e,
                     "delta": a - e})
    pre_rank = {r["rid"]: i for i, r in enumerate(
        sorted(rows, key=lambda r: -r["expected"]), 1)}
    rows.sort(key=lambda r: -r["actual"])
    maxv = max(max(r["actual"], r["expected"]) for r in rows)

    bars = []
    for i, r in enumerate(rows, 1):
        rid = r["rid"]
        base = min(r["actual"], r["expected"]) / maxv * 100
        seg = abs(r["delta"]) / maxv * 100
        gained = r["delta"] >= 0
        move = pre_rank[rid] - i
        arrow = (f'<span class="up">▲{move}</span>' if move > 0 else
                 f'<span class="dn">▼{-move}</span>' if move < 0 else
                 '<span class="fl">■</span>')
        me = " me" if rid == MY_RID else ""
        lvl = ('<span class="lvl gold">1</span>' if i == 1
               else f'<span class="lvl">{i}</span>')
        bars.append(f"""
<div class="row{me}">
  <div class="who">{lvl} <b>{esc(SHORT[rid])}</b></div>
  <div class="track">
    <div class="fill" style="width:{base:.1f}%"></div>
    <div class="seg {'gain' if gained else 'loss'}"
         style="left:{base:.1f}%;width:{seg:.1f}%"></div>
  </div>
  <div class="num">{r["actual"]:,.0f}</div>
  <div class="dxp {'up' if r["delta"] >= 0 else 'dn'}">
    {r["delta"]:+,.0f} XP</div>
  <div class="mv">{arrow}</div>
</div>""")

    h = ['<html data-theme="light"><head><meta charset="utf-8"><style>'
         + report_base_css() + bpr.banknote_css() + """
    * { box-sizing: border-box; margin: 0; }
    body { font-size: 10pt; padding: 20px 26px; }
    .legend { margin: 10px 0 14px; font-size: 8.5pt;
              color: var(--ml-muted); }
    .legend .chip { display: inline-block; width: 22px; height: 8px;
                    vertical-align: middle; margin: 0 4px 0 10px; }
    .chip.base { background: var(--ml-border-strong); }
    .chip.gain { background: var(--ml-success); }
    .chip.loss { background: var(--ml-danger); }
    .row { display: grid;
           grid-template-columns: 92px 1fr 52px 64px 34px;
           gap: 8px; align-items: center; padding: 10px 4px;
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
    .fill { position: absolute; top: 0; bottom: 0; left: 0;
            background: var(--ml-border-strong); }
    .seg { position: absolute; top: 0; bottom: 0; }
    .seg.gain { background: var(--ml-success); }
    .seg.loss { background: var(--ml-danger); }
    .num { text-align: right; font-family: var(--ml-font-mono);
           font-size: 9.5pt; }
    .dxp { text-align: right; font-family: var(--ml-font-mono);
           font-size: 9pt; }
    .dxp.up, .up { color: var(--ml-success); }
    .dxp.dn, .dn { color: var(--ml-danger); }
    .fl { color: var(--ml-muted); }
    .mv { text-align: center; font-size: 9pt; }
    .note { margin-top: 14px; font-size: 8.5pt;
            color: var(--ml-muted); max-width: 58em; }
    </style></head><body>"""]
    h.append(bpr.banknote_masthead(
        "POST-DRAFT SHIFT",
        "the table as an experience bar · projected starting lineup vs "
        f"what the sim expected · compiled {date.today():%b %d, %Y}"))
    h.append('<div class="legend">READING THE BARS — '
             '<span class="chip base"></span> expected at the table '
             '<span class="chip gain"></span> XP gained '
             '<span class="chip loss"></span> XP lost · '
             'rank arrows vs the expected order · number = projected '
             'points from the optimal starting lineup (keepers '
             'included)</div>')
    h.extend(bars)
    best = max(rows, key=lambda r: r["delta"])
    worst = min(rows, key=lambda r: r["delta"])
    me = next(r for r in rows if r["rid"] == MY_RID)
    h.append(
        '<div class="ml-h-label" style="margin-top:14px">TABLE AWARDS'
        '</div><table class="story awards"><tbody>'
        f'<tr><td class="sl">LEVELED UP</td><td><b>{SHORT[best["rid"]]}'
        f'</b> +{best["delta"]:.0f} XP over expectation — out-drafted '
        'the room model by the widest margin</td></tr>'
        f'<tr><td class="sl">DRAINED</td><td><b>{SHORT[worst["rid"]]}'
        f'</b> {worst["delta"]:.0f} XP — left the most projected points '
        'on the table vs the sim\'s read of his seat</td></tr>'
        f'<tr><td class="sl">THE DESK\'S SEAT</td><td><b>BRIAN</b> '
        f'{me["delta"]:+.0f} XP, rank {pre_rank[MY_RID]} expected → '
        f'{[r["rid"] for r in rows].index(MY_RID) + 1} actual — drafted '
        'to plan: QB liquidity + RB depth banked, the WR gap priced for '
        'the W6-10 trade window, not the table</td></tr>'
        '</tbody></table>')
    h.append("""<style>
    .story { border-collapse: collapse; width: 100%; max-width: 62em; }
    .story td { padding: 3px 6px 3px 0; font-size: 9pt; }
    .story td.sl { color: var(--ml-muted); font-weight: 700;
                   font-size: 7.5pt; letter-spacing: .4px;
                   white-space: nowrap; padding-right: 10px; }
    </style>""")
    h.append('<div class="note">Expectation = the final pre-draft '
             'simulation, frozen at keeper lock '
             '(draft_expectation_2026.json) — the sim already knew every '
             'keeper, so the delta is pure table performance: picks made '
             'vs the picks the model believed were coming. Projections '
             'are the current weekly feed; both sides of every bar move '
             'together as projections update, so the DELTA stays a clean '
             'read on draft skill.</div>')
    h.append(bpr.banknote_fineprint(
        "Metric: optimal starters (QB · 2RB · 3WR · TE · FLEX · SF) from "
        "half-PPR projections. One page, one story: who leveled up at "
        "the table."))
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
          f"({PDF_OUT.stat().st_size / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
