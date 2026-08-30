"""Invariant checks on pipeline outputs. Run after any rebuild.

Every check here is a regression we actually shipped once and caught by eye:
  - teams drafting only 1-2 QBs in a superflex league
  - traded picks not applied (Kyle missing his 3 R1s)
  - 3-TE / 6-K rosters from a bad position cap
  - MC cards collapsing multi-pick rounds (14 rows instead of 17)
  - keepers missing from the draft helper at load
  - elite players falling implausibly far on the display board

Exit code 0 = all pass. Non-zero = at least one failed (prints which).
"""
from __future__ import annotations

import json
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FAILURES: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    mark = "ok " if ok else "FAIL"
    print(f"  [{mark}] {name}" + (f" — {detail}" if detail and not ok else ""))
    if not ok:
        FAILURES.append(f"{name}: {detail}")


def main() -> None:
    picks = json.loads((ROOT / "data" / "mock_draft_picks.json").read_text())
    mc = json.loads((ROOT / "data" / "mc_summary_all.json").read_text())
    keepers = json.loads((ROOT / "data" / "keepers_2026.json").read_text())
    helper = json.loads((ROOT / "docs" / "draft_helper" / "data.json").read_text())

    print("Mock draft board:")
    by_team_count = defaultdict(int)
    by_team_pos = defaultdict(lambda: defaultdict(int))
    for p in picks:
        by_team_count[p["team_idx"]] += 1
        by_team_pos[p["team_idx"]][p["position"]] += 1

    check("204 total picks", len(picks) == 204, f"got {len(picks)}")
    check("every team has exactly 17 picks",
          all(v == 17 for v in by_team_count.values()),
          f"counts={dict(by_team_count)}")
    qbs = [by_team_pos[ti].get("QB", 0) for ti in range(12)]
    check("every team drafts 2-3 QBs (superflex)",
          all(2 <= q <= 3 for q in qbs), f"QB counts={qbs}")
    tes = [by_team_pos[ti].get("TE", 0) for ti in range(12)]
    check("no team has more than 2 TEs", all(t <= 2 for t in tes),
          f"TE counts={tes}")
    ks = [by_team_pos[ti].get("K", 0) + by_team_pos[ti].get("DEF", 0)
          for ti in range(12)]
    check("K+DEF <= 2 per team", all(k <= 2 for k in ks), f"K+DEF={ks}")

    # Traded picks: slot 3 (Kyle, team_idx=2) owns 3 R1s in 2026.
    kyle_r1 = sum(1 for p in picks if p["round"] == 1 and p["team_idx"] == 2)
    check("Kyle has 3 first-round picks (trades applied)", kyle_r1 == 3,
          f"got {kyle_r1}")
    trevor_r12 = sum(1 for p in picks
                     if p["round"] in (1, 2) and p["team_idx"] == 11)
    check("Trevor has 0 picks in R1-R2 (trades applied)", trevor_r12 == 0,
          f"got {trevor_r12}")

    # Keepers present on the board at their forfeit rounds.
    board_keepers = {p["player_name"] for p in picks if p["is_keeper"]}
    expected_keepers = {k["player_name"] for k in keepers
                        if k.get("status") == "carryover"}
    missing = expected_keepers - board_keepers
    check(f"all {len(expected_keepers)} keepers placed on board",
          not missing, f"missing: {sorted(missing)}")

    # Display board sanity: Ja'Marr Chase must not fall out of the top 6
    # (greedy display sim, temperature=0).
    chase = next((p for p in picks if p["player_name"] == "Ja'Marr Chase"), None)
    check("Ja'Marr Chase goes in the top 6 picks",
          chase is not None and chase["overall"] <= 6,
          f"overall={chase['overall'] if chase else 'UNDRAFTED'}")

    print("Monte Carlo summary:")
    per_team = mc.get("per_team", {})
    check("MC has all 12 teams", len(per_team) == 12, f"got {len(per_team)}")
    survival = mc.get("survival", {})
    check("MC survival quantiles for 200+ players", len(survival) >= 200,
          f"got {len(survival)}")
    bad_q = [nm for nm, q in survival.items()
             if len(q) != 11 or any(q[i] > q[i + 1] for i in range(10))]
    check("survival quantiles are 11-point and monotonic", not bad_q,
          f"bad: {bad_q[:3]}")
    # A keeper on a team with NO alternates is kept in every scenario, so
    # they're never draftable — quantiles must be all-zero. (Teams WITH
    # alternates legitimately release a keeper in ~30% of sims.)
    alt_rids = {k["roster_id"] for k in keepers if k.get("status") == "alternate"}
    fixed_keeper = next((k["player_name"] for k in keepers
                         if k.get("status") == "carryover"
                         and k["roster_id"] not in alt_rids), None)
    if fixed_keeper and fixed_keeper in survival:
        check(f"always-kept keeper ({fixed_keeper}) shows gone-from-start",
              max(survival[fixed_keeper]) == 0,
              f"quantiles: {survival[fixed_keeper]}")
    slot_counts = []
    for ti, data in per_team.items():
        n = sum(len(s) if isinstance(s, list) else 1
                for s in data.get("pick_distribution", {}).values())
        slot_counts.append(n)
    check("MC tracks 17 pick-slots per team",
          all(n == 17 for n in slot_counts), f"slots={slot_counts}")
    check("every team has a representative roster of 17",
          all(len(d.get("representative_roster", [])) == 17
              for d in per_team.values()))

    print("Draft helper bundle:")
    check("helper has 12 managers", len(helper["managers"]) == 12)
    check("helper schedule has 204 picks", len(helper["schedule"]) == 204)
    check("helper keepers match keepers_2026.json",
          {k["player_name"] for k in helper["keepers"]} == expected_keepers)
    check("helper has 300+ players", len(helper["players"]) >= 300,
          f"got {len(helper['players'])}")
    n_svq = sum(1 for p in helper["players"] if p.get("svq"))
    check("helper players carry survival quantiles (200+)", n_svq >= 200,
          f"got {n_svq}")
    kyle_helper_r1 = sum(1 for p in helper["schedule"]
                         if p["round"] == 1 and p["team_idx"] == 2)
    check("helper schedule reflects trades (Kyle 3 R1s)",
          kyle_helper_r1 == 3, f"got {kyle_helper_r1}")

    standalone = (ROOT / "docs" / "draft_helper" / "standalone.html").read_text()
    check("standalone.html has data inlined",
          "EMBEDDED_DATA" in standalone and "await fetch(DATA_URL)" not in standalone)

    print("PDFs exist and are non-trivial:")
    for name in ("MONEYLEAGUE_2026_MOCK.pdf", "MONEYLEAGUE_2026_PRESEASON.pdf",
                 "MONEYLEAGUE_POWER_RANKINGS.pdf",
                 "MONEYLEAGUE_RESEARCH_DESK.pdf", "MONEYLEAGUE_ROOM_CARD.pdf",
                 "MONEYLEAGUE_DOCTRINE.pdf", "MONEYLEAGUE_DRAFT_SHEET.pdf",
                 "MONEYLEAGUE_ALMANAC.pdf",
                 "MONEYLEAGUE_POSTDRAFT_SHIFT.pdf"):
        f = ROOT / "data" / name
        check(name, f.exists() and f.stat().st_size > 100_000,
              "missing or suspiciously small")

    print("Research Desk fragments:")
    for frag in ("market_screen", "trade_ledger", "counterparty_dossiers",
                 "pick_squeeze", "autopsy_2025", "stash_curve",
                 "keeper_sensitivity", "survival_calibration",
                 "timing_study", "champion_profile", "keeper_stack_screen",
                 "trade_targets", "coaching_tape"):
        p = ROOT / "data" / "research" / f"{frag}.html"
        check(f"research fragment {frag}",
              p.exists() and p.stat().st_size > 500,
              "missing or empty — its builder didn't run")
    bk = ROOT / "data" / "bot_knowledge.json"
    bk_ok = False
    if bk.exists():
        kd = json.loads(bk.read_text())
        bk_ok = (len(kd.get("seasons", {})) >= 15
                 and kd.get("titles") and kd.get("purse_all_time"))
    check("bot knowledge pack (seasons/titles/purse present)", bk_ok,
          "missing or thin — build_bot_knowledge.py didn't run")

    bench = ROOT / "data" / "research" / "benchmark_validation.json"
    check("benchmark validation json (corpus is committed, so this must "
          "build)", bench.exists() and bench.stat().st_size > 200,
          "missing — build_benchmark_validation.py didn't run or found "
          "no gradable leagues")
    cp = (ROOT / "data" / "research" / "champion_profile.html").read_text()
    check("champion profile carries the replication block",
          "Out-of-sample check" in cp,
          "benchmark json exists but section X omitted it")

    print("Design system:")
    ds = subprocess.run([sys.executable, "scripts/check_design_system.py"],
                        cwd=ROOT, capture_output=True, text=True)
    check("design system compliance", ds.returncode == 0,
          "raw hex / duplicate palette / drift / helper-link violations:\n"
          + (ds.stdout + ds.stderr).strip())

    print("Accessibility:")
    ay = subprocess.run([sys.executable, "scripts/check_a11y.py"],
                        cwd=ROOT, capture_output=True, text=True)
    check("a11y compliance", ay.returncode == 0,
          "structure / aria / responsive / css / contrast violations:\n"
          + (ay.stdout + ay.stderr).strip())

    print()
    if FAILURES:
        print(f"✗ {len(FAILURES)} check(s) FAILED:")
        for f in FAILURES:
            print(f"    - {f}")
        sys.exit(1)
    print("✓ all checks passed")


if __name__ == "__main__":
    main()
