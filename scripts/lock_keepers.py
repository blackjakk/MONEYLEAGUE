#!/usr/bin/env python3
"""Validate + normalize the locked 2026 keeper declarations.

Usage:
    python3 scripts/lock_keepers.py data/keepers_2026_actual.json [--dry-run] [--out PATH]

Input: a JSON list (see data/keepers_2026_actual.TEMPLATE.json). String
elements (the template's "_instructions") are ignored. Each dict entry
needs only player_name + roster_id + prior_round; everything else is
derived here by matching against data/keepers_2026.json (the predicted
file) and data/sleeper/players_nfl.json (the player catalog).

League rules enforced (all user-confirmed -- do not soften):
  * cost escalates 2 rounds/yr: forfeit_round = prior_round - 2
  * MAX 3 consecutive years kept; years_kept counts years BEFORE 2026,
    so years_kept >= 3 means INELIGIBLE (e.g. Jordan Love)
  * R1/R2 DRAFTEES ineligible: prior_round must be >= 3. The ESCALATED
    forfeit may legally climb into R2/R1 (commish ruling, Aug 2026:
    Bowers kept at R4 last year keeps again at R2 -- "ok to keep if
    he drafted in 4th"); the old reading banned R1/R2 forfeits
    outright, which was too strict
  * the keeper seat must be a round the team OWNS in the 2026 schedule
    (trades applied, from docs/draft_helper/data.json); if the exact
    round is consumed by another of the team's keepers or not owned,
    the BUMP-UP house rule seats it at the next EARLIER owned free
    round, down to R1; a keeper is only impossible if no such round
    is free
  * max 4 keepers per team

On OK (and not --dry-run) writes the normalized, schema-complete file
(status="carryover", same schema as data/keepers_2026.json) to
data/keepers_2026_actual.json, which `refresh_all.sh derive` copies
over data/keepers_2026.json so the whole pipeline regrades from it.

Exit code 0 only when validation passes. Stdlib only.
"""
from __future__ import annotations

import argparse
import difflib
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CATALOG_PATH = ROOT / "data" / "sleeper" / "players_nfl.json"
PREDICTED_PATH = ROOT / "data" / "keepers_2026.json"
HELPER_DATA_PATH = ROOT / "docs" / "draft_helper" / "data.json"
DEFAULT_OUT = ROOT / "data" / "keepers_2026_actual.json"

ROUND_PENALTY = 2      # cost escalates 2 rounds/yr
MAX_YEARS = 3          # 3-year cap; years_kept >= 3 -> ineligible in 2026
MAX_KEEPERS = 4        # per team
MIN_PRIOR_ROUND = 3    # R1/R2 draftees ineligible to be kept
MIN_FORFEIT_ROUND = 1  # escalated forfeits may reach R2/R1 (Bowers ruling)
N_ROUNDS = 17
ELIGIBLE_POS = {"QB", "RB", "WR", "TE"}  # K/DEF are not keeper-eligible

_SUFFIXES = {"jr", "sr", "ii", "iii", "iv", "v"}


def norm_name(name: str) -> str:
    """lowercase, strip punctuation and generational suffixes."""
    tokens = re.sub(r"[^a-z0-9 ]", "", (name or "").lower().replace(".", " ")).split()
    while len(tokens) > 2 and tokens[-1] in _SUFFIXES:
        tokens.pop()
    return " ".join(tokens)


def load_catalog():
    """name index over the Sleeper player catalog.

    Returns (by_norm_name -> [ (pid, meta) ], display_names_for_suggestions).
    """
    catalog = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    by_name: dict[str, list[tuple[str, dict]]] = defaultdict(list)
    suggest_pool: list[str] = []
    for pid, meta in catalog.items():
        full = meta.get("full_name") or (
            f"{(meta.get('first_name') or '').strip()} "
            f"{(meta.get('last_name') or '').strip()}"
        ).strip()
        if not full:
            continue
        by_name[norm_name(full)].append((pid, {**meta, "full_name": full}))
        if meta.get("position") in ELIGIBLE_POS:
            suggest_pool.append(full)
    return by_name, sorted(set(suggest_pool))


def load_predicted():
    """(roster_id, norm_name) -> predicted-file record (any status)."""
    recs = json.loads(PREDICTED_PATH.read_text(encoding="utf-8"))
    idx: dict[tuple[int, str], dict] = {}
    for r in recs:
        if isinstance(r, dict) and "player_name" in r:
            idx[(int(r["roster_id"]), norm_name(r["player_name"]))] = r
    return idx


def load_league():
    """Ownership + display names from docs/draft_helper/data.json.

    NOTE on the two team_idx conventions: the keepers files use
    team_idx = roster_id - 1; the helper's managers/schedule use a
    SLOT-ORDER team_idx. We bridge via the managers list
    (roster_id -> schedule team_idx) and only ever emit the
    keeper-file convention.
    Returns (owned[roster_id][round] = pick count, manager_id[roster_id]).
    """
    d = json.loads(HELPER_DATA_PATH.read_text(encoding="utf-8"))
    rid_to_sched_ti: dict[int, int] = {}
    manager_id: dict[int, str] = {}
    for m in d["managers"]:
        rid = int(m["roster_id"])
        rid_to_sched_ti[rid] = int(m["team_idx"])
        manager_id[rid] = m.get("name") or m.get("id") or f"roster_{rid}"
    sched_ti_to_rid = {ti: rid for rid, ti in rid_to_sched_ti.items()}
    owned: dict[int, dict[int, int]] = defaultdict(lambda: defaultdict(int))
    for e in d["schedule"]:
        rid = sched_ti_to_rid.get(int(e["team_idx"]))
        if rid is not None:
            owned[rid][int(e["round"])] += 1
    return owned, manager_id


def resolve_player(name, want_pos, by_name, suggest_pool, errors):
    """Resolve a declared name against the catalog. Returns meta or None."""
    key = norm_name(name)
    cands = by_name.get(key, [])
    if not cands:
        close = difflib.get_close_matches(name, suggest_pool, n=3, cutoff=0.4)
        hint = "; ".join(close) if close else "(no close matches)"
        errors.append(f"'{name}': not found in players_nfl.json. "
                      f"Closest names: {hint}")
        return None
    eligible = [c for c in cands if c[1].get("position") in ELIGIBLE_POS]
    if not eligible:
        positions = sorted({c[1].get("position") or "?" for c in cands})
        errors.append(f"'{name}': matched only position(s) "
                      f"{'/'.join(positions)} -- not keeper-eligible "
                      f"(QB/RB/WR/TE only)")
        return None
    if len(eligible) > 1 and want_pos:
        eligible = [c for c in eligible
                    if c[1].get("position") == want_pos] or eligible
    if len(eligible) > 1:
        active = [c for c in eligible if c[1].get("active")]
        eligible = active or eligible
    if len(eligible) > 1:
        opts = ", ".join(f"{m['full_name']} ({m.get('position')}, "
                         f"{m.get('team') or 'FA'})" for _, m in eligible)
        errors.append(f"'{name}': ambiguous -- {opts}. Add a \"position\" "
                      f"field to the entry to disambiguate.")
        return None
    return eligible[0][1]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("path", help="filled keeper declarations JSON "
                                 "(copy of data/keepers_2026_actual.TEMPLATE.json)")
    ap.add_argument("--dry-run", action="store_true",
                    help="validate only; never write the output file")
    ap.add_argument("--out", default=str(DEFAULT_OUT),
                    help=f"output path on OK (default: {DEFAULT_OUT})")
    args = ap.parse_args()

    in_path = Path(args.path)
    if not in_path.exists():
        print(f"FAIL: input file not found: {in_path}")
        return 1
    try:
        raw = json.loads(in_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        print(f"FAIL: {in_path} is not valid JSON: {e}")
        return 1
    if not isinstance(raw, list):
        print("FAIL: input must be a JSON list (see the TEMPLATE file)")
        return 1

    entries = [e for e in raw if isinstance(e, dict)]  # strings = instructions
    if not entries:
        print("FAIL: no keeper entries found (dict elements) in the input")
        return 1

    by_name, suggest_pool = load_catalog()
    predicted = load_predicted()
    owned, manager_id = load_league()
    # live vbd/adp for keepers the predictor never modeled (their
    # analytics fields would otherwise be null and crash consumers)
    helper = json.loads(HELPER_DATA_PATH.read_text(encoding="utf-8"))
    live_stats = {norm_name(p["name"]): (p.get("vbd"), p.get("adp"))
                  for p in helper.get("players", [])}
    pv_path = ROOT / "data" / "pick_value.json"
    round_baseline = {}
    if pv_path.exists():
        round_baseline = {int(r): v.get("median_vbd") or v.get("mean_vbd")
                          for r, v in json.loads(
                              pv_path.read_text())["by_round"].items()}

    errors: list[str] = []
    warnings: list[str] = []
    normalized: list[dict] = []
    seen_players: dict[str, int] = {}

    for i, e in enumerate(entries, 1):
        tag = f"entry {i} ({e.get('player_name', '?')})"
        # ---- required fields -------------------------------------------
        missing = [f for f in ("player_name", "roster_id", "prior_round")
                   if e.get(f) in (None, "")]
        if missing:
            errors.append(f"{tag}: missing required field(s): "
                          f"{', '.join(missing)}")
            continue
        name = str(e["player_name"])
        try:
            rid = int(e["roster_id"])
            prior_round = int(e["prior_round"])
        except (TypeError, ValueError):
            errors.append(f"{tag}: roster_id and prior_round must be integers")
            continue
        if rid not in manager_id:
            errors.append(f"{tag}: roster_id {rid} not in the league "
                          f"(valid: {sorted(manager_id)})")
            continue
        if not 1 <= prior_round <= N_ROUNDS:
            errors.append(f"{tag}: prior_round {prior_round} out of range "
                          f"1-{N_ROUNDS} (waiver pickups = 17)")
            continue

        # ---- resolve against catalog + predicted file ------------------
        pred = predicted.get((rid, norm_name(name)))
        want_pos = e.get("position") or (pred or {}).get("position")
        meta = resolve_player(name, want_pos, by_name, suggest_pool, errors)
        if meta is None:
            continue
        canonical = (pred or {}).get("player_name") or meta["full_name"]
        position = meta.get("position")

        dup_key = norm_name(canonical)
        if dup_key in seen_players:
            errors.append(f"{tag}: duplicate -- {canonical} already declared "
                          f"for roster {seen_players[dup_key]}")
            continue
        seen_players[dup_key] = rid

        # ---- years_kept + 3-year cap -----------------------------------
        if e.get("years_kept") is not None:
            years_kept = int(e["years_kept"])
            if pred and int(pred.get("years_kept", 0)) != years_kept:
                warnings.append(f"{canonical}: years_kept override {years_kept} "
                                f"(predicted file says {pred['years_kept']})")
        else:
            years_kept = int(pred["years_kept"]) if pred else 0
            if not pred:
                warnings.append(f"{canonical}: not in data/keepers_2026.json "
                                f"for roster {rid} -- assuming years_kept=0 "
                                f"(add \"years_kept\" to override); vbd/adp "
                                f"fields will be null")
        if years_kept >= MAX_YEARS:
            errors.append(f"{canonical} (roster {rid}, {manager_id[rid]}): "
                          f"INELIGIBLE -- years_kept={years_kept} hits the "
                          f"{MAX_YEARS}-year cap (counts years before 2026)")
            continue

        # ---- forfeit round + R1/R2-draftee floor -----------------------
        forfeit_round = prior_round - ROUND_PENALTY
        if e.get("forfeit_round") is not None and \
                int(e["forfeit_round"]) != forfeit_round:
            errors.append(f"{canonical}: forfeit_round {e['forfeit_round']} "
                          f"contradicts prior_round {prior_round} - "
                          f"{ROUND_PENALTY} = {forfeit_round}")
            continue
        if prior_round < MIN_PRIOR_ROUND:
            errors.append(f"{canonical} (roster {rid}, {manager_id[rid]}): "
                          f"INELIGIBLE -- drafted/kept at R{prior_round}; "
                          f"R1/R2 draftees cannot be kept")
            continue
        if forfeit_round < MIN_FORFEIT_ROUND:
            errors.append(f"{canonical} (roster {rid}, {manager_id[rid]}): "
                          f"IMPOSSIBLE -- forfeit round R{forfeit_round} "
                          f"below R{MIN_FORFEIT_ROUND}")
            continue
        if pred and int(pred.get("prior_round", prior_round)) != prior_round:
            warnings.append(f"{canonical}: prior_round {prior_round} differs "
                            f"from predicted file ({pred['prior_round']}) -- "
                            f"using YOUR value")

        if e.get("is_waiver") is not None:
            is_waiver = bool(e["is_waiver"])
        else:
            is_waiver = bool(pred["is_waiver"]) if pred else False

        raw_vbd = (pred or {}).get("raw_vbd")
        adp = (pred or {}).get("adp")
        baseline = (pred or {}).get("pick_value_baseline")
        net_vbd = (pred or {}).get("net_vbd")
        if raw_vbd is None or adp is None:
            lv, la = live_stats.get(norm_name(canonical), (None, None))
            raw_vbd = raw_vbd if raw_vbd is not None else (lv or 0.0)
            adp = adp if adp is not None else la
        if baseline is None:
            baseline = round_baseline.get(forfeit_round, 0.0) or 0.0
        if net_vbd is None:
            net_vbd = round((raw_vbd or 0.0) - baseline, 1)

        normalized.append({
            "team_idx": rid - 1,  # keeper-file convention (roster_id - 1)
            "roster_id": rid,
            "player_name": canonical,
            "position": position,
            "prior_round": prior_round,
            "forfeit_round": forfeit_round,
            "effective_forfeit_round": forfeit_round,  # seating may bump
            "years_kept": years_kept,
            "status": "carryover",
            "net_vbd": net_vbd,
            "raw_vbd": raw_vbd,
            "pick_value_baseline": baseline,
            "adp": adp,
            "is_waiver": is_waiver,
        })

    # ---- per-team caps + ownership / bump-up seating -------------------
    by_team: dict[int, list[dict]] = defaultdict(list)
    for r in normalized:
        by_team[r["roster_id"]].append(r)

    bumps: dict[str, int] = {}  # player_name -> natural round it bumped from
    for rid, recs in sorted(by_team.items()):
        if len(recs) > MAX_KEEPERS:
            errors.append(f"roster {rid} ({manager_id[rid]}): {len(recs)} "
                          f"keepers declared -- max is {MAX_KEEPERS}")
        team_owned = owned.get(rid, {})
        used: dict[int, int] = defaultdict(int)
        # Earlier (costlier) natural seats claim first so a later keeper
        # bumping up never steals an earlier keeper's natural round;
        # ADP breaks ties (better player keeps the natural seat).
        for r in sorted(recs, key=lambda r: (r["forfeit_round"],
                                             r["adp"] if r["adp"] is not None
                                             else 999.0,
                                             r["player_name"])):
            natural = r["forfeit_round"]
            seat = None
            for rnd in range(natural, MIN_FORFEIT_ROUND - 1, -1):
                if used[rnd] < team_owned.get(rnd, 0):
                    seat = rnd
                    break
            if seat is None:
                owned_rounds = sorted(rnd for rnd, n in team_owned.items()
                                      if n > 0 and rnd <= natural)
                errors.append(
                    f"{r['player_name']} (roster {rid}, {manager_id[rid]}): "
                    f"IMPOSSIBLE SEAT -- no owned free round at R{natural} or "
                    f"earlier (floor R{MIN_FORFEIT_ROUND}); team owns "
                    f"{['R%d' % x for x in owned_rounds] or 'nothing'} there, "
                    f"all consumed by other keepers")
                r["_no_seat"] = True
                continue
            used[seat] += 1
            r["effective_forfeit_round"] = seat
            if seat != natural:
                bumps[r["player_name"]] = natural
                reason = ("not owned (traded away)"
                          if team_owned.get(natural, 0) == 0
                          else "taken by another keeper")
                warnings.append(f"{r['player_name']} (roster {rid}): BUMP-UP "
                                f"-- R{natural} {reason}; seated at R{seat} "
                                f"(bump tax: earlier pick consumed)")

    # ---- report ---------------------------------------------------------
    print("=" * 74)
    print("KEEPER LOCK -- 2026 declared keepers")
    print("=" * 74)
    print(f"{'roster':>6}  {'manager':<18} {'n':>2}  keepers (seat, ^ = bumped)")
    print("-" * 74)
    for rid in sorted(manager_id):
        recs = sorted(by_team.get(rid, []),
                      key=lambda r: r["effective_forfeit_round"])
        cells = []
        for r in recs:
            if r.get("_no_seat"):
                cells.append(f"{r['player_name']} (NO SEAT)")
                continue
            mark = (f"^R{bumps[r['player_name']]}"
                    if r["player_name"] in bumps else "")
            cells.append(f"{r['player_name']} "
                         f"(R{r['effective_forfeit_round']}{mark})")
        n_bumped = sum(1 for r in recs if r["player_name"] in bumps)
        line = ", ".join(cells) if cells else "-- none declared --"
        print(f"{rid:>6}  {manager_id[rid]:<18} {len(recs):>2}  {line}")
        if n_bumped:
            print(f"{'':>29}  ({n_bumped} bump-up{'s' if n_bumped > 1 else ''} applied)")
    print("-" * 74)
    print(f"total: {len(normalized)} keepers across "
          f"{len(by_team)} teams, {len(bumps)} bump(s)")

    if warnings:
        print(f"\nWARNINGS ({len(warnings)}):")
        for w in warnings:
            print(f"  ! {w}")

    if errors:
        print(f"\nFAIL -- {len(errors)} violation(s):")
        for e in errors:
            print(f"  x {e}")
        print("\nFix the input file and re-run. Nothing was written.")
        return 1

    print("\nOK -- all league rules satisfied.")
    if args.dry_run:
        print("(--dry-run: nothing written)")
        return 0

    out_path = Path(args.out)
    clean = [{k: v for k, v in r.items() if not k.startswith("_")}
             for r in normalized]
    out_path.write_text(json.dumps(clean, indent=2) + "\n",
                        encoding="utf-8")
    print(f"Wrote {out_path} ({len(normalized)} entries, status=carryover).")
    print("\nNEXT -- regrade the whole pipeline from the locked keepers:")
    print("  scripts/refresh_all.sh derive sim reports verify")
    print("(derive copies keepers_2026_actual.json over keepers_2026.json;")
    print(" the Stack Screen title watch + war chest, the taxed keeper")
    print(" optimizer (scripts/optimize_my_keepers.py), and the Research")
    print(" Desk all regrade from it automatically.)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
