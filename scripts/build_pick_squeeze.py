"""Research Desk — PICK SQUEEZE: who is missing the pick their keeper needs.

Keepers consume a specific round's pick (cost = prior round − 2; waiver
keeps sit at R15), so demand for those picks is inelastic. Two tiers:

  HARD SQUEEZE   a carryover keeper with no owned pick in its round —
                 they must buy that round or lose the keeper.
  BLOCKED ALT    a positive-value alternate whose round is fully consumed
                 by carryovers — they'd need to BUY a pick to keep both.
                 These are the standing sales leads.

Inputs (on disk, no network): docs/draft_helper/data.json (schedule with
trades applied), data/keepers_2026.json. Outputs per the fragment
contract: data/research/pick_squeeze.{json,html}.
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
MY_RID = 9


def compute() -> dict:
    data = json.loads((ROOT / "docs" / "draft_helper" / "data.json").read_text())
    keepers = json.loads((ROOT / "data" / "keepers_2026.json").read_text())
    rid2ti = {m["roster_id"]: m["team_idx"] for m in data["managers"]}
    ti2name = {m["team_idx"]: m["id"] for m in data["managers"]}
    bt = rid2ti[MY_RID]

    owned: dict[int, dict[int, int]] = defaultdict(lambda: defaultdict(int))
    for p in data["schedule"]:
        owned[p["team_idx"]][p["round"]] += 1

    carry: dict[int, dict[int, list]] = defaultdict(lambda: defaultdict(list))
    for k in keepers:
        if k["status"] == "carryover":
            r = k.get("effective_forfeit_round") or k["forfeit_round"]
            carry[rid2ti[k["roster_id"]]][r].append(k)

    hard = []
    for ti, rounds in carry.items():
        for r, ks in rounds.items():
            short = len(ks) - owned[ti].get(r, 0)
            for k in ks[max(0, len(ks) - short):] if short > 0 else []:
                hard.append({
                    "manager": ti2name[ti], "player": k["player_name"],
                    "round": r, "net_vbd": round(k.get("net_vbd") or 0, 1),
                    "owned_in_round": owned[ti].get(r, 0),
                })

    def free(ti: int, r: int) -> int:
        return owned[ti].get(r, 0) - len(carry[ti].get(r, []))

    # House rule (user-confirmed): a keeper missing its exact round seats at
    # the next EARLIER owned free round. So a "blocked" alternate is never
    # lost while any earlier seat is free — the cost is the BUMP TAX: the
    # chart value of the earlier pick consumed minus the exact round's.
    try:
        from scripts.stash_curve import composed_round_values
        # Composed round value (The Option Book): max(0, redraft blind) +
        # empirical 2027 keeper option value. The redraft part keeps its
        # 0-floor (the blind curve goes negative past ~R9 and a rational
        # manager never values a pick below zero); the option term prices
        # the stash lottery a live late pick carries, so bump taxes now
        # reflect BOTH kinds of forgone value.
        _rv = composed_round_values()

        def round_value(r: int) -> float:
            return _rv.get(r, {}).get("total", 0.0)
    except Exception:
        def round_value(r: int) -> float:
            return 0.0

    blocked = []
    for k in keepers:
        if k["status"] != "alternate" or (k.get("net_vbd") or 0) <= 0:
            continue
        ti = rid2ti[k["roster_id"]]
        r = k.get("effective_forfeit_round") or k["forfeit_round"]
        if free(ti, r) > 0:
            continue
        bump_to = next((rr for rr in range(r - 1, 0, -1) if free(ti, rr) > 0),
                       None)
        bump_tax = (round(round_value(bump_to) - round_value(r), 1)
                    if bump_to else None)
        blocked.append({
            "manager": ti2name[ti], "player": k["player_name"],
            "position": k.get("position", "?"), "round": r,
            "net_vbd": round(k["net_vbd"], 1),
            "bump_to": bump_to,                # None => truly hard-blocked
            "bump_tax": bump_tax,              # chart VBD of the bump
            "is_me": ti == bt,
            "brian_can_sell": free(bt, r) > 0,
        })
    # Urgency = what buying the exact round saves them: tax + a draft slot.
    blocked.sort(key=lambda b: (-(b["bump_tax"] if b["bump_tax"] is not None
                                  else 999), -b["net_vbd"]))

    # Round-level demand vs supply (the R15 logjam lives here)
    demand_by_round: dict[int, int] = defaultdict(int)
    for b in blocked:
        demand_by_round[b["round"]] += 1
    sellers_by_round = {
        r: sorted(ti2name[ti] for ti in ti2name if free(ti, r) > 0
                  and not any(b["manager"] == ti2name[ti] and b["round"] == r
                              for b in blocked))
        for r in demand_by_round
    }

    # THE SEAT MARKET — natural pairs (user-prompted, Jul 2026: "am I
    # Tim's natural partner?" — answer was NO, Donnie was). A bare seller
    # list hides FIT: a seller holding a SPARE of the round gives up
    # nothing structural, and a seller missing exactly the rounds the
    # buyer owns doubles of can be paid in scraps. Rank every demand
    # case's sellers by (spare, barter fit) so the desk always shows who
    # undercuts whom before a negotiation opens.
    def team_profile(ti: int):
        frees = {r: free(ti, r) for r in range(1, 18)}
        missing = [r for r in range(1, 18) if owned[ti].get(r, 0) == 0]
        spares = [r for r, c in frees.items() if c > 1]
        return frees, missing, spares

    profiles = {ti: team_profile(ti) for ti in ti2name}
    name2ti = {v: k for k, v in ti2name.items()}
    seen_case = set()
    seat_market = []
    for src, tag in ((hard, "HARD"), (blocked, "")):
        for b in src:
            key = (b["manager"], b["round"])
            if key in seen_case:
                continue
            seen_case.add(key)
            bti = name2ti[b["manager"]]
            _, _bmiss, bspares = profiles[bti]
            offers = []
            for ti in ti2name:
                if ti == bti:
                    continue
                frees, smiss, sspares = profiles[ti]
                if frees.get(b["round"], 0) <= 0:
                    continue
                spare = b["round"] in sspares
                barter = sorted(set(smiss) & set(bspares))
                offers.append({
                    "seller": ti2name[ti], "spare": spare,
                    "barter_rounds": barter,
                    "fit": (2 if spare else 0) + len(barter),
                    "is_me": ti == bt,
                })
            offers.sort(key=lambda o: (-o["fit"], o["seller"]))
            seat_market.append({
                "buyer": b["manager"], "round": b["round"],
                "for_player": b["player"], "hard": bool(tag),
                "natural": offers[0]["seller"] if offers else None,
                "my_rank": next((i for i, o in enumerate(offers, 1)
                                 if o["is_me"]), None),
                "sellers": offers[:4],
            })
    seat_market.sort(key=lambda c: (not c["hard"], c["round"]))

    # ---- THE POSITION MARKET (user insight, Jul 2026): keeper seats are
    # ROUND-granular (the bump rule prices rounds, never pick numbers),
    # so within a keeper-consumed round the pick's POSITION is worthless
    # to its owner and genuinely valuable to anyone drafting there.
    # Sell your dead position; buy rivals' dead early positions in your
    # live rounds. The snake makes it two-sided (odd rounds favor early
    # slots, even rounds reverse).
    picks_of: dict[tuple[int, int], list[int]] = defaultdict(list)
    for p in data["schedule"]:
        picks_of[(p["team_idx"], p["round"])].append(p["overall"])
    def dead_pick(ti: int, r: int):
        """Earliest keeper-consumed pick overall# for (ti, r), if any."""
        n_keep = len(carry[ti].get(r, []))
        pk = sorted(picks_of.get((ti, r), []))
        return pk[0] if n_keep >= 1 and pk else None
    def live_pick(ti: int, r: int):
        n_keep = len(carry[ti].get(r, []))
        pk = sorted(picks_of.get((ti, r), []))
        live = pk[n_keep:]
        return live[0] if live else None
    sell_legs, buy_legs = [], []
    for r in range(1, 18):
        mine_dead = dead_pick(bt, r)
        mine_live = live_pick(bt, r)
        if mine_dead is not None:
            buyers = []
            for ti in owned:
                if ti == bt:
                    continue
                lp = live_pick(ti, r)
                if lp is not None and lp > mine_dead:
                    buyers.append({"manager": ti2name[ti],
                                   "their_pick": lp,
                                   "spots": lp - mine_dead})
            buyers.sort(key=lambda b: -b["spots"])
            if buyers:
                sell_legs.append({"round": r, "my_pick": mine_dead,
                                  "buyers": buyers[:4]})
        if mine_live is not None:
            for ti in owned:
                if ti == bt:
                    continue
                dp = dead_pick(ti, r)
                if dp is not None and dp < mine_live:
                    buy_legs.append({"round": r, "seller": ti2name[ti],
                                     "their_pick": dp, "my_pick": mine_live,
                                     "spots": mine_live - dp})
    buy_legs.sort(key=lambda b: -b["spots"])
    legs_by_rival: dict[str, int] = defaultdict(int)
    for s in sell_legs:
        for b in s["buyers"]:
            legs_by_rival[b["manager"]] += 1
    for b in buy_legs:
        legs_by_rival[b["seller"]] += 1
    package_partner = (max(legs_by_rival, key=legs_by_rival.get)
                       if legs_by_rival else None)

    return {
        "position_market": {
            "sell": sell_legs, "buy": buy_legs,
            "package_partner": package_partner,
            "partner_legs": legs_by_rival.get(package_partner, 0),
        },
        "meta": {
            "generated": date.today().isoformat(),
            "basis": "predicted keepers (keepers_2026.json) + schedule with "
                     "trades applied (helper data.json)",
            "hard_squeezes": len(hard),
            "blocked_alternates": len(blocked),
        },
        "hard": hard,
        "blocked": blocked,
        "seat_market": seat_market,
        "round_market": [
            {"round": r, "buyers": demand_by_round[r],
             "sellers": sellers_by_round.get(r, [])}
            for r in sorted(demand_by_round)
        ],
    }


def build_fragment(res: dict) -> str:
    e = _html.escape
    rows_hard = "".join(
        f'<tr><td>{e(h["manager"])}</td><td>{e(h["player"])}</td>'
        f'<td class="ml-num">R{h["round"]}</td>'
        f'<td class="ml-num ml-sv-lo">+{h["net_vbd"]:.1f}</td>'
        f'<td class="ml-num">{h["owned_in_round"]}</td></tr>'
        for h in res["hard"]) or (
        '<tr><td colspan="5" class="ml-empty">No hard squeezes — every '
        "carryover keeper currently has a seat. Recomputed weekly; a pick "
        "trade can create one overnight.</td></tr>")

    def bump_cell(b):
        if b["bump_to"] is None:
            return '<td class="ml-urgent">no earlier seat — HARD</td>'
        tax = f' · tax {b["bump_tax"]:+.0f}' if b["bump_tax"] else ""
        return f'<td class="ml-num">seats at R{b["bump_to"]}{tax}</td>'

    rows_blocked = "".join(
        "<tr>"
        f'<td>{e(b["manager"])}'
        + (' <span class="ml-badge ml-badge--keeper" aria-label="You">YOU</span>'
           if b["is_me"] else "")
        + f'</td><td>{e(b["player"])} <span class="ml-note">'
          f'{e(b["position"])}</span></td>'
          f'<td class="ml-num">R{b["round"]}</td>'
          f'<td class="ml-num ml-sv-hi">+{b["net_vbd"]:.1f}</td>'
        + bump_cell(b)
        + ("<td>your pick is spoken for</td>" if b["is_me"] else
           (f'<td class="ml-urgent">you hold a free R{b["round"]}</td>'
            if b["brian_can_sell"] else
            "<td>your seat there is taken too</td>"))
        + "</tr>"
        for b in res["blocked"]) or (
        '<tr><td colspan="6" class="ml-empty">Every positive alternate has '
        "a free seat.</td></tr>")

    def seller_txt(o: dict) -> str:
        bits = [e(o["seller"])]
        if o["is_me"]:
            bits[0] = f"<strong>{bits[0]} (me)</strong>"
        if o["spare"]:
            bits.append('<span class="ml-badge">SPARE</span>')
        if o["barter_rounds"]:
            bits.append('<span class="ml-note">wants '
                        + "/".join(f"R{r}" for r in o["barter_rounds"][:3])
                        + " — buyer holds them</span>")
        return " ".join(bits)

    market = "".join(
        "<tr>"
        f'<td>{e(c["buyer"])}{" <b>(HARD)</b>" if c["hard"] else ""}</td>'
        f'<td class="ml-num">R{c["round"]}</td>'
        f'<td>{e(c["for_player"])}</td>'
        f'<td>{seller_txt(c["sellers"][0]) if c["sellers"] else "—"}</td>'
        f'<td>{", ".join(seller_txt(o) for o in c["sellers"][1:3]) or "—"}</td>'
        f'<td class="ml-num">{("#%d" % c["my_rank"]) if c["my_rank"] else "—"}</td>'
        "</tr>"
        for c in res["seat_market"]) or (
        '<tr><td colspan="6" class="ml-empty">No seat demand — every '
        "keeper has a home.</td></tr>")

    return f"""<section class="ml-panel" id="pick-squeeze">
<h2>Pick Squeeze — who is missing the pick their keeper needs</h2>
<p class="ml-serial">KEEPER SEAT DEMAND vs PICK OWNERSHIP ·
{e(res["meta"]["generated"])}</p>
<div class="ml-h-label">Hard squeezes — carryover keeper, no seat
(must buy or lose him)</div>
<table class="ml-table ml-table--compact">
<thead><tr><th>Manager</th><th>Keeper at risk</th>
<th class="ml-num">Needs</th><th class="ml-num">Worth</th>
<th class="ml-num">Owned there</th></tr></thead>
<tbody>{rows_hard}</tbody></table>
<div class="ml-h-label">Blocked alternates — they'd buy a pick to keep
both (your sales leads)</div>
<table class="ml-table ml-table--compact">
<thead><tr><th>Manager</th><th>Wants to also keep</th>
<th class="ml-num">Needs</th><th class="ml-num">Worth (GUAP)</th>
<th>Cheap out (house rule)</th><th>Your position</th></tr></thead>
<tbody>{rows_blocked}</tbody></table>
<div class="ml-h-label">The seat market — natural pairs (who undercuts
whom)</div>
<table class="ml-table ml-table--compact">
<thead><tr><th>Buyer</th><th class="ml-num">Seat</th><th>To keep</th>
<th>Natural partner</th><th>Also can sell</th>
<th class="ml-num">My rank</th></tr></thead>
<tbody>{market}</tbody></table>
<p class="ml-fineprint">Natural partner = best FIT, not just a free seat:
a SPARE (seller owns two of the round) costs nothing structural to sell,
and barter fit means the seller is missing exactly the rounds the buyer
holds doubles of — payable in scraps. A full pick set is NOT a monopoly:
whoever holds a spare undercuts you. Demand for a keeper's round is
inelastic — there is no substitute pick, which is exactly what makes
these seats sellable above chart value. Waiver keeps all cost R15, so the R15 seat is the scarcest
asset in the league. Based on PREDICTED keepers until the league locks
(then data/keepers_2026_actual.json takes over); house rule (confirmed): a keeper
missing its exact round seats at the next EARLIER owned free round — so
sell against the BUMP TAX and the burned draft slot, not the keeper's
full value. Only a manager with no earlier free round is truly squeezed.
The empirical value curve is negative past ~R9 (a typical
late pick returns a below-replacement player), so most bump taxes floor
to zero: in THIS league, keeper seats are close to free and late-round
pick trades move almost no expected value — the pick market that
matters is R1-R8. League convention: pick trades run EQUAL COUNT both ways (e.g. R1+R17
for R3+R5) — structure any seat sale as a same-count package where the
round-quality difference carries the price.</p>
{position_block(res)}
</section>
"""


def position_block(res: dict) -> str:
    """THE POSITION MARKET — within-round pick-position arbitrage
    (user insight, Jul 2026): keeper seats are ROUND-granular, so a
    keeper-consumed pick's position inside its round is worthless to
    its owner and worth real board access to anyone drafting there."""
    e = _html.escape
    pm = res.get("position_market") or {}
    sell, buy = pm.get("sell") or [], pm.get("buy") or []
    if not (sell or buy):
        return ""
    sell_rows = "".join(
        f'<tr><td class="ml-num">R{s["round"]} &middot; #{s["my_pick"]}</td>'
        + "<td>" + ", ".join(
            f'{e(b["manager"])} <span class="ml-note">#{b["their_pick"]} '
            f'(+{b["spots"]} spots to them)</span>'
            for b in s["buyers"]) + "</td></tr>"
        for s in sell)
    buy_rows = "".join(
        f'<tr><td class="ml-num">R{b["round"]}</td>'
        f'<td>{e(b["seller"])} <span class="ml-note">their dead '
        f'#{b["their_pick"]} vs my #{b["my_pick"]}</span></td>'
        f'<td class="ml-num">+{b["spots"]} spots</td></tr>'
        for b in buy[:8])
    partner = pm.get("package_partner")
    partner_line = (
        f'<p><b>Natural package partner: {e(partner)}</b> '
        f'({pm.get("partner_legs")} complementary legs) — bundle the '
        "same-round swaps into one obviously-fair deal: every leg moves "
        "position from a keeper-dead pick to a live one, both sides "
        "upgrade, nobody gives up anything they can use.</p>"
        if partner else "")
    return f"""
<div class="ml-h-label">The position market — within-round arbitrage
(keeper seats are round-granular)</div>
<div class="ml-h-label">My keeper-dead positions — sell to whoever
drafts later in the round</div>
<table class="ml-table ml-table--compact">
<thead><tr><th class="ml-num">My dead pick</th><th>Buyers (their live
pick)</th></tr></thead><tbody>{sell_rows or
'<tr><td colspan="2" class="ml-empty">no dead positions with buyers</td></tr>'}</tbody></table>
<div class="ml-h-label">Rivals' keeper-dead EARLY positions in my live
rounds — buy the upgrade for scraps</div>
<table class="ml-table ml-table--compact">
<thead><tr><th class="ml-num">Round</th><th>Seller (their dead pick)</th>
<th class="ml-num">My upgrade</th></tr></thead>
<tbody>{buy_rows or
'<tr><td colspan="3" class="ml-empty">no early dead positions available</td></tr>'}</tbody></table>
{partner_line}
<p class="ml-fineprint">Why this is free money: the bump rule prices
keeper costs in ROUNDS, never pick numbers — so within a
keeper-consumed round, pick position is worth zero to the owner and
real board access to a drafter (~8-15 VBD per half-round in live mid
rounds; more when a specific stash target is the prize — R13 is the
ring-fuel round). The snake makes it two-sided: odd rounds favor early
slots, even rounds reverse. Same-round swaps read as obviously fair at
the table. Regrades at keeper lock.</p>"""


def main() -> None:
    res = compute()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "pick_squeeze.json").write_text(json.dumps(res, indent=2))
    (OUT_DIR / "pick_squeeze.html").write_text(build_fragment(res))
    print(f"[pick_squeeze] hard={res['meta']['hard_squeezes']} "
          f"blocked_alternates={res['meta']['blocked_alternates']} "
          f"rounds_in_demand={[m['round'] for m in res['round_market']]}")


if __name__ == "__main__":
    main()
