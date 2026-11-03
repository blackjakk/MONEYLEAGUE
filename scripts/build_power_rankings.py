"""MONEYLEAGUE Power Rankings — Madden cards + Trade Behavior combined.

Active long-tenure managers only (5+ years, still rostered). Composite OVR
weights: Rings 35%, Win% 25%, PPG 15%, Trade VBD 15%, Longevity 10%.
"""
from __future__ import annotations

import base64

import json
import math
import re
import subprocess
import sys
import unicodedata
from collections import defaultdict
from datetime import date
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.offsetbox import OffsetImage, AnnotationBbox
import matplotlib.image as mpimg
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fantasy_draft.results import load_all_seasons  # noqa: E402
from fantasy_draft.team_identity import (  # noqa: E402
    all_managers, manager_for_sleeper_roster,
)
# Design system: single source of truth for palettes, CSS base + mpl style.
# PALETTE / MANAGER_COLORS / mgr_color are re-exported here for backward
# compat — downstream scripts do `bpr.mgr_color(...)`.
from design.tokens import (  # noqa: E402, F401
    CHART, MANAGER_COLORS, PALETTE, POS_COLORS, SURFACE_LIGHT,
    mgr_color, mpl_style, report_base_css,
)

ROOT = Path(__file__).resolve().parent.parent
PDF_OUT = ROOT / "data" / "MONEYLEAGUE_POWER_RANKINGS.pdf"
MD_OUT = ROOT / "data" / "MONEYLEAGUE_POWER_RANKINGS.md"
CHART_DIR = ROOT / "data" / "charts" / "rankings"
CHART_DIR.mkdir(parents=True, exist_ok=True)

mpl_style()  # register league fonts + standard chart rcParams


# ---------------------------------------------------------------------------
# Banknote chrome — the engraved-banknote print face shared by every PDF
# builder (preseason / mock / round menu consume these via `bpr.`).
# design/guilloche.py is the design system's engraving generator; until it
# lands, the chrome degrades to bare paper (empty SVG strings) so the
# builders keep running end-to-end.
try:
    from design.guilloche import lattice_svg, rosette_svg  # noqa: E402
except ImportError:  # pre-integration fallback: no lattice, no rosettes
    def lattice_svg(width: int, height: int, stroke: str,
                    opacity: float) -> str:
        return ""

    def rosette_svg(size: int, stroke: str, opacity: float) -> str:
        return ""


FINE_PRINT = ("Past performance (2025: 12th of 12) is not indicative of "
              "future results.")

# Engraving ink for generated guilloché — resolved from design.tokens so the
# SVG strings inherit any surface retune (SVG attrs can't read CSS vars).
BANKNOTE_INK = SURFACE_LIGHT["text"]


def _git_short_rev() -> str:
    try:
        r = subprocess.run(["git", "rev-parse", "--short", "HEAD"],
                           capture_output=True, text=True, cwd=ROOT)
        rev = r.stdout.strip()
        return rev if r.returncode == 0 and rev else "local"
    except OSError:
        return "local"


def banknote_serial() -> str:
    """Report serial: SERIES 2026 · WK{ISO week} · {git short rev}."""
    return (f"SERIES 2026 · WK{date.today().isocalendar()[1]} · "
            f"{_git_short_rev()}")


def banknote_css() -> str:
    """Layout-only rules for the shared banknote chrome. Colors and type
    identity come from ml.css (--ml-* vars, .ml-serial/.ml-fineprint)."""
    return """
    .bn-mast { position: relative; overflow: hidden; padding: 16px 20px 14px;
               border: 2px solid var(--ml-text); border-radius: 6px;
               background: var(--ml-panel); margin-bottom: 16px; }
    .bn-mast::before { content: ""; position: absolute; inset: 3px;
               border: 1px solid var(--ml-border-strong); border-radius: 4px;
               pointer-events: none; }
    .bn-lattice { position: absolute; inset: 0; z-index: 0; line-height: 0; }
    .bn-lattice svg { width: 100%; height: 100%; display: block; }
    .bn-corner { position: absolute; z-index: 0; line-height: 0; }
    .bn-corner--tl { top: 7px; left: 7px; }
    .bn-corner--br { bottom: 7px; right: 7px; }
    .bn-mast-top, .bn-mast h1, .bn-mast .bn-sub {
               position: relative; z-index: 1; }
    .bn-mast-top { display: flex; justify-content: space-between;
                   align-items: baseline; gap: 12px; }
    .bn-league { font-family: var(--ml-font-engraving, var(--ml-font-display));
                 font-weight: 700; letter-spacing: 3px;
                 text-transform: uppercase; font-size: 10pt; }
    .bn-mast h1 { font-family: var(--ml-font-engraving, var(--ml-font-display));
                  color: var(--ml-text); margin: 6px 0 0; }
    .bn-sub { color: var(--ml-muted); margin: 5px 0 0; }
    .bn-mast--compact { padding: 7px 12px 6px; margin-bottom: 6px; }
    /* compact band is too short for the top-left rosette — it clips
       into a dark wedge over the title (formatting audit, Jul 2026) */
    .bn-mast--compact .bn-corner--tl { display: none; }
    .bn-mast--compact .bn-league { font-size: 7.5pt; letter-spacing: 2px; }
    .bn-mast--compact h1 { margin: 1px 0 0; }
    .bn-mast--compact .bn-sub { margin: 1px 0 0; }
    .bn-foot { display: flex; justify-content: space-between; gap: 12px;
               border-top: 1px solid var(--ml-border); margin-top: 14px;
               padding-top: 5px; }
    """


def banknote_masthead(title: str, subtitle: str = "",
                      league_line: str = "✦ MONEY LEAGUE · SERIES 2026 ✦",
                      compact: bool = False) -> str:
    """Engraved masthead: guilloché band + corner rosettes + serial."""
    band_h = 80 if compact else 150
    rose = 34 if compact else 54
    lat = lattice_svg(1400, band_h, BANKNOTE_INK, 0.10)
    ros = rosette_svg(rose, BANKNOTE_INK, 0.28)
    cls = "bn-mast bn-mast--compact" if compact else "bn-mast"
    sub = f'<p class="bn-sub">{subtitle}</p>' if subtitle else ""
    return (
        f'<header class="{cls}">'
        f'<div class="bn-lattice" aria-hidden="true">{lat}</div>'
        f'<div class="bn-corner bn-corner--tl" aria-hidden="true">{ros}</div>'
        f'<div class="bn-corner bn-corner--br" aria-hidden="true">{ros}</div>'
        '<div class="bn-mast-top">'
        f'<span class="bn-league">{league_line}</span>'
        f'<span class="ml-serial">{banknote_serial()}</span></div>'
        f'<h1>{title}</h1>{sub}</header>'
    )


def banknote_fineprint(generated: str = "") -> str:
    """Disclosure footer: fine print + the report's generation date."""
    right = f"<span>{generated}</span>" if generated else ""
    return (f'<div class="bn-foot ml-fineprint"><span>{FINE_PRINT}</span>'
            f'{right}</div>')


def _avatar_path(mid):
    p = ROOT / "data" / "charts" / "avatars" / f"{mid}.jpg"
    return p if p.exists() else None


def _data_uri(path: Path, mime: str | None = None) -> str:
    """Return base64 data: URI for an image (Playwright headless won't follow file://)."""
    if not Path(path).exists():
        return ""
    if mime is None:
        ext = str(path).lower().split(".")[-1]
        mime = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg",
                "svg": "image/svg+xml"}.get(ext, "image/png")
    b = Path(path).read_bytes()
    return f"data:{mime};base64,{base64.b64encode(b).decode()}"

# Reuse build_trades_report helpers
from scripts import build_trades_report as btr  # noqa: E402
from scripts.build_history_charts import KNOWN_CHAMPIONS  # noqa: E402

ROSTER_HANDOFFS = {(2023, 10): "dave_aka_wang",
                    (2024, 10): "dave_aka_wang",
                    (2025, 10): "josh_wildboy"}

MIN_YEARS_CURRENT = 5     # current managers need 5+ years
MIN_YEARS_FORMER = 10     # former managers need 10+ years (e.g. Dave Wang)

# Unique "calling card" per manager, derived from the underlying data
PERSONALITIES = {
    "trevor_bergerboy": ("The Volume Drafter",
        "15 straight years, 3 rings, AND the league's most-frequent trader (52 trades). "
        "Despite never drafting from a high slot, his +9.0 surplus/pick is the best in the "
        "league — he wrings value out of every round. The closest thing to a perennial contender."),
    "coop": ("The Stealth Champion",
        "3 rings on a .537 win pct — wins championships without ever dominating the regular season. "
        "Famously didn't even attend the 2017 Club Risqué draft and still won the title. "
        "Iron-man 15-year vet who shows up when it matters."),
    "dave_aka_wang": ("The Departed GOAT",
        "By the numbers, the most complete manager in league history: +4718 trade VBD (#1 by a mile), "
        ".596 win pct, 2 rings in 12 years. Then he handed the roster to Josh after 2024. "
        "He left at the peak."),
    "kyle_figgy": ("The Manic-Depressive",
        "Two rings (2012, 2016) but the most volatile finishing record in the league — "
        "regularly oscillates between #1 and #10. When he's on, he wins it. When he's off, "
        "he's the basement."),
    "brower_barry": ("The Choker (Sorry)",
        "League's best win pct (.701), best PPG (135.8), and #2 draft skill (+8.7 surplus). "
        "0 rings. Every regular season is a coronation; every playoff is a heart attack. "
        "Most underrated active manager."),
    "ankur_patel": ("The Rookie Champion",
        "Won his ring in 2022, his FIRST season in the league. Has been respectable since "
        "but hasn't replicated it. The cautionary tale that a hot draft can carry you all the way."),
    "eric_m": ("The Sneaky Drafter",
        "Below-average trade VBD (-879) but quietly #4 in draft skill (+7.2 surplus/pick). "
        "His 2023 ring came mostly from the draft — not midseason wheeling. The exact opposite "
        "profile of Donnie."),
    "troy_mullings": ("The Heist Survivor",
        "13-year vet, 1 ring (2019), and the most schedule-unlucky player in recent years "
        "(-0.54 fpts-to-wins gap). Often scores his way out of the playoff race but can't "
        "translate to W's."),
    "brian_bigguap": ("The Beautiful Loser",
        "15 years, 46 trades, 0 rings. The most active manager who has never won. "
        "Went 11-0 in 2018's regular season then lost in the playoffs to finish 4th. "
        "Has played every snap of MONEYLEAGUE history without lifting the trophy."),
    "lem": ("The Cosmically Unlucky",
        "15 years, 0 rings, schedule luck -0.80 (worst in the league). Routinely scores enough "
        "to win but gets matched against the week's highest scorer. The universe owes him a ring."),
    "donnie": ("The Lottery Winner",
        "1 ring + EVERYTHING ELSE is worst-or-near-worst: -3777 trade VBD (worst by 1700+), "
        ".362 win pct, -13.4 draft surplus. Living proof that fantasy football has a luck variance "
        "the size of Texas."),
    "tim_breswick": ("The Quiet Anchor",
        "9 years, 0 rings, .452 win pct. Doesn't trade much (-2077 VBD), doesn't draft well "
        "(-10.7 surplus). Doesn't get fleeced either. The league's bedrock — always there, "
        "never the story."),
    "josh_wildboy": ("The Heir",
        "Took over Dave's roster in 2025 and went 9-5 in his rookie season. "
        "Inherited a champion's infrastructure; the question is whether he can keep the dynasty alive."),
    "nark": ("The Original Champion",
        "Won the inaugural title in 2011 (back when the league was 8 teams). Stuck around through "
        "2016, then peaced out. Holds the unique distinction of being the only champion who "
        "doesn't exist in the Sleeper era."),
}


def _mgr_name(mid):
    for m in all_managers():
        if m["id"] == mid:
            return m["canonical_name"].split(" (")[0]
    return mid


def _norm(s):
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower().strip()
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", s)).strip()


def compute_career_stats(year_filter=None):
    """Per-manager: years, wins, losses, fpts, ppg, rings.
    year_filter: callable(year) -> bool to scope to subset of seasons.
    """
    ytm = {}
    for m in all_managers():
        for yr, tn in (m.get("yahoo_team_names") or {}).items():
            if yr == "_note" or not tn:
                continue
            ytm[(int(yr), tn.strip().lower())] = m["id"]

    wl = defaultdict(lambda: [0, 0])
    fpts = defaultdict(float)
    years = defaultdict(set)

    # Yahoo
    for f in sorted((ROOT / "data" / "yahoo").glob("league_*/matchups_*.json")):
        yr = int(f.stem.split("_")[1])
        if year_filter and not year_filter(yr):
            continue
        d = json.loads(f.read_text())
        teams = d.get("teams", {})
        tid_to_mgr = {}
        for tid, name in teams.items():
            mid = ytm.get((yr, name.strip().lower()))
            if mid:
                tid_to_mgr[int(tid)] = mid
                years[mid].add(yr)
        n_teams = len(teams)
        reg_end = 14 if n_teams == 12 else 13
        for wk_str, games in d.get("weeks", {}).items():
            if int(wk_str) > reg_end:
                continue
            for g in games:
                ma = tid_to_mgr.get(g["team_a"])
                mb = tid_to_mgr.get(g["team_b"])
                if not (ma and mb):
                    continue
                fpts[ma] += g["pts_a"]
                fpts[mb] += g["pts_b"]
                if g["winner"] == g["team_a"]:
                    wl[ma][0] += 1
                    wl[mb][1] += 1
                elif g["winner"] == g["team_b"]:
                    wl[mb][0] += 1
                    wl[ma][1] += 1

    # Sleeper
    rings = defaultdict(int)
    for yr, mid in KNOWN_CHAMPIONS.items():
        if year_filter and not year_filter(yr):
            continue
        rings[mid] += 1
    for season, s in load_all_seasons().items():
        if year_filter and not year_filter(season):
            continue
        for rid, r in s["rosters"].items():
            m = manager_for_sleeper_roster(int(rid))
            mid = ROSTER_HANDOFFS.get((season, int(rid)),
                                      m["id"] if m else None)
            if not mid:
                continue
            wl[mid][0] += r["wins"]
            wl[mid][1] += r["losses"]
            fpts[mid] += r["fpts"]
            years[mid].add(season)
        rid = s.get("champion_roster_id")
        if rid and season not in KNOWN_CHAMPIONS:
            m = manager_for_sleeper_roster(int(rid))
            mid = ROSTER_HANDOFFS.get((season, int(rid)),
                                      m["id"] if m else None)
            if mid:
                rings[mid] += 1

    out = {}
    for mid, ys in years.items():
        w, l = wl[mid]
        games = w + l
        out[mid] = {
            "years": sorted(ys),
            "n_years": len(ys),
            "first": min(ys), "last": max(ys),
            "w": w, "l": l, "fpts": fpts[mid],
            "winpct": w / games if games else 0,
            "ppg": fpts[mid] / games if games else 0,
            "rings": rings[mid],
        }
    return out


def compute_draft_stats(year_filter=None):
    """Returns {mid: {'pts', 'picks', 'ppp', 'surplus', 'spp'}}.

    'ppp'      = raw rookie-year pts/pick (volume — rewards high picks)
    'surplus'  = total pts over league avg for that (year, round)
    'spp'      = surplus per pick — actual drafting skill independent of slot
    """
    nfl = btr._load_nflverse()
    sleeper_names = btr._load_sleeper_players()
    ynm = btr._yahoo_name_lookup()
    mgr_rid_to_id = {m["sleeper_roster_id"]: m["id"]
                     for m in all_managers() if m.get("sleeper_roster_id")}

    # Pass 1: gather every pick
    picks_raw = []
    import csv
    for f in sorted((ROOT / "data" / "yahoo").glob("league_*/draft_*.csv")):
        with open(f) as fh:
            for row in csv.DictReader(fh):
                yr = int(row["season"])
                if yr not in btr.NFL_SCORED_YEARS:
                    continue
                if year_filter and not year_filter(yr):
                    continue
                tn = row["team_name"].strip().lower()
                mid = ynm.get((yr, tn))
                player = row.get("player_name") or ""
                if not (mid and player):
                    continue
                pts = nfl.get((yr, _norm(player)), 0)
                picks_raw.append((yr, int(row["round"]), mid, pts))
    for lg in ["league_1001657805583077376",
               "league_1085805164784664576",
               "league_1245039290518360064"]:
        d_idx = json.loads((ROOT / "data/sleeper" / lg / "drafts.json").read_text())
        for d in d_idx:
            picks_f = (ROOT / "data/sleeper" / lg /
                        f"draft_{d['draft_id']}_picks.json")
            if not picks_f.exists():
                continue
            season = int(d["season"])
            if season not in btr.NFL_SCORED_YEARS:
                continue
            if year_filter and not year_filter(season):
                continue
            for p in json.loads(picks_f.read_text()):
                rid = int(p.get("roster_id") or 0)
                mid = ROSTER_HANDOFFS.get((season, rid)) or mgr_rid_to_id.get(rid)
                pid = p.get("player_id")
                name = sleeper_names.get(pid, "") if pid else ""
                if not (mid and name):
                    continue
                pts = nfl.get((season, _norm(name)), 0)
                picks_raw.append((season, int(p.get("round") or 0), mid, pts))

    # Pass 2: league avg pts per (year, round)
    by_yr_rnd = defaultdict(list)
    for yr, rnd, mid, pts in picks_raw:
        by_yr_rnd[(yr, rnd)].append(pts)
    round_avg = {k: (sum(v) / len(v)) for k, v in by_yr_rnd.items() if v}

    # Pass 3: per-manager aggregation
    pts_by_mgr = defaultdict(float)
    picks_by_mgr = defaultdict(int)
    surplus_by_mgr = defaultdict(float)
    for yr, rnd, mid, pts in picks_raw:
        pts_by_mgr[mid] += pts
        picks_by_mgr[mid] += 1
        surplus_by_mgr[mid] += pts - round_avg.get((yr, rnd), 0)

    out = {}
    for mid in picks_by_mgr:
        n = picks_by_mgr[mid]
        out[mid] = {
            "pts": pts_by_mgr[mid], "picks": n,
            "ppp": pts_by_mgr[mid] / n if n else 0,
            "surplus": surplus_by_mgr[mid],
            "spp": surplus_by_mgr[mid] / n if n else 0,
        }
    return out


def compute_trade_vbd(year_filter=None):
    """Returns ({mid: net_vbd}, {mid: n_trades})."""
    nfl = btr._load_nflverse()
    sleeper_names = btr._load_sleeper_players()
    spp = btr._build_sleeper_pick_resolver()
    ypp = btr._build_yahoo_pick_resolver()
    ynm = btr._yahoo_name_lookup()
    mgr_rid = {m["id"]: m["sleeper_roster_id"]
               for m in all_managers() if m.get("sleeper_roster_id")}

    def score(side, source, year, giver):
        pts = sum(nfl.get((year, _norm(p["name"])), 0)
                  for p in side.get("received_players", []))
        for pk in side.get("received_picks", []):
            rnd = pk.get("round")
            if not rnd:
                continue
            if source == "sleeper":
                season = int(pk.get("season") or 0)
                orig = pk.get("previous_owner_id") or pk.get("roster_id")
                if not (season and orig):
                    continue
                pid = spp.get((season, rnd, orig))
                n = sleeper_names.get(pid, "") if pid else ""
                if n:
                    pts += nfl.get((season, _norm(n)), 0)
            else:
                ty = year + 1
                of = (pk.get("originally_from") or "").rstrip("?").strip().lower()
                om = ynm.get((year, of)) if of else None
                om = om or giver
                pl = ypp.get((ty, rnd, om))
                if pl:
                    pts += nfl.get((ty, _norm(pl)), 0)
                elif ty >= 2023:
                    r = mgr_rid.get(om)
                    if r:
                        pid = spp.get((ty, rnd, r))
                        n = sleeper_names.get(pid, "") if pid else ""
                        if n:
                            pts += nfl.get((ty, _norm(n)), 0)
        return pts

    trades = btr._load_all_trades()
    vbd = defaultdict(float)
    n = defaultdict(int)
    for t in trades:
        if t["year"] not in btr.NFL_SCORED_YEARS:
            continue
        if year_filter and not year_filter(t["year"]):
            continue
        pa = score(t["side_a"], t["source"], t["year"], t["side_b_mgr"])
        pb = score(t["side_b"], t["source"], t["year"], t["side_a_mgr"])
        vbd[t["side_a_mgr"]] += (pa - pb)
        vbd[t["side_b_mgr"]] += (pb - pa)
        n[t["side_a_mgr"]] += 1
        n[t["side_b_mgr"]] += 1
    return vbd, n


def _scale(val, lo, hi, lo_rating=50, hi_rating=99):
    if hi == lo:
        return (lo_rating + hi_rating) // 2
    r = (val - lo) / (hi - lo)
    r = max(0, min(1, r))
    return int(round(lo_rating + r * (hi_rating - lo_rating)))


def is_current(mid):
    """Currently rostered in Sleeper (2025)?"""
    for m in all_managers():
        if m["id"] == mid and m.get("sleeper_roster_id"):
            return True
    return False


def build_madden_cards(stats, vbd, vbd_n, draft):
    """Returns list of card dicts with all ratings + OVR."""
    # Current 5y+ OR long-tenured former (10y+)
    pool = {mid: s for mid, s in stats.items()
            if (s["n_years"] >= MIN_YEARS_CURRENT and is_current(mid))
            or s["n_years"] >= MIN_YEARS_FORMER}
    if not pool:
        return []

    def _safe(getter, default=0):
        vals = [getter(mid) for mid in pool]
        return (min(vals), max(vals)) if vals else (default, default)

    rng = {
        "rings": (0, max(s["rings"] for s in pool.values())),
        "winpct": _safe(lambda m: pool[m]["winpct"]),
        "ppg": _safe(lambda m: pool[m]["ppg"]),
        "vbd": _safe(lambda m: vbd.get(m, 0)),
        "yrs": _safe(lambda m: pool[m]["n_years"]),
        "spp": _safe(lambda m: draft.get(m, {}).get("spp", 0)),
    }

    cards = []
    for mid, s in pool.items():
        rings = _scale(s["rings"], 0, max(rng["rings"][1], 1), 50, 99)
        winp = _scale(s["winpct"], rng["winpct"][0], rng["winpct"][1])
        ppg = _scale(s["ppg"], rng["ppg"][0], rng["ppg"][1])
        trd = _scale(vbd.get(mid, 0), rng["vbd"][0], rng["vbd"][1], 40, 99)
        lng = _scale(s["n_years"], rng["yrs"][0], rng["yrs"][1])
        d = draft.get(mid, {"pts": 0, "picks": 0, "ppp": 0, "surplus": 0, "spp": 0})
        drf = _scale(d["spp"], rng["spp"][0], rng["spp"][1], 40, 99)
        # OVR weights — longevity excluded (called out separately as tenure)
        # Rings 33 + Win% 22 + Draft 18 + Trade 14 + PPG 13 = 100
        ovr = round(0.33 * rings + 0.22 * winp + 0.13 * ppg
                    + 0.14 * trd + 0.18 * drf)
        cards.append({
            "mid": mid, "name": _mgr_name(mid), "ovr": ovr,
            "rings_rating": rings, "winp_rating": winp,
            "ppg_rating": ppg, "trade_rating": trd,
            "draft_rating": drf, "long_rating": lng,
            "rings": s["rings"], "winpct": s["winpct"], "ppg": s["ppg"],
            "trade_vbd": vbd.get(mid, 0), "trade_n": vbd_n.get(mid, 0),
            "draft_ppp": d["ppp"], "draft_spp": d["spp"], "draft_surplus": d["surplus"], "draft_picks": d["picks"],
            "years": s["n_years"], "w": s["w"], "l": s["l"],
            "is_current": is_current(mid),
        })
    cards.sort(key=lambda c: -c["ovr"])
    return cards


def tier(ovr):
    if ovr >= 90:
        return "Franchise"
    if ovr >= 85:
        return "Star"
    if ovr >= 80:
        return "Pro Bowler"
    if ovr >= 75:
        return "Solid Starter"
    if ovr >= 65:
        return "Depth"
    return "Bench"


def archetype(card):
    """Madden-style descriptor based on the card's profile."""
    s = card
    if s["rings"] >= 3 and s["years"] >= 12:
        return "Iron-man 3-Ring Vet"
    if s["rings"] >= 2 and s["trade_vbd"] >= 1000:
        return "Franchise Player"
    if s["rings"] >= 2:
        return "Multi-Ring Vet"
    if s["winpct"] >= 0.60 and s["rings"] == 0:
        return "Regular-Season MVP, No Lombardi"
    if s["years"] <= 6 and s["rings"] >= 1:
        return "Rookie Champion"
    if s["rings"] == 1 and s["winpct"] < 0.40:
        return "Lucky-Ring Owner"
    if s["winpct"] < 0.40:
        return "Cellar Dweller"
    if s["rings"] == 0 and s["winpct"] >= 0.50:
        return "Steady Vet, Still Chasing"
    if s["rings"] == 0:
        return "Long-Tenured Underdog"
    return "Solid Pro"


def render_card_html(c):
    color = mgr_color(c["mid"])
    arch = archetype(c)
    badge = "" if c.get("is_current", True) else ' <span class="badge-fmr">FMR</span>'
    av = _avatar_path(c["mid"])
    av_html = (f'<img class="avatar" src="{_data_uri(av)}"/>'
               if av else '<div class="avatar avatar-placeholder"></div>')
    return f"""
    <div class="card">
      <div class="card-head" style="background:linear-gradient(135deg, {color} 0%, {color}dd 100%)">
        <div class="ovr">{c['ovr']}</div>
        {av_html}
        <div class="card-name">
          <div class="player-name">{c['name']}{badge}</div>
          <div class="archetype">{arch} · {tier(c['ovr'])}</div>
          <div class="tenure-tag">{c['years']} yrs in league</div>
        </div>
      </div>
      <div class="card-body">
        <table class="attr-table">
          <tr><td class="attr">RING</td><td class="bar"><div class="bar-fill" style="width:{c['rings_rating']}%;background:{color}"></div></td><td class="val">{c['rings_rating']}</td><td class="raw">{c['rings']} ring{'s' if c['rings']!=1 else ''}</td></tr>
          <tr><td class="attr">WIN%</td><td class="bar"><div class="bar-fill" style="width:{c['winp_rating']}%;background:{color}"></div></td><td class="val">{c['winp_rating']}</td><td class="raw">{c['w']}-{c['l']} ({c['winpct']:.3f})</td></tr>
          <tr><td class="attr">PPG</td><td class="bar"><div class="bar-fill" style="width:{c['ppg_rating']}%;background:{color}"></div></td><td class="val">{c['ppg_rating']}</td><td class="raw">{c['ppg']:.1f}</td></tr>
          <tr><td class="attr">DRFT</td><td class="bar"><div class="bar-fill" style="width:{c['draft_rating']}%;background:{color}"></div></td><td class="val">{c['draft_rating']}</td><td class="raw">{c['draft_spp']:+.1f}/pk · {c['draft_picks']}p</td></tr>
          <tr><td class="attr">TRADE</td><td class="bar"><div class="bar-fill" style="width:{c['trade_rating']}%;background:{color}"></div></td><td class="val">{c['trade_rating']}</td><td class="raw">{c['trade_vbd']:+.0f} ({c['trade_n']}t)</td></tr>
        </table>
      </div>
    </div>
    """


def build_madden_cards_sleeper(stats, vbd, vbd_n, draft):
    """Sleeper-era only: include all 12 current rosters."""
    pool = {mid: s for mid, s in stats.items()
            if s["n_years"] >= 1 and is_current(mid)}
    if not pool:
        return []

    def _safe(getter):
        vals = [getter(mid) for mid in pool]
        return (min(vals), max(vals)) if vals else (0, 0)

    rng = {
        "rings": (0, max(s["rings"] for s in pool.values()) or 1),
        "winpct": _safe(lambda m: pool[m]["winpct"]),
        "ppg": _safe(lambda m: pool[m]["ppg"]),
        "vbd": _safe(lambda m: vbd.get(m, 0)),
        "yrs": _safe(lambda m: pool[m]["n_years"]),
        "spp": _safe(lambda m: draft.get(m, {}).get("spp", 0)),
    }
    cards = []
    for mid, s in pool.items():
        rings = _scale(s["rings"], 0, rng["rings"][1], 50, 99)
        winp = _scale(s["winpct"], rng["winpct"][0], rng["winpct"][1])
        ppg = _scale(s["ppg"], rng["ppg"][0], rng["ppg"][1])
        trd = _scale(vbd.get(mid, 0), rng["vbd"][0], rng["vbd"][1], 40, 99)
        lng = _scale(s["n_years"], rng["yrs"][0], rng["yrs"][1])
        d = draft.get(mid, {"pts": 0, "picks": 0, "ppp": 0, "surplus": 0, "spp": 0})
        drf = _scale(d["spp"], rng["spp"][0], rng["spp"][1], 40, 99)
        # Sleeper era — same exclusion of longevity
        # Rings 26 + Win% 24 + Draft 23 + Trade 14 + PPG 13 = 100
        ovr = round(0.26 * rings + 0.24 * winp + 0.13 * ppg
                    + 0.14 * trd + 0.23 * drf)
        cards.append({
            "mid": mid, "name": _mgr_name(mid), "ovr": ovr,
            "rings_rating": rings, "winp_rating": winp,
            "ppg_rating": ppg, "trade_rating": trd,
            "draft_rating": drf, "long_rating": lng,
            "rings": s["rings"], "winpct": s["winpct"], "ppg": s["ppg"],
            "trade_vbd": vbd.get(mid, 0), "trade_n": vbd_n.get(mid, 0),
            "draft_ppp": d["ppp"], "draft_spp": d["spp"], "draft_surplus": d["surplus"], "draft_picks": d["picks"],
            "years": s["n_years"], "w": s["w"], "l": s["l"],
            "is_current": True,
        })
    cards.sort(key=lambda c: -c["ovr"])
    return cards


def chart_ovr_ranking(cards, path, title="All-Time Power Rankings"):
    mpl_style()
    cards = sorted(cards, key=lambda c: c["ovr"])
    names = [c["name"] + (" (FMR)" if not c.get("is_current", True) else "") for c in cards]
    ovrs = [c["ovr"] for c in cards]
    colors = [mgr_color(c["mid"]) for c in cards]
    fig, ax = plt.subplots(figsize=(9, max(2.8, 0.32 * len(cards) + 0.5)), dpi=140)
    bars = ax.barh(names, ovrs, color=colors, edgecolor="white", linewidth=1.5, height=0.72)
    ax.set_xlim(40, 100)
    ax.set_xlabel("OVR Rating", fontweight="bold")
    ax.set_title(title, loc="left", pad=14)
    ax.grid(axis="x", linestyle="--", alpha=0.4)
    ax.set_axisbelow(True)
    for bar, ovr in zip(bars, ovrs):
        ax.text(bar.get_width() + 0.8, bar.get_y() + bar.get_height() / 2,
                f"{ovr}", va="center", ha="left",
                fontweight="bold", fontsize=11, color=PALETTE["ink"])
    # Tier divider lines
    for v, lbl in [(65, "Depth"), (75, "Starter"), (80, "Pro Bowler"),
                   (85, "Star"), (90, "Franchise")]:
        ax.axvline(v, color=PALETTE["gray"], linestyle=":", alpha=0.5, linewidth=0.8)
        ax.text(v, len(cards) - 0.4, lbl, ha="center", va="bottom",
                color=PALETTE["gray"], fontsize=7, alpha=0.8)
    plt.tight_layout()
    plt.savefig(path, bbox_inches="tight", facecolor="white")
    plt.close()


def chart_radar_grid(cards, path, title="Top 6 Player Profiles"):
    mpl_style()
    top = sorted(cards, key=lambda c: -c["ovr"])[:6]
    cats = ["RING", "WIN%", "PPG", "DRFT", "TRADE"]
    angles = np.linspace(0, 2 * np.pi, len(cats), endpoint=False).tolist()
    angles += angles[:1]
    fig, axes = plt.subplots(2, 3, figsize=(10, 7), dpi=140,
                              subplot_kw=dict(polar=True))
    for ax, c in zip(axes.flat, top):
        vals = [c["rings_rating"], c["winp_rating"], c["ppg_rating"],
                c["draft_rating"], c["trade_rating"]]
        vals += vals[:1]
        color = mgr_color(c["mid"])
        ax.plot(angles, vals, color=color, linewidth=2.2)
        ax.fill(angles, vals, color=color, alpha=0.25)
        ax.set_xticks(angles[:-1])
        ax.set_xticklabels(cats, fontsize=8, color=PALETTE["ink"])
        ax.set_yticks([40, 60, 80, 100])
        ax.set_yticklabels([], fontsize=7)
        ax.set_ylim(30, 100)
        ax.set_title(f"{c['name']}  ({c['ovr']})", color=color,
                     fontweight="bold", fontsize=11, pad=12)
        ax.grid(color=CHART["grid_strong"], linewidth=0.6)
        ax.spines["polar"].set_color(CHART["grid_strong"])
    for ax in axes.flat[len(top):]:
        ax.set_visible(False)
    fig.suptitle(title, fontweight="bold", fontsize=14, color=PALETTE["ink"], y=0.99)
    plt.tight_layout()
    plt.savefig(path, bbox_inches="tight", facecolor="white")
    plt.close()


def chart_scatter_winpct_ppg(cards, path):
    mpl_style()
    fig, ax = plt.subplots(figsize=(9, 6), dpi=140)
    # Bubble size = rings (exponential so 0 -> dot, 3 -> big circle)
    for c in cards:
        color = mgr_color(c["mid"])
        size = 60 + (c["rings"] ** 2) * 380   # 0:60, 1:440, 2:1580, 3:3480
        ax.scatter(c["winpct"], c["ppg"], s=size, color=color,
                   alpha=0.55, edgecolor="white", linewidth=1.6, zorder=3)
        # Label below the bubble
        ax.annotate(c["name"] + (f"  {c['rings']}R" if c["rings"] else ""),
                    (c["winpct"], c["ppg"]),
                    xytext=(0, -(math.sqrt(size) / 2) - 8),
                    textcoords="offset points",
                    fontsize=9, ha="center", color=PALETTE["ink"],
                    fontweight="bold")
    ax.axvline(0.5, color=PALETTE["gray"], linestyle="--", alpha=0.5)
    ax.axhline(np.mean([c["ppg"] for c in cards]),
               color=PALETTE["gray"], linestyle="--", alpha=0.5)
    ax.set_xlabel("Career Win %", fontweight="bold")
    ax.set_ylabel("Career PPG", fontweight="bold")
    ax.set_title("Win% vs PPG  ·  Bubble size = championship count  "
                 "·  Dot = 0 rings · Giant = 3 rings",
                 loc="left", pad=14)
    # Pad axes a bit so big bubbles fit
    xpad = (max(c["winpct"] for c in cards) - min(c["winpct"] for c in cards)) * 0.18
    ypad = (max(c["ppg"] for c in cards) - min(c["ppg"] for c in cards)) * 0.18
    ax.set_xlim(min(c["winpct"] for c in cards) - xpad,
                max(c["winpct"] for c in cards) + xpad)
    ax.set_ylim(min(c["ppg"] for c in cards) - ypad,
                max(c["ppg"] for c in cards) + ypad)
    ax.grid(linestyle="--", alpha=0.4)
    ax.set_axisbelow(True)
    plt.tight_layout()
    plt.savefig(path, bbox_inches="tight", facecolor="white")
    plt.close()


def chart_trade_vbd(cards, path):
    mpl_style()
    s = sorted(cards, key=lambda c: c["trade_vbd"])
    names = [c["name"] for c in s]
    vals = [c["trade_vbd"] for c in s]
    colors = [PALETTE["emerald"] if v >= 0 else PALETTE["crimson"] for v in vals]
    fig, ax = plt.subplots(figsize=(9, max(3, 0.4 * len(s) + 1)), dpi=140)
    ax.barh(names, vals, color=colors, edgecolor="white", linewidth=1.2, height=0.7)
    ax.axvline(0, color=PALETTE["ink"], linewidth=1)
    for i, (v, c) in enumerate(zip(vals, s)):
        x = v + (60 if v >= 0 else -60)
        ha = "left" if v >= 0 else "right"
        ax.text(x, i, f"{v:+.0f}  ({c['trade_n']}t)", va="center", ha=ha,
                fontsize=9, color=PALETTE["ink"], fontweight="bold")
    pad = max(abs(min(vals)), max(vals)) * 0.25
    ax.set_xlim(min(vals) - pad, max(vals) + pad)
    ax.set_xlabel("Net VBD (points)", fontweight="bold")
    ax.set_title("Trade Fleecer Ledger  ·  green = winner, red = loser",
                 loc="left", pad=14)
    ax.grid(axis="x", linestyle="--", alpha=0.4)
    ax.set_axisbelow(True)
    plt.tight_layout()
    plt.savefig(path, bbox_inches="tight", facecolor="white")
    plt.close()


def chart_drafters(cards, path):
    mpl_style()
    s = sorted([c for c in cards if c["draft_picks"] > 20],
                key=lambda c: c["draft_spp"])
    names = [c["name"] for c in s]
    vals = [c["draft_spp"] for c in s]
    colors = [mgr_color(c["mid"]) for c in s]
    fig, ax = plt.subplots(figsize=(9, max(3, 0.4 * len(s) + 1)), dpi=140)
    ax.barh(names, vals, color=colors, edgecolor="white", linewidth=1.2, height=0.7)
    ax.axvline(0, color=PALETTE["ink"], linewidth=1)
    for i, (v, c) in enumerate(zip(vals, s)):
        x = v + (1.0 if v >= 0 else -1.0)
        ha = "left" if v >= 0 else "right"
        ax.text(x, i, f"{v:+.1f}  ({c['draft_picks']}p · raw {c['draft_ppp']:.0f})",
                va="center", ha=ha, fontsize=9, color=PALETTE["ink"],
                fontweight="bold")
    rng = max(abs(min(vals)), abs(max(vals))) * 1.7
    ax.set_xlim(-rng, rng)
    ax.set_xlabel("Surplus pts per pick (vs round avg)", fontweight="bold")
    ax.set_title("Best Drafters  ·  pts vs league round avg — true drafting skill, "
                 "not pick-slot luck",
                 loc="left", pad=14)
    ax.grid(axis="x", linestyle="--", alpha=0.4)
    ax.set_axisbelow(True)
    plt.tight_layout()
    plt.savefig(path, bbox_inches="tight", facecolor="white")
    plt.close()


def chart_championships_timeline(path):
    mpl_style()
    # Collect (year, mgr_id) for every champion
    champs = []
    for yr, mid in KNOWN_CHAMPIONS.items():
        champs.append((yr, mid))
    for season, s in load_all_seasons().items():
        if season in KNOWN_CHAMPIONS:
            continue
        rid = s.get("champion_roster_id")
        if rid:
            mid = ROSTER_HANDOFFS.get((season, int(rid)),
                                       (manager_for_sleeper_roster(int(rid)) or {}).get("id"))
            if mid:
                champs.append((season, mid))
    champs.sort()
    # Order managers by total rings desc
    counts = defaultdict(int)
    for _, mid in champs:
        counts[mid] += 1
    mgr_order = sorted(counts, key=lambda m: -counts[m])
    y_pos = {m: i for i, m in enumerate(mgr_order)}
    fig, ax = plt.subplots(figsize=(10, 0.55 * len(mgr_order) + 1), dpi=140)
    years = sorted({y for y, _ in champs})
    yr_min, yr_max = min(years), max(years)
    # Grid: faint vertical line per year
    for y in range(yr_min, yr_max + 1):
        ax.axvline(y, color=CHART["grid"], linewidth=0.5, zorder=0)
    # Trophies — star markers
    for yr, mid in champs:
        ax.scatter(yr, y_pos[mid], s=420, color=PALETTE["gold"], zorder=3,
                   edgecolor=PALETTE["ink"], linewidth=1.2, marker="*")
    ax.set_yticks(range(len(mgr_order)))
    ax.set_yticklabels([f"{_mgr_name(m)}  ({counts[m]})" for m in mgr_order],
                       fontweight="bold")
    ax.set_xticks(years)
    ax.set_xticklabels([str(y) for y in years], rotation=0, fontsize=8)
    ax.set_xlim(yr_min - 0.5, yr_max + 0.5)
    ax.invert_yaxis()
    ax.set_title("Championship Timeline (2011-2025)", loc="left", pad=14, fontsize=14)
    ax.spines["left"].set_visible(False)
    ax.tick_params(left=False)
    plt.tight_layout()
    plt.savefig(path, bbox_inches="tight", facecolor="white")
    plt.close()


def chart_trade_heatmap(path, cards):
    """Pairwise net VBD matrix: cell[row][col] = row mgr's net advantage
    over col mgr across all their trades together."""
    mpl_style()
    nfl = btr._load_nflverse()
    sleeper_names = btr._load_sleeper_players()
    spp = btr._build_sleeper_pick_resolver()
    ypp = btr._build_yahoo_pick_resolver()
    ynm = btr._yahoo_name_lookup()
    mgr_rid = {m["id"]: m["sleeper_roster_id"]
               for m in all_managers() if m.get("sleeper_roster_id")}

    def score(side, source, year, giver):
        pts = sum(nfl.get((year, _norm(p["name"])), 0)
                  for p in side.get("received_players", []))
        for pk in side.get("received_picks", []):
            rnd = pk.get("round")
            if not rnd:
                continue
            if source == "sleeper":
                season = int(pk.get("season") or 0)
                orig = pk.get("previous_owner_id") or pk.get("roster_id")
                if not (season and orig):
                    continue
                pid = spp.get((season, rnd, orig))
                n = sleeper_names.get(pid, "") if pid else ""
                if n:
                    pts += nfl.get((season, _norm(n)), 0)
            else:
                ty = year + 1
                of = (pk.get("originally_from") or "").rstrip("?").strip().lower()
                om = ynm.get((year, of)) if of else None
                om = om or giver
                pl = ypp.get((ty, rnd, om))
                if pl:
                    pts += nfl.get((ty, _norm(pl)), 0)
                elif ty >= 2023:
                    r = mgr_rid.get(om)
                    if r:
                        pid = spp.get((ty, rnd, r))
                        n = sleeper_names.get(pid, "") if pid else ""
                        if n:
                            pts += nfl.get((ty, _norm(n)), 0)
        return pts

    # Build pairwise stats
    pair_net = defaultdict(float)
    pair_n = defaultdict(int)
    trades = btr._load_all_trades()
    for t in trades:
        if t["year"] not in btr.NFL_SCORED_YEARS:
            continue
        ma, mb = t["side_a_mgr"], t["side_b_mgr"]
        pa = score(t["side_a"], t["source"], t["year"], mb)
        pb = score(t["side_b"], t["source"], t["year"], ma)
        pair_net[(ma, mb)] += (pa - pb)
        pair_net[(mb, ma)] += (pb - pa)
        pair_n[(ma, mb)] += 1
        pair_n[(mb, ma)] += 1

    # Order managers by their card OVR (best to worst, top-down)
    mgrs = [c["mid"] for c in sorted(cards, key=lambda c: -c["ovr"])]
    n = len(mgrs)
    M = np.full((n, n), np.nan)
    cnt = np.zeros((n, n), dtype=int)
    for i, a in enumerate(mgrs):
        for j, b in enumerate(mgrs):
            if i == j:
                continue
            if pair_n[(a, b)] > 0:
                M[i, j] = pair_net[(a, b)]
                cnt[i, j] = pair_n[(a, b)]

    # Symmetric diverging scale around 0
    vmax = float(np.nanmax(np.abs(M)))
    if not vmax or np.isnan(vmax):
        vmax = 1.0

    fig, ax = plt.subplots(figsize=(10, 8.5), dpi=140)
    cmap = plt.get_cmap("RdYlGn")
    im = ax.imshow(M, cmap=cmap, vmin=-vmax, vmax=vmax, aspect="equal")
    # Diagonal = gray
    for i in range(n):
        ax.add_patch(plt.Rectangle((i - 0.5, i - 0.5), 1, 1,
                                    color=PALETTE["ink"], zorder=2))
    names = [_mgr_name(m) for m in mgrs]
    ax.set_xticks(range(n))
    ax.set_yticks(range(n))
    ax.set_xticklabels(names, rotation=45, ha="right", fontsize=9,
                        fontweight="bold")
    ax.set_yticklabels(names, fontsize=9, fontweight="bold")
    ax.tick_params(top=True, labeltop=True, bottom=False, labelbottom=False)
    plt.setp(ax.get_xticklabels(), rotation=45, ha="left",
             rotation_mode="anchor")
    # Annotate cells
    for i in range(n):
        for j in range(n):
            if i == j or np.isnan(M[i, j]):
                continue
            val = M[i, j]
            # Text color based on cell brightness
            tc = "white" if abs(val) > 0.55 * vmax else PALETTE["ink"]
            ax.text(j, i - 0.12, f"{val:+.0f}", ha="center", va="center",
                    fontsize=8, color=tc, fontweight="bold")
            ax.text(j, i + 0.25, f"{cnt[i, j]}t", ha="center", va="center",
                    fontsize=6.5, color=tc, alpha=0.85)
    # Subtle grid
    for x in range(n + 1):
        ax.axhline(x - 0.5, color="white", linewidth=2)
        ax.axvline(x - 0.5, color="white", linewidth=2)
    ax.set_title("Trade Fleecing Matrix  ·  ROW's net VBD vs COLUMN  "
                 "·  green = row dominated, red = row got fleeced",
                 loc="left", pad=24, fontsize=12)
    cbar = plt.colorbar(im, ax=ax, fraction=0.04, pad=0.02)
    cbar.set_label("Net VBD (row - column)", fontweight="bold")
    cbar.ax.tick_params(labelsize=8)
    plt.tight_layout()
    plt.savefig(path, bbox_inches="tight", facecolor="white")
    plt.close()


def chart_trade_network(path, cards):
    """Force-directed trade network. Nodes = avatars, edges = trade
    relationships (thickness = volume, color intensity = imbalance)."""
    import networkx as nx
    mpl_style()

    nfl = btr._load_nflverse()
    sleeper_names = btr._load_sleeper_players()
    spp = btr._build_sleeper_pick_resolver()
    ypp = btr._build_yahoo_pick_resolver()
    ynm = btr._yahoo_name_lookup()
    mgr_rid = {m["id"]: m["sleeper_roster_id"]
               for m in all_managers() if m.get("sleeper_roster_id")}

    def score(side, source, year, giver):
        pts = sum(nfl.get((year, _norm(p["name"])), 0)
                  for p in side.get("received_players", []))
        for pk in side.get("received_picks", []):
            rnd = pk.get("round")
            if not rnd:
                continue
            if source == "sleeper":
                season = int(pk.get("season") or 0)
                orig = pk.get("previous_owner_id") or pk.get("roster_id")
                if not (season and orig):
                    continue
                pid = spp.get((season, rnd, orig))
                n = sleeper_names.get(pid, "") if pid else ""
                if n:
                    pts += nfl.get((season, _norm(n)), 0)
            else:
                ty = year + 1
                of = (pk.get("originally_from") or "").rstrip("?").strip().lower()
                om = ynm.get((year, of)) if of else None
                om = om or giver
                pl = ypp.get((ty, rnd, om))
                if pl:
                    pts += nfl.get((ty, _norm(pl)), 0)
                elif ty >= 2023:
                    r = mgr_rid.get(om)
                    if r:
                        pid = spp.get((ty, rnd, r))
                        n = sleeper_names.get(pid, "") if pid else ""
                        if n:
                            pts += nfl.get((ty, _norm(n)), 0)
        return pts

    pair_count = defaultdict(int)
    pair_net = defaultdict(float)
    trades = btr._load_all_trades()
    for t in trades:
        if t["year"] not in btr.NFL_SCORED_YEARS:
            continue
        ma, mb = t["side_a_mgr"], t["side_b_mgr"]
        key = tuple(sorted([ma, mb]))
        pa = score(t["side_a"], t["source"], t["year"], mb)
        pb = score(t["side_b"], t["source"], t["year"], ma)
        pair_count[key] += 1
        # Net from key[0]'s perspective
        if key[0] == ma:
            pair_net[key] += (pa - pb)
        else:
            pair_net[key] += (pb - pa)

    G = nx.Graph()
    mgr_ids = [c["mid"] for c in cards]
    trade_n_by_mgr = {c["mid"]: c["trade_n"] for c in cards}
    for mid in mgr_ids:
        G.add_node(mid, trades=trade_n_by_mgr.get(mid, 0))
    for (a, b), n in pair_count.items():
        if a in mgr_ids and b in mgr_ids and n >= 2:
            G.add_edge(a, b, weight=n, net=pair_net[(a, b)])

    fig, ax = plt.subplots(figsize=(10, 9), dpi=140)
    pos = nx.spring_layout(G, k=1.8, iterations=120, seed=42, weight="weight")

    # Edges: thickness = trade count, color = imbalance direction
    max_net = max((abs(d["net"]) for _, _, d in G.edges(data=True)), default=1)
    for u, v, d in G.edges(data=True):
        net = d["net"]
        # Color intensity by imbalance (red = lopsided, gray = balanced)
        intensity = min(1.0, abs(net) / max(max_net, 1))
        color = (0.55 + 0.4 * intensity, 0.55 - 0.3 * intensity, 0.6 - 0.4 * intensity)
        lw = 0.6 + 0.45 * d["weight"]
        x = [pos[u][0], pos[v][0]]
        y = [pos[u][1], pos[v][1]]
        ax.plot(x, y, color=color, linewidth=lw, alpha=0.55, zorder=1)

    # Nodes: avatars sized by trade volume
    max_trades = max((G.nodes[n]["trades"] for n in G.nodes()), default=1)
    for n in G.nodes():
        x, y = pos[n]
        size = 0.06 + 0.08 * (G.nodes[n]["trades"] / max(max_trades, 1))
        # Color ring for manager
        ax.scatter(x, y, s=2800 * size * size, color=mgr_color(n),
                   alpha=0.85, zorder=2,
                   edgecolor="white", linewidth=2)
        av = _avatar_path(n)
        if av:
            img = mpimg.imread(av)
            im = OffsetImage(img, zoom=0.14 + 0.10 * (G.nodes[n]["trades"] / max(max_trades, 1)))
            ab = AnnotationBbox(im, (x, y), frameon=False, zorder=3)
            ax.add_artist(ab)
        ax.text(x, y - 0.12, _mgr_name(n), ha="center", va="top",
                fontsize=9, fontweight="bold", color=PALETTE["ink"], zorder=4)

    ax.set_axis_off()
    ax.set_title("Trade Network · node size = trade volume · "
                 "edge thickness = pair frequency · edge color = imbalance",
                 fontsize=12, loc="left", pad=14)
    plt.tight_layout()
    plt.savefig(path, bbox_inches="tight", facecolor="white")
    plt.close()


def compute_season_table():
    """Returns {(season, mid): {'w','l','fpts','games','ppg',
                                  'wins_rank','fpts_rank','n_teams'}}."""
    ytm = {}
    for m in all_managers():
        for yr, tn in (m.get("yahoo_team_names") or {}).items():
            if yr == "_note" or not tn:
                continue
            ytm[(int(yr), tn.strip().lower())] = m["id"]
    rows = defaultdict(lambda: {"w": 0, "l": 0, "fpts": 0.0, "games": 0})

    for f in sorted((ROOT / "data" / "yahoo").glob("league_*/matchups_*.json")):
        yr = int(f.stem.split("_")[1])
        d = json.loads(f.read_text())
        teams = d.get("teams", {})
        tid_to_mgr = {}
        for tid, name in teams.items():
            mid = ytm.get((yr, name.strip().lower()))
            if mid:
                tid_to_mgr[int(tid)] = mid
        n_teams = len(teams)
        reg_end = 14 if n_teams == 12 else 13
        for wk_str, games in d.get("weeks", {}).items():
            if int(wk_str) > reg_end:
                continue
            for g in games:
                ma = tid_to_mgr.get(g["team_a"])
                mb = tid_to_mgr.get(g["team_b"])
                if not (ma and mb):
                    continue
                rows[(yr, ma)]["fpts"] += g["pts_a"]
                rows[(yr, mb)]["fpts"] += g["pts_b"]
                rows[(yr, ma)]["games"] += 1
                rows[(yr, mb)]["games"] += 1
                if g["winner"] == g["team_a"]:
                    rows[(yr, ma)]["w"] += 1
                    rows[(yr, mb)]["l"] += 1
                elif g["winner"] == g["team_b"]:
                    rows[(yr, mb)]["w"] += 1
                    rows[(yr, ma)]["l"] += 1

    for season, s in load_all_seasons().items():
        for rid, r in s["rosters"].items():
            m = manager_for_sleeper_roster(int(rid))
            mid = ROSTER_HANDOFFS.get((season, int(rid)),
                                       m["id"] if m else None)
            if not mid:
                continue
            rows[(season, mid)]["w"] = r["wins"]
            rows[(season, mid)]["l"] = r["losses"]
            rows[(season, mid)]["fpts"] = r["fpts"]
            rows[(season, mid)]["games"] = r["wins"] + r["losses"]

    # Add ranks per season
    by_year = defaultdict(dict)
    for (yr, mid), v in rows.items():
        by_year[yr][mid] = v
    out = {}
    for yr, mgrs in by_year.items():
        n_teams = len(mgrs)
        wr = sorted(mgrs, key=lambda m: -mgrs[m]["w"])
        fr = sorted(mgrs, key=lambda m: -mgrs[m]["fpts"])
        for mid, v in mgrs.items():
            out[(yr, mid)] = {
                **v, "n_teams": n_teams,
                "ppg": v["fpts"] / v["games"] if v["games"] else 0,
                "wins_rank": wr.index(mid) + 1,
                "fpts_rank": fr.index(mid) + 1,
            }
    return out


def chart_tenure_timeline(path, cards):
    """Gantt-style timeline of who was in the league each year, with ring stars."""
    mpl_style()
    # Pull every (yr, mid) from season table to know tenure
    season_table = compute_season_table()
    # Champions per year
    champs = dict(KNOWN_CHAMPIONS)
    for season, s in load_all_seasons().items():
        if season in champs:
            continue
        rid = s.get("champion_roster_id")
        if rid:
            m = manager_for_sleeper_roster(int(rid))
            mid = ROSTER_HANDOFFS.get((season, int(rid)),
                                       m["id"] if m else None)
            if mid:
                champs[season] = mid
    # Years present per manager
    years_by_mid = defaultdict(set)
    for (yr, mid) in season_table:
        years_by_mid[mid].add(yr)

    mgr_ids = [c["mid"] for c in sorted(cards, key=lambda c: -len(years_by_mid.get(c["mid"], set())))]
    years_all = sorted({y for ys in years_by_mid.values() for y in ys})
    yr_min, yr_max = min(years_all), max(years_all)
    fig, ax = plt.subplots(figsize=(11, 0.42 * len(mgr_ids) + 1), dpi=140)
    for i, mid in enumerate(mgr_ids):
        ys = sorted(years_by_mid.get(mid, set()))
        if not ys:
            continue
        # Plot continuous bars (consecutive ranges) and gap markers
        color = mgr_color(mid)
        prev = None
        run_start = None
        for y in ys + [None]:
            if prev is None:
                run_start = y; prev = y; continue
            if y == prev + 1:
                prev = y; continue
            # End of run
            ax.barh(i, prev - run_start + 1, left=run_start - 0.4,
                    height=0.66, color=color, alpha=0.85,
                    edgecolor="white", linewidth=0.5)
            run_start = y; prev = y
        # Champion stars
        for y in ys:
            if champs.get(y) == mid:
                ax.scatter(y, i, marker="*", s=250, color=PALETTE["gold"],
                           edgecolor=PALETTE["ink"], linewidth=1.2,
                           zorder=4)
    n_rings = {m: sum(1 for y in years_by_mid[m] if champs.get(y) == m)
               for m in mgr_ids}
    names = [f"{_mgr_name(m)}  ({len(years_by_mid[m])}y · {n_rings[m]}R)"
             for m in mgr_ids]
    ax.set_yticks(range(len(mgr_ids)))
    ax.set_yticklabels(names, fontweight="bold", fontsize=9)
    ax.set_xticks(years_all)
    ax.set_xticklabels([str(y) for y in years_all], fontsize=8)
    ax.set_xlim(yr_min - 0.5, yr_max + 0.5)
    ax.invert_yaxis()
    ax.set_title("Tenure Timeline  ·  bars = active in league  "
                 "·  gold stars = championships",
                 loc="left", pad=14, fontsize=13)
    ax.spines["left"].set_visible(False)
    ax.tick_params(left=False)
    ax.grid(axis="x", linestyle=":", color=CHART["grid_strong"], alpha=0.6, zorder=0)
    ax.set_axisbelow(True)
    plt.tight_layout()
    plt.savefig(path, bbox_inches="tight", facecolor="white")
    plt.close()


def chart_finish_heatmap(path, cards):
    """Manager rows × year cols, color = regular-season finishing rank
    (1 = gold, last = red)."""
    mpl_style()
    season_table = compute_season_table()
    mgrs = [c["mid"] for c in sorted(cards, key=lambda c: -c["ovr"])]
    years_all = sorted({yr for (yr, _) in season_table})
    # Normalize: 1 -> 0.0 (best), last -> 1.0 (worst)
    M = np.full((len(mgrs), len(years_all)), np.nan)
    labels = np.full((len(mgrs), len(years_all)), "", dtype=object)
    for i, mid in enumerate(mgrs):
        for j, yr in enumerate(years_all):
            s = season_table.get((yr, mid))
            if s:
                rank = s["wins_rank"]
                n = s["n_teams"]
                M[i, j] = (rank - 1) / max(n - 1, 1)
                labels[i, j] = str(rank)

    fig, ax = plt.subplots(figsize=(11, 0.42 * len(mgrs) + 1.5), dpi=140)
    cmap = plt.get_cmap("RdYlGn_r")
    im = ax.imshow(M, cmap=cmap, vmin=0, vmax=1, aspect="auto")
    for i in range(len(mgrs)):
        for j in range(len(years_all)):
            if not np.isnan(M[i, j]):
                # text color
                v = M[i, j]
                tc = "white" if v < 0.18 or v > 0.78 else PALETTE["ink"]
                ax.text(j, i, labels[i, j], ha="center", va="center",
                        color=tc, fontsize=8, fontweight="bold")
    ax.set_xticks(range(len(years_all)))
    ax.set_xticklabels([str(y) for y in years_all], fontsize=8)
    ax.set_yticks(range(len(mgrs)))
    ax.set_yticklabels([_mgr_name(m) for m in mgrs], fontweight="bold",
                       fontsize=9)
    ax.set_title("Regular-Season Finish by Year  ·  green = top, red = bottom  "
                 "·  number = rank within that year's league",
                 loc="left", pad=14, fontsize=12)
    for x in range(len(years_all) + 1):
        ax.axvline(x - 0.5, color="white", linewidth=1.2)
    for y in range(len(mgrs) + 1):
        ax.axhline(y - 0.5, color="white", linewidth=1.2)
    cbar = plt.colorbar(im, ax=ax, fraction=0.025, pad=0.01,
                         ticks=[0, 0.5, 1])
    cbar.ax.set_yticklabels(["#1", "Middle", "Last"])
    cbar.ax.tick_params(labelsize=8)
    plt.tight_layout()
    plt.savefig(path, bbox_inches="tight", facecolor="white")
    plt.close()


def chart_schedule_luck(path, cards):
    """Career schedule-luck index: (fpts_rank - wins_rank) avg per manager.
    Positive = luckier than they scored; negative = unlucky."""
    mpl_style()
    season_table = compute_season_table()
    luck = defaultdict(list)
    for (yr, mid), s in season_table.items():
        luck[mid].append(s["fpts_rank"] - s["wins_rank"])
    # luck > 0 → won more games than fpts-rank would predict
    avg = {m: np.mean(v) for m, v in luck.items() if len(v) >= 3}
    items = sorted([c["mid"] for c in cards if c["mid"] in avg],
                   key=lambda m: -avg[m])
    fig, ax = plt.subplots(figsize=(9, 0.42 * len(items) + 1), dpi=140)
    vals = [avg[m] for m in items]
    colors = [mgr_color(m) for m in items]
    bars = ax.barh([_mgr_name(m) for m in items][::-1], vals[::-1],
                    color=colors[::-1], edgecolor="white", linewidth=1.4,
                    height=0.72)
    ax.axvline(0, color=PALETTE["ink"], linewidth=1)
    for i, (m, v) in enumerate(list(zip(items, vals))[::-1]):
        x = v + (0.08 if v >= 0 else -0.08)
        ha = "left" if v >= 0 else "right"
        ax.text(x, i, f"{v:+.2f}", va="center", ha=ha, fontsize=9,
                fontweight="bold", color=PALETTE["ink"])
    rng = max(abs(min(vals)), max(vals)) * 1.35
    ax.set_xlim(-rng, rng)
    ax.set_xlabel("Avg (FPTS rank − Wins rank) per season",
                  fontweight="bold")
    ax.set_title("Schedule Luck  ·  positive = won more than score suggested · "
                 "negative = unlucky", loc="left", pad=14, fontsize=12)
    ax.grid(axis="x", linestyle="--", alpha=0.4)
    ax.set_axisbelow(True)
    plt.tight_layout()
    plt.savefig(path, bbox_inches="tight", facecolor="white")
    plt.close()


def _load_player_positions():
    """Map normalized player name -> NFL position."""
    import csv
    pos = {}
    with open(ROOT / "data" / "nflverse" / "player_stats_season.csv") as f:
        for row in csv.DictReader(f):
            n = (row["player_display_name"] or row["player_name"] or "").strip()
            p = row.get("position")
            if n and p:
                pos.setdefault(_norm(n), p)
    return pos


def _load_all_drafts():
    """Returns list of {season, round, mid, player, pos}."""
    import csv
    name_to_mgr = btr._yahoo_name_lookup()
    sleeper_names = btr._load_sleeper_players()
    sleeper_pos = {pid: d.get("position")
                    for pid, d in json.loads(
                        (ROOT / "data" / "sleeper" / "players_nfl.json").read_text()
                    ).items()}
    pos_lookup = _load_player_positions()
    mgr_rid_to_id = {m["sleeper_roster_id"]: m["id"]
                     for m in all_managers() if m.get("sleeper_roster_id")}
    out = []
    # Yahoo
    for f in sorted((ROOT / "data" / "yahoo").glob("league_*/draft_*.csv")):
        with open(f) as fh:
            for row in csv.DictReader(fh):
                yr = int(row["season"])
                tn = row["team_name"].strip().lower()
                mid = name_to_mgr.get((yr, tn))
                player = row.get("player_name", "")
                if not (mid and player):
                    continue
                pos = pos_lookup.get(_norm(player), "?")
                out.append({"season": yr, "round": int(row["round"]),
                             "mid": mid, "player": player, "pos": pos})
    # Sleeper
    for lg in ["league_1001657805583077376",
               "league_1085805164784664576",
               "league_1245039290518360064"]:
        d_idx = json.loads((ROOT / "data/sleeper" / lg / "drafts.json").read_text())
        for d in d_idx:
            picks_f = (ROOT / "data/sleeper" / lg /
                        f"draft_{d['draft_id']}_picks.json")
            if not picks_f.exists():
                continue
            season = int(d["season"])
            for p in json.loads(picks_f.read_text()):
                rid = int(p.get("roster_id") or 0)
                mid = ROSTER_HANDOFFS.get((season, rid)) or mgr_rid_to_id.get(rid)
                pid = p.get("player_id")
                name = sleeper_names.get(pid, "") if pid else ""
                if not (mid and name):
                    continue
                pos = sleeper_pos.get(pid) or pos_lookup.get(_norm(name), "?")
                out.append({"season": season, "round": int(p.get("round") or 0),
                             "mid": mid, "player": name, "pos": pos or "?"})
    return out


def chart_position_drafted(path, cards):
    """Stacked horizontal bars per manager — what positions they draft
    in each round. Shows draft strategy preferences."""
    mpl_style()
    drafts = _load_all_drafts()
    mgrs = [c["mid"] for c in cards]
    positions = ["QB", "RB", "WR", "TE", "K", "DEF"]
    # rounds to show
    rounds = list(range(1, 11))  # focus on rounds 1-10
    # data: mgr -> round -> position -> count
    cnt = defaultdict(lambda: defaultdict(lambda: defaultdict(int)))
    for p in drafts:
        if p["mid"] in mgrs and p["round"] in rounds:
            pos = p["pos"] if p["pos"] in positions else "?"
            if pos != "?":
                cnt[p["mid"]][p["round"]][pos] += 1
    n_mgrs = len(mgrs)
    ncols = 3
    nrows = math.ceil(n_mgrs / ncols)
    fig, axes = plt.subplots(nrows, ncols, figsize=(11.5, 2.0 * nrows + 1), dpi=140)
    axes_flat = axes.flat if hasattr(axes, "flat") else [axes]
    for ax, mid in zip(axes_flat, mgrs):
        bottoms = np.zeros(len(rounds))
        for pos in positions:
            vals = [cnt[mid][r][pos] for r in rounds]
            ax.bar(rounds, vals, bottom=bottoms, color=POS_COLORS[pos],
                    label=pos, edgecolor="white", linewidth=0.6, width=0.85)
            bottoms += np.array(vals)
        ax.set_title(_mgr_name(mid), fontsize=10, fontweight="bold",
                     color=mgr_color(mid), loc="left")
        ax.set_xticks(rounds)
        ax.set_xticklabels(rounds, fontsize=7)
        ax.tick_params(axis="y", labelsize=7)
        ax.set_xlim(0.4, len(rounds) + 0.6)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
    for ax in axes_flat[n_mgrs:]:
        ax.set_visible(False)
    # Single legend across the top
    handles = [plt.Rectangle((0, 0), 1, 1, color=POS_COLORS[p]) for p in positions]
    fig.legend(handles, positions, loc="upper center", ncol=len(positions),
               frameon=False, bbox_to_anchor=(0.5, 1.02), fontsize=9)
    fig.suptitle("Positions Drafted by Round  ·  rounds 1-10  ·  "
                 "stacked counts across career",
                 fontsize=13, fontweight="bold", y=1.06, x=0.07, ha="left")
    plt.tight_layout()
    plt.savefig(path, bbox_inches="tight", facecolor="white")
    plt.close()


def chart_h2h_matrix(path, cards):
    """Pairwise W-L matrix across all regular-season matchups (career)."""
    mpl_style()
    ytm = {}
    for m in all_managers():
        for yr, tn in (m.get("yahoo_team_names") or {}).items():
            if yr == "_note" or not tn:
                continue
            ytm[(int(yr), tn.strip().lower())] = m["id"]
    h2h = defaultdict(lambda: [0, 0])  # (a, b) -> [a_wins, b_wins]
    # Yahoo
    for f in sorted((ROOT / "data" / "yahoo").glob("league_*/matchups_*.json")):
        yr = int(f.stem.split("_")[1])
        d = json.loads(f.read_text())
        teams = d.get("teams", {})
        tid_to_mgr = {}
        for tid, name in teams.items():
            mid = ytm.get((yr, name.strip().lower()))
            if mid:
                tid_to_mgr[int(tid)] = mid
        n_teams = len(teams)
        reg_end = 14 if n_teams == 12 else 13
        for wk_str, games in d.get("weeks", {}).items():
            if int(wk_str) > reg_end:
                continue
            for g in games:
                ma = tid_to_mgr.get(g["team_a"])
                mb = tid_to_mgr.get(g["team_b"])
                if not (ma and mb):
                    continue
                key = tuple(sorted([ma, mb]))
                if g["winner"] == g["team_a"]:
                    if key[0] == ma:
                        h2h[key][0] += 1
                    else:
                        h2h[key][1] += 1
                elif g["winner"] == g["team_b"]:
                    if key[0] == mb:
                        h2h[key][0] += 1
                    else:
                        h2h[key][1] += 1
    # Sleeper
    for season, s in load_all_seasons().items():
        rid_to_mid = {}
        for rid in s["rosters"]:
            m = manager_for_sleeper_roster(int(rid))
            mid = ROSTER_HANDOFFS.get((season, int(rid)),
                                       m["id"] if m else None)
            if mid:
                rid_to_mid[int(rid)] = mid
        # Walk Sleeper matchups
        mu_dir = ROOT / "data" / "sleeper" / f"league_{s['league_id']}" / "matchups"
        for wkf in sorted(mu_dir.glob("week_*.json")):
            wk = int(wkf.stem.split("_")[1])
            if wk > 14:
                continue
            entries = json.loads(wkf.read_text())
            # Group by matchup_id
            by_mid = defaultdict(list)
            for e in entries:
                if e.get("matchup_id") is not None:
                    by_mid[e["matchup_id"]].append(e)
            for mids_pair in by_mid.values():
                if len(mids_pair) != 2:
                    continue
                a, b = mids_pair
                ma = rid_to_mid.get(int(a["roster_id"]))
                mb = rid_to_mid.get(int(b["roster_id"]))
                if not (ma and mb):
                    continue
                key = tuple(sorted([ma, mb]))
                pa = a.get("points") or 0
                pb = b.get("points") or 0
                if pa > pb:
                    if key[0] == ma:
                        h2h[key][0] += 1
                    else:
                        h2h[key][1] += 1
                elif pb > pa:
                    if key[0] == mb:
                        h2h[key][0] += 1
                    else:
                        h2h[key][1] += 1
    # Build matrix
    mgrs = [c["mid"] for c in sorted(cards, key=lambda c: -c["ovr"])]
    n = len(mgrs)
    M = np.full((n, n), np.nan)
    Lbl = np.full((n, n), "", dtype=object)
    for i, a in enumerate(mgrs):
        for j, b in enumerate(mgrs):
            if i == j:
                continue
            key = tuple(sorted([a, b]))
            wa, wb = h2h.get(key, [0, 0])
            if key[0] == a:
                w, l = wa, wb
            else:
                w, l = wb, wa
            if w + l > 0:
                M[i, j] = w - l
                Lbl[i, j] = f"{w}-{l}"
    vmax = float(np.nanmax(np.abs(M))) or 1.0
    fig, ax = plt.subplots(figsize=(10, 8.5), dpi=140)
    im = ax.imshow(M, cmap="RdYlGn", vmin=-vmax, vmax=vmax, aspect="equal")
    for i in range(n):
        ax.add_patch(plt.Rectangle((i - 0.5, i - 0.5), 1, 1,
                                    color=PALETTE["ink"], zorder=2))
    names = [_mgr_name(m) for m in mgrs]
    ax.set_xticks(range(n)); ax.set_yticks(range(n))
    ax.set_xticklabels(names, rotation=45, ha="left", fontsize=9,
                       fontweight="bold", rotation_mode="anchor")
    ax.set_yticklabels(names, fontsize=9, fontweight="bold")
    ax.tick_params(top=True, labeltop=True, bottom=False, labelbottom=False)
    for i in range(n):
        for j in range(n):
            if i == j or np.isnan(M[i, j]):
                continue
            v = M[i, j]
            tc = "white" if abs(v) > 0.55 * vmax else PALETTE["ink"]
            ax.text(j, i, Lbl[i, j], ha="center", va="center",
                    fontsize=8, color=tc, fontweight="bold")
    for x in range(n + 1):
        ax.axhline(x - 0.5, color="white", linewidth=2)
        ax.axvline(x - 0.5, color="white", linewidth=2)
    ax.set_title("Head-to-Head Matrix  ·  career regular-season record  "
                 "·  ROW vs COLUMN  ·  green = ROW dominant",
                 loc="left", pad=24, fontsize=12)
    cbar = plt.colorbar(im, ax=ax, fraction=0.04, pad=0.02)
    cbar.set_label("Win margin (row - column)", fontweight="bold")
    cbar.ax.tick_params(labelsize=8)
    plt.tight_layout()
    plt.savefig(path, bbox_inches="tight", facecolor="white")
    plt.close()


def chart_recent_vs_lifetime(path, cards, cards_s):
    """Sleeper-era OVR minus all-time OVR per current manager."""
    mpl_style()
    by_mid = {c["mid"]: c["ovr"] for c in cards}
    by_mid_s = {c["mid"]: c["ovr"] for c in cards_s}
    rows = []
    for mid, ovr_s in by_mid_s.items():
        if mid in by_mid:
            rows.append((mid, ovr_s - by_mid[mid], by_mid[mid], ovr_s))
    rows.sort(key=lambda r: -r[1])
    fig, ax = plt.subplots(figsize=(9, 0.45 * len(rows) + 1), dpi=140)
    names = [_mgr_name(r[0]) for r in rows][::-1]
    vals = [r[1] for r in rows][::-1]
    colors = [mgr_color(r[0]) for r in rows][::-1]
    ax.barh(names, vals, color=colors, edgecolor="white", linewidth=1.2,
            height=0.72)
    ax.axvline(0, color=PALETTE["ink"], linewidth=1)
    for i, (mid, delta, ovr, ovr_s) in enumerate(rows[::-1]):
        x = delta + (0.45 if delta >= 0 else -0.45)
        ha = "left" if delta >= 0 else "right"
        ax.text(x, i, f"{delta:+d}  ({ovr}→{ovr_s})", va="center", ha=ha,
                fontsize=9, fontweight="bold", color=PALETTE["ink"])
    rng = max(abs(min(vals)), max(vals)) * 1.6
    ax.set_xlim(-rng, rng)
    ax.set_xlabel("Sleeper-era OVR − All-time OVR", fontweight="bold")
    ax.set_title("Recent vs Lifetime  ·  who’s heating up, who’s cooling off",
                 loc="left", pad=14, fontsize=12)
    ax.grid(axis="x", linestyle="--", alpha=0.4)
    ax.set_axisbelow(True)
    plt.tight_layout()
    plt.savefig(path, bbox_inches="tight", facecolor="white")
    plt.close()


def chart_best_worst_seasons(path):
    """Top 8 best + 8 worst (mgr, year) seasons by composite score."""
    mpl_style()
    st = compute_season_table()
    items = []
    for (yr, mid), s in st.items():
        if s["games"] < 8:
            continue
        # Composite: win_pct + ppg z-score
        items.append((yr, mid, s["w"], s["l"], s["w"] / s["games"],
                      s["ppg"], s["n_teams"], s["wins_rank"]))
    # Best 8 by win pct (tie-break PPG)
    best = sorted(items, key=lambda x: (-x[4], -x[5]))[:8]
    worst = sorted(items, key=lambda x: (x[4], x[5]))[:8]
    fig, axes = plt.subplots(1, 2, figsize=(12, 0.42 * 8 + 1.5), dpi=140)
    for ax, rows, title, cmap in [
        (axes[0], best, "Top 8 Seasons (by win%)", "Greens"),
        (axes[1], worst, "Bottom 8 Seasons", "Reds"),
    ]:
        labels = [f"{_mgr_name(m)}  {y}" for y, m, w, l, wp, p, n, r in rows][::-1]
        vals = [wp for y, m, w, l, wp, p, n, r in rows][::-1]
        colors = [mgr_color(m) for y, m, w, l, wp, p, n, r in rows][::-1]
        ax.barh(labels, vals, color=colors, edgecolor="white",
                linewidth=1.2, height=0.72)
        for i, (y, m, w, l, wp, p, n, r) in enumerate(rows[::-1]):
            ax.text(wp + 0.005, i, f"{w}-{l} · {p:.1f} PPG · #{r}/{n}",
                    va="center", fontsize=8.5, color=PALETTE["ink"])
        ax.set_xlim(0, 1)
        ax.set_xlabel("Regular-season win %", fontweight="bold")
        ax.set_title(title, loc="left", pad=12, fontsize=12)
        ax.grid(axis="x", linestyle="--", alpha=0.4)
        ax.set_axisbelow(True)
    plt.tight_layout()
    plt.savefig(path, bbox_inches="tight", facecolor="white")
    plt.close()


def fav_players_by_mgr(top_n=3):
    """{mid: [(player, times_drafted), ...]} top players each mgr has drafted."""
    drafts = _load_all_drafts()
    cnt = defaultdict(lambda: defaultdict(int))
    for p in drafts:
        if p["pos"] == "DEF":
            continue
        cnt[p["mid"]][p["player"]] += 1
    out = {}
    for mid, players in cnt.items():
        top = sorted(players.items(), key=lambda kv: -kv[1])
        # Take only those drafted 2+ times
        top = [(n, c) for n, c in top if c >= 2][:top_n]
        out[mid] = top
    return out


def sleeper_championship_blueprint():
    """Returns analysis of each Sleeper-era champion: roster snapshot,
    trade count + timing, top contributors."""
    LEAGUES = {2023: "league_1001657805583077376",
               2024: "league_1085805164784664576",
               2025: "league_1245039290518360064"}
    champs = {}
    mgr_rid = {m["sleeper_roster_id"]: m["id"]
               for m in all_managers() if m.get("sleeper_roster_id")}
    seasons = load_all_seasons()
    sleeper_names = btr._load_sleeper_players()
    for season, lg in LEAGUES.items():
        s = seasons[season]
        rid = s.get("champion_roster_id")
        if not rid:
            continue
        mid = ROSTER_HANDOFFS.get((season, int(rid)), mgr_rid.get(int(rid)))
        # Draft pool
        picks_f = list((ROOT / "data" / "sleeper" / lg).glob("draft_*_picks.json"))[0]
        picks = json.loads(picks_f.read_text())
        their_picks = [p for p in picks if int(p.get("roster_id") or 0) == rid]
        # Sort by round
        their_picks.sort(key=lambda p: p.get("pick_no") or 0)
        # Trades during season (theirs)
        tx_dir = ROOT / "data" / "sleeper" / lg / "transactions"
        trade_history = []
        for wf in sorted(tx_dir.glob("week_*.json")):
            wk = int(wf.stem.split("_")[1])
            for t in json.loads(wf.read_text()):
                if t.get("type") != "trade" or t.get("status") != "complete":
                    continue
                if rid not in (t.get("roster_ids") or []):
                    continue
                # Players they got
                adds = t.get("adds") or {}
                got = [sleeper_names.get(pid, pid)
                       for pid, r in adds.items() if int(r) == rid]
                gave = [sleeper_names.get(pid, pid)
                        for pid, r in adds.items() if int(r) != rid]
                trade_history.append((wk, got, gave,
                                      t.get("draft_picks") or []))
        # Top contributors (top season points among players they finished season with)
        # Use player_total_points from season + last roster snapshot
        # Approximate: use draft picks + adds during season minus drops
        # Simpler: top 10 player point totals from their drafted picks
        drafted_pts = []
        for p in their_picks:
            pid = p.get("player_id")
            pts = s["player_total_points"].get(pid, 0)
            nm = sleeper_names.get(pid, "?")
            pos = (p.get("metadata") or {}).get("position", "?")
            rnd = p.get("round")
            drafted_pts.append((nm, pos, rnd, pts))
        drafted_pts.sort(key=lambda x: -x[3])
        champs[season] = {
            "mid": mid, "name": _mgr_name(mid),
            "picks": their_picks,
            "trades": trade_history,
            "top_contributors": drafted_pts[:6],
        }
    return champs


def chart_sleeper_winpct_trend(path):
    """Per-season win pct per current manager."""
    mpl_style()
    rid_to_mid = {m["sleeper_roster_id"]: m["id"]
                  for m in all_managers() if m.get("sleeper_roster_id")}
    series = defaultdict(dict)
    for season, s in load_all_seasons().items():
        for rid, r in s["rosters"].items():
            mid = ROSTER_HANDOFFS.get((season, int(rid)), rid_to_mid.get(int(rid)))
            if not mid:
                continue
            g = r["wins"] + r["losses"]
            if g:
                series[mid][season] = r["wins"] / g
    # Plot
    seasons = sorted(set().union(*[set(s.keys()) for s in series.values()]))
    fig, ax = plt.subplots(figsize=(9, 5), dpi=140)
    items = sorted(series.items(), key=lambda kv: -np.mean(list(kv[1].values())))
    for mid, ser in items:
        ys = [ser.get(s, np.nan) for s in seasons]
        ax.plot(seasons, ys, marker="o", linewidth=2.4, markersize=8,
                color=mgr_color(mid), label=_mgr_name(mid),
                markeredgecolor="white", markeredgewidth=1.4)
    ax.set_xticks(seasons)
    ax.axhline(0.5, color=PALETTE["gray"], linestyle="--", alpha=0.5)
    ax.set_ylim(0, 1)
    ax.set_ylabel("Win %", fontweight="bold")
    ax.set_title("Sleeper-Era Win% by Season",
                 loc="left", pad=14, fontsize=14)
    ax.legend(loc="center left", bbox_to_anchor=(1.0, 0.5), fontsize=8,
              frameon=False, ncol=1)
    ax.grid(linestyle="--", alpha=0.4)
    ax.set_axisbelow(True)
    plt.tight_layout()
    plt.savefig(path, bbox_inches="tight", facecolor="white")
    plt.close()


def build_html():
    # All-time
    stats = compute_career_stats()
    vbd, vbd_n = compute_trade_vbd()
    draft = compute_draft_stats()
    cards = build_madden_cards(stats, vbd, vbd_n, draft)

    # Sleeper era only (2023-2025)
    sl = lambda y: 2023 <= y <= 2025
    stats_s = compute_career_stats(year_filter=sl)
    vbd_s, vbd_ns = compute_trade_vbd(year_filter=sl)
    draft_s = compute_draft_stats(year_filter=sl)
    cards_s = build_madden_cards_sleeper(stats_s, vbd_s, vbd_ns, draft_s)

    today = date.today().strftime("%B %Y")

    # Generate charts
    print("rendering charts…")
    chart_paths = {
        "ovr_all": CHART_DIR / "ovr_all.png",
        "radar_top": CHART_DIR / "radar_top.png",
        "scatter": CHART_DIR / "scatter.png",
        "vbd": CHART_DIR / "vbd.png",
        "drafters": CHART_DIR / "drafters.png",
        "champs": CHART_DIR / "champs.png",
        "trade_heatmap": CHART_DIR / "trade_heatmap.png",
        "trade_network": CHART_DIR / "trade_network.png",
        "tenure": CHART_DIR / "tenure.png",
        "finish_heatmap": CHART_DIR / "finish_heatmap.png",
        "schedule_luck": CHART_DIR / "schedule_luck.png",
        "position_drafted": CHART_DIR / "position_drafted.png",
        "h2h_matrix": CHART_DIR / "h2h_matrix.png",
        "recent_vs_lifetime": CHART_DIR / "recent_vs_lifetime.png",
        "best_worst_seasons": CHART_DIR / "best_worst_seasons.png",
        "ovr_sleeper": CHART_DIR / "ovr_sleeper.png",
        "radar_sleeper": CHART_DIR / "radar_sleeper.png",
        "sleeper_trend": CHART_DIR / "sleeper_trend.png",
    }
    chart_ovr_ranking(cards, chart_paths["ovr_all"], "All-Time OVR Rankings")
    chart_radar_grid(cards, chart_paths["radar_top"], "All-Time Top 6 — Attribute Profiles")
    chart_scatter_winpct_ppg(cards, chart_paths["scatter"])
    chart_trade_vbd(cards, chart_paths["vbd"])
    chart_drafters(cards, chart_paths["drafters"])
    chart_trade_heatmap(chart_paths["trade_heatmap"], cards)
    chart_trade_network(chart_paths["trade_network"], cards)
    chart_tenure_timeline(chart_paths["tenure"], cards)
    chart_finish_heatmap(chart_paths["finish_heatmap"], cards)
    chart_schedule_luck(chart_paths["schedule_luck"], cards)
    chart_position_drafted(chart_paths["position_drafted"], cards)
    chart_h2h_matrix(chart_paths["h2h_matrix"], cards)
    chart_recent_vs_lifetime(chart_paths["recent_vs_lifetime"], cards, cards_s)
    chart_best_worst_seasons(chart_paths["best_worst_seasons"])
    fav_players = fav_players_by_mgr(top_n=4)
    blueprint = sleeper_championship_blueprint()
    chart_ovr_ranking(cards_s, chart_paths["ovr_sleeper"], "Sleeper Era OVR Rankings")
    chart_radar_grid(cards_s, chart_paths["radar_sleeper"],
                     "Sleeper Era Top 6 — Attribute Profiles")
    chart_sleeper_winpct_trend(chart_paths["sleeper_trend"])

    # Page-specific rules only — palette/base components come from
    # report_base_css() (design/ml.css) + design.tokens.PALETTE.
    from string import Template
    css = Template("""
    body { max-width: 780px; margin: 18px auto; padding: 0 22px;
           line-height: 1.5; font-size: 10.5pt;
           background: var(--ml-bg); }
    h1 { font-size: 23pt; letter-spacing: 1px; margin: 0;
         line-height: 1.1; }
    .bn-mast .bn-sub { font-size: 10.5pt; }
    h2 { font-size: 22pt; letter-spacing: 1px; color: $navy; margin: 16px 0 2px;
         padding-bottom: 3px; border-bottom: 3px solid $gold;
         break-after: avoid-page; page-break-after: avoid; }
    h3 { font-family: var(--ml-font-body); font-size: 11pt; color: $slate;
         margin: 10px 0 4px;
         font-weight: 700; text-transform: uppercase; letter-spacing: 0.5px; }
    .subtitle { color: var(--ml-muted); margin: 0 0 10px; font-size: 10pt; }
    .chart { width: 100%; max-height: 4.2in; object-fit: contain;
             margin: 2px 0 4px; display: block; }
    .chart.tall { max-height: 6in; }
    .section-intro { margin: 2px 0 6px; }
    .cards-grid { display: grid; grid-template-columns: 1fr 1fr;
                  gap: 10px; margin: 10px 0; }
    .card { border: 1px solid var(--ml-border); border-radius: 12px;
            overflow: hidden; page-break-inside: avoid;
            box-shadow: 0 2px 6px rgba(0,0,0,0.06); }
    .card-head { color: white; padding: 12px 14px; display: flex;
                 align-items: center; gap: 12px; position: relative;
                 overflow: hidden; }
    .ovr { font-family: var(--ml-font-display); font-size: 36pt;
           font-weight: bold; min-width: 50px; text-align: center;
           line-height: 1; text-shadow: 0 2px 4px rgba(0,0,0,0.25); }
    .avatar { width: 46px; height: 46px; border-radius: 50%;
              object-fit: cover; border: 2.5px solid rgba(255,255,255,0.85);
              box-shadow: 0 2px 6px rgba(0,0,0,0.2); }
    .avatar-placeholder { background: rgba(255,255,255,0.25); }
    .player-name { font-size: 14pt; font-weight: 800; line-height: 1.1; }
    .archetype { font-size: 8.5pt; opacity: 0.92; margin-top: 3px;
                 font-weight: 500; }
    .tenure-tag { font-size: 7.5pt; opacity: 0.8; margin-top: 4px;
                  font-weight: 500; letter-spacing: 0.4px;
                  text-transform: uppercase; }
    .card-body { padding: 8px 12px 10px; }
    .attr-table { width: 100%; font-size: 8.5pt; }
    .attr-table td { padding: 2px 4px; }
    .attr { font-weight: 700; color: $slate; width: 38px;
            font-size: 8pt; letter-spacing: 0.4px; }
    .bar { width: 100%; }
    .bar-fill { height: 8px; border-radius: 4px; background: var(--ml-muted);
                min-width: 4px; }
    .val { width: 24px; text-align: right; font-weight: 800;
           color: var(--ml-text); }
    .raw { color: var(--ml-muted); font-size: 8pt; text-align: right;
           min-width: 90px; }
    .badge-fmr { font-size: 7pt; background: rgba(0,0,0,0.3); color: white;
                 padding: 1px 5px; border-radius: 4px;
                 vertical-align: middle; font-weight: 700; }
    table { width: 100%; border-collapse: collapse; margin: 4px 0 12px;
            font-size: 9.5pt; }
    th { background: $navy; color: white; padding: 5px 8px;
         text-align: left; font-weight: 700; }
    td { padding: 4px 8px; border-bottom: 1px solid var(--ml-row); }
    tr:nth-child(even) td { background: var(--ml-panel2); }
    p.ml-note { font-size: 9pt; margin: 4px 0 14px; line-height: 1.5; }
    .stat-cards { display: grid; grid-template-columns: repeat(4, 1fr);
                  gap: 8px; margin: 8px 0 14px; }
    .stat-card { background: $cream; border-radius: 10px; padding: 10px 12px;
                 text-align: center; border: 1px solid var(--ml-border); }
    .stat-card .num { font-family: var(--ml-font-display);
                       font-size: 22pt; color: $navy; line-height: 1; }
    .stat-card .lbl { font-size: 8pt; color: var(--ml-muted); margin-top: 4px;
                      text-transform: uppercase; letter-spacing: 0.5px;
                      font-weight: 600; }
    .section-intro { color: $slate; font-size: 10pt; margin: 2px 0 6px;
                     break-after: avoid-page; page-break-after: avoid; }
    .callout { background: var(--ml-banner-warn-bg);
               border-left: 4px solid $gold;
               padding: 8px 12px; font-size: 9.5pt; margin: 4px 0 14px;
               color: var(--ml-text); border-radius: 0 6px 6px 0; }
    .callout strong { color: $navy; }
    .personalities { display: grid; grid-template-columns: 1fr 1fr;
                     gap: 8px; margin: 6px 0; }
    .persona { border: 1px solid var(--ml-border); border-left: 5px solid;
               border-radius: 6px; padding: 8px 12px;
               page-break-inside: avoid; }
    .persona-name { font-family: var(--ml-font-display);
                    letter-spacing: 0.8px; font-size: 15pt;
                    margin: 0 0 2px; }
    .persona-label { font-weight: 700; color: $navy;
                     font-size: 9pt; text-transform: uppercase;
                     letter-spacing: 0.6px; margin-bottom: 4px; }
    .persona-body { font-size: 9.5pt; color: $slate; line-height: 1.5; }
    .bp-card { margin: 6px 0; padding: 8px 12px 4px;
               background: var(--ml-panel2); border-radius: 6px; }
    .bp-head { font-family: var(--ml-font-display); letter-spacing: 1px;
               font-size: 16pt; margin-bottom: 4px; }
    .bp-year { color: var(--ml-muted); margin-right: 8px; }
    .bp-champ { font-weight: 700; }
    .bp-section { font-size: 9.5pt; margin: 4px 0; }
    .bp-section ul { margin: 2px 0 4px 18px; padding: 0; }
    .bp-section li { margin: 1px 0; }
    @page { size: letter; margin: 0.4in; }
    """).substitute(
        navy=PALETTE["navy"], teal=PALETTE["teal"], gold=PALETTE["gold"],
        slate=PALETTE["slate"], cream=PALETTE["cream"]) + banknote_css()

    n_yrs = max(c["years"] for c in cards)
    n_champs = sum(c["rings"] for c in cards)
    n_trades = sum(c["trade_n"] for c in cards) // 2
    top_ovr = max(c["ovr"] for c in cards)

    h = ['<!DOCTYPE html><html data-theme="light"><head><meta charset="utf-8">',
         f'<style>{report_base_css()}{css}</style></head><body>']

    # Masthead (engraved-banknote chrome)
    h.append(banknote_masthead(
        'MONEYLEAGUE POWER RANKINGS',
        f'{today} · 15-year retrospective · Madden-style attribute '
        'scoring · charts + cards'))

    # Stat strip
    h.append('<div class="stat-cards">'
             f'<div class="stat-card"><div class="num">{n_yrs}</div>'
             '<div class="lbl">Yrs of History</div></div>'
             f'<div class="stat-card"><div class="num">{n_champs}</div>'
             '<div class="lbl">Champions Crowned</div></div>'
             f'<div class="stat-card"><div class="num">{n_trades}</div>'
             '<div class="lbl">Trades Logged</div></div>'
             f'<div class="stat-card"><div class="num">{top_ovr}</div>'
             '<div class="lbl">Top OVR</div></div>'
             '</div>')

    # ===== All-time chart =====
    h.append('<h2>All-Time Power Rankings</h2>')
    h.append('<p class="section-intro">OVR composite (longevity excluded — '
             'called out separately as tenure): '
             '<strong>Rings 33%</strong>, <strong>Win% 22%</strong>, '
             '<strong>Draft 18%</strong>, Trade 14%, PPG 13%. Each '
             'attribute normalized 0-99 within the pool. '
             '<strong>FMR</strong> = former manager.</p>')
    h.append(f'<img class="chart" src="{_data_uri(chart_paths["ovr_all"])}"/>')
    h.append("<div class=\"callout\"><strong>Take:</strong> Dave (FMR) still tops the all-time ladder — he left the league at peak. Among current managers, <strong>Trevor</strong> is the lone Franchise-tier player.</div>")
    h.append(f'<img class="chart tall" src="{_data_uri(chart_paths["radar_top"])}"/>')
    h.append("<div class=\"callout\"><strong>Take:</strong> Compare the polygon shapes — Dave's is the most balanced (high on every axis); Coop is win-and-rings-heavy but lighter on draft + trade.</div>")

    # ===== Madden cards =====
    h.append('<h2>All-Time Player Cards</h2>')
    h.append('<div class="cards-grid">')
    for c in cards:
        h.append(render_card_html(c))
    h.append('</div>')

    # ===== Win% vs PPG scatter =====
    h.append('<h2>Win% vs Scoring</h2>')
    h.append('<p class="section-intro">Where each manager lives on the '
             'win-rate / scoring plane. The top-right is the dream; the '
             'bottom-left is the basement. Bubble size = rings.</p>')
    h.append(f'<img class="chart" src="{_data_uri(chart_paths["scatter"])}"/>')
    h.append("<div class=\"callout\"><strong>Take:</strong> <strong>Brower</strong> lives alone in the top-right — best win% AND PPG in the league, with a tiny 0-ring dot. <strong>Donnie</strong> sits in the bottom-left with a 1-ring bubble: lucky ring on otherwise-bottom-tier production.</div>")

    # ===== Trade fleecer ledger =====
    h.append('<h2>Trade Fleecer Ledger</h2>')
    h.append('<p class="section-intro">Net VBD across every scored trade '
             '(Yahoo 2011-2022 + Sleeper 2023-2024), including picks '
             '(scored as the rookie-year production of the player actually '
             'drafted). Green = won, red = lost.</p>')
    h.append(f'<img class="chart" src="{_data_uri(chart_paths["vbd"])}"/>')
    h.append("<div class=\"callout\"><strong>Take:</strong> <strong>Dave</strong> won the trade ledger by +4718, more than 3× the next closest. <strong>Donnie</strong> lost -3777, the worst pile of bad trades in league history.</div>")

    # ===== Trade heatmap =====
    h.append('<h2>Trade Fleecing Matrix</h2>')
    h.append('<p class="section-intro">Every pairwise relationship in the '
             'league. Read across a row: <em>green cells</em> are managers '
             'this person fleeced, <em>red cells</em> are the ones who '
             'fleeced them. Number = net VBD; small subscript = trade count. '
             'Rows ordered by all-time OVR.</p>')
    h.append(f'<img class="chart tall" src="{_data_uri(chart_paths["trade_heatmap"])}"/>')
    h.append("<div class=\"callout\"><strong>Take:</strong> Look at Dave's row — almost universally green. Look at Donnie's row — almost universally red. The Brian-Eric cell is roughly neutral (~+180 Brian once picks are scored, which surprised everyone).</div>")

    # ===== Trade network =====
    h.append('<h2>Trade Network</h2>')
    h.append('<p class="section-intro">Force-directed graph of the league\'s '
             'trade economy. Bigger node = trades more; edges show pair '
             'frequency (thickness) and imbalance (color depth). Managers '
             'who only trade with a few others get pulled to the periphery.</p>')
    h.append(f'<img class="chart tall" src="{_data_uri(chart_paths["trade_network"])}"/>')
    h.append("<div class=\"callout\"><strong>Take:</strong> Trevor and Brian are central hubs (they trade with everyone). Tim and Ankur sit near the periphery — light traders who prefer the wire.</div>")

    # ===== Best drafters =====
    h.append('<h2>Best Drafters</h2>')
    h.append('<p class="section-intro"><strong>Draft skill</strong> measured '
             'as surplus rookie-year points vs the league average for the '
             'same round and year. Strips out the "high-pick advantage" — a '
             'drafter with a bunch of R1 picks isn\'t penalized for finding '
             'a normal R1 player. Positive = found above-replacement value. '
             'Min 20 career picks.</p>')
    h.append(f'<img class="chart" src="{_data_uri(chart_paths["drafters"])}"/>')
    h.append("<div class=\"callout\"><strong>Take:</strong> <strong>Trevor's +9.0 surplus/pick</strong> is the league-best drafter — even though his raw pts/pick is mid-tier, he beats round expectation more than anyone. Ankur's raw was deceptively high; once normalized for slot, he's actually a bottom-3 drafter.</div>")

    # ===== Tenure timeline =====
    h.append('<h2>Tenure Timeline</h2>')
    h.append('<p class="section-intro">Who was in the league each year, '
             'with championships marked as gold stars. Shows how the '
             'league has evolved (8 → 10 → 12 teams) and who\'s been the '
             'most loyal.</p>')
    h.append(f'<img class="chart tall" src="{_data_uri(chart_paths["tenure"])}"/>')
    h.append("<div class=\"callout\"><strong>Take:</strong> Six managers have played all 15 seasons (Trevor, Coop, Kyle, Eric, Brian, Lem). Only Trevor + Coop have 3 rings; Brian + Lem are the only iron-men with zero.</div>")

    # ===== Finish heatmap =====
    h.append('<h2>Regular-Season Finish, Year by Year</h2>')
    h.append('<p class="section-intro">Each cell is where that manager '
             'finished in the regular-season standings that year (green = '
             'top, red = bottom). Reveals consistency, peak years, droughts.'
             '</p>')
    h.append(f'<img class="chart tall" src="{_data_uri(chart_paths["finish_heatmap"])}"/>')
    h.append("<div class=\"callout\"><strong>Take:</strong> Kyle's row is the most volatile (#1 three times AND #10 four times). Brower's row since 2019 is an unbroken streak of top-3 regular seasons. Donnie's recent years are mostly red.</div>")

    # ===== Schedule luck =====
    h.append('<h2>Schedule Luck</h2>')
    h.append('<p class="section-intro">Average gap between FPTS rank and '
             'Wins rank across every season. <strong>Positive</strong> = '
             'won more games than their scoring deserved (lucky matchups). '
             '<strong>Negative</strong> = scored well but couldn\'t catch '
             'a break.</p>')
    h.append(f'<img class="chart" src="{_data_uri(chart_paths["schedule_luck"])}"/>')
    h.append("<div class=\"callout\"><strong>Take:</strong> <strong>Lem at -0.80</strong> is brutally unlucky — scores enough to win but constantly matched against the week's high score. Brower + Ankur both at +1.00 — their records flatter their actual scoring.</div>")

    # (Championship timeline removed — redundant with tenure timeline stars)

    # ===== Head-to-Head Matrix =====
    h.append('<h2>Head-to-Head Career Matrix</h2>')
    h.append('<p class="section-intro">Every pairwise regular-season '
             'matchup record. Cell = ROW manager\'s career W-L vs the '
             'COLUMN manager. Green = ROW dominant; red = ROW gets beat. '
             'Rows ordered by all-time OVR.</p>')
    h.append(f'<img class="chart tall" src="{_data_uri(chart_paths["h2h_matrix"])}"/>')
    h.append("<div class=\"callout\"><strong>Take:</strong> Dave's row is mostly green (he beat almost everyone he played). Coop owns Lem and Donnie. Donnie's row is mostly red.</div>")

    # ===== Position Drafted Strategy =====
    h.append('<h2>Position Drafted by Round — Draft Strategy</h2>')
    h.append('<p class="section-intro">Stacked position mix across each '
             'manager\'s entire drafting career (rounds 1-10). Reveals '
             'whether they reach for QBs early, hoard RBs, ignore TE, etc.</p>')
    h.append(f'<img class="chart tall" src="{_data_uri(chart_paths["position_drafted"])}"/>')
    h.append("<div class=\"callout\"><strong>Take:</strong> Notice who hoards QBs early (red blocks in early rounds) vs who waits. Most managers go RB/WR heavy in rounds 1-4; the early-QB drafters stand out clearly.</div>")

    # ===== Best & worst single seasons =====
    h.append('<h2>Best & Worst Single Seasons of All Time</h2>')
    h.append('<p class="section-intro">Top 8 and bottom 8 individual '
             'manager-seasons across 15 years of regular-season play '
             '(minimum 8 games).</p>')
    h.append(f'<img class="chart" src="{_data_uri(chart_paths["best_worst_seasons"])}"/>')
    h.append("<div class=\"callout\"><strong>Take:</strong> Brower's recent Sleeper-era seasons dominate the top-8 list — most rings-less elite stretch in league history. Brian + Lem each appear multiple times in the bottom-8.</div>")

    # ===== Favorite players =====
    h.append('<h2>Favorite Players — Drafted Multiple Times</h2>')
    h.append('<p class="section-intro">Players each manager has drafted '
             'in multiple seasons. The repeat targets reveal who manages by '
             'crush versus who casts a wide net.</p>')
    h.append('<table><thead><tr><th>Manager</th><th>Favorite players (× times drafted)</th></tr></thead><tbody>')
    ordered_mgrs = [c["mid"] for c in cards]
    for mid in ordered_mgrs:
        favs = fav_players.get(mid, [])
        if not favs:
            cells = "<em class='ml-note'>no repeat targets</em>"
        else:
            cells = " · ".join(f"<strong>{n}</strong> ×{c}" for n, c in favs)
        h.append(f'<tr><td><strong style="color:{mgr_color(mid)}">'
                 f'{_mgr_name(mid)}</strong></td><td>{cells}</td></tr>')
    h.append('</tbody></table>')

    # ===== Recent vs Lifetime delta =====
    h.append('<h2>Heating Up vs Cooling Off</h2>')
    h.append('<p class="section-intro">Sleeper-era OVR minus all-time OVR. '
             'Positive = they\'re playing better than their career average '
             'suggests. Negative = falling off.</p>')
    h.append(f'<img class="chart" src="{_data_uri(chart_paths["recent_vs_lifetime"])}"/>')
    h.append("<div class=\"callout\"><strong>Take:</strong> <strong>Brower</strong> is heating up the most (Sleeper-era OVR well above his all-time). <strong>Trevor</strong> is the steadiest (small delta). Watch out for the cooling-off trend on the bottom.</div>")

    # ===== Sleeper era split =====
    h.append('<h2>Sleeper Era (2023-2025)</h2>')
    h.append('<p class="section-intro">The last 3 seasons only — recency '
             'view. Weights: Rings 26%, Win% 24%, Draft 23%, Trade 14%, '
             'PPG 13%. All 12 current rosters included regardless of '
             'tenure.</p>')
    h.append(f'<img class="chart" src="{_data_uri(chart_paths["ovr_sleeper"])}"/>')
    h.append(f'<img class="chart" src="{_data_uri(chart_paths["sleeper_trend"])}"/>')
    h.append(f'<img class="chart tall" src="{_data_uri(chart_paths["radar_sleeper"])}"/>')

    h.append('<h2>Sleeper Era Player Cards</h2>')
    h.append('<div class="cards-grid">')
    for c in cards_s:
        h.append(render_card_html(c))
    h.append('</div>')

    # ===== Championship blueprint =====
    h.append('<h2>What a Sleeper-Era Championship Looks Like</h2>')
    h.append('<p class="section-intro">Each Sleeper-era champion\'s '
             'roster blueprint: their top contributing draftees + '
             'in-season trade activity.</p>')
    for season in sorted(blueprint.keys()):
        bp = blueprint[season]
        color = mgr_color(bp["mid"])
        n_tr = len(bp["trades"])
        trade_weeks = sorted({wk for wk, *_ in bp["trades"]})
        avg_wk = f"W{int(np.mean(trade_weeks))}" if trade_weeks else "—"
        h.append(f'<div class="bp-card" style="border-left:6px solid {color}">')
        h.append(f'<div class="bp-head"><span class="bp-year">{season}</span> '
                 f'<span class="bp-champ" style="color:{color}">{bp["name"]}</span></div>')
        # Top contributors
        h.append('<div class="bp-section"><strong>Top draft contributors:</strong><ul>')
        for nm, pos, rnd, pts in bp["top_contributors"]:
            h.append(f'<li><strong>{nm}</strong> ({pos}, R{rnd}) — '
                     f'{pts:.0f} pts</li>')
        h.append('</ul></div>')
        # Trade activity
        if bp["trades"]:
            h.append(f'<div class="bp-section"><strong>{n_tr} in-season trade'
                     f'{"s" if n_tr != 1 else ""}</strong> · avg week: {avg_wk}<ul>')
            for wk, got, gave, picks in bp["trades"]:
                got_s = ", ".join(got[:4]) or "—"
                gave_s = ", ".join(gave[:4]) or "—"
                pk_s = (f" + {len(picks)} pick(s) moved"
                        if picks else "")
                h.append(f'<li>W{wk}: <strong>got</strong> {got_s}; '
                         f'<strong>gave</strong> {gave_s}{pk_s}</li>')
            h.append('</ul></div>')
        else:
            h.append('<div class="bp-section"><em>No in-season trades — '
                     'won via draft + waivers alone.</em></div>')
        h.append('</div>')

    # ===== League Personalities =====
    h.append('<h2>League Personalities</h2>')
    h.append('<p class="section-intro">One sentence per manager — '
             'what the numbers and lore say defines them.</p>')
    h.append('<div class="personalities">')
    # Order: current managers by OVR, then former managers
    ordered = [c["mid"] for c in cards if c.get("is_current", True)] + \
              [c["mid"] for c in cards if not c.get("is_current", True)]
    for mid in ordered:
        if mid not in PERSONALITIES:
            continue
        label, body = PERSONALITIES[mid]
        color = mgr_color(mid)
        h.append(f'<div class="persona" style="border-left-color:{color}">'
                 f'<div class="persona-label" style="color:{color}">{label}</div>'
                 f'<div class="persona-name">{_mgr_name(mid)}</div>'
                 f'<div class="persona-body">{body}</div></div>')
    h.append('</div>')

    # ===== Methodology =====
    h.append('<h2>Methodology</h2>')
    h.append('<p class="ml-note">Win/loss + PPG: regular-season games only '
             '(weeks 1-13 for 8/10-team years, 1-14 for 12-team years). '
             'Yahoo data via scraped matchups; Sleeper via league API. '
             'Rings: KNOWN_CHAMPIONS dict (Yahoo era) + winners_bracket.json '
             '(Sleeper era). Trade VBD: full-season nflverse fantasy points '
             '(0.5 PPR for 2019+, 0 PPR before) for players + rookie-year '
             'points of the player actually drafted at each traded pick '
             '(snake-order math against each year\'s actual draft data). '
             'Draft skill: total rookie-year points / total picks made. '
             '2025 Sleeper trades excluded — no nflverse 2025 totals yet.</p>')

    h.append(banknote_fineprint(f'Generated {today}'))
    h.append('</body></html>')
    return "\n".join(h)


def _find_chromium() -> str | None:
    """Locate a Chromium binary across environments.

    Order: CHROMIUM_EXEC env var -> any /opt/pw-browsers install (remote
    sandbox, version-agnostic) -> None, which lets Playwright resolve its
    own managed browser (CI after `playwright install chromium`).
    """
    import glob
    import os
    env = os.environ.get("CHROMIUM_EXEC")
    if env and Path(env).exists():
        return env
    hits = sorted(glob.glob("/opt/pw-browsers/chromium-*/chrome-linux*/chrome"))
    if hits:
        os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", "/opt/pw-browsers")
        return hits[-1]
    return None


CHROMIUM_EXEC = _find_chromium()


def _render_pdf_playwright(html: str, out_path: Path):
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch(executable_path=CHROMIUM_EXEC,
                              args=["--no-sandbox", "--disable-dev-shm-usage"])
        ctx = b.new_context(viewport={"width": 820, "height": 1100})
        page = ctx.new_page()
        page.set_content(html, wait_until="networkidle")
        # Wait for fonts + images
        page.evaluate("document.fonts.ready")
        page.pdf(
            path=str(out_path),
            format="Letter",
            margin={"top": "0.4in", "bottom": "0.4in",
                    "left": "0.4in", "right": "0.4in"},
            print_background=True,
            prefer_css_page_size=False,
        )
        b.close()


def main():
    html = build_html()
    MD_OUT.write_text(html)
    _render_pdf_playwright(html, PDF_OUT)
    print(f"Wrote {PDF_OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
