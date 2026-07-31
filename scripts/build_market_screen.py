"""R3 — Market Inefficiency Screen: where the room's price diverges from
the experts' price.

The room drafts on Sleeper, so Sleeper's superflex ADP (adp_2qb) IS the
price MONEYLEAGUE actually pays. FantasyPros' superflex (OP) half-PPR
consensus is what 59 experts think the asset is worth. Both live on the
same overall-pick scale, so:

    gap = sleeper_adp - fp_consensus_pick

  gap > 0  → the room is LATE  (experts higher → your value window)
  gap < 0  → the room is EARLY (the room reaches → let them pay it)

Pipeline position: research layer. No network — on-disk caches only.
  Inputs:
    - data/sleeper_projections_2026.json  (raw Sleeper feed; same cache
      scripts/build_players_csv.py reads, parsed with the same code —
      fantasy_draft.projections with scoring="superflex" → adp_2qb)
    - data/rankings_fantasypros.json      (scripts/fetch_fantasypros.py)
  Outputs:
    - data/research/market_screen.json    (findings, machine-readable)
    - data/research/market_screen.html    (one <section> fragment,
      ml.css classes only — consumed by build_research_desk.py)

Also imported by scripts/build_weekly_movers.py (summary_lines) so the
weekly MARKET REPORT and the research desk share one computation.
"""
from __future__ import annotations

import html
import json
import re
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fantasy_draft.projections import load_projections_from_cache  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
SLEEPER_CACHE = ROOT / "data" / "sleeper_projections_2026.json"
FP_PATH = ROOT / "data" / "rankings_fantasypros.json"
FP_1QB_PATH = ROOT / "data" / "rankings_fantasypros_1qb.json"
OUT_DIR = ROOT / "data" / "research"

TEAMS = 12               # league size → 12 picks per round
MAX_ADP = 180            # ignore the undrafted tail (spec: exclude ADP>180)
TOP_N = 12               # divergences reported per direction

# FP's OP (superflex) consensus covers QB/RB/WR/TE only — K/DEF cannot be
# screened and are excluded by construction.
_SUFFIX = re.compile(r"\s+(jr|sr|ii|iii|iv|v)$")


def _norm(s: str) -> str:
    """Name key, same shape as build_draft_helper_data._norm plus suffix
    stripping (FP says 'Marvin Harrison Jr.', Sleeper says 'Marvin
    Harrison' — 19 of the top-180 differ only by suffix)."""
    s = s.lower().replace(".", "").replace("'", "").replace("-", " ").strip()
    return _SUFFIX.sub("", s)


def _round_of(pick: float) -> int:
    return int((max(pick, 1.0) - 1) // TEAMS) + 1


def _round_label(pick: float) -> str:
    """Overall pick → 'R3.04' (round + pick-within-round)."""
    p = max(pick, 1.0)
    return f"R{_round_of(p)}.{int((p - 1) % TEAMS) + 1:02d}"


def _read_phrase(entry: dict) -> str:
    fr, sr = entry["fp_round"], entry["sleeper_round"]
    if entry["gap"] > 0:
        return f"experts see R{fr} · the room pays R{sr}"
    return f"the room pays R{sr} · experts see R{fr}"


def _survival_at(q: list[int] | None, overall: float) -> float:
    """P(player still available at overall pick N) from the Monte Carlo
    draft-position quantiles svq = [p0, p10, ..., p100] of where he left
    the board across the sims (helper data.json). Same 11-point linear
    interpolation as the helper's survivalAt() — avail(N) = 1 - F(N).
    No svq = never drafted in any sim = always there."""
    if not q:
        return 1.0
    if overall <= q[0]:
        return 1.0
    if overall > q[10]:
        return 0.0
    for i in range(1, 11):
        if overall <= q[i]:
            span = (q[i] - q[i - 1]) or 1
            f = (i - 1 + (overall - q[i - 1]) / span) / 10
            return max(0.0, min(1.0, 1.0 - f))
    return 0.0


def _my_live_picks(helper: dict) -> list[dict]:
    """Brian's own picks that actually go on the clock: slot-6 schedule
    minus the rounds his keepers consume (seats spent before pick 1)."""
    my_idx = helper["my_team_idx"]
    my_rid = next(m["roster_id"] for m in helper["managers"]
                  if m["team_idx"] == my_idx)
    keeper_rounds = {k["effective_forfeit_round"] for k in helper["keepers"]
                     if k["roster_id"] == my_rid
                     and k.get("status") == "carryover"}
    return sorted((s for s in helper["schedule"]
                   if s["team_idx"] == my_idx
                   and s["round"] not in keeper_rounds),
                  key=lambda s: s["overall"])


def _kept_names() -> set[str]:
    """Names off the board before pick 1: every carryover keeper league-wide
    (Christian Watson is Brian's keeper — he slides to nobody)."""
    try:
        keepers = json.loads((ROOT / "data" / "keepers_2026.json")
                             .read_text(encoding="utf-8"))
    except FileNotFoundError:
        return set()
    return {_norm(k["player_name"]) for k in keepers
            if k.get("status") == "carryover"}


def compute_screen(top_n: int = TOP_N) -> dict:
    """The single source of truth for the screen. Returns
    {meta, room_late, room_early} with entries sorted by |gap| desc."""
    players = load_projections_from_cache(SLEEPER_CACHE, scoring="superflex")
    fp = json.loads(FP_PATH.read_text(encoding="utf-8"))
    fp_by_key: dict[tuple[str, str], dict] = {}
    for p in fp.get("players", []):
        if p.get("fp_rank_overall") is None:
            continue  # spec: exclude fp_rank missing
        fp_by_key.setdefault((_norm(p["name"]), p["position"].upper()), p)

    screened, rows = 0, []
    kept = _kept_names()
    for pl in players:
        if pl.adp > MAX_ADP:          # spec: exclude ADP>180 (room's price)
            continue
        if _norm(pl.name) in kept:    # kept players never reach the board
            continue
        f = fp_by_key.get((_norm(pl.name), pl.position.upper()))
        if f is None:
            continue
        try:  # consensus pick: average expert rank, already pick-scale
            fp_pick = float(f.get("fp_adp_avg") or f["fp_rank_overall"])
        except (TypeError, ValueError):
            fp_pick = float(f["fp_rank_overall"])
        screened += 1
        gap = round(pl.adp - fp_pick, 1)
        rows.append({
            "name": pl.name,
            "position": pl.position,
            "team": pl.team,
            "sleeper_adp": round(pl.adp, 1),
            "sleeper_round": _round_of(pl.adp),
            "sleeper_slot": _round_label(pl.adp),
            "fp_pick": round(fp_pick, 1),
            "fp_rank": f["fp_rank_overall"],
            "fp_round": _round_of(fp_pick),
            "fp_slot": _round_label(fp_pick),
            "gap": gap,
            "gap_rounds": round(gap / TEAMS, 1),
        })
    for r in rows:
        r["read"] = _read_phrase(r)

    late = sorted((r for r in rows if r["gap"] > 0), key=lambda r: -r["gap"])
    early = sorted((r for r in rows if r["gap"] < 0), key=lambda r: r["gap"])
    return {
        "meta": {
            "generated": date.today().isoformat(),
            "sleeper_source": "adp_2qb (superflex), data/sleeper_projections_2026.json",
            "fp_source": (f"FantasyPros OP half-PPR consensus, "
                          f"{fp.get('total_experts', '?')} experts, "
                          f"updated {fp.get('last_updated', '?')}"),
            "players_screened": screened,
            "max_adp": MAX_ADP,
            "teams": TEAMS,
            "convention": "gap = sleeper_adp - fp_consensus_pick; "
                          ">0 room late (value), <0 room early (avoid)",
        },
        "room_late": late[:top_n],
        "room_early": early[:top_n],
    }


def compute_model_vs_paper(top_n: int = TOP_N) -> dict:
    """MODEL vs THE ROOM'S PAPER — this league drafts live, in person, and
    rivals bring popular printed rankings in SUPERFLEX/2QB form (they're
    not bringing 1QB sheets). So the room's paper is, to first order, the
    FantasyPros OP consensus itself. The exploitable edge is therefore
    where OUR league-specific model (superflex VBD board) disagrees with
    the paper everyone else is holding:

        gap = fp_rank - model_rank

      gap > 0 → the sheets sleep on him (our board is higher) → he
                slides past the room to you
      gap < 0 → the sheets love him more than our model does → let the
                room pay the paper price
    """
    helper = json.loads((ROOT / "docs" / "draft_helper" / "data.json")
                        .read_text(encoding="utf-8"))
    kept = _kept_names()
    board = [(pl["name"], pl["pos"], pl["vbd"]) for pl in helper["players"]
             if pl.get("pos") not in ("K", "DEF", "DST")
             and pl.get("vbd") is not None]
    board.sort(key=lambda t: -t[2])
    model_rank = {(_norm(n), pos.upper()): i + 1
                  for i, (n, pos, _) in enumerate(board)}
    svq_by_key = {(_norm(pl["name"]), pl["pos"].upper()): pl.get("svq")
                  for pl in helper["players"]}
    my_picks = _my_live_picks(helper)

    fp = json.loads(FP_PATH.read_text(encoding="utf-8"))
    rows = []
    for p in fp.get("players", []):
        r_fp = p.get("fp_rank_overall")
        if r_fp is None or r_fp > 150:
            continue
        key = (_norm(p["name"]), p["position"].upper())
        if key[0] in kept:
            continue  # keepers never reach the board — no edge to trade on
        r_model = model_rank.get(key)
        if r_model is None or r_model > 200:
            continue
        gap = r_fp - r_model
        row = {
            "name": p["name"], "position": p["position"],
            "team": p.get("team", ""),
            "model_rank": r_model, "model_round": _round_of(r_model),
            "fp_rank": r_fp, "fp_round": _round_of(r_fp),
            "gap": gap,
            "read": (f"our board R{_round_of(r_model)} · "
                     f"their paper R{_round_of(r_fp)}"),
        }
        if gap > 0:
            # REACHABILITY: an edge that can't reach Brian isn't an edge.
            # The player's paper price is fp_round; the earliest seat where
            # Brian can act on the sleep is his nearest own live pick at or
            # after that round. reach = MC survival probability there.
            seat = next((s for s in my_picks if s["round"] >= row["fp_round"]),
                        None)
            reach = (_survival_at(svq_by_key.get(key), seat["overall"])
                     if seat else 0.0)
            row["reach"] = round(reach, 3)
            row["reach_pct"] = int(round(reach * 100))
            row["reach_pick"] = seat["overall"] if seat else None
            row["reach_round"] = seat["round"] if seat else None
            row["edge_score"] = round(gap * reach, 1)
        rows.append(row)
    return {
        "meta": {
            "generated": date.today().isoformat(),
            "model_source": "helper data.json superflex VBD board (K/DEF excluded)",
            "paper_source": (f"FP OP consensus ({fp.get('total_experts', '?')} "
                             "experts) — the room brings superflex paper"),
            "players_compared": len(rows),
            "reach_source": ("MC survival (svq quantiles, helper data.json) "
                             "at Brian's nearest own live pick at/after the "
                             "player's paper round; keeper rounds 8/9/14/15 "
                             "consumed"),
            "sheets_sleep_sort": "gap × reach (edge_score), desc",
        },
        "sheets_sleep": sorted((r for r in rows if r["gap"] > 0),
                               key=lambda r: (-r["edge_score"], -r["gap"])
                               )[:top_n],
        "sheets_love": sorted((r for r in rows if r["gap"] < 0),
                              key=lambda r: r["gap"])[:top_n],
    }


def summary_lines(result: dict | None = None, top_n: int = 5) -> list[str]:
    """Compact text section for the weekly MARKET REPORT
    (build_weekly_movers.py). Same computation, print-tape voice."""
    if result is None:
        result = compute_screen()
    meta = result["meta"]
    lines = ["", "INEFFICIENCY SCREEN (Sleeper room price vs FantasyPros "
                 f"consensus, {meta['players_screened']} assets)"]

    def block(title, entries):
        out = [title]
        if not entries:
            out.append("- none — the room and the experts are aligned.")
            return out
        for e in entries[:top_n]:
            out.append(
                f"- {e['name']} ({e['position']}): {e['read']} "
                f"(FP {e['fp_pick']:.0f} vs ADP {e['sleeper_adp']:.0f}, "
                f"{e['gap']:+.0f} picks)")
        return out

    lines += block("UNDERPRICED — the room is late (your window):",
                   result["room_late"])
    lines += [""]
    lines += block("OVERPRICED — the room is early (let them reach):",
                   result["room_early"])
    try:
        mvp = compute_model_vs_paper()
        lines += ["", "MODEL vs THE ROOM'S PAPER (rivals bring superflex "
                      "consensus — edge = where our board disagrees, "
                      "sorted gap x reach):"]
        for e in mvp["sheets_sleep"][:3]:
            reach = (f", {e['reach_pct']}% still there at your R"
                     f"{e['reach_round']} seat" if e.get("reach_pct")
                     is not None else "")
            lines.append(f"- {e['name']} ({e['position']}): {e['read']} "
                         f"(+{e['gap']} ranks{reach})")
        for e in mvp["sheets_love"][:2]:
            lines.append(f"- {e['name']} ({e['position']}): {e['read']} "
                         f"({e['gap']} ranks, let them pay it)")
    except FileNotFoundError:
        pass  # players csv missing — screen still valid
    return lines


# ---------------------------------------------------------------- fragment
def _badge(pos: str) -> str:
    return (f'<span class="ml-badge ml-badge--{pos.lower()}">'
            f'{html.escape(pos)}</span>')


def _table(entries: list[dict], gap_cls: str) -> str:
    head = ("<tr><th>Asset</th><th>Pos</th>"
            '<th class="ml-num">Experts</th><th class="ml-num">The room</th>'
            '<th class="ml-num">Gap</th></tr>')
    body = []
    for e in entries:
        nm = html.escape(e["name"])
        tm = html.escape(e["team"] or "FA")
        body.append(
            "<tr>"
            f'<td>{nm} <span class="ml-note">{tm}</span></td>'
            f"<td>{_badge(e['position'])}</td>"
            f'<td class="ml-num">{e["fp_pick"]:.0f} · {e["fp_slot"]}</td>'
            f'<td class="ml-num">{e["sleeper_adp"]:.0f} · {e["sleeper_slot"]}</td>'
            f'<td class="ml-num {gap_cls}">{e["gap"]:+.0f}</td>'
            "</tr>")
    if not body:
        body = ['<tr><td colspan="5" class="ml-empty">No divergences '
                "here — the room and the experts are aligned.</td></tr>"]
    return ('<table class="ml-table ml-table--compact">'
            f"<thead>{head}</thead><tbody>{''.join(body)}</tbody></table>")


def _reach_cell(e: dict) -> str:
    """Reach% styled like the helper's survival column (sv classes carry
    the same hi/mid/lo thresholds: >=70 / >=30)."""
    pct = e.get("reach_pct")
    if pct is None or e.get("reach_pick") is None:
        return '<td class="ml-num">—</td>'
    cls = "ml-sv-hi" if pct >= 70 else ("ml-sv-mid" if pct >= 30 else "ml-sv-lo")
    return (f'<td class="ml-num"><span class="{cls}">{pct}%</span> '
            f'<span class="ml-note">R{e["reach_round"]}</span></td>')


def _mvp_table(entries: list[dict], gap_cls: str, with_reach: bool = False) -> str:
    reach_th = ('<th class="ml-num">Reach</th>' if with_reach else "")
    head = ("<tr><th>Asset</th><th>Pos</th>"
            '<th class="ml-num">Our board</th>'
            '<th class="ml-num">Their paper</th>'
            f'<th class="ml-num">Gap</th>{reach_th}</tr>')
    body = []
    for e in entries:
        reach_td = _reach_cell(e) if with_reach else ""
        body.append(
            "<tr>"
            f'<td>{html.escape(e["name"])} '
            f'<span class="ml-note">{html.escape(e["team"] or "FA")}</span></td>'
            f"<td>{_badge(e['position'])}</td>"
            f'<td class="ml-num">#{e["model_rank"]} · R{e["model_round"]}</td>'
            f'<td class="ml-num">#{e["fp_rank"]} · R{e["fp_round"]}</td>'
            f'<td class="ml-num {gap_cls}">{e["gap"]:+d}</td>'
            f"{reach_td}"
            "</tr>")
    if not body:
        cols = 6 if with_reach else 5
        body = [f'<tr><td colspan="{cols}" class="ml-empty">Our board and '
                "the paper agree — no edges here.</td></tr>"]
    return ('<table class="ml-table ml-table--compact">'
            f"<thead>{head}</thead><tbody>{''.join(body)}</tbody></table>")


def build_model_block(mvp: dict | None = None) -> str:
    """MODEL vs THE ROOM'S PAPER — the headline block. The room brings
    superflex consensus paper (user-confirmed), so the edge is where OUR
    board disagrees with it — discounted by whether the edge can
    actually reach Brian's seat (reach%)."""
    if mvp is None:
        try:
            mvp = compute_model_vs_paper(top_n=10)
        except FileNotFoundError:
            return ""
    m = mvp["meta"]
    return "\n".join([
        '<div class="ml-h-label">Model vs the room\u2019s paper '
        "(they bring superflex consensus \u2014 this is the real edge)</div>",
        '<div class="ml-h-label">The sheets sleep on \u2014 slides to you '
        "(sorted by gap \u00d7 reach)</div>",
        _mvp_table(mvp["sheets_sleep"], "ml-sv-hi", with_reach=True),
        '<div class="ml-h-label">The sheets love \u2014 let them pay the paper price</div>',
        _mvp_table(mvp["sheets_love"], "ml-sv-lo"),
        '<p class="ml-fineprint">This league drafts live and in person, and '
        "rivals bring printed superflex/2QB rankings \u2014 assume every seat "
        "sees what FantasyPros sees. The exploitable edge is therefore where "
        "our league-specific board (superflex VBD + keeper context) departs "
        "from that consensus: positive gap = the paper ranks him later than "
        "we do, so he should reach your pick; negative gap = the paper is "
        "higher than our board, so someone else will pay it. REACH = Monte "
        "Carlo survival probability (the helper\u2019s 300-sim draft-position "
        "quantiles, same 11-point interpolation) at Brian\u2019s nearest own "
        "live pick at or after the player\u2019s paper round \u2014 slot 6, "
        "keeper rounds 8/9/14/15 already spent. The sleep table is ordered "
        "by gap \u00d7 reach because an edge that can\u2019t reach your seat "
        "isn\u2019t an edge: a big gap at single-digit reach is trivia, not "
        f"a plan. Sources: {html.escape(m['model_source'])} vs "
        f"{html.escape(m['paper_source'])}; "
        f"{m['players_compared']} players compared.</p>",
    ]) + "\n"


def build_sharp_block() -> str:
    """THE SHARP MINORITY — trimmed consensus of FP's top-8 draft-accuracy
    experts (equal weight, select-crowd construction) vs the full
    consensus the room prints. RB/WR/TE only: the sharp file is
    1QB-format, so its QB ordering is meaningless in a superflex room.
    Divergence >= 1.5 rounds flags where the informed minority disagrees
    with the room's paper."""
    sharp_f = ROOT / "data" / "rankings_fantasypros_sharp.json"
    paper_f = ROOT / "data" / "rankings_fantasypros_1qb.json"
    if not (sharp_f.exists() and paper_f.exists()):
        return ""
    sharp = json.loads(sharp_f.read_text())
    paper = json.loads(paper_f.read_text())
    experts = sharp.get("experts") or []
    paper_rank = {_norm(p["name"]): p.get("fp_rank_overall")
                  for p in paper.get("players", [])
                  if p.get("position") in ("RB", "WR", "TE")}
    rows = []
    for p in sharp.get("players", []):
        if p.get("position") not in ("RB", "WR", "TE"):
            continue
        pr = paper_rank.get(_norm(p["name"]))
        sr = p.get("sharp_rank")
        if pr is None or sr is None or (pr > 150 and sr > 150):
            continue
        gap = pr - sr          # positive = sharps HIGHER than the paper
        if abs(gap) >= 12:
            rows.append({"name": p["name"], "pos": p["position"],
                         "sharp": sr, "paper": pr, "gap": gap})
    rows.sort(key=lambda r: -abs(r["gap"]))
    if not rows:
        return ""

    def tbl(entries, cls):
        body = "".join(
            f'<tr><td>{html.escape(r["name"])}</td><td>{_badge(r["pos"])}</td>'
            f'<td class="ml-num">#{r["sharp"]}</td>'
            f'<td class="ml-num">#{r["paper"]}</td>'
            f'<td class="ml-num {cls}"><b>{r["gap"]:+d}</b></td></tr>'
            for r in entries)
        return ('<table class="ml-table ml-table--compact"><thead><tr>'
                '<th>Player</th><th>Pos</th><th class="ml-num">Sharp-8</th>'
                '<th class="ml-num">Room paper</th>'
                '<th class="ml-num">Gap</th></tr></thead>'
                f"<tbody>{body}</tbody></table>")
    love = [r for r in rows if r["gap"] > 0][:6]
    fade = [r for r in rows if r["gap"] < 0][:6]
    names = ", ".join(f'{html.escape(e["name"] or "?")} '
                      f'(#{e["draft_rank"]})' for e in experts[:8])
    return "\n".join([
        '<div class="ml-h-label">The sharp minority — top-8 accuracy '
        "experts vs the room's paper (RB/WR/TE)</div>",
        '<div class="ml-h-label">Sharps higher than the paper '
        "(hidden value)</div>", tbl(love, "ml-sv-hi"),
        '<div class="ml-h-label">Sharps lower — extra reason to let '
        "the room pay</div>", tbl(fade, "ml-sv-lo"),
        '<p class="ml-fineprint">Trimmed consensus = equal-weight average '
        "of the top 8 experts by FantasyPros draft-accuracy placement "
        "(select-crowd construction: selection by past accuracy, boring "
        "weights, K large enough to dilute single-season contest noise). "
        f"Current panel: {names}. 1QB-format ranks — QBs excluded as "
        "meaningless for this superflex room. HEADLINE FINDING: the sharp "
        "panel agrees with the full consensus within about one round on "
        "nearly every player — the rows above are the ONLY daylight, none "
        "beyond a round and a half. Whispers for coin-flip picks, never a "
        "board; the measured edges (VBD, keeper context, room tendencies) "
        "remain the real product.</p>",
    ]) + "\n"


def build_vegas_block() -> str:
    """THE VEGAS BOOK — season projections implied by Vegas player props
    (firstdown.studio, user-requested) vs the room's superflex paper.
    Money, not opinion. POSITION ranks only (the site's scoring format
    never touches our points), all four positions valid — including QBs,
    since pos-rank order is format-free."""
    veg_f = ROOT / "data" / "rankings_vegas.json"
    paper_f = ROOT / "data" / "rankings_fantasypros.json"
    if not (veg_f.exists() and paper_f.exists()):
        return ""
    veg = json.loads(veg_f.read_text())
    paper = json.loads(paper_f.read_text())
    # paper position ranks from the superflex consensus
    by_pos: dict[str, list] = {}
    for p in paper.get("players", []):
        if p.get("position") in ("QB", "RB", "WR", "TE"):
            by_pos.setdefault(p["position"], []).append(p)
    paper_rank = {}
    for pos, lst in by_pos.items():
        lst.sort(key=lambda p: p.get("fp_rank_overall") or 9999)
        for i, p in enumerate(lst, 1):
            paper_rank[(pos, _norm(p["name"]))] = i
    rows = []
    for v in veg.get("players", []):
        pr = paper_rank.get((v["position"], _norm(v["name"])))
        if pr is None or (pr > 40 and v["vegas_pos_rank"] > 40):
            continue
        gap = pr - v["vegas_pos_rank"]   # positive = Vegas HIGHER
        if abs(gap) >= 6:
            rows.append({"name": v["name"], "pos": v["position"],
                         "vegas": v["vegas_pos_rank"], "paper": pr,
                         "gap": gap})
    rows.sort(key=lambda r: -abs(r["gap"]))
    if not rows:
        return ""

    def tbl(entries, cls):
        body = "".join(
            f'<tr><td>{html.escape(r["name"])}</td><td>{_badge(r["pos"])}</td>'
            f'<td class="ml-num">{r["pos"]}{r["vegas"]}</td>'
            f'<td class="ml-num">{r["pos"]}{r["paper"]}</td>'
            f'<td class="ml-num {cls}"><b>{r["gap"]:+d}</b></td></tr>'
            for r in entries)
        return ('<table class="ml-table ml-table--compact"><thead><tr>'
                '<th>Player</th><th>Pos</th><th class="ml-num">Vegas</th>'
                '<th class="ml-num">Room paper</th>'
                '<th class="ml-num">Gap</th></tr></thead>'
                f"<tbody>{body}</tbody></table>")
    love = [r for r in rows if r["gap"] > 0][:7]
    fade = [r for r in rows if r["gap"] < 0][:7]
    return "\n".join([
        '<div class="ml-h-label">The Vegas book — props-implied season '
        "ranks vs the room's paper (money, not opinion)</div>",
        '<div class="ml-h-label">Vegas higher than the paper</div>',
        tbl(love, "ml-sv-hi"),
        '<div class="ml-h-label">Vegas lower — the books are not '
        "paying for the hype</div>", tbl(fade, "ml-sv-lo"),
        '<p class="ml-fineprint">Source: firstdown.studio season '
        "projections implied by Vegas player props — the only board on "
        "this page backed by money rather than opinion. POSITION ranks "
        "compared (the site's scoring format never touches our VBD "
        "math); gaps of 6+ positional spots shown. Props price VOLUME "
        "commitments (yardage/TD markets) and are strongest exactly "
        "where projections argue — role questions. A third voice for "
        "coin flips: when our model, the paper, and the money point the "
        "same way, stop hesitating.</p>",
    ]) + "\n"


def build_tiers_block() -> str:
    """THE CROWD'S TIER CLIFFS — clustered-consensus tier boundaries
    (fantasyfootballtiers.com, user-requested). Rivals running tier
    sheets panic when a tier is about to empty: the boundaries are a
    RUN-TRIGGER map for the live draft. Each boundary is annotated with
    our market round; misfits (players the crowd tiers >=1.5 rounds away
    from where our board prices them) are called out."""
    tiers_f = ROOT / "data" / "rankings_tiers.json"
    if not tiers_f.exists():
        return ""
    tiers = json.loads(tiers_f.read_text()).get("tiers", {})
    helper_f = ROOT / "docs" / "draft_helper" / "data.json"
    if not (tiers and helper_f.exists()):
        return ""
    helper = json.loads(helper_f.read_text())
    adp_of = {_norm(p["name"]): p.get("adp")
              for p in helper.get("players", [])}
    kept = {_norm(n) for n in _kept_names()}

    def rd(name: str):
        a = adp_of.get(_norm(name))
        return None if a is None or a >= 900 else max(1, round(a / 12))

    boundary_rows, misfits = [], []
    for pos in ("QB", "RB", "WR", "TE"):
        ts = tiers.get(pos) or []
        bits = []
        for t in ts[:-1]:
            last = t["players"][-1]
            r = rd(last)
            k = "*" if _norm(last) in kept else ""
            bits.append(f'T{t["tier"]}&rarr; after {html.escape(last)}{k}'
                        + (f' <span class="ml-note">~R{r}</span>' if r else ""))
        if bits:
            boundary_rows.append(
                f'<tr><td>{_badge(pos)}</td><td>{" &middot; ".join(bits)}</td></tr>')
        for t in ts:
            rds = [x for x in (rd(p) for p in t["players"]) if x]
            if len(rds) < 3:
                continue
            med = sorted(rds)[len(rds) // 2]
            for p in t["players"]:
                r = rd(p)
                if r and abs(r - med) >= 2:
                    misfits.append(
                        f'{html.escape(p)} <span class="ml-note">{pos} crowd '
                        f'T{t["tier"]} (tier ~R{med}) vs market R{r}</span>')
    if not boundary_rows:
        return ""
    misfit_line = ("<p><b>Tier misfits</b> (the crowd groups them "
                   f"rounds away from their market price): "
                   f"{'; '.join(misfits[:8])}</p>" if misfits else "")
    return "\n".join([
        '<div class="ml-h-label">The crowd’s tier cliffs — '
        "run-trigger map (clustered consensus tiers)</div>",
        '<table class="ml-table ml-table--compact"><tbody>',
        *boundary_rows,
        "</tbody></table>", misfit_line,
        '<p class="ml-fineprint">Source: fantasyfootballtiers.com '
        "(Boris-Chen-style clustering of expert consensus, half-PPR; the "
        "QB list is 1QB-ordered — tier GROUPS usable, superflex pricing "
        "not). How to use at the table: when a tier’s last man "
        "(listed above) is about to go, rivals on tier sheets start the "
        "run — act one pick before the cliff, not one after. * = "
        "predicted keeper (that cliff arrives a body sooner than the "
        "sheet suggests). Refreshes weekly, cache-first.</p>",
    ]) + "\n"


def build_fragment(result: dict) -> str:
    meta = result["meta"]
    late, early = result["room_late"], result["room_early"]
    # The EDGE leads (truth #7: model-vs-paper is what's tradeable); the
    # Sleeper-vs-FP blocks are market context and follow it.
    mvp = result.get("model_vs_paper") or {}
    sleep = (mvp.get("sheets_sleep") or [{}])
    hero = (f"{sleep[0]['name']}: our board R{sleep[0]['model_round']} · "
            f"their paper R{sleep[0]['fp_round']} · reach "
            f"{sleep[0]['reach_pct']}%" if sleep and sleep[0].get("name")
            else (f"{late[0]['name']}: {late[0]['read']}" if late
                  else "the room and the experts are aligned"))
    parts = [
        '<section class="ml-panel" id="market-screen">',
        "<h2>Market Inefficiency Screen</h2>",
        f'<p class="ml-serial">SLEEPER ADP_2QB vs FANTASYPROS OP CONSENSUS '
        f'· {meta["players_screened"]} ASSETS · '
        f'{html.escape(meta["generated"])}</p>',
        f"<p>Top edge — {html.escape(hero)}.</p>",
        build_model_block(result.get("model_vs_paper")),
        build_vegas_block(),
        build_sharp_block(),
        build_tiers_block(),
        '<div class="ml-h-label">Market context — underpriced vs the '
        "experts (the room is late)</div>",
        _table(late, "ml-sv-hi"),
        '<div class="ml-h-label">Market context — overpriced vs the '
        "experts (the room is early)</div>",
        _table(early, "ml-sv-lo"),
        '<p class="ml-fineprint">How to read: the room drafts on Sleeper, '
        "so Sleeper superflex ADP is the price MONEYLEAGUE actually pays; "
        "FantasyPros is what the experts say the asset is worth. When the "
        "experts are higher (positive gap, in picks), that’s your "
        "window ONLY if that seat drafts off online ADP — in THIS room, "
        "everyone reads the paper, so treat these gaps as market context, "
        "not guaranteed slides (the model-vs-paper block above is the real edge). "
        f"Sources: {html.escape(meta['fp_source'])}; Sleeper adp_2qb, "
        f"assets priced inside pick {meta['max_adp']} only (K/DEF not "
        "covered by the consensus). Consensus disagreement, injuries and "
        "keeper withdrawals can all masquerade as inefficiency — "
        "check the disclosures before trading on this page.</p>",
        "</section>",
    ]
    return "\n".join(parts) + "\n"


def main() -> None:
    result = compute_screen()
    try:
        result["model_vs_paper"] = compute_model_vs_paper(top_n=10)
    except FileNotFoundError:
        pass  # helper data.json missing — ADP screen still valid
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    jpath = OUT_DIR / "market_screen.json"
    hpath = OUT_DIR / "market_screen.html"
    jpath.write_text(json.dumps(result, indent=2), encoding="utf-8")
    hpath.write_text(build_fragment(result), encoding="utf-8")

    meta = result["meta"]
    print(f"[market_screen] screened {meta['players_screened']} assets "
          f"(ADP ≤ {meta['max_adp']}, FP-ranked)")
    for label, key in (("room late ", "room_late"),
                       ("room early", "room_early")):
        top = result[key][0] if result[key] else None
        if top:
            print(f"  #1 {label}: {top['name']} ({top['position']}) "
                  f"{top['gap']:+.0f} picks — {top['read']}")
    mvp = result.get("model_vs_paper")
    if mvp and mvp["sheets_sleep"]:
        e = mvp["sheets_sleep"][0]
        print(f"  #1 reachable edge: {e['name']} ({e['position']}) "
              f"+{e['gap']} ranks x {e.get('reach_pct', '?')}% reach "
              f"at R{e.get('reach_round', '?')} "
              f"(edge_score {e.get('edge_score')})")
    print(f"  Wrote {jpath.relative_to(ROOT)} and {hpath.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
