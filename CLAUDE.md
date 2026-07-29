# MONEYLEAGUE — project memory

Fantasy football analytics for Brian's (bsg5032 / bigguap69, Sleeper rid 9,
slot 6) 12-team superflex 0.5-PPR keeper league. Repo renamed from
`datasciencecoursera` → `MONEYLEAGUE` (July 2026); local dir may keep the
old name. Everything rebuilds via `scripts/refresh_all.sh` (stages:
fetch|derive|sim|reports|helper|verify). **Read docs/PIPELINE.md first.**

## Branch map
- `master` — the project (pipeline, data, docs, design system)
- `claude/football-sim-blockchain-game-b3sdq` — GitHub Pages source ONLY
  (name is historical): hosts the HQ landing page (site root) +
  `/draft_helper/`, auto-synced from master by the weekly workflow; never
  develop here. Deploy = static workflow (`.github/workflows/pages.yml`
  on that branch). The old gridiron-chain game was deleted at user
  request (July 2026, commit 042055b; recoverable from branch history).
- `claude/trusting-hamilton-3MNt9` — frozen pre-migration archive
- Weekly automation: `.github/workflows/weekly_refresh.yml`, Tuesdays
  ~9:23am ET — full pipeline, verify-gated push to master, PDFs to the
  `latest-artifacts` release, helper sync to Pages, movers+injury
  briefing as commit body, auto-issue on failure

## Live URLs (Pages paths are CASE-SENSITIVE; old-name paths don't redirect)
- HQ landing: https://blackjakk.github.io/MONEYLEAGUE/ (old /hq/ redirects)
- Helper: https://blackjakk.github.io/MONEYLEAGUE/draft_helper/
- PDFs: https://github.com/blackjakk/MONEYLEAGUE/releases/tag/latest-artifacts

## Hard-won data truths (do not relearn these)
1. **The xlsx is the source of truth for pick ownership**
   (`data/historical/MONEY_LEAGUE.xlsx` cell colors). Sleeper's 2023 draft
   feed misattributes 194/204 picks (Brian entered all picks manually,
   first Sleeper year); 2024 has ~17 mismatches; 2025 is clean. Anything
   attributing historical picks joins xlsx on (round, slot) → pick_no.
2. This league enters keepers as ordinary unflagged draft picks (except
   2025+). Detect implicit keepers by ADP gap ≥1.5 rounds.
3. Sleeper's *stored historical projections* are contaminated with
   in-season knowledge — period-honest backtests use ADP only.
4. rid↔manager stable 2023-2025 except rid 10 (handoff → josh_wildboy in
   2025; config `roster_handoffs`).
5. Keeper seating house rule (user-confirmed, Jul 2026): if the exact
   cost round isn't owned/free, the keeper seats at the next EARLIER
   owned free round (bump-up). Nobody is ever hard-blocked while an
   earlier round is free — the cost of a missing seat is the BUMP TAX
   (earlier pick consumed), not the keeper itself.
6. Pick-trade convention (user-confirmed): trades run EQUAL COUNT both
   ways (1-for-1, 2-for-2 — e.g. R1+R17 for R3+R5); value balances via
   round quality, not pick quantity. Structure all pick asks this way.
7. The league drafts LIVE IN PERSON; rivals bring their own printed
   analysis — popular (often Reddit-sourced) rankings, and they are
   smart enough to bring SUPERFLEX/2QB versions (user-confirmed; do NOT
   assume a 1QB naivety discount). Model the room's paper as ≈ the
   FantasyPros OP consensus; the exploitable edge is where OUR
   league-specific model (VBD + keeper/contract context + this room's
   measured tendencies) disagrees with that consensus — not where
   online ADP disagrees with it.
8. Room social map (user-provided, Jul 2026): Troy=Bills fan, Eric=Jets,
   Figgy=Packers, Lem=Seahawks, Brian="Jets" (ironic quotes), everyone
   else ≈ Eagles fans; nearly all Penn State alumni except Donnie. BUT
   measured: NO fan/alumni price premium exists — PSU alumni reach
   +1.36 vs +1.32 baseline (n=12; Saquon went at/below market 3x in a
   PSU-Eagles room), and drafted-team clusters do NOT match stated
   fandom (Bills-fan Troy drafts zero Bills). Do not model a fan tax;
   the room drafts mercenary. Caveat: team-at-draft tests need
   historical rosters (players_nfl.json carries CURRENT team only —
   burned once on Bigsby JAX→PHI). PARTIAL FIX (Jul 17): backtest
   proj/stats rows carry a TOP-LEVEL at-time `team` field (validated:
   Saquon NYG'23/PHI'24) — historical team available 2023-25; the
   team-at-draft retest is now possible. Live test pending: 2026 PSU
   rookie class (Allar/Singleton) + Tyler Warren (Figgy paid +1.8 in
   2025).
9. Keeper contract rules (user-confirmed, Jul 2026): cost escalates 2
   rounds/yr, MAX 3 consecutive years kept, R1/R2 forfeits ineligible —
   and the 3-year clock FOLLOWS THE PLAYER; it does NOT reset on trade.
   An expiring keeper is therefore a pure rental to any acquirer. 2027
   expiry board (from 2026 predicted keeps): Trevor loses Collins+
   Achane+Puka simultaneously, coop loses McBride+Jamo — half the
   league holds ≥1 expiring asset; Brian holds ZERO (all fresh) and a
   full 2027 pick set (the currency forced sellers want).
10. LOW-SCORE TAX (user, Jul 2026; RULE STARTED 2022): each week the
    LOW scorer pays the TOP scorer $15, escalating +$5 per additional
    low week by the same owner that season (4th low week = $30).
    Regular-season weeks only (USER-CONFIRMED, pre-playoffs).
    Rule-era ledger 2022-25 (scratch, on record): BRIAN
    IS DEAD LAST (7 low wks, paid $150, collected $15 once, net
    −$135; $90 in 2025 alone). Trevor +$125 / Dave +$120 / brower
    +$105 top collectors. Worst bleed: coop 2023, 6 lows, $165.
    Fold-rule interaction: bottom-3-PF-at-W6 teams average ~$38 in
    W7+ fines (max $130) — the tax does NOT overturn
    sell-with-conviction, but it prices punting the lineup: sell
    PLAYERS, never stop setting the best remaining lineup. Sept
    war-room item: weekly briefing should carry the live tax tape
    (who paid whom, season tabs) once 2026 scores flow.

## Season plumbing (2026)
- 2026 Sleeper league EXISTS: id `1364055104709230592` (auto-discovered
  via trade-intel scouting; 0 transactions as of Jul 2026)
- `configs/season_2026.json` — slot→rid map (predicted order; update when
  Sleeper posts the real one), my_roster_id, league dir
- Keepers lock → write `data/keepers_2026_actual.json` (same schema);
  derive prefers it over the model prediction
- Brian's keepers: predictor says Loveland R8, Burden R9, Pierce R14,
  Watson R15 — Watson USER-CONFIRMED (Jul 2026). BUT the tax-aware
  optimizer (regression tax from the keep-side book, Jul 2026) drops
  that set to #5/50; its best set is KEEP 2 ONLY: Burden R9 + Watson
  R15 (+15 proj pts) — Loveland (TE −25 tax, fair price) and Pierce
  (free-round fair price, the worst historical tier) grade as ceremony
  keeps; drafting fresh at R8/R14 is better. Decide at lock; write
  keepers_2026_actual.json with whatever Brian declares. Jordan Love is
  INELIGIBLE (years_kept=3, at the cap — user-confirmed): in
  keepers_2026.json, status forced_drop MEANS ineligible, never a
  testable keep (he re-enters the draft pool at market ~R4)

## Design system (July 2026 refactor — enforced, no bypassing)
`design/tokens.json` → `design/build_design.py` → generated `design/ml.css`
+ `design/tokens.py`. ALL UI (helper, 4 PDF builders, matplotlib) consumes
it. `scripts/check_design_system.py` (inside verify) fails on raw hex,
duplicate palettes, hand-edited generated files. Use the `design-review`
skill for any UI diff. Catalog: docs/DESIGN_SYSTEM.md. **Intent/aesthetic
doctrine: DESIGN.md (repo root) — read before building ANY UI**; it is
hex-free by rule (RAW HEX scan covers it) so it can't fork from tokens.
Theme (July 2026): **The Exchange** — trading terminal (dark) + engraved
banknote (light/PDFs); gold = market state + blue-chip ONLY; GUAP labels
never replace numbers; tape is static. Contract: docs/GOAL_EXCHANGE.md.
Fonts self-hosted OFL (data/fonts/), guilloché via design/guilloche.py.
data/adp_history.csv accumulates weekly ADP (sparklines ready ~Aug).

## Accessibility (July 2026 hardening — enforced)
Helper is WCAG 2.1 AA: keyboard-draftable (roving tabindex, focus
restoration in refresh()), SR live regions (#sr-clock), phone-clean at
360px (column collapse + sticky header), AA contrast both themes.
`scripts/check_a11y.py` (inside verify) guards it; use the `a11y-review`
skill for any helper/design diff. Record: docs/A11Y_AUDIT.md.

## Research Desk (July 2026 — the analyst layer, 13 sections)
`data/MONEYLEAGUE_RESEARCH_DESK.pdf`, assembled by
`scripts/build_research_desk.py` from fragments in `data/research/`
(contract: docs/GOAL_RESEARCH.md — one <section>, ml classes, no hex;
goal docs: GOAL_RESEARCH.md, GOAL_OPTIONS.md). Caches: `data/scouting/`
(trade intel, cache-first, `--refresh-current`), `data/league_history/`
(matchups). Findings ON RECORD:
- Trade Ledger (PAR-graded): Josh is the real shark (+188 PAR); Troy's
  raw +288 was QB volume; BRIAN grades PAR fish (−187 over 12 deals).
- 2025 Autopsy verdict: ROSTER STRENGTH killed 2025 (optimal PF 364 below
  median); lineup-setting −12 vs median (rank 4/12); luck +1.3 wins.
  Consistent with backtest: drafting fine → edge is deals + rosters.
- Option Book (`scripts/stash_curve.py`, empirical 2023-24): late picks
  carry real 2027 keeper option value — R9 +30 (50% hit), R7 +17, R17
  +13; composed_round_values() = max(0,redraft)+option feeds advisor,
  squeeze, helper SIM.
  + ROOKIE & YOUNG PLAYER BOOK (in VI, Jul 18; CORRECTED Jul 21 after
  the user's example request exposed two bugs — implicit 2023/24
  keepers counted as draft picks (keeper discounts masquerading as
  market prices: "R13 ARSB", "R15 Purdy") and 2023 owner attribution
  from the misattributing Sleeper feed (truth #1 violation; now xlsx-
  joined + ADP-gap excluded): NO young class beats its market price —
  rookies −13.8/pick, yr-2 POST-HYPE −11.2, yr-2 PRICED −4.3 (the
  earlier +4.3 "market under-escalates sophomores" verdict was the
  keeper artifact and FLIPPED; the sophomore edge lives in the KEEP at
  a discount, never at sticker), yr-3 null (−7), vets +4.6 = the value
  class. BAND SPLIT (user-caught: high-capital rookies carry a
  guaranteed ROLE — fantasy round proxies committed NFL volume): R1-4
  +3.6/pick, 8% bust = market-fair floor (variance is efficiency, not
  opportunity); tax concentrates in R5-8 hype zone (−18.7, capital
  without guaranteed volume); R9-12 −5.2 ≈ free before the option
  premium; R13-17 −25.4. Owner rookie grades (xlsx-true): trevor +28
  (Daniels R3), ankur +12 (Nix R9/Thomas R7 — selection not volume),
  dave +4; Brian −13; donnie 0-for-7 (−57). Doctrine: R1-4 fine at
  market; R5-8 only fallen values; R10+ darts as 2027 option
  purchases. Waiver corollary (chat-level, Jul 21): 30 drafted rookies
  CUT by owners, median W2, 75% by W5; breakouts land median 2 wks
  post-drop — wire-watch W3-8 for R9+ rookie cuts (Monangai
  W5-cut→Tim-scoop→keeper; R15 waiver-keep rule makes every scoop an
  option buy); early-round rookie frustration exits by TRADE not
  waiver (Daniels W9'24 traded to Brian — his textbook elite-buy).
  2026 draftable yr-2 pool (grade at MARKET now, not premium): Dart
  R2, Jeanty R2, Hampton R3, McMillan R4, Egbuka R5, Ward/Judkins/
  Warren/Henderson R6, RJ Harvey R9.
- Market screen: MODEL vs THE ROOM'S PAPER is the edge (truth #7); edges
  carry reach% (survival to Brian's seat) — Bowers top reachable edge.
  + SHARP MINORITY block (Jul 22, user-prompted): trimmed consensus of
  FP's top-8 draft-accuracy experts (select-crowd: chosen on past
  accuracy, EQUAL weight, K=8 ≈ top decile to dilute contest noise;
  fetch_fantasypros.py scrapes the cheatsheet page's embedded expert
  directory w/ draft_rank, cache data/fp_experts.json, then hits the
  keyless partner endpoint with filters=id:id → rankings_fantasypros_
  sharp.json). RB/WR/TE ONLY (1QB ranks; QB ordering superflex-
  meaningless). MEASURED HEADLINE: the sharp-8 agree with the full
  86-expert consensus within ~1 round on nearly everyone (max gap 17
  rank spots) — whispers for coin flips, never a board. Context on
  file: projection-accuracy tests (chat, Jul 22) — rotowire beat
  superflex ADP .68/.51 Spearman every year, naive composites and a
  LOSO coaching-adjusted proj both FAILED to beat it; forecast accuracy
  is a commodity, the edge is league context. FP accuracy contest:
  2025 winner Seth Miller; 3-yr sharps Jody Smith/Koerner/Wright/
  Ratcliffe/Kluge (not in FP's submitting pool).
  + VEGAS BOOK block (Jul 22, user-requested): firstdown.studio
  Vegas-props season projections (fetch_vegas_rankings.py, Next.js
  server-rendered tables at /season-rankings{,/rb,/wr,/te}; structural
  span parse; cache-first per position on failure →
  data/rankings_vegas.json). POSITION RANKS ONLY consumed (site
  scoring format never touches VBD); ±6 pos-rank gaps vs the room's
  paper rendered in I. Money-not-opinion third voice; props price
  committed VOLUME, strongest on role questions. Notable at build:
  Vegas WR37 on unsigned Diggs (books expect a real landing spot).
- Pick Squeeze: bump rule (truth #5) + negative-tail curve ⇒ keeper
  seats ~free; pick market that matters is R1-R8. + SEAT MARKET (Jul 15,
  user-prompted): natural pairs by spare+barter fit — a full pick set ≠
  monopoly; Donnie (spare R3, missing R13/R14 = Tim's doubles) undercuts
  Brian on BOTH of Tim's seats (Brian ranks #5/#4). Check "my rank"
  before opening any seat negotiation. + POSITION MARKET (Jul 23,
  user-insight, in IV): keeper seats are ROUND-granular ⇒ within a
  keeper-consumed round, pick POSITION is worth 0 to the owner and
  ~8-15 VBD/half-round to a drafter (more at stash targets — R13).
  Snake makes it two-sided (odd rounds favor early slots, even rounds
  reverse). Brian sells dead R8#91/R9#102/R14#163/R15#174 positions;
  best buys: trevor's dead R6#61 + R12#133 (+6 spots each), lem's dead
  R5#49/R11#121/R13#145. NATURAL PACKAGE PARTNER = LEM (4
  complementary same-round legs — every leg trades dead position for
  live, near-Pareto). Auto-computed in pick_squeeze.json
  position_market; regrades at lock. Also draft-order rule
  RULE-VERIFIED (Jul 23, user-provided): consolation-bracket placements
  → slots 1-6 (2024 actual matched 2023 consolation 6-for-6), playoff
  finish reversed → 7-12 (champ 12; one 7/8 wobble in 2024); config's
  predicted order = rule-derived, Brian slot 6 = lost the 2025 toilet
  bowl.
- Desk hygiene (Jul 15 cleanup): assembler strips each fragment's own
  <h2> (numbered desk titles canonical; fragments keep h2 standalone);
  market screen leads with MODEL vs PAPER (edge before context);
  dossier cards carry AT THE DRAFT TABLE fingerprint lines (shared
  renderer with the Room Card).
- Keeper sensitivity: no rival declaration hurts Brian; upside if coop
  keeps Rodriguez over Darnold (+7.6) or Tim keeps Monangai (+4.9).
- Survival calibration (period-honest 2025): Brier 0.10 vs 0.23 base
  (+56% skill); 60-80% band realizes ~58% — pad it.
- Timing Study doctrine: sell mid-season (W6-10, +33/deal), buy at the
  deadline (−2.7 ≈ free); contender-buyers lose in EVERY window.
- Champion Profile (`scripts/build_champion_profile.py`, auto-folds new
  seasons once bracket decides): champs avg +230 keeper VBD vs field +14
  (runners −6 — keeper surplus is CHAMPION fuel); every ring carried a
  ≥5-round-discount keeper built from a late pick/waiver the year before
  (Puka R13, Achane R8, McBride R15, ARSB R13, Etienne R10); 2QB-by-R6
  → 67% playoff rate vs 38% (3/3 champs; shape = one elite + one solid,
  both R1+R2-QB starts finished bottom-two); finalists' title trades
  land W6-10 (lose the trade on paper, win the title); waiver-point
  share is a LOSING signal (field 32% vs champs 11%); wins don't
  separate finalists from playoff-outs — PF does (champs #1,#1,#4).
- YAHOO-ERA DECADE LAYER (Jul 2026, user-prompted): xlsx holds draft
  boards 2015-2022 (8 more drafts; format CONSTANT — 2.2-2.8 QBs/team
  every year since 2015); name_aliases.py resolves league dialect at
  93-96%. manager_tendencies.json gains decade_history (per-owner QB
  timing/rookie/age over 11 drafts): Troy QB2 median R10 STABLE 11 yrs,
  Lem R4 stable early-QB, eric_m 21% rookies, Figgy punt long-run but
  volatile (IQR 6). Dossiers carry DECADE BOOK lines. DECADE CHECK on
  champion QB shape: only 4/11 recorded champs had 2QB-by-R6 and 3 of
  4 are Sleeper-era (Figgy won 2016 at R1+R8, coop 2017 at R9+R10) —
  CONFOUND: Yahoo rounds include unflagged keepers at cost (late "QB2"
  may be kept elite), so it refutes early QB SPENDING as law, not QB
  capital. Verdict everywhere now: 2QB-by-R6 = current-regime room
  exploit, revocable. YAHOO API BACKFILL LANDED (Jul 15): user's OLD
  Yahoo app (GroupMe-bot era, registered redirect
  groupmebotlmao5.herokuapp.com/auth — dead redirect is fine, code
  reads from address bar) carried the fantasy scope the new app
  couldn't get; yahoo_backfill.yml (one-shot workflow_dispatch, auth
  code as input, no token stored) archived 51 league-seasons raw to
  data/yahoo/ (30MB): moneyleague EVERY season 2011-2022 (8tm→10tm→
  12tm growth) + Brian's other leagues (Bean Counters, Playoffs?,
  Ruffians...). build_yahoo_history.py normalizes standings →
  data/league_history/yahoo_era.json; VALIDATED: 12/12 champions match
  KNOWN_CHAMPIONS, 0 unmatched team names. FINDINGS: adjustment null
  now DEFINITIVE (n=103 transitions: burned dQB2 3.66 vs fine 3.39);
  CHAMPION PF LAW over 15 titles — median PF rank #1, 8/15 were the
  top scorer, 11/15 top-3 (exceptions: ankur '22 heist at PF#7, figgy
  '12 at #5/8); TIM career = 7 bottom-half PF in 2017-24 BUT 2025
  PF#4 w/ 10 wins — rehabilitated, not a soft touch. Old cookie-scraper
  output also already committed (data/yahoo/league_*: matchups/trades
  per league-year, from a pre-compaction session) — reconcile someday.
  DECADE TRADE LOG (parsed Jul 15, behavioral only — no weekly stats
  pre-2023 so no value grades): 136 trades 2011-2022. Champs 3.1
  deals/yr vs field 2.0 — champions-out-trade is a 15-YEAR pattern
  (outside rooms' MIXED verdict was about THEIR thin markets). Career:
  Trevor 39, BRIAN 35 (#2 all-time), coop 35, donnie 31; top pair ALL
  TIME = Brian↔Trevor 11 deals (and Brian grades PAR fish in the
  Sleeper era — decade-long farming suspicion, ungradeable pre-2023).
  Ankur's 2022 heist title = 5 of his 7 career trades in ONE season
  (one-off all-in, not a profile). Timing eternal: 60% of all decade
  trades in W6-10; deadline always thin (14/136). Tim: 9 trades in 12
  years — one deal per season; a seat offer to him IS his annual trade.
  DECADE LEDGER VALUE-GRADED (build_decade_ledger.py; Sleeper weekly
  stats reach 2011, fetched via fetch_trade_intel.fetch_stats into
  scouting/stats — ~5MB committed; PAR method mirrors the Sleeper
  ledger, replacement scaled to league size): Yahoo-era standings
  Trevor +1070 (39 deals) / coop +683 / troy +624 ... BRIAN −848,
  ALL-TIME LAST. THE PAIR VERDICT: Brian↔Trevor 11 deals = −686 TO
  BRIAN (−62/deal) — 81% of Brian's career deficit is ONE counterparty;
  combined eras Brian ≈ −1035 over 47 deals. Ankur 2022 heist graded
  +234/5 deals (w7 Henry+Diggs from donnie +128 was the title trade).
  Biggest single heist ever: coop +325 v Tim (2017 w5). Tim −55/deal
  worst rate in history. STANDING RULE: no deal with Trevor without
  running the advisor first — and 2026 is the year the leverage flips
  (he's the forced seller; Brian holds the picks).
  DECADE CROSS-CUTS (Jul 15): (a) COUNTERPARTY-CONTENDER is the
  biggest edge axis ever measured — RE-MEASURED Jul 16 at TRADE TIME
  (both eras, n=342 sides, endogeneity-proof): the side AHEAD in PF
  when the deal closes wins mixed-strength trades +44/deal; equal
  halves wash to 0 (T→B +44 / B→T −44 / T→T and B→B ≈ 0). Doctrine =
  BE THE STRONGER SIDE / farm below, never call up out of weakness;
  the original "SELL TO CONTENDERS" label had the direction BACKWARDS
  (advisor rule 1 rewritten Jul 16). (b) Skill persistence WEAK (3/8 same-sign
  across halves): Trevor's +1226 was ALL 2011-16 (since 2017: −156 +
  Sleeper −55 — reputation now exceeds reality, exploitable); the LIVE
  shark is COOP (+638 recent + biggest heist ever + strong Sleeper) —
  caution transfers Trevor→coop. (c) Champions WIN their swaps (+174
  title-year mean, 9/11 positive) — "lose the trade win the title"
  applies only to pick-funded buys. (d) Early swaps most lopsided
  (|PAR| 100 vs 79 mid, 45 deadline). (e) Brian ex-Trevor = −162/24
  ≈ league-average; his two fixable leaks: early-window deals
  (−62/deal, don't trade before W6) and QB swap-acquisitions
  (−51/deal n=14 — draft QBs, never swap for them). House rules print
  atop every trade_advisor.py run; Decade Book table lives in desk II.
  RIVALS' OTHER YAHOO LEAGUES: not pullable systematically (Yahoo
  redacts GUIDs/nicknames, no per-user league listing — unlike
  Sleeper). Shared-league mining works: archive holds Brian's 39
  other league-seasons; team-name matching confirmed Trevor =
  "Reno Mahe 911" (Playoffs? 2012-13), Donnie = "Mrs. Doubtfire"
  (Bean Counters 2017-18). More rivals likely in the Playoffs?
  series under unknown names — 2022 rosters were shown to Brian for
  identification (pending); any ID he gives unlocks that owner's
  decade outside-book (per-team trade/move counts sit in every
  archived standings file). Repo Actions secrets YAHOO_CLIENT_ID/
  SECRET hold the working fantasy-scoped app (the old GroupMe-bot
  app); yahoo_backfill.yml is rerunnable with a fresh auth code.
- Benchmark corpus (out-of-sample validation, July 2026): 13 owner-free
  MONEYLEAGUE-format league-seasons (6th Floor Crew, Ciely-Style 12tm;
  Warren 10tm) found by snowball crawl through rivals' leaguemates;
  cached data/scouting/benchmark/ (cache-first fetcher; grow corpus by
  appending _corpus.json). Verdicts (9 gradable): keeper VBD REPLICATES
  (champs 211 vs field 73), waiver-share REPLICATES, champ PF rank
  REPLICATES (mean 2.4); trade share MIXED (outside rooms barely
  trade); 2QB-by-R6 FAILS outside (43% vs 50%, negative in BOTH size
  classes) → the QB edge prices THIS room's QB-late minority, not a
  superflex law.
- Stack Screen (XI, `build_keeper_stack_screen.py`, + lines in weekly
  movers briefing; also carries the EXPIRY BOARD — truth #9 rental
  shelf, forced-seller flags Trevor 3 / coop 2, W9-11 buy window): preseason keeper surplus is a COIN FLIP for titles
  (champs ranked 6/9/1 preseason; 12-league backtest percentile ~49);
  the "title watch" shape (rank-1 surplus ≥120 + proven majority) went
  1-for-3 (2025 Trevor hit; 2024 coop same shape missed) ≈ 4x base
  rate, not a crown. NOTE: coop = rid 12 (displays wvw5022 AND
  BigDickNicholas across seasons — display names change, manager ids
  don't). v2 adds WAR CHEST (keepers at market + live picks,
  trades applied, keeper seats consumed) — user-prompted fix: surplus
  alone ignored total capital. 2026 predicted: watch fires on Trevor
  (surplus #1, 167, 100% proven) BUT he's war chest #8 (355) having
  shipped R1+R2; war-chest leader is FIGGY (629 — 3 R1s, no keepers);
  Brian surplus #7 / war #7 (406). 2025 champ was #1 in BOTH; 2026
  Trevor is NOT the 2025 configuration. Champ war ranks 6/3/1 (mildly
  better signal than surplus 6/9/1). Auto-regrades on real declarations
  when keepers_2026_actual.json lands.
- PF-LEADER AUTOPSY (Jul 16, user-prompted; scratch analysis, on record
  here + qualifies the PF law): PF leader won 8/15 titles; all 7 upsets
  were ONE-WEEK variance, never a better roster — 5 were the leader's
  own dud (−17 to −45 under season avg; Brian 2018 11-2/PF#1 lost the
  semi 121.5-126.8 to a BELOW-average Lem week), 2 were opponent
  heaters (coop 2020 scored above avg in both playoff games and lost
  both; coop also lost the 2012 semi 124.60-124.62 = 0.02 pts, the
  cruelest beat ever — coop owns BOTH mega-upsets). Winner archetypes:
  adjacent contender who avoided the dud (3), December-hot team whose
  W15-17 strength > season PF (3: Trevor'20 heater, Ankur'22
  trade-rebuilt, eric'23 boom-bust), coin flip (1). Lesson: PF law is
  a QUALIFICATION law; December roster > season-long roster (mid-season
  trades reprice you for the bracket).
- EARLY-SEASON FORK (Jul 16, user-prompted; scratch analysis, on record
  here + in the Doctrine Card calendar): W4 knows only the extreme top
  (top-2 PF = 62/40% finals; everything else mush — champs have started
  W4 PF#10/1-3 Trevor'20, PF#7 Ankur'22/eric'23, 1-3 coop'17). Watch
  POINTS not record (W4 good-record/bad-PF teams: 0 finalists). W6 is
  decision-grade: top-3 PF → buy with conviction (#1 = 69% finals/46%
  title); BOTTOM-3 PF AT W6 = 0 FINALISTS IN 43 TEAM-SEASONS over 15
  yrs → sell with conviction into the best-paid window; ranks 4-9 →
  force it by W8 (bottom-half at W8 ≈ dead; sole escape Ankur'22
  BOUGHT his way out W7). 13/15 champs top-half PF by W6. Buckets are
  n=9-15 each, ranks scaled /12 across league sizes — floors are
  strong, not physics.
- TRADE-STYLE COHORTS (Jul 16, 342 sides both eras, by season outcome):
  finalists +46.5/deal at 70% win rate vs field −12.2 at 45%; champs
  3.1 deals/yr (runners-up trade LEAST, 1.7). Star-buy (got the deal's
  single best ROS player) is the biggest shape separator: finalists 54%
  vs field 28% (Brian career 22% — THE leak). Champs deal 76% with
  bottom-half teams; missed teams deal 74% with top-half (feeding
  sharks). TIMING SEPARATES NOBODY (all cohorts ~60% W6-10) — who you
  call and what you insist on separates. QB-in: champs 30% = field.
  10/14 champion title books positive (mean +137); the exceptions:
  figgy'12/coop'24 barely traded, and BOTH Trevor rings ('20 −131,
  '25 −106) came with LOSING books (heater + keeper surplus carried).
  Causality caveat on record: trade PAR partly causes the outcome.
- THE CALL SHEET (XII, `build_trade_targets.py`, Jul 16): ranked 2026
  partner/target board fusing the axis + exploitability (career
  PAR/deal) + LIVE FORM (2017+ both eras — decade ledger now exports
  deals/net_par_2017plus + per-manager style: star_buys/concessions/
  qb_in) + star-concession% + liquidity + 2026 motive (expiry board,
  war-chest rank, seat lanes) ± Brian pair history. Also behind
  `trade_advisor.py --partners`. Board (predicted keepers, regrades
  weekly): #1 Tim (SLOW FARM, −28/deal, one call = his seats), #2
  donnie (CONTENDER SHOP: war-rich, live −36/deal, sell him
  production), #3 Trevor (FORCED SELLER W9-11 + standing rule), #4 lem
  (52% star concession, highest), #5 coop (FORCED SELLER + shark
  caution). SELL-ONLY sharks: figgy (live +35!), ankur, troy, josh.
  rid-10 attribution fixed: Dave through 2024, josh 2025-only.
  + ELITE-BUY PAYOFF (Jul 16, in XII; cache
  data/research/elite_buy_payoff.json, season-stamped — regrinds 15
  seasons of stats only when a new completed season lands): acquiring
  a league top-3 ROS asset mid-season → 33% title (4x base) / 56%
  finals; top-10 → 24%/45%; 8/15 champions made a top-10 buy in their
  title year (Bell bought by figgy'16 AND coop'17, Jacobs by ankur'22
  — all rings; CMC'19/Cam'15 buys lost the final; Adams bought twice,
  no ring). Conditions: buyer must already be top-half (axis) and pay
  in picks. Hindsight caveat on record. This is the empirical case
  for the Trevor W9-11 rental play — Brian holds the picks.
- COACHING TAPE (XIII, `build_coaching_tape.py`, Jul 17, user-prompted
  tree model): dataset data/coaching/coaches.json (play-caller + scheme
  family + tree, 32 teams 2022-2026, per-entry confidence, conf-L
  excluded; 2026 verified vs Jul trackers — 10 HC changes/21 new OCs,
  and a hallucinated "Chip Kelly to SF" from one fetch was CAUGHT by
  cross-checking: Shanahan remains). Backtest 2023-25 vs preseason
  projections using the at-time team field: SAME-TREE HANDOFFS ARE THE
  MARKET'S BLIND SPOT (actual/proj 0.929 vs continuity 0.861; RB cell
  1.035 = only cell beating projection); scheme flips priced right on
  average (0.867) EXCEPT WRs (0.801, worst cell — never pay full
  freight for a WR in a scheme flip). 2026 same-tree buys: ATL (Bijan
  under Stefanski), ARI, MIA (McDaniel→Slowik), SEA. KC = Reid
  continuity (Walker's move there is player-side, not a coaching
  event); WAS = scheme flip to first-time caller (Kaytron Allen).
  Tilt not law: n=51 blind-spot cell, one vendor, 3 seasons; regrades
  when 2026 closes.

## Key analyses on record
- Backtest (`scripts/backtest_recommender.py`): tool vs real-Brian
  2023-2025 = ~break-even (+19/season). Brian already drafts QB-early
  superflex structure; tool's value = variance reduction + live facts
  (survival %, keeper costs), not superior player-picking.
- Keeper optimizer (`scripts/optimize_my_keepers.py`): now applies the
  keep-side regression tax to Brian's kept players (rivals untaxed —
  they don't price with our book). Taxed verdict: Burden+Watson
  2-keeper set #1/50; predictor's 4-set drops to #5 (−15).
- Keep-side tier book (in Option Book VI, `stash_curve.py`): 541
  keepers, 12 league-seasons. All keeper profit = locked discount −
  regression tax (QB 0 / RB 14 / WR 14 / TE 25; alpha vs own ADP).
  7+ rd discounts +50/keeper (76% hit); <4 rds discount = ceremony
  (73% of all keeps, ~0 EV); fair-price R14-17 keeps are the WORST
  tier (−34, 21% hit); discounted QBs the best cell (+36, no tax);
  kept TEs underperform their price by −28.
- Trade advisor (`scripts/trade_advisor.py`): swap pricing now prints
  redraft + keeper-option components (Option Book).
- Owner fingerprints (Jul 2026, in manager_tendencies.json + sim + bots
  + dossier-grade cards): robust method = MEDIAN positional reach with
  ADP<216 cap (mean poisoning: one undrafted dart once faked a +5.7
  "coop RB tax"), keepers excluded + rookie/yr2 shares + age. Durable
  reads: ankur RB +2.5, figgy TE +2.7, donnie TE +1.9, troy drafts OLD
  (27.9, 2% rookies), eric_m rookies 30%, trevor most disciplined
  (+0.3; QB −0.7), troy/trevor get QBs under market. MC sim tilts by
  these (survival curves room-aware); practice bots too. Market
  anchors BOTH ways (user-caught: Mendoza, rookie QB stash ADP R10,
  free-fell to R17 because candidates are VBD-ranked): sim injects
  top-3 market FALLERS (≥2 rds past ADP) into every bot's candidate
  set + symmetric reach penalty (>1.5 rds ahead of market); helper
  bots got stronger fall-catch + R10+ stash term. Mendoza now R12.
  ADJUSTMENT TEST (user-proposed "scared-off" drift, Jul 2026): burned
  owners (bottom-4 PF) change next-year strategy NO more than baseline
  — dQB2 4.0 vs 4.6 rds, dRook 0.07 vs 0.09, dReach 0.78 vs 0.66 over
  22 transitions; Figgy finished DEAD LAST 2024 punting QB and punted
  QB again (dQB2=1). Do NOT model scared-off drift; the room repeats.
  This is WHY the 2QB-by-R6 edge persists here (the QB-late minority
  doesn't learn) and why fingerprints stay valid after bad years.
  User refinement (surprise-conditional: expected burns teach nothing):
  direction AGREES — surprise burns (rich war chest, bottom-4 PF) moved
  QB timing 5.3 rds vs 3.2 for expected burns; Figgy'24 = expected burn,
  changed nothing — but the FINE control churns 5.6 rds naturally, so
  n=3 signal < noise floor; still no drift term (retest after 2026).
  Byproduct: TIM = serial SURPRISE-burner (war #5→PF11 '23, war #4→PF11
  '24) — good capital, bad rosters, the other autopsy case. Trade
  counterparty, not a threat: his players outrun his standings.
  Injury layer (user refinement #2, value-weighted early-capital weeks
  missed): explains Trevor'24 no-change (20% hurt) and reveals coop'23
  "surprise" burn was a 36% injury wipeout — but Figgy'24 (7% = healthy,
  dead last, changed nothing) breaks even the full attribution model:
  the room's non-adjustment is habit, not rationality. 2025 was a
  BLOODBATH (median 21% vs 12-15%): Troy 38 / Figgy 29 / coop 29 /
  Brian 24 (Tim only 8 — no excuse, strengthens serial-underperformer
  read). All burned-2025 owners have the injury excuse ⇒ maximum
  strategy persistence in 2026; Brian's autopsy verdict survives but
  his true 2025 talent gap was smaller than standings said.
- Draft-day artifacts: MONEYLEAGUE_ROOM_CARD.pdf (1-page banknote crib
  sheet: room fingerprints, reachable edges, let-them-pay, keeper math,
  forward market; build_room_card.py, in release uploads).
  + MONEYLEAGUE_DOCTRINE.pdf (Jul 16, build_doctrine_card.py, in
  release uploads + verify): the SEASON one-pager — 6 laws (PF
  qualifies/variance crowns, be the stronger side, take the best
  player, buy elite when contending, discount−tax, the room repeats),
  the W-by-W 2026 operating calendar (lock→draft→hold W1-5→window
  W6-10→rent W9-11→free deadline→bracket), and the live board (call
  sheet top rows, sharks, Brian's four do-nots, assets+the play).
  Live JSONs; runs AFTER build_trade_targets in the pipeline.
  + MONEYLEAGUE_DRAFT_SHEET.pdf (Jul 22, build_draft_sheet.py, in
  release uploads + verify): the BeerSheets-style one-page LEAGUE
  BOARD — QB/RB/WR/TE columns tiered on VBD cliffs (bounded-band rule:
  cliff OR band-width break; gap-only collapsed the tails), per-row
  bye/proj/VBD, ▲/▼ model-vs-paper badges, ★ R9+ option darts, RK#
  chips w/ NFL draft round (data/nfl_draft_2026.json, web-sourced,
  cosmetic only; user caught Lemon/Concepcion R1 gaps), K? chips for
  predicted keepers (kept ON sheet at true VBD), all-rookie guarantee
  (ADP≤204 darts always on board — Kaytron Allen case), full QB pool
  (exempt from shrink). Two user-caught bugs fixed here: falsy-zero
  VBD sort (Jadarian Price, VBD exactly 0.0 → 'or -999' sorted him
  last) and the rookie-map gaps. Regenerates weekly + at keeper lock. Keeper lock
  = 5-min runbook: docs/KEEPER_LOCK.md + lock_keepers.py validator
  (template data/keepers_2026_actual.TEMPLATE.json; enforces cap/floor/
  bump/ownership; then refresh derive sim reports verify).
- Helper features: live Sleeper sync (GO LIVE), PRACTICE (market-anchored
  bots + measured owner-fingerprint tilts), CEILING, Next✓ survival, SIM column (= recs brain incl. 2027
  option term R10+), sortable order book, movers tape + Δwk, LEAGUE
  PORTFOLIOS (auto-follows the clock), saves (Ctrl+S/Save As/Open, dirty
  dot), reset board (Back restores via pushState), full interaction
  states (skeleton/empty/error/aria-disabled/receipts).

## Deploy mechanics (hard-won)
- Pages = STATIC workflow on the hosting branch (assembles _site: hq/ →
  root, draft_helper/); pushing files to the branch ≠ live until its
  workflow runs. GITHUB_TOKEN pushes NEVER trigger it (GitHub loop
  guard) — the weekly sync silently served a stale site for days until
  weekly_refresh gained an explicit `gh workflow run pages.yml`
  dispatch (workflow_dispatch IS exempt from the token restriction).
  Also: data/backtest (41MB, gitignored) is fetched on demand by
  scripts/fetch_backtest_data.py — CI died for 3 days on its absence
  (issues #2-#10). Verify a triggered run's CONCLUSION, not the queue. Manual sync = temp worktree of the hosting branch, write
  files, push (cd OUT of a worktree before `git worktree remove`).
- Release PDFs republish via workflow_dispatch of weekly_refresh.yml
  (MCP actions_run_trigger). Weekly runs push to master → expect races:
  fetch + rebase + regenerate + force-with-lease the feature branch.
- Session proxy blocks unauthenticated api.github.com and release-asset
  downloads — use the GitHub MCP tools instead of curl for those.

## Conventions
- Verify gate before trusting any rebuild: `scripts/refresh_all.sh verify`
- Weekly PDFs + WEEKLY_MOVERS.md are gitignored (Releases host PDFs);
  `data/injury_snapshot.json` IS committed (week-over-week diff baseline)
- Playwright: PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers, launch args
  --no-sandbox --disable-dev-shm-usage
- User corrections about league history are gold — three of them each
  uncovered a real data bug. When the user contradicts the data, check
  the xlsx.
