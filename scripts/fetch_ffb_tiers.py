#!/usr/bin/env python3
"""Fetch fantasyfootballtiers.com clustered consensus tiers
(user-requested). Boris-Chen-style tier clustering of expert consensus
— the marginal signal vs raw ranks is the TIER BREAK LOCATIONS: at a
live draft, rivals running tier sheets panic when a tier is about to
empty, so the crowd's tier boundaries are a run-trigger map.

Half-PPR variants where offered; QB list is 1QB-ordered (usable for
tier GROUPING, not for superflex pricing). Output:
data/rankings_tiers.json {pos: [{tier, players: [...]}, ...]} —
cache-first per position on fetch/parse failure.
"""
from __future__ import annotations

import html as _html
import json
import re
import urllib.request
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "rankings_tiers.json"
BASE = "https://fantasyfootballtiers.com/gallery_files"
PAGES = {"QB": "QB.html", "RB": "RB-HALF.html",
         "WR": "WR-HALF.html", "TE": "TE-HALF.html"}
TIER_RE = re.compile(r"<li>\s*Tier\s+(\d+):(.*?)</li>", re.S)


def parse(raw: str) -> list[dict]:
    out = []
    for m in TIER_RE.finditer(raw):
        names = _html.unescape(m.group(2))
        names = re.sub(r"<[^>]+>", "", names)
        players = [n.strip() for n in names.split(",") if n.strip()]
        if players:
            out.append({"tier": int(m.group(1)), "players": players})
    return out


def main() -> None:
    prior = {}
    if OUT.exists():
        try:
            prior = json.loads(OUT.read_text()).get("tiers", {})
        except json.JSONDecodeError:
            pass
    tiers, fetched, kept = {}, [], []
    for pos, page in PAGES.items():
        try:
            req = urllib.request.Request(f"{BASE}/{page}",
                                         headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                rows = parse(resp.read().decode("utf-8", "replace"))
            if len(rows) < 3:
                raise ValueError(f"only {len(rows)} tiers parsed")
            tiers[pos] = rows
            fetched.append(f"{pos}:{len(rows)}t")
        except Exception as exc:                    # noqa: BLE001
            if pos in prior:
                tiers[pos] = prior[pos]
                kept.append(f"{pos} ({exc}; cached)")
            else:
                kept.append(f"{pos} MISSING ({exc})")
    OUT.write_text(json.dumps({
        "meta": {"source": "fantasyfootballtiers.com (clustered expert "
                           "consensus, half-PPR; QB list is 1QB-ordered)",
                 "fetched": str(date.today())},
        "tiers": tiers}, indent=1))
    print(f"[tiers] fetched {', '.join(fetched) or 'nothing'}"
          + (f"; fallback: {'; '.join(kept)}" if kept else "")
          + f" -> {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
