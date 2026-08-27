"""Build the League Desk bot's knowledge pack.

One JSON with everything the bot may talk about in the league chat.
The boundary is deliberate and simple: ONLY what the Almanac already
publishes to the whole league — standings, champions, the purse and
tax ledgers, season stories (swing trades, tank years), all-time
records, head-to-heads, league rules. NOTHING from the Research Desk
(dossiers, fingerprints, edges, keeper predictions, draft plans) —
the bot is a records clerk, not a leak.

Output: data/bot_knowledge.json (committed — the bot fetches it from
GitHub raw so a locally-running bot self-updates with the weekly
pipeline).
"""
from __future__ import annotations

import json
from collections import defaultdict
from datetime import date
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.build_almanac import (DUES, PURSE_START, SHORT,  # noqa: E402
                                   TANK_BAR, sleeper_champions,
                                   sleeper_engines, sleeper_standings,
                                   swing_trades, tank_ledger, tax_ledger,
                                   yahoo_games, sleeper_games)
from scripts.build_history_charts import KNOWN_CHAMPIONS  # noqa: E402
from fantasy_draft.team_identity import load_identity  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "bot_knowledge.json"

RULES = {
    "format": "12-team superflex, half-PPR, keeper league on Sleeper "
              "(founded 2011 on Yahoo at 8 teams; 10 from 2013, 12 from "
              "2019; moved to Sleeper in 2023)",
    "keepers": "Up to 4 keepers; cost = round drafted minus 2 per year "
               "kept; max 3 consecutive years kept (the clock follows "
               "the player through trades); R1/R2 forfeits are "
               "ineligible; missing the exact cost round bumps the "
               "keeper to the next earlier owned free round",
    "draft_order": "Consolation-bracket placements set picks 1-6 "
                   "(toilet-bowl winner drafts 1st); playoff finish "
                   "reversed sets 7-12 (champion drafts 12th). In force "
                   "since 2015 ('You can tank, but at what cost?')",
    "money": "Dues $150 (were $75 in 2015, $100 2016-21). Winner takes "
             "the pot; regular-season best gets the buy-in back (voted "
             "2016). Low-score tax: each regular-season week the low "
             "scorer pays the top scorer — $10 flat 2017-18 (born 'to "
             "prevent tanking'), 10+5 per consecutive low 2019-21 "
             "(newcomers flat $10), $15 +$5 per additional low week "
             "since 2022",
}


def main() -> None:
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
        champs[s], runners[s] = c, r

    yg, sg = yahoo_games(), sleeper_games()
    all_gm = {**yg, **sg}
    tanks = tank_ledger()
    trades = swing_trades()
    engines = sleeper_engines()

    def standings_rows(season):
        if season in era:
            return [{"manager": t["manager"], "rank": t["rank"],
                     "wins": t["wins"], "losses": t["losses"],
                     "pf": t["pf"], "reg_best":
                         str(t.get("playoff_seed")) == "1"}
                    for t in sorted(era[season]["teams"],
                                    key=lambda t: t["rank"])]
        rows = sl_stand.get(season) or []
        return [{**r, "reg_best": i == 0} for i, r in enumerate(rows)]

    debuts: dict[str, int] = {}
    for s in sorted(set(era) | set(sl_stand)):
        for r in standings_rows(s):
            debuts.setdefault(r["manager"], s)
    taxes = tax_ledger(all_gm, debuts)

    seasons = {}
    purse = defaultdict(lambda: {"net": 0, "titles": 0, "reg": 0,
                                 "tax": 0, "seasons": 0})
    for s in sorted(set(era) | set(sl_stand)):
        rows = standings_rows(s)
        entry = {"champion": champs.get(s), "runner_up": runners.get(s),
                 "teams": len(rows), "standings": rows}
        games = all_gm.get(s) or []
        reg = [g for g in games if not g["playoffs"]]
        if reg:
            shoot = max(reg, key=lambda g: g["sides"][0][1] + g["sides"][1][1])
            entry["shootout"] = {"week": shoot["week"], "sides": shoot["sides"]}
            tm, tp, tw = max(((m, p, g["week"]) for g in reg
                              for m, p in g["sides"]), key=lambda x: x[1])
            entry["top_week"] = {"manager": tm, "points": tp, "week": tw}
        finals = [g for g in games if g["playoffs"] and not g["consolation"]
                  and champs.get(s) in {m for m, _ in g["sides"]}]
        if finals:
            f = max(finals, key=lambda g: g["week"])
            entry["final"] = {"week": f["week"], "sides": f["sides"]}
        if s in trades:
            entry["swing_trade"] = trades[s]
        tanky = {m: {"sold_par": round(r["sold"]), "deals": r["deals"]}
                 for m, r in (tanks.get(s) or {}).items()
                 if r["sold"] >= TANK_BAR}
        if tanky:
            entry["tank_years"] = tanky
        if s in engines:
            entry["champion_engine_started_pts"] = engines[s]
        if s >= PURSE_START and champs.get(s):
            dues = DUES.get(s, 150)
            entrants = [r["manager"] for r in rows]
            rw = next((r["manager"] for r in rows if r["reg_best"]), None)
            tx = taxes.get(s) or {}
            entry["purse"] = {
                "dues": dues,
                "champion_collects": dues * (len(entrants) - 1),
                "reg_season_best_plays_free": rw,
                "tax": {m: {"paid": v["paid"], "collected": v["got"],
                            "low_weeks": v["lows"]}
                        for m, v in tx.items()
                        if v["paid"] or v["got"]},
            }
            for m in entrants:
                purse[m]["net"] -= dues
                purse[m]["seasons"] += 1
            if rw:
                purse[rw]["net"] += dues
                purse[rw]["reg"] += 1
            purse[champs[s]]["net"] += dues * (len(entrants) - 1)
            purse[champs[s]]["titles"] += 1
            for m, v in tx.items():
                purse[m]["net"] += v["got"] - v["paid"]
                purse[m]["tax"] += v["got"] - v["paid"]
        seasons[s] = entry

    h2h = defaultdict(lambda: {"w": 0, "l": 0, "playoff_w": 0,
                               "playoff_l": 0})
    for s, games in all_gm.items():
        for g in games:
            (a, ap), (b, bp) = g["sides"]
            if not (a and b) or ap == bp:
                continue
            win, lose = (a, b) if ap > bp else (b, a)
            h2h[f"{win}|{lose}"]["w"] += 1
            h2h[f"{lose}|{win}"]["l"] += 1
            if g["playoffs"] and not g["consolation"]:
                h2h[f"{win}|{lose}"]["playoff_w"] += 1
                h2h[f"{lose}|{win}"]["playoff_l"] += 1

    ident = load_identity(ROOT / "data/team_identity.json")
    managers = {}
    for mid, rec in ident["managers"].items():
        managers[mid] = {
            "short": SHORT.get(mid, mid[:4].upper()),
            "name": rec.get("canonical_name"),
            "sleeper_display": rec.get("sleeper_display_name"),
            "yahoo_team_names": rec.get("yahoo_team_names") or {},
        }

    tank_career = defaultdict(lambda: {"sold_par": 0, "tank_years": []})
    for s, d in tanks.items():
        for m, r in d.items():
            tank_career[m]["sold_par"] += round(r["sold"])
            if r["sold"] >= TANK_BAR:
                tank_career[m]["tank_years"].append(s)

    out = {
        "meta": {"generated": str(date.today()),
                 "league": "MONEYLEAGUE",
                 "coverage": "2011-" + str(max(seasons)),
                 "note": "All figures computed from the league archives "
                         "(Yahoo 2011-2022, Sleeper 2023+, the league "
                         "xlsx). Purse from 2016 (winner-takes-all era); "
                         "tax from 2017. PAR = rest-of-season points "
                         "above replacement."},
        "rules": RULES,
        "titles": {m: sum(1 for c in champs.values() if c == m)
                   for m in {c for c in champs.values() if c}},
        "seasons": seasons,
        "purse_all_time": dict(sorted(purse.items(),
                                      key=lambda kv: -kv[1]["net"])),
        "tank_all_time": dict(sorted(tank_career.items(),
                                     key=lambda kv: -kv[1]["sold_par"])),
        "head_to_head": dict(h2h),
        "managers": managers,
    }
    OUT.write_text(json.dumps(out, separators=(",", ":")))
    print(f"[bot_knowledge] wrote {OUT.relative_to(ROOT)} "
          f"({OUT.stat().st_size / 1024:.0f} KB, "
          f"{len(seasons)} seasons, {len(h2h)} h2h pairs)")


if __name__ == "__main__":
    main()
