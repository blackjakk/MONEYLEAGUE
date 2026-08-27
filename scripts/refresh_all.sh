#!/usr/bin/env bash
# MONEYLEAGUE data + report pipeline orchestrator.
#
# Rebuilds artifacts from current data. Idempotent — safe to re-run.
#
# Usage:
#   scripts/refresh_all.sh                 # everything + verify
#   scripts/refresh_all.sh derive          # one stage
#   scripts/refresh_all.sh sim reports     # multiple stages, run in order given
#   scripts/refresh_all.sh verify          # just the invariant checks
#
# Stages: fetch | derive | sim | reports | helper | verify | all
#
# Pipeline (dependency order):
#
#   LAYER 1 — fetch: external pulls (Sleeper, FantasyPros, FantasyCalc)
#   LAYER 2 — derive: players csv, pick value, keepers, tendencies, skill
#   LAYER 3 — sim: mock draft + Monte Carlo  -> data/mock_draft_picks.json,
#                                               data/mc_summary_all.json
#   LAYER 4 — reports: 3 PDFs + draft helper bundle + standalone.html
#   LAYER 5 — verify: invariant checks on all outputs (exit 1 on failure)
#
set -euo pipefail
cd "$(dirname "$0")/.."

log() { printf "\n\033[1;36m▶ %s\033[0m\n" "$1"; }

ensure_player_catalog() {
  # 14MB Sleeper player catalog is not in git; derive-layer scripts need it.
  if [ ! -f data/sleeper/players_nfl.json ]; then
    log "players_nfl.json missing — fetching from Sleeper"
    curl -sS --fail --retry 3 --retry-delay 2 \
      https://api.sleeper.app/v1/players/nfl -o data/sleeper/players_nfl.json
  fi
}

ensure_backtest_data() {
  # ~41MB of gitignored period archives (proj_/stats_ per season) that the
  # historical analytics grade against; cache-first, no-op when present.
  python3 scripts/fetch_backtest_data.py
}

# ---------- LAYER 1: external fetches ----------
do_fetch() {
  log "Fetch Sleeper (league + projections + transactions)"
  scripts/fetch_sleeper.sh
  log "Fetch FantasyPros consensus rankings"
  python3 scripts/fetch_fantasypros.py
  python3 scripts/fetch_vegas_rankings.py
  python3 scripts/fetch_ffb_tiers.py
  log "Fetch FantasyCalc trade values"
  python3 scripts/fetch_fantasycalc.py
  log "Refresh trade intelligence cache (current season)"
  python3 scripts/fetch_trade_intel.py --refresh-current
  log "Refresh league history cache (matchups)"
  python3 scripts/fetch_league_history.py
  log "Benchmark corpus (cache-first; no-op when fully cached)"
  python3 scripts/fetch_benchmark_leagues.py
}

# ---------- LAYER 2: derived data ----------
do_derive() {
  ensure_player_catalog
  ensure_backtest_data
  log "Regenerate design-system artifacts from tokens"
  python3 design/build_design.py
  log "Rebuild players_2026.csv from Sleeper projections"
  python3 scripts/build_players_csv.py
  log "Append ADP snapshot to price history"
  python3 scripts/append_adp_history.py
  log "Rebuild empirical pick-value chart"
  python3 scripts/build_pick_value.py
  log "Predict 2026 keepers"
  python3 scripts/build_2026_keepers.py
  # Once the league's keeper deadline passes, write the REAL keepers to
  # data/keepers_2026_actual.json (same schema) — it overrides the model.
  if [ -f data/keepers_2026_actual.json ]; then
    log "keepers_2026_actual.json found — overriding predictions with actual keepers"
    cp data/keepers_2026_actual.json data/keepers_2026.json
  fi
  log "Extract per-manager draft tendencies"
  python3 scripts/build_manager_tendencies.py
  log "Compute historical draft skill"
  python3 scripts/build_historical_draft_skill.py
}

# ---------- LAYER 3: simulator ----------
do_sim() {
  ensure_player_catalog
  log "Run mock draft sim + Monte Carlo"
  python3 scripts/build_mock_draft_sim.py
}

# ---------- LAYER 4: reports ----------
do_reports() {
  ensure_backtest_data
  log "Option Book: empirical stash curve (feeds helper data + advisor)"
  python3 scripts/stash_curve.py
  log "Render Power Rankings PDF"
  python3 scripts/build_power_rankings.py
  log "Render 2026 Preseason GUAP Rankings PDF"
  python3 scripts/build_preseason_2026.py
  log "Render 2026 Mock Draft PDF"
  python3 scripts/build_mock_draft_report.py
  do_helper
  log "Render Round-by-Round Menu one-pager"
  python3 scripts/build_round_menu.py
  log "Render draft-day Room Card one-pager"
  python3 scripts/build_room_card.py
  log "Summarize week-over-week movers"
  python3 scripts/build_weekly_movers.py
  log "Research Desk: market screen, trade ledger, dossiers, autopsy"
  python3 scripts/build_market_screen.py
  python3 scripts/build_trade_ledger.py
  python3 scripts/build_autopsy_2025.py
  python3 scripts/build_pick_squeeze.py
  python3 scripts/build_keeper_sensitivity.py
  python3 scripts/backtest_survival_calibration.py
  python3 scripts/build_timing_study.py
  python3 scripts/build_benchmark_validation.py
  python3 scripts/build_champion_profile.py
  python3 scripts/build_keeper_stack_screen.py
  python3 scripts/build_trade_targets.py
  python3 scripts/build_coaching_tape.py
  python3 scripts/build_research_desk.py
  log "Render Doctrine Card one-pager (laws / calendar / board — needs trade_targets)"
  python3 scripts/build_doctrine_card.py
  log "Render Draft Sheet one-pager (the board — needs market screen + helper)"
  python3 scripts/build_draft_sheet.py
  log "Render the Almanac (league record — extends itself each season)"
  python3 scripts/build_almanac.py
  log "Build the League Desk bot knowledge pack (Almanac facts only)"
  python3 scripts/build_bot_knowledge.py
}

# ---------- Draft helper ----------
do_helper() {
  ensure_player_catalog
  log "Sync design-system CSS into the helper"
  cp design/ml.css docs/draft_helper/ml.css
  log "Refresh draft helper data bundle"
  python3 scripts/build_draft_helper_data.py
  log "Rebuild standalone.html (data inlined)"
  python3 scripts/build_standalone_helper.py
  # Mirror into football-sim branch's draft_helper/ for htmlpreview hosting
  if [ -d "draft_helper" ]; then
    cp docs/draft_helper/*.html docs/draft_helper/data.json docs/draft_helper/ml.css draft_helper/
    echo "Synced to draft_helper/ (football-sim branch path)"
  fi
}

# ---------- LAYER 5: verification ----------
do_verify() {
  log "Verify output invariants"
  python3 scripts/verify_outputs.py
}

run_stage() {
  case "$1" in
    all)      do_fetch; do_derive; do_sim; do_reports; do_verify ;;
    fetch)    do_fetch ;;
    derive)   do_derive ;;
    sim)      do_sim ;;
    reports)  do_reports ;;
    helper)   do_helper ;;
    verify)   do_verify ;;
    *)        echo "unknown stage: $1 (want: fetch|derive|sim|reports|helper|verify|all)"; exit 1 ;;
  esac
}

if [ $# -eq 0 ]; then
  run_stage all
else
  for stage in "$@"; do
    run_stage "$stage"
  done
fi

log "Done. (${*:-all})"
