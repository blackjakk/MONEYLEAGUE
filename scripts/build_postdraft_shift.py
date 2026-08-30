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


def optimal_lineup(players: list[tuple[str, str, float, bool]]):
    """1QB 2RB 3WR 1TE FLEX SF, greedy on projections.
    players: (name, pos, proj, is_keeper). Returns (total, keeper_pts,
    drafted_pts) — starter points attributed to their origin."""
    by: dict[str, list[tuple[float, bool]]] = defaultdict(list)
    for _, pos, pr, keep in players:
        by[pos].append((pr, keep))
    for k in by:
        by[k].sort(reverse=True)
    picked: list[tuple[float, bool]] = []

    def take(pos, cnt):
        for _ in range(cnt):
            if by[pos]:
                picked.append(by[pos].pop(0))
    take("QB", 1), take("RB", 2), take("WR", 3), take("TE", 1)
    flex = sorted(by["RB"] + by["WR"] + by["TE"], reverse=True)
    if flex:
        picked.append(flex[0])
        for k in ("RB", "WR", "TE"):
            if flex[0] in by[k]:
                by[k].remove(flex[0])
                break
    sf = sorted(by["QB"] + by["RB"] + by["WR"] + by["TE"], reverse=True)
    if sf:
        picked.append(sf[0])
    total = sum(p for p, _ in picked)
    kpts = sum(p for p, k in picked if k)
    return total, kpts, total - kpts


def main() -> None:
    # FROZEN draft-night market state — projections and ADP as they
    # stood at the draft. The page is a snapshot document: season news
    # never rewrites anyone's table grade.
    base = json.loads((ROOT / "data/draft_baseline_2026.json").read_text())
    proj = {n: (base["projections"].get(n, 0.0),
                base["positions"].get(n, "?"))
            for n in base["projections"]}
    adp = base["adp"]
    cat = json.loads((ROOT / "data/sleeper/players_nfl.json").read_text())

    def nm(pid):
        p = cat.get(str(pid), {})
        return f"{p.get('first_name', '')} {p.get('last_name', '')}".strip()

    # keeper origin: the authoritative locked record (catches donnie's
    # commish-entered keeps the draft feed leaves unflagged)
    kept_by_rid = defaultdict(set)
    for k in json.loads(
            (ROOT / "data/keepers_2026_actual.json").read_text()):
        if isinstance(k, dict) and k.get("status") == "carryover":
            kept_by_rid[k["roster_id"]].add(k["player_name"])

    # actual draft: newest completed draft in the live league dir
    cfg = json.loads((ROOT / "configs/season_2026.json").read_text())
    lg_dir = ROOT / cfg["league_dir"]
    picks_f = sorted(glob.glob(str(lg_dir / "draft_*_picks.json")))[-1]
    actual = defaultdict(list)
    for p in json.loads(Path(picks_f).read_text()):
        n = nm(p["player_id"])
        pr, pos = proj.get(n, (0.0, "?"))
        actual[p["roster_id"]].append(
            (n, pos, pr, n in kept_by_rid[p["roster_id"]]))

    # expectation: the frozen pre-draft mock (slot team_idx -> rid)
    slot_rid = {int(k): v for k, v in cfg["slot_to_roster_id"].items()}
    expect = defaultdict(list)
    for m in json.loads(EXPECT.read_text()):
        rid = slot_rid[m["team_idx"] + 1]
        pr, pos = proj.get(m["player_name"], (0.0, m.get("position", "?")))
        expect[rid].append((m["player_name"], pos, pr,
                            m["player_name"] in kept_by_rid[rid]))

    # MARKET-ROBOT counterfactual: replay the draft's exact pick
    # sequence; keepers keep their players, every other pick takes the
    # best remaining player by frozen ADP. A team's robot haul = what
    # its seats were worth to a consensus drafter — beating it is
    # skill against the market, not against our model.
    raw_picks = sorted(json.loads(Path(picks_f).read_text()),
                       key=lambda p: p["pick_no"])
    board = sorted(adp, key=lambda n: adp[n])
    taken: set[str] = set()
    robot = defaultdict(list)
    for p in raw_picks:
        rid = p["roster_id"]
        n = nm(p["player_id"])
        if n in kept_by_rid[rid]:
            taken.add(n)
            pr, pos = proj.get(n, (0.0, "?"))
            robot[rid].append((n, pos, pr, True))
            continue
        pick = next((c for c in board if c not in taken), None)
        if pick is None:
            continue
        taken.add(pick)
        pr, pos = proj.get(pick, (0.0, "?"))
        robot[rid].append((pick, pos, pr, False))

    # 2027 OPTION BOOK: empirical option value of each drafted round
    # (stash curve) — the future-capital component starters can't see.
    curve = {c["round"]: c["option_value"] for c in json.loads(
        (ROOT / "data/research/stash_curve.json").read_text())["curve"]}
    opt = defaultdict(float)
    for p in raw_picks:
        n = nm(p["player_id"])
        if n not in kept_by_rid[p["roster_id"]]:
            pr, pos = proj.get(n, (0.0, "?"))
            if pos in ("QB", "RB", "WR", "TE"):
                opt[p["roster_id"]] += max(0.0, curve.get(p["round"], 0.0))

    rows = []
    for rid in SHORT:
        a, akeep, adraft = optimal_lineup(actual.get(rid, []))
        e, ekeep, edraft = optimal_lineup(expect.get(rid, []))
        rb, _, _ = optimal_lineup(robot.get(rid, []))
        rows.append({"rid": rid, "actual": a, "expected": e,
                     "keep": akeep, "draft": adraft,
                     "ekeep": ekeep, "edraft": edraft,
                     "delta": a - e, "vs_mkt": a - rb,
                     "opt": opt[rid]})
    pre_rank = {r["rid"]: i for i, r in enumerate(
        sorted(rows, key=lambda r: -r["expected"]), 1)}
    rows.sort(key=lambda r: -r["actual"])
    maxv = max(max(r["actual"], r["expected"]) for r in rows)

    bars = []
    for i, r in enumerate(rows, 1):
        rid = r["rid"]
        keep_w = r["keep"] / maxv * 100
        gained = r["delta"] >= 0
        # drafted segment stops at expectation when the team fell short;
        # the shortfall renders as a drained (red) segment up to the tick
        draft_end = (min(r["actual"], r["expected"])
                     if not gained else r["expected"])
        draft_w = max(0.0, draft_end - r["keep"]) / maxv * 100
        seg = abs(r["delta"]) / maxv * 100
        tick = r["expected"] / maxv * 100
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
    <div class="fill keepc" style="left:0;width:{keep_w:.1f}%"></div>
    <div class="fill draftc"
         style="left:{keep_w:.1f}%;width:{draft_w:.1f}%"></div>
    <div class="fill {'gain' if gained else 'loss'}"
         style="left:{keep_w + draft_w:.1f}%;width:{seg:.1f}%"></div>
    <div class="tick" style="left:{tick:.1f}%"></div>
  </div>
  <div class="num">{r["actual"]:,.0f}</div>
  <div class="dxp {'up' if r["delta"] >= 0 else 'dn'}">
    {r["delta"]:+,.0f}</div>
  <div class="dxp {'up' if r["vs_mkt"] >= 0 else 'dn'}">
    {r["vs_mkt"]:+,.0f}</div>
  <div class="optc">+{r["opt"]:.0f}</div>
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
    .chip.keep { background: var(--ml-border-strong); }
    .chip.draft { background: var(--ml-muted); }
    .chip.gain { background: var(--ml-success); }
    .chip.loss { background: var(--ml-danger); }
    .row { display: grid;
           grid-template-columns: 88px 1fr 50px 52px 52px 44px 30px;
           gap: 7px; align-items: center; padding: 9px 4px;
           border-bottom: 1px solid var(--ml-border); }
    .hdr { font-size: 6.8pt; letter-spacing: .5px;
           color: var(--ml-muted); border-bottom: 1px solid
           var(--ml-border-strong); padding: 2px 4px; }
    .hdr div { text-align: right; }
    .hdr .l { text-align: left; }
    .optc { text-align: right; font-family: var(--ml-font-mono);
            font-size: 9pt; color: var(--ml-muted); }
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
    .fill.keepc { background: var(--ml-border-strong); }
    .fill.draftc { background: var(--ml-muted); }
    .fill.gain { background: var(--ml-success); }
    .fill.loss { background: var(--ml-danger); }
    .tick { position: absolute; top: -3px; bottom: -3px; width: 0;
            border-left: 2px solid var(--ml-ink); }
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
        "projected starting lineup vs what the sim expected · "
        f"compiled {date.today():%b %d, %Y}"))
    h.append('<div class="legend">READING THE BARS — '
             '<span class="chip keep"></span> KEEPER CORE (assets locked '
             'before the draft) '
             '<span class="chip draft"></span> DRAFTED (what the picks '
             'became) '
             '<span class="chip gain"></span> gained vs expectation '
             '<span class="chip loss"></span> lost vs expectation · '
             'the black tick = where the pre-draft sim expected the bar '
             'to end. All numbers use the FROZEN draft-night market '
             '(projections + ADP) — season news never rewrites a table '
             'grade. VS MKT = starters vs a consensus robot drafting '
             'best-available-by-ADP from the same seats (skill against '
             'the market, not against our model). 2027 OPT = empirical '
             'option value of the rounds spent (the stash curve) — the '
             'future capital a starters-only number can\'t see.</div>')
    h.append('<div class="row hdr"><div class="l">LVL · TEAM</div>'
             '<div class="l">STARTERS BAR</div><div>PTS</div>'
             '<div>VS SIM</div><div>VS MKT</div><div>2027</div>'
             '<div></div></div>')
    h.extend(bars)
    best = max(rows, key=lambda r: r["vs_mkt"])
    worst = min(rows, key=lambda r: r["vs_mkt"])
    hoard = max(rows, key=lambda r: r["opt"])
    me = next(r for r in rows if r["rid"] == MY_RID)
    h.append(
        '<div class="ml-h-label" style="margin-top:14px">TABLE AWARDS'
        '</div><table class="story awards"><tbody>'
        f'<tr><td class="sl">BEAT THE MARKET</td><td>'
        f'<b>{SHORT[best["rid"]]}</b> {best["vs_mkt"]:+.0f} vs the '
        'ADP robot — the widest true-skill margin at the table</td></tr>'
        f'<tr><td class="sl">FED THE MARKET</td><td>'
        f'<b>{SHORT[worst["rid"]]}</b> {worst["vs_mkt"]:+.0f} — a '
        'consensus robot drafting his seats builds a better lineup'
        '</td></tr>'
        f'<tr><td class="sl">OPTION HOARD</td><td>'
        f'<b>{SHORT[hoard["rid"]]}</b> +{hoard["opt"]:.0f} in 2027 '
        'option value — the deepest futures book bought at the table'
        '</td></tr>'
        f'<tr><td class="sl">THE DESK\'S SEAT</td><td><b>BRIAN</b> '
        f'{me["delta"]:+.0f} vs sim, {me["vs_mkt"]:+.0f} vs market, '
        f'+{me["opt"]:.0f} in 2027 options — drafted to plan: QB '
        'liquidity + RB depth banked, the WR gap priced for the W6-10 '
        'trade window, not the table</td></tr>'
        '</tbody></table>')
    h.append("""<style>
    .story { border-collapse: collapse; width: 100%; max-width: 62em; }
    .story td { padding: 3px 6px 3px 0; font-size: 9pt; }
    .story td.sl { color: var(--ml-muted); font-weight: 700;
                   font-size: 7.5pt; letter-spacing: .4px;
                   white-space: nowrap; padding-right: 10px; }
    </style>""")
    h.append('<div class="note">Two baselines, one snapshot. VS SIM '
             'grades the table against the final pre-draft simulation '
             '(frozen at keeper lock — it knew every keeper), which '
             'mixes drafting skill with model surprise; VS MKT grades '
             'it against a consensus robot taking best-available-by-ADP '
             'from the identical pick sequence, which is skill alone. '
             f'Everything prices off the {esc(base["frozen"])} '
             'draft-night market snapshot (draft_baseline_2026.json), '
             'so this page is a permanent record — the season cannot '
             'retroactively change what happened at the table.</div>')
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
