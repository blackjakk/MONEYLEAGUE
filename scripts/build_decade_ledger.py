"""The DECADE LEDGER: PAR-grade every Yahoo-era trade, 2011-2022.

The behavioral pass (Jul 15) counted 136 trades; this grades them the
same way the Sleeper-era Trade Ledger grades its book — each side's
received-minus-sent rest-of-season points above positional replacement
(PAR) over the weeks AFTER the trade week — so the two eras concatenate
into one all-time standings table.

Cross-platform adaptations, stated plainly:
  - Player join: Yahoo trade payloads carry full names; points come
    from Sleeper's weekly archive (data/scouting/stats/stats_<yr>.json,
    fetched by fetch_trade_intel.fetch_stats back to 2011). Names
    resolve via the catalog (normalized) — unresolved players are
    dropped and COUNTED, never guessed.
  - Replacement levels scale with league size (the league grew
    8 -> 10 -> 12): rank N per position = the 12-team ledger ranks
    times teams/12, using each season's median weekly score at that
    rank.
  - Trade week from the Yahoo timestamp vs a Sep-5 kickoff anchor
    (accurate to +-1 week, which PAR windows tolerate).
  - Draft-pick legs: the Yahoo transactions API drops them, but the
    old cookie-scraper archive (data/yahoo/league_*/trades_*.json)
    kept them — 97 of the 136 trades moved picks. Each cookie trade
    is joined to its API twin by the set of player names moved, and
    per-side picks_in/picks_out ride along. A side that eats a PAR
    loss while netting future picks isn't fleeced — it's SELLING THE
    YEAR; the Almanac's tank labels read exactly this.

Output: data/research/decade_ledger.json + printed verdicts (all-time
standings incl. the Sleeper era, the Brian<->Trevor pair net, Ankur's
2022 heist grade, biggest heists of the decade).
"""
from __future__ import annotations

import datetime
import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fantasy_draft.name_aliases import resolve_xlsx_name  # noqa: E402
from fantasy_draft.team_identity import load_identity  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
YAHOO = ROOT / "data" / "yahoo"
STATS = ROOT / "data" / "scouting" / "stats"
OUT = ROOT / "data" / "research" / "decade_ledger.json"
SEASONS = range(2011, 2023)
# 12-team replacement ranks (same as the Sleeper ledger), scaled by size.
RANKS_12 = {"QB": 12, "RB": 30, "WR": 36, "TE": 12, "K": 12, "DEF": 12}


def norm(s: str) -> str:
    s = (s.lower().replace(".", "").replace("'", "")
         .replace("-", " ").strip())
    for suf in (" iii", " ii", " iv", " jr", " sr", " v"):
        if s.endswith(suf):
            s = s[: -len(suf)].strip()
    return s


def week_of(ts: str, season: int) -> int:
    d = datetime.datetime.utcfromtimestamp(int(ts)).date()
    kickoff = datetime.date(season, 9, 5)
    if d < kickoff:
        return 0
    return min(17, (d - kickoff).days // 7 + 1)


def load_week_stats(season: int) -> dict[int, dict]:
    raw = json.loads((STATS / f"stats_{season}.json").read_text())
    return {int(w): v for w, v in raw.items() if w != "_meta"}


def replacement_levels(weeks: dict[int, dict], teams: int) -> dict[str, float]:
    """Per-position replacement = median across weeks of the rank-N
    weekly half-PPR score, N scaled to league size."""
    import statistics as st
    per_pos_weekly: dict[str, list[float]] = defaultdict(list)
    for w, players in weeks.items():
        by_pos: dict[str, list[float]] = defaultdict(list)
        for rec in players.values():
            pts = rec.get("pts_half_ppr")
            if pts is None:
                pts = (rec.get("pts_ppr") or 0) - 0.5 * (rec.get("rec") or 0)
            if rec.get("pos") in RANKS_12:
                by_pos[rec["pos"]].append(float(pts))
        for pos, lst in by_pos.items():
            n = max(1, round(RANKS_12[pos] * teams / 12))
            lst.sort(reverse=True)
            if len(lst) >= n:
                per_pos_weekly[pos].append(lst[n - 1])
    return {pos: round(st.median(v), 2) for pos, v in per_pos_weekly.items()
            if v}


def parse_trades(season: int, name_mid: dict) -> list[dict]:
    lid_dir = next(
        p for p in YAHOO.iterdir()
        if p.name.startswith(f"{season}_") and p.is_dir()
        and json.loads((p / "league.json").read_text())["fantasy_content"]
        ["league"][0]["name"].strip().lower() == "moneyleague")
    raw = json.loads((lid_dir / "transactions.json").read_text())
    lg = raw["fantasy_content"]["league"]
    tx = next(p["transactions"] for p in lg
              if isinstance(p, dict) and "transactions" in p)
    trades = []
    for i in range(int(tx["count"])):
        e = tx[str(i)]["transaction"]
        meta = e[0] if isinstance(e, list) else e
        if meta.get("type") != "trade" or meta.get("status") != "successful":
            continue
        a = name_mid.get((season, meta["trader_team_name"].strip().lower()))
        b = name_mid.get((season, meta["tradee_team_name"].strip().lower()))
        if not (a and b):
            continue
        a_key, b_key = meta["trader_team_key"], meta["tradee_team_key"]
        got: dict[str, list] = {a: [], b: []}
        players_block = next((p["players"] for p in e[1:]
                              if isinstance(p, dict) and "players" in p),
                             None) if isinstance(e, list) else None
        if not players_block:
            continue
        for j in range(int(players_block["count"])):
            pl = players_block[str(j)]["player"]
            pmeta = {k: v for part in pl[0] if isinstance(part, dict)
                     for k, v in part.items()}
            tdata = pl[1]["transaction_data"]
            tdata = tdata[0] if isinstance(tdata, list) else tdata
            dest = tdata.get("destination_team_key")
            who = a if dest == a_key else b if dest == b_key else None
            if who:
                got[who].append({
                    "name": (pmeta.get("name") or {}).get("full", "?"),
                    "pos": pmeta.get("display_position", "?").split(",")[0],
                })
        trades.append({"season": season,
                       "week": week_of(meta["timestamp"], season),
                       "a": a, "b": b, "got": got})
    return trades


def _canon_set(names) -> frozenset:
    return frozenset(norm(resolve_xlsx_name(n) or n) for n in names)


def cookie_pick_legs(season: int) -> list[dict]:
    """Pick legs per trade from the cookie-scraper archive, keyed for
    joining: [{all: set, sides: [{names: set, picks: [rounds]}]}]."""
    import glob
    fs = glob.glob(str(YAHOO / f"league_*/trades_{season}.json"))
    out = []
    for f in fs:
        for t in json.loads(Path(f).read_text()):
            sides = []
            for s in t.get("sides") or []:
                sides.append({
                    "names": _canon_set(p["name"] for p in
                                        s.get("received_players") or []),
                    "picks": [pk.get("round") for pk in
                              s.get("received_picks") or []],
                })
            if any(s["picks"] for s in sides):
                out.append({"all": frozenset().union(
                    *[s["names"] for s in sides]), "sides": sides})
    return out


def attach_pick_legs(t: dict, cookie: list[dict]) -> dict[str, list]:
    """got-picks per manager for one API trade, joined by player-name
    overlap (132/136 join; misses just mean no pick annotation)."""
    a, b = t["a"], t["b"]
    got_names = {w: _canon_set(p["name"] for p in t["got"][w])
                 for w in (a, b)}
    key = got_names[a] | got_names[b]
    best, best_ov = None, 0.0
    for ct in cookie:
        ov = len(ct["all"] & key) / max(1, len(ct["all"] | key))
        if ov > best_ov:
            best, best_ov = ct, ov
    picks: dict[str, list] = {a: [], b: []}
    if not best or best_ov < 0.5:
        return picks
    # map each cookie side to the API side whose received set fits best
    for cs in best["sides"]:
        who = max((a, b), key=lambda w: len(cs["names"] & got_names[w]))
        if not cs["names"]:                      # pure-pick side: the one
            who = min((a, b),                    # who received fewer players
                      key=lambda w: len(got_names[w]))
        picks[who].extend(cs["picks"])
    return picks


def main() -> None:
    ident = load_identity(ROOT / "data" / "team_identity.json")
    name_mid: dict[tuple[int, str], str] = {}
    for mid, rec in ident["managers"].items():
        for s, nm in (rec.get("yahoo_team_names") or {}).items():
            if str(s).isdigit() and isinstance(nm, str):
                name_mid[(int(s), nm.strip().lower())] = mid

    catalog = json.loads((ROOT / "data/sleeper/players_nfl.json").read_text())
    pid_by_name: dict[str, str] = {}
    for pid, p in catalog.items():
        nm = f"{p.get('first_name', '')} {p.get('last_name', '')}".strip()
        if nm:
            pid_by_name.setdefault(norm(nm), pid)

    era = {int(k): v for k, v in json.loads(
        (ROOT / "data/league_history/yahoo_era.json").read_text()).items()}

    all_sides = []
    headliner_pool: list[dict] = []
    unresolved: dict[str, int] = defaultdict(int)
    for season in SEASONS:
        weeks = load_week_stats(season)
        teams_n = era[season]["num_teams"]
        repl = replacement_levels(weeks, teams_n)
        cookie = cookie_pick_legs(season)

        def ros_par(pid: str, pos: str, after_week: int) -> float:
            lvl = repl.get(pos, 0.0)
            tot = 0.0
            for w in range(after_week + 1, 18):
                rec = weeks.get(w, {}).get(pid)
                if rec:
                    pts = rec.get("pts_half_ppr")
                    if pts is None:
                        pts = ((rec.get("pts_ppr") or 0)
                               - 0.5 * (rec.get("rec") or 0))
                    tot += float(pts) - lvl
                # absent week = didn't play = 0 - replacement
                else:
                    tot -= lvl
            return tot

        for t in parse_trades(season, name_mid):
            sides = {}
            legs: dict[str, list[dict]] = {}
            for who in (t["a"], t["b"]):
                par = 0.0
                legs[who] = []
                for p in t["got"][who]:
                    canon = resolve_xlsx_name(p["name"]) or p["name"]
                    pid = pid_by_name.get(norm(canon))
                    if pid is None:
                        unresolved[p["name"]] += 1
                        continue
                    p_par = ros_par(pid, p["pos"], t["week"])
                    legs[who].append({"name": canon, "pos": p["pos"],
                                      "par": p_par})
                    par += p_par
                sides[who] = par
            best = max((leg["par"] for who in legs for leg in legs[who]),
                       default=0.0)
            a, b = t["a"], t["b"]
            picks = attach_pick_legs(t, cookie)
            # season-headliner candidate: the trade itself, names kept,
            # from the winning side's perspective (the Almanac reads this)
            win, lose = (a, b) if sides[a] >= sides[b] else (b, a)

            def _got(who):
                return ([leg["name"] for leg in sorted(
                    legs[who], key=lambda x: -x["par"])]
                    + [f"R{r} pick" for r in picks[who] if r])
            headliner_pool.append({
                "season": t["season"], "week": t["week"],
                "winner": win, "loser": lose,
                "par": round(sides[win] - sides[lose], 1),
                "got_winner": _got(win), "got_loser": _got(lose),
            })
            for who, other in ((a, b), (b, a)):
                all_sides.append({
                    "season": t["season"], "week": t["week"],
                    "manager": who, "counterparty": other,
                    "par": round(sides[who] - sides[other], 1),
                    # star flags: did the single best rest-of-season player
                    # in the deal land here (buy) or leave here (concede)?
                    "star_buy": best > 0 and any(
                        leg["par"] == best for leg in legs[who]),
                    "star_concede": best > 0 and any(
                        leg["par"] == best for leg in legs[other]),
                    "qb_in": any(leg["pos"] == "QB" for leg in legs[who]),
                    "picks_in": [r for r in picks[who] if r],
                    "picks_out": [r for r in picks[other] if r],
                })

    standings = defaultdict(lambda: {"deals": 0, "par": 0.0,
                                     "deals_2017plus": 0, "par_2017plus": 0.0})
    style = defaultdict(lambda: {"sides": 0, "star_buys": 0,
                                 "star_concessions": 0, "qb_in": 0})
    for s in all_sides:
        st2 = style[s["manager"]]
        st2["sides"] += 1
        st2["star_buys"] += int(s["star_buy"])
        st2["star_concessions"] += int(s["star_concede"])
        st2["qb_in"] += int(s["qb_in"])
        # 2017+ split: skill persistence is weak (3/8 same-sign across
        # halves), so consumers weigh the recent half separately.
        if s["season"] >= 2017:
            st3 = standings[s["manager"]]
            st3["deals_2017plus"] += 1
            st3["par_2017plus"] += s["par"]
    pair_net = defaultdict(float)
    for s in all_sides:
        st_ = standings[s["manager"]]
        st_["deals"] += 1
        st_["par"] += s["par"]
        pair_net[tuple(sorted((s["manager"], s["counterparty"])))] += 0
    # pair net from one perspective (a-side of sorted pair)
    pair_view = defaultdict(float)
    pair_deals = defaultdict(int)
    for s in all_sides:
        key = tuple(sorted((s["manager"], s["counterparty"])))
        if s["manager"] == key[0]:
            pair_view[key] += s["par"]
            pair_deals[key] += 1

    result = {
        "meta": {"seasons": "2011-2022",
                 "sides_graded": len(all_sides),
                 "unresolved_players": dict(sorted(
                     unresolved.items(), key=lambda kv: -kv[1])[:15]),
                 "method": "rest-of-season half-PPR PAR after the trade "
                           "week; replacement = median weekly score at "
                           "rank N scaled to league size; absent weeks "
                           "cost full replacement"},
        "standings": {m: {"deals": v["deals"], "net_par": round(v["par"], 1),
                          "deals_2017plus": v["deals_2017plus"],
                          "net_par_2017plus": round(v["par_2017plus"], 1)}
                      for m, v in sorted(standings.items(),
                                         key=lambda kv: -kv[1]["par"])},
        "style": dict(style),
        "pairs": {f"{k[0]} vs {k[1]}": {"deals": pair_deals[k],
                                        "net_to_first": round(v, 1)}
                  for k, v in sorted(pair_view.items(),
                                     key=lambda kv: -pair_deals[kv[0]])
                  if pair_deals[k] >= 3},
        "biggest": sorted(all_sides, key=lambda s: -s["par"])[:10],
        # every graded side, pick legs attached — the tank ledger and
        # any future per-side analysis read this instead of re-grading
        "sides": all_sides,
        # per-season swing trade WITH player names — the Almanac's
        # "season story" strip reads these for 2011-2022
        "season_headliners": {
            str(s): max((h for h in headliner_pool if h["season"] == s),
                        key=lambda h: h["par"])
            for s in sorted({h["season"] for h in headliner_pool})
        },
    }
    OUT.write_text(json.dumps(result, indent=2))
    print(f"[decade_ledger] {len(all_sides)} sides graded; "
          f"{sum(unresolved.values())} unresolved player-legs")
    print("\nALL-TIME YAHOO-ERA STANDINGS (net PAR):")
    for m, v in result["standings"].items():
        print(f"  {m:<18} {v['deals']:>3} deals  {v['net_par']:>+8.1f}")


if __name__ == "__main__":
    main()
