"""Research Desk — THE OPTION BOOK: what a late pick's keeper option is worth.

The gap this closes: the empirical redraft curve says a R10+ pick returns a
below-replacement player (expected redraft value ≤ 0), yet Watson-class
stashes are the league's best assets. The missing term is the KEEPER OPTION:
every drafted player in R3+ can be kept NEXT season at (draft round − 2),
so a late pick is a lottery ticket on next year's surplus.

Empirical, league-own method (no theory, our drafts):
  * Universe: players DRAFTED (not kept) in rounds 3-17 of the 2023 and
    2024 MONEYLEAGUE drafts. Keepers are excluded two ways, mirroring
    backtest_recommender.py: the explicit is_keeper flag, plus the repo's
    implicit-keeper rule (actual round ≥ 1.5 rounds later than the
    period-ADP-implied round — this league entered keepers as ordinary
    picks pre-2025).
  * Option payoff = what keeping him the FOLLOWING season would have been
    worth: max(0, next_season_VBD − floor0(blind[r−2])), where
    next_season_VBD = actual half-PPR points minus the superflex
    replacement level (QB22/RB31/WR42/TE13, same ranks as the VBD engine)
    from data/backtest/stats_<year+1>.json, and floor0(blind[r−2]) is the
    forgone chart value of the pick the keep would consume.
  * option_value[r] = mean payoff INCLUDING zeros (busts count);
    hit_rate[r] = share with payoff > 0. 2023 draft → 2024 stats,
    2024 draft → 2025 stats. The 2025 draft has no 2026 outcomes yet and
    is EXCLUDED. R1/R2 are keeper-ineligible → option value 0 by rule.
    Waiver adds are a different acquisition channel — out of scope.

Attribution: pick ownership joins the xlsx color overlay on
(round, slot) → pick_no (Sleeper's 2023 feed misattributes 194/204 picks),
so best-hit credits name the manager who actually made the pick.

Consumers import:
  * load_option_values()    — round → option VBD (cached json; zeros if absent)
  * composed_round_values() — round → {redraft, option, total}; the ONE
    round-value composition trade_advisor.py and build_pick_squeeze.py use:
    total = max(0, redraft blind) + option_value[round].
  * stash_score(player)     — 0..1 breakout proxy (same formula as the
    helper's CEILING upsideBonus: expert disagreement + youth).

CLI: python3 scripts/stash_curve.py
Writes data/research/stash_curve.{json,html} per the fragment contract.
"""
from __future__ import annotations

import html as _html
import json
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "data" / "research"
CURVE_JSON = OUT_DIR / "stash_curve.json"

# Same season → (league dir, draft id) map as backtest_recommender.py.
# 2025 draft intentionally absent: its option payoffs need 2026 stats.
DRAFTS = {
    2023: ("data/sleeper/league_1001657805583077376", "1001657806530957312"),
    2024: ("data/sleeper/league_1085805164784664576", "1085805164784664577"),
}
# Superflex replacement ranks — identical to the VBD engine
# (compute_replacement_ranks) and pick_value.json's replacement_ranks_used.
REPL_RANKS = {"QB": 22, "RB": 31, "WR": 42, "TE": 13, "K": 12, "DEF": 12}
ROUNDS = range(3, 18)          # keeper-eligible draft rounds
MY_RID = 9                     # Brian


# ---------------------------------------------------------------- loaders

def _blind_curve() -> dict[int, float]:
    """The forward-looking redraft chart (mean projected VBD per ADP round),
    same baseline every other pick-value consumer uses."""
    from scripts.build_2026_keepers import _load_adp_baselines
    blind, _pos = _load_adp_baselines()
    return {r: float(blind.get(r, 0.0)) for r in range(1, 18)}


def _period_adp(year: int) -> dict[str, float]:
    """Period superflex ADP (adp_2qb) per player id — the only period
    signal we trust (stored projections are contaminated; see backtest)."""
    raw = json.loads((ROOT / "data" / "backtest" / f"proj_{year}.json").read_text())
    out: dict[str, float] = {}
    for row in raw:
        pid = str(row.get("player_id") or (row.get("player") or {}).get("player_id") or "")
        try:
            adp = float((row.get("stats") or {}).get("adp_2qb") or 999.0)
        except (TypeError, ValueError):
            adp = 999.0
        if pid:
            out[pid] = adp
    return out


def _season_vbd(year: int) -> dict[str, float]:
    """Actual half-PPR VBD for a season: points minus the superflex
    replacement level at the player's position (QB22/RB31/WR42/TE13)."""
    raw = json.loads((ROOT / "data" / "backtest" / f"stats_{year}.json").read_text())
    pts_pos: dict[str, tuple[float, str]] = {}
    by_pos: dict[str, list[float]] = defaultdict(list)
    for row in raw:
        pid = str(row.get("player_id") or "")
        pts = (row.get("stats") or {}).get("pts_half_ppr")
        pos = ((row.get("player") or {}).get("position") or "").upper()
        if not pid or pts is None or pos not in REPL_RANKS:
            continue
        pts = float(pts)
        pts_pos[pid] = (pts, pos)
        by_pos[pos].append(pts)
    repl: dict[str, float] = {}
    for pos, lst in by_pos.items():
        lst.sort(reverse=True)
        rank = REPL_RANKS[pos]
        repl[pos] = lst[rank - 1] if rank <= len(lst) else (lst[-1] if lst else 0.0)
    return {pid: pts - repl[pos] for pid, (pts, pos) in pts_pos.items()}


def _xlsx_owner_by_pick_no(year: int) -> dict[int, str]:
    """(round, slot) → pick_no join against the xlsx color overlay — the
    league's source of truth for who actually made each pick."""
    from fantasy_draft.team_identity import manager_for_xlsx_nickname
    from fantasy_draft.xlsx_drafts import load_xlsx_drafts
    drafts = load_xlsx_drafts(str(ROOT / "data" / "historical" / "MONEY_LEAGUE.xlsx"))
    out: dict[int, str] = {}
    for xp in drafts.get(year, []):
        m = manager_for_xlsx_nickname(xp.manager_nickname)
        if m:
            pir = xp.slot if xp.round % 2 == 1 else 13 - xp.slot
            out[(xp.round - 1) * 12 + pir] = m["id"]
    return out


# ------------------------------------------------------------ core curve

def compute_curve() -> dict:
    blind = _blind_curve()

    def floor0_blind(r: int) -> float:
        return max(0.0, blind.get(r, 0.0))

    payoffs: dict[int, list[float]] = defaultdict(list)
    best: dict[int, dict] = {}
    keepers_excluded = 0

    for year, (ldir, did) in DRAFTS.items():
        picks = json.loads((ROOT / ldir / f"draft_{did}_picks.json").read_text())
        adp = _period_adp(year)
        nxt_vbd = _season_vbd(year + 1)
        owners = _xlsx_owner_by_pick_no(year)
        for pk in sorted(picks, key=lambda p: p["pick_no"]):
            r = pk["round"]
            if r not in ROUNDS:
                continue
            pid = str(pk["player_id"])
            # Keeper exclusion — explicit flag OR the implicit ADP-gap rule
            # (≥1.5 rounds later than period ADP implies), exactly as the
            # backtest detects this league's unflagged keepers.
            a = adp.get(pid, 999.0)
            implicit = a < 999 and (r - max(1.0, a / 12.0)) >= 1.5
            if bool(pk.get("is_keeper")) or implicit:
                keepers_excluded += 1
                continue
            baseline = floor0_blind(r - 2)
            payoff = max(0.0, nxt_vbd.get(pid, -999.0) - baseline)
            payoffs[r].append(payoff)
            if payoff > best.get(r, {}).get("payoff", 0.0):
                md = pk.get("metadata") or {}
                best[r] = {
                    "player": f"{md.get('first_name', '')} {md.get('last_name', '')}".strip(),
                    "pos": (md.get("position") or "").upper(),
                    "year": year,
                    "payoff": round(payoff, 1),
                    "manager": owners.get(pk["pick_no"], "?"),
                }

    curve = []
    for r in ROUNDS:
        lst = payoffs.get(r, [])
        n = len(lst)
        hits = sum(1 for x in lst if x > 0)
        curve.append({
            "round": r,
            "option_value": round(sum(lst) / n, 1) if n else 0.0,
            "n": n,
            "hit_rate": round(hits / n, 3) if n else 0.0,
            "hits": hits,
            "best_hit": best.get(r),
        })

    option_values = {str(r): 0.0 for r in (1, 2)}
    option_values.update({str(c["round"]): c["option_value"] for c in curve})

    return {
        "meta": {
            "generated": date.today().isoformat(),
            "seasons_used": sorted(DRAFTS),
            "excluded": "2025 draft (no 2026 outcomes yet); keepers "
                        f"(explicit flag + ADP-gap rule, {keepers_excluded} "
                        "picks); waiver adds (different acquisition channel)",
            "method": "option payoff = max(0, following-season half-PPR VBD "
                      "- floor0(blind[round-2])); mean includes zeros",
            "replacement_ranks": REPL_RANKS,
            "keeper_rule": "cost = draft round - 2; R1/R2 ineligible "
                           "(option value 0 by rule)",
        },
        "curve": curve,
        "option_values": option_values,
    }


# ------------------------------------------------- stash score + survival

def stash_score(p: dict) -> float:
    """Breakout proxy, 0..1 — the helper CEILING mode's upsideBonus
    (expert disagreement + youth) normalized by its 40-point max."""
    u = 0.0
    if p.get("fp_std") is not None:
        u += min(float(p["fp_std"]), 20.0) * 1.2          # 0..24
    if p.get("years_exp") is not None and p["years_exp"] <= 2:
        u += 10.0
    age = p.get("age")
    if age and age <= 24:
        u += 6.0
    if age and age >= 29:
        u -= 12.0
    return round(max(0.0, min(u, 40.0)) / 40.0, 3)


def survival_at(p: dict, overall: int) -> float:
    """P(still available at overall pick N) from the helper's 11-point
    draft-position quantiles svq — same interpolation as the helper JS."""
    q = p.get("svq")
    if not q:
        return 1.0
    if overall <= q[0]:
        return 1.0
    if overall > q[10]:
        return 0.0
    for i in range(1, 11):
        if overall <= q[i]:
            span = (q[i] - q[i - 1]) or 1
            f = (i - 1 + (overall - q[i - 1]) / span) / 10.0
            return max(0.0, min(1.0, 1.0 - f))
    return 0.0


def brian_stash_board(option_values: dict[str, float]) -> list[dict]:
    """Brian's R10+ picks annotated with the top-3 stash candidates likely
    (P ≥ 50%) still available. Each candidate listed once, at the earliest
    of Brian's late picks where he clears 50%."""
    data = json.loads((ROOT / "docs" / "draft_helper" / "data.json").read_text())
    my_ti = data["my_team_idx"]
    picks = [s for s in data["schedule"]
             if s["team_idx"] == my_ti and s["round"] >= 10]
    picks.sort(key=lambda s: s["overall"])
    scored = sorted(
        ((stash_score(p), p) for p in data["players"] if stash_score(p) > 0),
        key=lambda t: (-t[0], p_adp(t[1])))
    used: set[str] = set()
    board = []
    for pk in picks:
        cands = []
        for sc, p in scored:
            if p["name"] in used or len(cands) >= 3:
                continue
            sv = survival_at(p, pk["overall"])
            if sv >= 0.5:
                used.add(p["name"])
                cands.append({
                    "name": p["name"], "pos": p["pos"], "stash": sc,
                    "survival": round(sv, 2), "adp": p.get("adp"),
                    "keeper_cost": f"R{pk['round'] - 2}",
                })
        board.append({"round": pk["round"], "overall": pk["overall"],
                      "option_value": option_values.get(str(pk["round"]), 0.0),
                      "candidates": cands})
    return board


def p_adp(p: dict) -> float:
    a = p.get("adp")
    return float(a) if a else 999.0


# ---------------------------------------------------------- consumers API

def load_option_values() -> dict[int, float]:
    """Round → empirical keeper-option VBD from the cached curve.
    Zeros when the cache hasn't been built yet (degrade, don't crash)."""
    try:
        raw = json.loads(CURVE_JSON.read_text())["option_values"]
        return {int(r): float(v) for r, v in raw.items()}
    except Exception:
        return {}


def composed_round_values() -> dict[int, dict[str, float]]:
    """THE round-value composition (trade advisor + pick squeeze):
    total = max(0, redraft blind) + option_value[round].
    Redraft keeps its 0-floor (a pick is never worth negative); the option
    term prices the 2027 keeper lottery a live pick carries."""
    blind = _blind_curve()
    opt = load_option_values()
    out = {}
    for r in range(1, 18):
        redraft = max(0.0, blind.get(r, 0.0))
        option = float(opt.get(r, 0.0))
        out[r] = {"redraft": round(redraft, 1), "option": round(option, 1),
                  "total": round(redraft + option, 1)}
    return out


# ------------------------------------------------- keep-side tier book

_ML_LEAGUES = {
    2023: "data/sleeper/league_1001657805583077376",
    2024: "data/sleeper/league_1085805164784664576",
    2025: "data/sleeper/league_1245039290518360064",
}
_TIER_GHOST_VBD = -30.0        # kept player with no stats = hard bust


def keeper_tier_analysis() -> dict:
    """The keep-side of the book: every detected keeper 2023-25 (this
    league + the owner-free benchmark corpus), graded THREE ways —
      net    = season VBD − blind value of the pick burned
      locked = blind(market/ADP round) − blind(cost round)  [arbitrage]
      alpha  = season VBD − blind(market round)  [vs own price]
    net = locked + alpha. The empirical law: alpha is NEGATIVE for
    skill keepers (~−14 RB/WR, ~−25 TE — the regression tax; keepers
    skew toward last year's breakouts and the market overprices
    breakouts) and ~0 for QBs. All keeper profit is locked-in discount
    minus that tax."""
    blind = _blind_curve()

    def b(r: float) -> float:
        return max(0.0, blind.get(max(1, min(17, round(r))), 0.0))

    players = json.loads(
        (ROOT / "data/sleeper/players_nfl.json").read_text())

    units: list[tuple[int, Path, int]] = [
        (s, ROOT / rel, 12) for s, rel in _ML_LEAGUES.items()]
    corpus_f = ROOT / "data/scouting/benchmark/_corpus.json"
    if corpus_f.exists():
        for lid, m in json.loads(corpus_f.read_text()).items():
            if lid.startswith("_"):
                continue
            season = int(m["season"])
            if (ROOT / "data/backtest" / f"proj_{season}.json").exists():
                units.append((season,
                              ROOT / "data/scouting/benchmark"
                              / f"{m['season']}_{lid}", m["teams"]))

    rows = []
    for season, d, teams in units:
        adp = _period_adp(season)
        vbd = _season_vbd(season)
        for p in json.loads(next(d.glob("draft_*_picks.json")).read_text()):
            a = adp.get(p["player_id"], 999.0)
            ar = max(1.0, a / teams) if a < 999 else None
            if not (bool(p.get("is_keeper"))
                    or (ar is not None and p["round"] - ar >= 1.5)):
                continue
            if ar is None:
                continue
            v = vbd.get(p["player_id"], _TIER_GHOST_VBD)
            pos = (players.get(p["player_id"]) or {}).get("position") or "?"
            rows.append({"pos": pos, "disc": p["round"] - ar,
                         "locked": b(ar) - b(p["round"]),
                         "alpha": v - b(ar), "net": v - b(p["round"])})

    def bucket(grp: list[dict]) -> dict:
        n = len(grp)
        m = lambda k: round(sum(r[k] for r in grp) / n, 1)  # noqa: E731
        return {"n": n, "net": m("net"), "locked": m("locked"),
                "alpha": m("alpha"),
                "hit": round(100 * sum(r["net"] > 0 for r in grp) / n),
                "smash": round(100 * sum(r["net"] > 50 for r in grp) / n)}

    by_disc = [
        {"tier": name, **bucket(g)} for name, g in (
            ("<2 rds (fair price)", [r for r in rows if r["disc"] < 2]),
            ("2-4 rds", [r for r in rows if 2 <= r["disc"] < 4]),
            ("4-7 rds", [r for r in rows if 4 <= r["disc"] < 7]),
            ("7+ rds (mega)", [r for r in rows if r["disc"] >= 7]),
        ) if g]
    by_pos = [
        {"tier": pos, **bucket(g)} for pos, g in (
            (pos, [r for r in rows if r["pos"] == pos])
            for pos in ("QB", "RB", "WR", "TE")) if g]
    tax = {p["tier"]: round(max(0.0, -p["alpha"]), 1) for p in by_pos}
    return {
        "n_keepers": len(rows), "league_seasons": len(units),
        "by_discount": by_disc, "by_position": by_pos,
        "regression_tax": tax,
        "formula": "keeper value ≈ locked discount (blind-curve pts) − "
                   "regression tax (QB {QB} · RB {RB} · WR {WR} · TE {TE}); "
                   "keep only if clearly positive".format(
                       **{k: f"{v:.0f}" for k, v in tax.items()}),
    }


def keeper_regression_tax() -> dict[str, float]:
    """Position regression tax for consumers (keeper optimizer): points a
    KEPT player underperforms his own market price, empirically. Prefers
    the cached book; recomputes if absent."""
    if CURVE_JSON.exists():
        cached = json.loads(CURVE_JSON.read_text()).get("keeper_tiers")
        if cached and cached.get("regression_tax"):
            return cached["regression_tax"]
    return keeper_tier_analysis()["regression_tax"]


# ----------------------------------------------------------- fragment

def young_player_book() -> dict:
    """Grade every Sleeper-era draft pick by career-stage scenario
    (excess vs round-cohort mean), plus per-owner rookie strategy
    grades. The Rookie/Young Book (user-prompted, Jul 2026)."""
    import glob
    from collections import defaultdict
    from statistics import mean
    from scripts import fetch_backtest_data
    fetch_backtest_data.main()

    rookie_year = {}
    pos_of: dict[str, str] = {}
    for season in (2023, 2024, 2025):
        for r in json.loads((ROOT / f"data/backtest/proj_{season}.json").read_text()):
            p = r.get("player") or {}
            ry = (p.get("metadata") or {}).get("rookie_year")
            if ry:
                rookie_year[r["player_id"]] = int(ry)
            if p.get("position"):
                pos_of.setdefault(r["player_id"], p["position"])
    actual: dict[int, dict[str, float]] = {}
    wk22 = json.loads((ROOT / "data/scouting/stats/stats_2022.json").read_text())
    m22: dict[str, float] = defaultdict(float)
    for w, players in wk22.items():
        if w == "_meta":
            continue
        for pid, rec in players.items():
            pts = rec.get("pts_half_ppr")
            if pts is None:
                pts = (rec.get("pts_ppr") or 0) - 0.5 * (rec.get("rec") or 0)
            m22[pid] += float(pts)
    actual[2022] = dict(m22)
    for season in (2023, 2024, 2025):
        actual[season] = {
            r["player_id"]: float(r["stats"]["pts_half_ppr"])
            for r in json.loads((ROOT / f"data/backtest/stats_{season}.json").read_text())
            if (r.get("stats") or {}).get("pts_half_ppr") is not None}

    ident = json.loads((ROOT / "data/team_identity.json").read_text())
    rid_mid = {rec["sleeper_roster_id"]: mid
               for mid, rec in ident["managers"].items()
               if rec.get("sleeper_roster_id")}
    rid_of = {s: dict(rid_mid) for s in (2023, 2024, 2025)}
    rid_of[2023][10] = rid_of[2024][10] = "dave_aka_wang"
    rid_of[2025][10] = "josh_wildboy"

    cells = defaultdict(lambda: {"excess": [], "hits": 0})
    owners = defaultdict(lambda: {"excess": [], "hits": 0, "rounds": []})
    for d in sorted(glob.glob(str(ROOT / "data/sleeper/league_*"))):
        season = int(json.loads(open(d + "/league.json").read())["season"])
        if season not in (2023, 2024, 2025):
            continue        # the LIVE league dir matches this glob too
        picks = json.loads(open(glob.glob(d + "/draft_*_picks.json")[0]).read())
        # Keeper exclusion must include the IMPLICIT ADP-gap rule — 2023/24
        # keepers were entered as ordinary picks (truth #2); counting them
        # as draft picks lets keeper DISCOUNTS masquerade as market prices
        # (user-exposed: "R13 ARSB", "R15 Purdy" were keeps, not picks).
        adp = _period_adp(season)
        live = []
        for pk in picks:
            a = adp.get(str(pk["player_id"]), 999.0)
            implicit = a < 999 and (pk["round"] - max(1.0, a / 12.0)) >= 1.5
            if ((pk.get("metadata") or {}).get("is_keeper")
                    or pk.get("is_keeper") or implicit):
                continue
            live.append(pk)
        # Owner attribution: Sleeper's 2023 feed misattributes 194/204
        # picks (truth #1) — join the xlsx for 2023/24; 2025 is clean.
        xlsx_owner = (_xlsx_owner_by_pick_no(season)
                      if season in (2023, 2024) else {})
        by_round = defaultdict(list)
        for pk in live:
            by_round[pk["round"]].append(actual[season].get(pk["player_id"], 0.0))
        rmean = {r: mean(v) for r, v in by_round.items()}
        for pk in live:
            pid = pk["player_id"]
            ry = rookie_year.get(pid)
            if ry is None:
                continue
            yrs = season - ry
            prior = actual.get(season - 1, {}).get(pid, 0.0)
            cls = ("ROOKIE" if yrs == 0 else
                   ("YR2_PRICED" if prior >= 100 else "YR2_POSTHYPE")
                   if yrs == 1 else "YR3" if yrs == 2 else "VET")
            ex = actual[season].get(pid, 0.0) - rmean[pk["round"]]
            cells[cls]["excess"].append(ex)
            cells[cls]["hits"] += int(ex > 0)
            # position split (user-prompted, Aug 2026): the aggregate
            # cells hid a sharp per-position profile
            if pos_of.get(pid) in ("QB", "RB", "WR", "TE"):
                pc = cells[f"{cls}|{pos_of[pid]}"]
                pc["excess"].append(ex)
                pc["hits"] += int(ex > 0)
            if cls == "ROOKIE":
                mgr = (xlsx_owner.get(pk.get("pick_no"))
                       or rid_of[season].get(pk["roster_id"], "?"))
                o = owners[mgr]
                o["excess"].append(ex)
                o["hits"] += int(ex > 0)
                o["rounds"].append(pk["round"])
                # band split (user-caught: early rookies carry a ROLE
                # floor; the tax concentrates in the R5-8 hype zone)
                band = ("R1-4" if pk["round"] <= 4 else
                        "R5-8" if pk["round"] <= 8 else
                        "R9-12" if pk["round"] <= 12 else "R13-17")
                cells[f"ROOKIE_{band}"]["excess"].append(ex)
                cells[f"ROOKIE_{band}"]["hits"] += int(ex > 0)
    return {
        "cells": {c: {"n": len(v["excess"]),
                      "excess_per_pick": round(mean(v["excess"]), 1),
                      "hit_pct": round(v["hits"] / len(v["excess"]) * 100)}
                  for c, v in cells.items() if v["excess"]},
        "rookie_owners": {mid: {"n": len(v["excess"]),
                                "avg_round": round(mean(v["rounds"]), 1),
                                "excess_per_pick": round(mean(v["excess"]), 1),
                                "hit_pct": round(v["hits"] / len(v["excess"]) * 100)}
                          for mid, v in sorted(
                              owners.items(),
                              key=lambda kv: -mean(kv[1]["excess"]))
                          if v["excess"]},
    }


def build_fragment(res: dict, board: list[dict]) -> str:
    e = _html.escape

    def hit_cell(bh):
        if not bh:
            return '<td class="ml-empty">no hit yet</td>'
        return (f'<td>{e(bh["player"])} <span class="ml-note">{e(bh["pos"])} '
                f'&middot; {bh["year"]} draft ({e(bh["manager"])}) &middot; '
                f'+{bh["payoff"]:.0f}</span></td>')

    rows = "".join(
        "<tr>"
        f'<td class="ml-num">R{c["round"]}</td>'
        f'<td class="ml-num{" ml-sv-hi" if c["option_value"] >= 10 else ""}">'
        f'{c["option_value"]:.1f}</td>'
        f'<td class="ml-num">{c["n"]}</td>'
        f'<td class="ml-num">{c["hit_rate"] * 100:.0f}% '
        f'<span class="ml-note">({c["hits"]}/{c["n"]})</span></td>'
        + hit_cell(c["best_hit"]) + "</tr>"
        for c in res["curve"])

    def cand_txt(cands):
        if not cands:
            return '<span class="ml-note">covered by earlier rows</span>'
        return " &middot; ".join(
            f'{e(c["name"])} <span class="ml-note">{e(c["pos"])} '
            f'stash {c["stash"]:.2f}, P {c["survival"] * 100:.0f}%</span>'
            for c in cands)

    board_rows = "".join(
        "<tr>"
        f'<td class="ml-num">R{b["round"]} &middot; pick {b["overall"]}</td>'
        f'<td class="ml-num">{b["option_value"]:.1f}</td>'
        f'<td>{cand_txt(b["candidates"])}</td></tr>'
        for b in board)

    kt = res.get("keeper_tiers")
    tier_block = ""
    if kt:
        def tier_tbl(rows_):
            body = "".join(
                f'<tr><td>{e(t["tier"])}</td><td class="ml-num">{t["n"]}</td>'
                f'<td class="ml-num">{t["net"]:+.1f}</td>'
                f'<td class="ml-num">{t["locked"]:+.1f}</td>'
                f'<td class="ml-num">{t["alpha"]:+.1f}</td>'
                f'<td class="ml-num">{t["hit"]}%</td>'
                f'<td class="ml-num">{t["smash"]}%</td></tr>'
                for t in rows_)
            return ('<table class="ml-table ml-table--compact"><thead><tr>'
                    '<th>Tier</th><th class="ml-num">n</th>'
                    '<th class="ml-num">Net</th><th class="ml-num">Locked</th>'
                    '<th class="ml-num">Alpha</th><th class="ml-num">Hit</th>'
                    '<th class="ml-num">Smash</th></tr></thead>'
                    f"<tbody>{body}</tbody></table>")
        tier_block = f"""
<div class="ml-h-label">The keep-side book — which keeper tiers actually
pay ({kt["n_keepers"]} keepers, {kt["league_seasons"]} league-seasons
incl. the benchmark corpus)</div>
<p><strong>{e(kt["formula"])}</strong> — net return over the pick burned
splits into LOCKED (market price minus cost: the arbitrage) plus ALPHA
(performance vs the player's own price). Alpha is the regression tax:
kept players are last year's breakouts and the market overprices
breakouts. QBs alone carry no tax.</p>
{tier_tbl(kt["by_discount"])}
{tier_tbl(kt["by_position"])}
<p class="ml-fineprint">Discounts measured against period superflex ADP;
value in blind-curve points; ghosted seasons (kept player, zero stats)
counted as hard busts. Below 4 rounds of discount a keep is ceremony —
73% of all keeps in the sample sit there at ≈0 EV. The "free" R14-17
fair-price keep is the worst tier in keeper football (−34/keeper, 21%
hit): a known-mediocre veteran over a fresh lottery pick that carries
the option value priced above. The keeper optimizer scores Brian's
candidates with this tax applied natively.</p>"""

    return f"""<section class="ml-panel" id="stash-curve">
<h2>The Option Book — what a late pick's keeper option is worth</h2>
<p class="ml-serial">EMPIRICAL 2027 KEEPER OPTION BY DRAFT ROUND ·
LEAGUE DRAFTS {"+".join(str(y) for y in res["meta"]["seasons_used"])} ·
{e(res["meta"]["generated"])}</p>
<p>The redraft chart prices a R10+ pick at zero — the typical player taken
there finishes below replacement. But every drafted player is also a call
option on NEXT season: keep him at (round − 2). This table is what that
option actually paid in our league — mean next-season keeper surplus per
round, busts included.</p>
<div class="ml-h-label">The stash curve (option value = mean of
max(0, next-season VBD − cost-round chart value), zeros included)</div>
<table class="ml-table ml-table--compact">
<thead><tr><th class="ml-num">Drafted in</th>
<th class="ml-num">Option VBD</th><th class="ml-num">n</th>
<th class="ml-num">Hit rate</th><th>Best hit</th></tr></thead>
<tbody>{rows}</tbody></table>
<div class="ml-h-label">Your late picks — top stash candidates likely
there (P ≥ 50%), listed at your earliest pick that clears 50%</div>
<table class="ml-table ml-table--compact">
<thead><tr><th class="ml-num">Your pick</th>
<th class="ml-num">Round option VBD</th>
<th>Stash candidates (breakout proxy 0-1 &middot; P available)</th></tr>
</thead><tbody>{board_rows}</tbody></table>
<p class="ml-fineprint">Two seasons of history ({len(res["meta"]["seasons_used"])}
drafts, ~12 picks per round-year) — wide error bars; read this as a PRIOR,
not a price. The 2025 draft is excluded (its options pay in 2026 —
outcomes unknown). Keepers are excluded from the sample (explicit flags
plus the implicit ADP-gap rule; they were bought, not drafted); waiver
pickups are a different acquisition channel and out of scope. R1/R2 picks
are keeper-ineligible — their option value is zero by rule. Next-season
VBD uses actual half-PPR points minus superflex replacement
(QB22/RB31/WR42/TE13). Trade math elsewhere now prices every pick as
max(0, redraft chart) + this option value, so a "worthless" R14 is no
longer free — it is a lottery ticket with a measured league-own premium.
Stash candidates use the CEILING-mode breakout proxy (expert disagreement
+ youth) and the Monte-Carlo survival quantiles.</p>
{tier_block}
{young_block(res)}
</section>
"""


CELL_LABELS = [
    ("ROOKIE", "Rookies (yr 0, all rounds)"),
    ("ROOKIE_R1-4", "&nbsp;&nbsp;&middot; rookies R1-4 (role-guaranteed)"),
    ("ROOKIE_R5-8", "&nbsp;&nbsp;&middot; rookies R5-8 (the hype zone)"),
    ("ROOKIE_R9-12", "&nbsp;&nbsp;&middot; rookies R9-12"),
    ("ROOKIE_R13-17", "&nbsp;&nbsp;&middot; rookies R13-17 (option darts)"),
    ("YR2_POSTHYPE", "Yr-2 post-hype (rookie yr flopped)"),
    ("YR2_PRICED", "Yr-2 priced (rookie yr hit 100+)"),
    ("YR3", "Yr-3 (the folklore breakout window)"),
    ("VET", "Veterans (4+ yrs)"),
]


def young_block(res: dict) -> str:
    yb = res.get("young_book")
    if not yb:
        return ""
    cell_rows = "".join(
        f'<tr><td>{label}</td><td class="ml-num">{c["n"]}</td>'
        f'<td class="ml-num">{c["excess_per_pick"]:+.1f}</td>'
        f'<td class="ml-num">{c["hit_pct"]}%</td></tr>'
        for key, label in CELL_LABELS
        if (c := yb["cells"].get(key)))
    own_rows = "".join(
        f'<tr><td>{mid}</td><td class="ml-num">{o["n"]}</td>'
        f'<td class="ml-num">{o["avg_round"]}</td>'
        f'<td class="ml-num">{o["excess_per_pick"]:+.1f}</td>'
        f'<td class="ml-num">{o["hit_pct"]}%</td></tr>'
        for mid, o in yb["rookie_owners"].items())
    return f"""
<div class="ml-h-label">The Rookie &amp; Young Player Book — career-stage
scenarios, graded vs the round they cost (Sleeper-era drafts)</div>
<table class="ml-table ml-table--compact">
<thead><tr><th>Scenario</th><th class="ml-num">n</th>
<th class="ml-num">Excess/pick</th><th class="ml-num">Hit</th></tr></thead>
<tbody>{cell_rows}</tbody></table>
<p><strong>No young-player class beats its market price.</strong> With
implicit keepers excluded (their discounts once masqueraded as draft
prices here), yr-2 sophomores — proven OR post-hype — grade at or
below market, the yr-3 breakout window is a null, and veterans remain
the draft's quiet value class. The sophomore edge is real but it lives
in the KEEP (a yr-2 producer held at a round discount), never in
paying his sticker. The rookie tax is NOT uniform (user-caught): R1-4
rookies carry a guaranteed ROLE and grade market-fair with an 8% bust
rate — the bleed concentrates in the R5-8 hype zone (real draft
capital, no guaranteed volume), while R9-12 darts run nearly free
before the 2027 option premium priced above. Rules: R1-4 rookies fine
at market; R5-8 only when one FALLS to clear value; R10+ darts on
purpose.</p>
<table class="ml-table ml-table--compact">
<thead><tr><th>Owner rookie record</th><th class="ml-num">Picks</th>
<th class="ml-num">Avg rd</th><th class="ml-num">Excess/pick</th>
<th class="ml-num">Hit</th></tr></thead>
<tbody>{own_rows}</tbody></table>
<p class="ml-fineprint">Excess = actual half-PPR points minus the mean
of ALL players drafted in the same round that season — "did this pick
beat the one you passed on". Keepers excluded by explicit flag AND the
implicit ADP-gap rule; 2023/24 pick ownership joined to the xlsx
(Sleeper's 2023 feed misattributes — truth #1). Rookie honors: trevor
(+28/pick — Daniels R3) and ankur (+12 — Nix R9, Thomas R7) grade
positive by SELECTION, not volume; donnie is 0-for-7. Every
rookie&rarr;kept-next-year conversion in the sample came from R9-R14,
the ring-fuel pattern (Puka R13 / ARSB R13 / McBride R15).
Young-producers-who-changed-teams: n=4, no verdict — price the scheme
half with the Coaching Tape (XIII). Three drafts of data; cells are
directional, not laws.</p>
{position_grid(yb)}"""


POS_GRID_ROWS = [("ROOKIE", "Rookie"), ("YR2_POSTHYPE", "Yr-2 post-hype"),
                 ("YR2_PRICED", "Yr-2 priced"), ("YR3", "Yr-3"),
                 ("VET", "Veteran")]


def position_grid(yb: dict) -> str:
    cells = yb["cells"]

    def fmt(cls, pos):
        c = cells.get(f"{cls}|{pos}")
        if not c or c["n"] < 2:
            return '<td class="ml-num">&mdash;</td>'
        return (f'<td class="ml-num">{c["excess_per_pick"]:+.0f} &middot; '
                f'{c["hit_pct"]}% <span class="ml-fineprint">'
                f'({c["n"]})</span></td>')
    rows = "".join(
        f"<tr><td>{label}</td>"
        + "".join(fmt(cls, p) for p in ("QB", "RB", "WR", "TE"))
        + "</tr>"
        for cls, label in POS_GRID_ROWS)
    return f"""
<div class="ml-h-label">The position grid — same cells, split by
position (excess/pick &middot; hit rate)</div>
<table class="ml-table ml-table--compact">
<thead><tr><th>Scenario</th><th class="ml-num">QB</th>
<th class="ml-num">RB</th><th class="ml-num">WR</th>
<th class="ml-num">TE</th></tr></thead>
<tbody>{rows}</tbody></table>
<p><strong>The profile is position-specific and the aggregate hid
it.</strong> QB is the one aisle where youth pays: rookie QBs beat
their slots even at this room's jump prices, and the post-hype yr-2
QB is the best cell on the grid (Howell +154 at R11, Ridder +64; the
one bust was Richardson at R2 — the price, not the profile). RB pays
sticker only for PROVEN sophomores (+29/pick at an 86% hit rate — the
grid's most reliable cell); post-hype RBs work only as double-digit
darts. Every young-WR cell loses — rookie, post-hype, priced, yr-3
alike — the trap being the priced sophomore (the post-breakout
sticker, a 67% miss). Young-WR value exists only as a keeper
discount. TE has no sample. Caveats: n runs small, 2023-25 was a
historic rookie-QB run, and the excess baseline is the mixed-position
round cohort — trust directions, not magnitudes; the 2026 season is
the QB column's out-of-sample test.</p>"""


# ---------------------------------------------------------------- main

def main() -> None:
    res = compute_curve()
    board = brian_stash_board(res["option_values"])
    res["brian_stash_board"] = board
    res["keeper_tiers"] = keeper_tier_analysis()
    res["young_book"] = young_player_book()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    CURVE_JSON.write_text(json.dumps(res, indent=2))
    (OUT_DIR / "stash_curve.html").write_text(build_fragment(res, board))

    print("[stash_curve] round → option VBD (n, hit rate, best hit)")
    for c in res["curve"]:
        bh = c["best_hit"]
        tag = (f"best {bh['player']} {bh['year']} +{bh['payoff']:.0f}"
               if bh else "no hit")
        print(f"  R{c['round']:>2}: {c['option_value']:>6.1f}  "
              f"(n={c['n']:>2}, hit {c['hit_rate'] * 100:>3.0f}%, {tag})")
    print(f"[stash_curve] wrote {CURVE_JSON.relative_to(ROOT)} + .html "
          f"({len(board)} late picks on the stash board)")


if __name__ == "__main__":
    main()
