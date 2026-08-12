"""THE ALMANAC — the MONEY_LEAGUE.xlsx use case as a living PDF.

The xlsx is the league's bible: every draft board with TRUE pick
ownership (cell colors), plus who won. This report recreates that
record beautifully and keeps itself current: seasons are DISCOVERED
from the data (xlsx boards 2015+, yahoo_era standings 2011+, Sleeper
brackets for champions) — when the 2026 draft lands in the xlsx or the
Sleeper archive, it folds in on the next weekly run with zero edits.

Pages: honor-roll cover (champions by year, title counts, era growth,
all-time records), a standings-only spread for the pre-board years
(2011-2014), then one page per season: champion banner, final
standings, a SEASON STORY strip (the final's score, game of the year,
the season's swing trade, the champion's engine players), and the full
draft board (round x slot, players position-colored, owner tag per
pick — the xlsx cell-color truth, typeset). Champion picks are bold.

Story sources: Yahoo scoreboards + the Decade Ledger's season
headliners for 2011-2022; Sleeper matchups (lineup-level) + the
PAR-graded Trade Ledger for 2023+. Engine = points actually started
in the champion's lineup (Sleeper era) or the champion's draft-class
season totals (Yahoo era — no lineup data survives).

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


def norm(s: str) -> str:
    s = (s.lower().replace(".", "").replace("'", "")
         .replace("-", " ").strip())
    for suf in (" iii", " ii", " iv", " jr", " sr", " v"):
        if s.endswith(suf):
            s = s[: -len(suf)].strip()
    return s


def short_name(nm: str) -> str:
    """Board cells are ~18 chars wide; long names lose their owner tag
    to the ellipsis. First-initial the long ones so the tag survives."""
    parts = nm.split()
    if len(nm) <= 13 or len(parts) < 2:
        return nm
    return parts[0][0] + ". " + " ".join(parts[1:])


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


def yahoo_name_mid() -> dict[tuple[int, str], str]:
    ident = load_identity(ROOT / "data/team_identity.json")
    out = {}
    for mid, rec in ident["managers"].items():
        for s, nm in (rec.get("yahoo_team_names") or {}).items():
            if str(s).isdigit() and isinstance(nm, str):
                out[(int(s), nm.strip().lower())] = mid
    return out


def yahoo_games() -> dict[int, list[dict]]:
    """season -> [{week, playoffs, consolation, sides:[(mid,pts)x2]}]
    from the MONEYLEAGUE Yahoo scoreboard archive."""
    name_mid = yahoo_name_mid()
    out: dict[int, list[dict]] = defaultdict(list)
    for d in sorted((ROOT / "data" / "yahoo").iterdir()):
        if not (d.is_dir() and d.name[:4].isdigit()
                and (d / "league.json").exists()):
            continue
        meta = json.loads((d / "league.json").read_text())
        if (meta["fantasy_content"]["league"][0].get("name") or "") \
                .strip().lower() != "moneyleague":
            continue
        season = int(d.name[:4])
        for sf in sorted(d.glob("scoreboard_w*.json")):
            lg = json.loads(sf.read_text())["fantasy_content"]["league"]
            sb = next((p["scoreboard"] for p in lg
                       if isinstance(p, dict) and "scoreboard" in p), None)
            if not sb:
                continue
            ms = sb["0"]["matchups"]
            for i in range(int(ms["count"])):
                mm = ms[str(i)]["matchup"]
                if isinstance(mm, list):
                    mm = mm[0]
                teams = mm["0"]["teams"]
                sides = []
                for j in range(int(teams["count"])):
                    tt = teams[str(j)]["team"]
                    tmeta = {k: v for part in tt[0] if isinstance(part, dict)
                             for k, v in part.items()}
                    mid = name_mid.get(
                        (season, (tmeta.get("name") or "").strip().lower()))
                    pts = float(tt[1]["team_points"]["total"])
                    sides.append((mid, pts))
                if len(sides) == 2 and all(m for m, _ in sides):
                    out[season].append({
                        "week": int(mm["week"]),
                        "playoffs": mm.get("is_playoffs") == "1",
                        "consolation": mm.get("is_consolation") == "1",
                        "sides": sides})
    return dict(out)


def sleeper_games() -> dict[int, list[dict]]:
    """season -> games in the same shape, from the Sleeper matchup
    archive. Playoff flag from each league's playoff_week_start;
    consolation from the losers bracket (winners-bracket games and
    the rest of the playoff weeks are told apart via brackets)."""
    import glob
    ident = load_identity(ROOT / "data/team_identity.json")
    rid_mid = {rec["sleeper_roster_id"]: mid
               for mid, rec in ident["managers"].items()
               if rec.get("sleeper_roster_id")}
    # per-season playoff start + winners-bracket (rid pairs by week)
    starts: dict[int, int] = {}
    wb_weeks: dict[int, set[tuple[int, int]]] = defaultdict(set)
    for d in glob.glob(str(ROOT / "data/sleeper/league_*")):
        lg = json.loads(open(d + "/league.json").read())
        season = int(lg["season"])
        start = int(lg.get("settings", {}).get("playoff_week_start") or 15)
        starts[season] = start
        wb_f = Path(d) / "winners_bracket.json"
        if wb_f.exists():
            for g in json.loads(wb_f.read_text()):
                t1, t2 = g.get("t1"), g.get("t2")
                if isinstance(t1, int) and isinstance(t2, int):
                    wk = start + int(g.get("r", 1)) - 1
                    wb_weeks[season].add((wk, t1))
                    wb_weeks[season].add((wk, t2))
    out: dict[int, list[dict]] = defaultdict(list)
    seasons = sorted({int(f.split("/")[-1].split("_")[0]) for f in
                      glob.glob(str(ROOT / "data/league_history/*_matchups_w1.json"))})
    for season in seasons:
        rmap = dict(rid_mid)
        rmap[10] = "josh_wildboy" if season >= 2025 else "dave_aka_wang"
        start = starts.get(season, 15)
        for wf in glob.glob(str(ROOT / f"data/league_history/{season}_matchups_w*.json")):
            wk = int(wf.split("_w")[1].split(".")[0])
            bym = defaultdict(list)
            for r in json.loads(open(wf).read()):
                if r["matchup_id"] is not None:
                    bym[r["matchup_id"]].append(r)
            for g in bym.values():
                if len(g) != 2:
                    continue
                po = wk >= start
                in_wb = any((wk, r["roster_id"]) in wb_weeks[season]
                            for r in g)
                out[season].append({
                    "week": wk, "playoffs": po,
                    "consolation": po and not in_wb,
                    "sides": [(rmap.get(r["roster_id"]), r["points"])
                              for r in g]})
    return dict(out)


def sleeper_engines() -> dict[int, list[tuple[str, float]]]:
    """season -> champion's top players by points STARTED in the
    champion's lineup across the whole season (playoffs included)."""
    import glob
    ident = load_identity(ROOT / "data/team_identity.json")
    mid_rid = {mid: rec["sleeper_roster_id"]
               for mid, rec in ident["managers"].items()
               if rec.get("sleeper_roster_id")}
    cat = json.loads((ROOT / "data/sleeper/players_nfl.json").read_text())
    out = {}
    for season, (champ, _) in sleeper_champions().items():
        rid = 10 if champ == "josh_wildboy" else mid_rid.get(champ)
        if rid is None:
            continue
        tot: dict[str, float] = defaultdict(float)
        for wf in glob.glob(str(ROOT / f"data/league_history/{season}_matchups_w*.json")):
            for r in json.loads(open(wf).read()):
                if r["roster_id"] != rid:
                    continue
                pp = r.get("players_points") or {}
                for pid in (r.get("starters") or []):
                    if pid in pp:
                        tot[pid] += pp[pid]
        top = sorted(tot.items(), key=lambda kv: -kv[1])[:3]
        named = []
        for pid, pts in top:
            p = cat.get(pid, {})
            nm = (f"{p.get('first_name', '')} "
                  f"{p.get('last_name', '')}").strip() or pid
            named.append((nm, round(pts, 1)))
        out[season] = named
    return out


def yahoo_engine(season: int, champ_picks: list[str]) -> list[tuple[str, float]]:
    """Champion's top-3 draft-class scorers, season half-PPR totals.
    (No lineup data survives from the Yahoo era.)"""
    sf = ROOT / "data" / "scouting" / "stats" / f"stats_{season}.json"
    if not sf.exists() or not champ_picks:
        return []
    weeks = {int(w): v for w, v in json.loads(sf.read_text()).items()
             if w != "_meta"}
    cat = json.loads((ROOT / "data/sleeper/players_nfl.json").read_text())
    pid_by_name = {}
    for pid, p in cat.items():
        nm = f"{p.get('first_name', '')} {p.get('last_name', '')}".strip()
        if nm:
            pid_by_name.setdefault(norm(nm), pid)
    from fantasy_draft.name_aliases import resolve_xlsx_name
    named = []
    for raw in champ_picks:
        canon = resolve_xlsx_name(raw) or raw
        pid = pid_by_name.get(norm(canon))
        if pid is None:
            continue
        tot = 0.0
        for w, players in weeks.items():
            rec = players.get(pid)
            if rec:
                pts = rec.get("pts_half_ppr")
                if pts is None:
                    pts = (rec.get("pts_ppr") or 0) - 0.5 * (rec.get("rec") or 0)
                tot += float(pts)
        named.append((canon, round(tot, 1)))
    return sorted(named, key=lambda kv: -kv[1])[:3]


def swing_trades() -> dict[int, dict]:
    """season -> the year's biggest trade, with players, both eras."""
    out = {}
    dl = ROOT / "data" / "research" / "decade_ledger.json"
    if dl.exists():
        for s, h in json.loads(dl.read_text()).get(
                "season_headliners", {}).items():
            out[int(s)] = h
    tl = ROOT / "data" / "research" / "trade_ledger.json"
    if tl.exists():
        ident = load_identity(ROOT / "data/team_identity.json")
        rid_mid = {rec["sleeper_roster_id"]: mid
                   for mid, rec in ident["managers"].items()
                   if rec.get("sleeper_roster_id")}
        best: dict[int, dict] = {}
        for t in json.loads(tl.read_text())["trades"]:
            if len(t["parties"]) != 2:
                continue
            season = int(t["season"])
            rmap = dict(rid_mid)
            rmap[10] = "josh_wildboy" if season >= 2025 else "dave_aka_wang"
            a, b = t["parties"]
            net = (a.get("swing_par_pts") or 0) - (b.get("swing_par_pts") or 0)
            win, lose = (a, b) if net >= 0 else (b, a)

            def legs(party):
                names = [p["name"] for p in sorted(
                    party["received"].get("players") or [],
                    key=lambda p: -(p.get("ros_par") or 0))]
                names += [f"{pk['season']} R{pk['round']}"
                          for pk in party["received"].get("picks") or []]
                return names
            rec = {"season": season, "week": t["week"],
                   "winner": rmap.get(win["roster_id"]),
                   "loser": rmap.get(lose["roster_id"]),
                   "par": round(abs(net), 1),
                   "got_winner": legs(win), "got_loser": legs(lose)}
            if season not in best or rec["par"] > best[season]["par"]:
                best[season] = rec
        out.update(best)
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
    yg = yahoo_games()
    sg = sleeper_games()
    engines_sl = sleeper_engines()
    trades = swing_trades()
    from fantasy_draft.name_aliases import resolve_xlsx_name

    def label(mid) -> str:
        return SHORT.get(mid, (mid or "?")[:4].upper())

    def champ_pick_rounds(season: int) -> dict[str, int]:
        """norm(canonical player name) -> draft round, champion only."""
        out = {}
        for p in boards.get(season) or []:
            m = manager_for_xlsx_nickname(p.manager_nickname)
            if m and m["id"] == champs.get(season) and p.player_name:
                canon = resolve_xlsx_name(p.player_name) or p.player_name
                out[norm(canon)] = p.round
        return out

    def score_line(g: dict) -> str:
        (wm, wp), (lm, lp) = sorted(g["sides"], key=lambda s: -s[1])
        return (f'W{g["week"]} · <b>{esc(label(wm))} {wp:.1f}</b> '
                f'def. {esc(label(lm))} {lp:.1f}')

    def story_items(season: int) -> list[tuple[str, str]]:
        games = yg.get(season) or sg.get(season) or []
        items: list[tuple[str, str]] = []
        champ = champs.get(season)
        finals = [g for g in games if g["playoffs"] and not g["consolation"]
                  and champ in {m for m, _ in g["sides"]}]
        if finals:
            items.append(("THE FINAL", score_line(
                max(finals, key=lambda g: g["week"]))))
        reg = [g for g in games if not g["playoffs"]]
        if reg:
            shoot = max(reg, key=lambda g: g["sides"][0][1] + g["sides"][1][1])
            items.append(("SHOOTOUT", score_line(shoot)))
            tm, tp, tw = max(((m, p, g["week"]) for g in reg
                              for m, p in g["sides"]), key=lambda x: x[1])
            items.append(("TOP WEEK", f"{esc(label(tm))} {tp:.1f} (W{tw})"))
        t = trades.get(season)
        if t and t.get("winner"):
            got = ", ".join(map(esc, t["got_winner"][:2])) or "—"
            gave = ", ".join(map(esc, t["got_loser"][:2])) or "—"
            more = len(t["got_winner"]) + len(t["got_loser"]) - 4
            items.append(("SWING TRADE",
                          f'W{t["week"]} · <b>{esc(label(t["winner"]))} '
                          f'+{t["par"]:.0f}</b> over '
                          f'{esc(label(t["loser"]))}: got {got} for {gave}'
                          + (f" (+{more} more)" if more > 0 else "")))
        if champ:
            rounds = champ_pick_rounds(season)
            if season in engines_sl:
                eng, tag = engines_sl[season], "started pts"
            else:
                eng = yahoo_engine(
                    season, [p.player_name for p in boards.get(season) or []
                             if (m := manager_for_xlsx_nickname(
                                 p.manager_nickname)) and m["id"] == champ])
                tag = "season pts, draft class"
            if eng:
                bits = []
                for nm, pts in eng:
                    canon = resolve_xlsx_name(nm) or nm
                    rd = rounds.get(norm(canon))
                    pos = pos_of.get(nm.strip().lower())
                    cls = POS_CLASS.get(pos, "")
                    bits.append(f'<span class="{cls}">{esc(short_name(nm))}'
                                f"</span> {pts:.0f}"
                                + (f" (R{rd})" if rd else " (add)"))
                items.append((f"CHAMP'S ENGINE",
                              " · ".join(bits) + f' <span class="own">'
                              f"{tag}</span>"))
        return items

    def story_table(season: int) -> str:
        items = story_items(season)
        if not items:
            return ""
        rows = "".join(f'<tr><td class="sl">{lbl}</td><td>{txt}</td></tr>'
                       for lbl, txt in items)
        return ('<div class="ml-h-label" style="margin-top:7px">SEASON '
                f'STORY</div><table class="story">{rows}</table>')

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
                    f'<td{bold}><span class="nm {cls}">'
                    f'{esc(short_name(p.player_name or ""))}'
                    f'</span><span class="own">{esc(label(mid))}</span></td>')
            rows_html.append(f'<tr><td class="ml-num rnd">{r}</td>'
                             + "".join(cells) + "</tr>")
        cols = ('<colgroup><col class="rndcol">'
                + "<col>" * len(slots) + "</colgroup>")
        return ('<table class="board">' + cols + '<thead><tr><th></th>'
                + head + "</tr></thead><tbody>" + "".join(rows_html)
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

    # ---------------- cover: all-time record book ----------------
    all_games = [(s, g) for src in (yg, sg)
                 for s, lst in src.items() for g in lst]
    season_rows = [(s, r) for s in all_seasons for r in standings_rows(s)]
    rec_rows: list[tuple[str, str]] = []
    if season_rows:
        s, r = max(season_rows,
                   key=lambda sr: (sr[1]["wins"] /
                                   max(1, sr[1]["wins"] + sr[1]["losses"]),
                                   sr[1]["pf"]))
        rec_rows.append(("BEST RECORD",
                         f'<b>{esc(label(r["manager"]))}</b> '
                         f'{r["wins"]}-{r["losses"]} ({s})'))
        s, r = max(season_rows, key=lambda sr: sr[1]["pf"])
        rec_rows.append(("MOST PF, SEASON",
                         f'<b>{esc(label(r["manager"]))}</b> '
                         f'{r["pf"]:.0f} ({s})'))
    if all_games:
        s, m, p, w = max(((s, m, p, g["week"]) for s, g in all_games
                          for m, p in g["sides"]), key=lambda x: x[2])
        rec_rows.append(("TOP WEEK EVER",
                         f"<b>{esc(label(m))}</b> {p:.1f} (W{w} {s})"))
        s, g = max(all_games,
                   key=lambda sg2: abs(sg2[1]["sides"][0][1]
                                       - sg2[1]["sides"][1][1]))
        rec_rows.append(("BIGGEST BLOWOUT", f"{score_line(g)} ({s})"))
        po = [(s2, g2) for s2, g2 in all_games
              if g2["playoffs"] and not g2["consolation"]]
        if po:
            s, g = min(po, key=lambda sg2: abs(sg2[1]["sides"][0][1]
                                               - sg2[1]["sides"][1][1]))
            margin = abs(g["sides"][0][1] - g["sides"][1][1])
            rec_rows.append(("CRUELEST BEAT",
                             f"{score_line(g)} — by {margin:.2f} ({s})"))
    if trades:
        t = max(trades.values(), key=lambda t: t["par"])
        rec_rows.append(("BIGGEST HEIST",
                         f'<b>{esc(label(t["winner"]))} +{t["par"]:.0f}</b> '
                         f'over {esc(label(t["loser"]))}: got '
                         + ", ".join(map(esc, t["got_winner"][:2]))
                         + f' (W{t["week"]} {t["season"]})'))
    records = ("".join(f'<tr><td class="sl">{lbl}</td><td>{txt}</td></tr>'
                       for lbl, txt in rec_rows))
    legend = " ".join(f'<span class="{cls}"><b>{pos}</b></span>'
                      for pos, cls in POS_CLASS.items())

    h = ['<html data-theme="light"><head><meta charset="utf-8"><style>'
         + report_base_css() + bpr.banknote_css() + """
    * { box-sizing: border-box; margin: 0; }
    body { font-size: 8pt; line-height: 1.3; padding: 16px 22px; }
    .season { page-break-before: always; }
    .season h2 { font-family: var(--ml-font-engraving); font-size: 13pt;
                 letter-spacing: 1px; border-bottom: 1px solid
                 var(--ml-border-strong); padding-bottom: 3px;
                 margin-bottom: 6px; }
    .cols { display: grid; grid-template-columns: 175px 1fr; gap: 10px;
            align-items: start; }
    .story { border-collapse: collapse; width: 100%; }
    .story td { padding: 1.5px 3px 1.5px 0; font-size: 6.4pt;
                line-height: 1.35; vertical-align: top; }
    .story td.sl { color: var(--ml-muted); font-weight: 700;
                   font-size: 5.6pt; letter-spacing: .4px;
                   white-space: nowrap; padding-right: 6px; }
    .story.rec td { font-size: 7pt; }
    .story.rec td.sl { font-size: 6pt; }
    .cover-cols { display: grid; grid-template-columns: 340px 1fr;
                  gap: 24px; align-items: start; }
    .cover-cols p { max-width: 52em; margin-bottom: 6px; }
    .st td, .st th { padding: 1px 5px; font-size: 7pt; }
    .board { border-collapse: collapse; width: 100%; table-layout: fixed; }
    .board td, .board th { border: 1px solid var(--ml-border);
        padding: 0.5px 2px; font-size: 6pt; white-space: nowrap;
        overflow: hidden; }
    .board th { font-size: 6pt; }
    .board col.rndcol { width: 14px; }
    /* two-line cell: name above, owner tag below — the tag is never
       lost to an ellipsis no matter how long the name runs */
    .board .nm { display: block; overflow: hidden;
                 text-overflow: ellipsis; }
    .board .own { display: block; }
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
             'Draft boards preserved from 2015 onward. Keepers entered as '
             'ordinary picks before 2025 appear at their cost round. '
             'Standings are regular-season; the trophy follows the bracket. '
             'Season stories are computed from the archives: every scoreboard '
             '2011+, trades graded rest-of-season points above replacement '
             '(PAR), the champion\'s engine from lineup data (Sleeper era) '
             'or draft-class season totals (Yahoo era).</p>'
             '<div class="ml-h-label" style="margin-top:8px">READING THE '
             f'BOARDS</div><p>{legend} — a player\'s color is his position. '
             'The small gray tag after each pick is its TRUE owner, typeset '
             'from the xlsx cell-color record (keeper costs and traded picks '
             'included). A <b>bold</b> cell is a champion\'s pick — the '
             'roster that won it all, at the table. Long names are '
             'first-initialed to fit.</p>'
             '<div class="ml-h-label" style="margin-top:8px">ALL-TIME '
             'RECORD BOOK</div>'
             f'<table class="story rec">{records}</table>'
             '</div></div>')

    # pre-board years, four-up
    pre = [s for s in all_seasons if s not in boards]
    if pre:
        h.append('<div class="season"><h2>THE EARLY YEARS — '
                 f'{pre[0]}–{pre[-1]} (standings only)</h2>'
                 '<div class="fourup">')
        for s in pre:
            h.append(f'<div><div class="ml-h-label">{s} · '
                     f'{esc(label(champs.get(s)))} 🏆</div>'
                     + standings_table(s, compact=True)
                     + story_table(s) + "</div>")
        h.append("</div></div>")

    for s in board_seasons:
        c, ru = champs.get(s), runners.get(s)
        h.append(f'<div class="season"><h2>{s}</h2>'
                 f'<p class="banner"><b>🏆 {esc(label(c))}</b>'
                 + (f' over {esc(label(ru))}' if ru else "")
                 + '</p><div class="cols"><div>'
                 + standings_table(s) + story_table(s) + "</div><div>"
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
