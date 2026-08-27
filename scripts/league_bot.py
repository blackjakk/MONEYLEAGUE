"""The League Desk — a Q&A bot for the MONEYLEAGUE Sleeper chat.

Runs on any always-on-ish computer (a laptop that sleeps is fine — it
answers while awake, stays quiet while not). Polls the league chat
every few seconds through Sleeper's PRIVATE API using a dedicated bot
account's token, and answers questions addressed to it using the
Anthropic API + the knowledge pack this repo's pipeline builds
(data/bot_knowledge.json — Almanac-grade facts only, no edges).

IMPORTANT — the chat endpoints are Sleeper's undocumented private
API. They can change without notice. First run should be:

    python3 scripts/league_bot.py --probe

which verifies auth + chat read with your token and reports exactly
what works. If probe fails, bring its output back to a Claude session
and the operation shapes below get fixed in one pass (they live in
OPS so nothing else changes). See docs/LEAGUE_BOT.md for setup.

Env vars (or a .env file next to this script):
    SLEEPER_BOT_TOKEN   the bot account's token (docs show how to get)
    ANTHROPIC_API_KEY   for answering questions
    LEAGUE_ID           default: the live 2026 league
    BOT_TRIGGER         word that summons the bot (default: desk)
    ANTHROPIC_MODEL     default: claude-haiku-4-5-20251001
    POLL_SECONDS        default: 5
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATE = Path.home() / ".moneyleague_bot_state.json"
DEFAULT_LEAGUE = "1364055104709230592"
KNOWLEDGE_URL = ("https://raw.githubusercontent.com/blackjakk/MONEYLEAGUE/"
                 "master/data/bot_knowledge.json")
GRAPHQL = "https://sleeper.com/graphql"
ANTHROPIC = "https://api.anthropic.com/v1/messages"

# ---- Sleeper private-API operation shapes (the fragile part) ----
# Each action lists candidate GraphQL operations, tried in order until
# one succeeds; the winner is cached in the state file. --probe prints
# the full response of every candidate so a broken shape is easy to
# diagnose and replace here.
OPS = {
    "me": [
        {"operationName": "initialize_app",
         "query": "query initialize_app { me { user_id display_name } }",
         "variables": {}},
        {"operationName": "my_user",
         "query": "query my_user { my_user { user_id display_name } }",
         "variables": {}},
    ],
    "read": [
        {"operationName": "league_messages",
         "query": "query league_messages($parent_id: String!, $limit: Int) {"
                  " messages(parent_id: $parent_id, limit: $limit) {"
                  " message_id parent_id text user_id created } }",
         "variables": {"parent_id": None, "limit": 20}},
        {"operationName": "get_messages",
         "query": "query get_messages($channel_id: String!, $limit: Int) {"
                  " channel_messages(channel_id: $channel_id, limit: $limit)"
                  " { message_id text user_id created } }",
         "variables": {"channel_id": None, "limit": 20}},
    ],
    "post": [
        {"operationName": "create_message",
         "query": "mutation create_message($parent_id: String!,"
                  " $text: String!, $client_id: String!) {"
                  " create_message(parent_id: $parent_id, text: $text,"
                  " client_id: $client_id) { message_id } }",
         "variables": {"parent_id": None, "text": None, "client_id": None}},
    ],
}

PERSONA = (
    "You are THE LEAGUE DESK, the records clerk of MONEYLEAGUE — a "
    "12-team superflex half-PPR keeper league running since 2011. You "
    "answer questions in the league's group chat.\n"
    "Voice: dry, precise, a banknote engraver who has seen every ledger "
    "line. Light needling is fine — these are old friends — but facts "
    "first, always with the year/number that backs them.\n"
    "Rules:\n"
    "- Answer ONLY from the knowledge pack below. If the books don't "
    "show it, say so plainly. Never invent numbers.\n"
    "- Keep replies SHORT — 1-3 sentences for most questions, a compact "
    "list only when genuinely asked for a table.\n"
    "- Managers go by their short tags (BRI, TREV, COOP...). Map "
    "nicknames via the managers section.\n"
    "- You have no knowledge of anyone's current draft plans, keeper "
    "intentions, or strategy, and you give NO fantasy advice — you are "
    "a historian, not an advisor. Deflect advice questions with the "
    "relevant historical fact instead.\n"
    "- Money figures are the official ledger (dues, pot, tax). PAR = "
    "rest-of-season points above replacement, the league's trade-"
    "grading unit.\n"
)


def _post_json(url: str, payload: dict, headers: dict) -> dict:
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode(),
        headers={"content-type": "application/json", **headers})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())


class SleeperChat:
    def __init__(self, token: str, league_id: str, state: dict):
        self.token = token
        self.league_id = league_id
        self.state = state

    def _gql(self, op: dict, **vars_) -> dict:
        payload = dict(op)
        payload["variables"] = {**op["variables"], **vars_}
        payload["variables"] = {k: v for k, v in
                                payload["variables"].items() if v is not None}
        return _post_json(GRAPHQL, payload,
                          {"authorization": self.token})

    def _try(self, action: str, verbose=False, **vars_):
        cached = self.state.get("ops", {}).get(action)
        order = OPS[action]
        if cached is not None:
            order = [OPS[action][cached]] + [o for i, o in
                                             enumerate(OPS[action])
                                             if i != cached]
        last = None
        for op in order:
            try:
                res = self._gql(op, **vars_)
                if verbose:
                    print(f"[probe] {action} / {op['operationName']}: "
                          + json.dumps(res)[:500])
                if res.get("data") and not res.get("errors"):
                    self.state.setdefault("ops", {})[action] = \
                        OPS[action].index(op)
                    return res["data"]
                last = res
            except Exception as e:                       # noqa: BLE001
                if verbose:
                    print(f"[probe] {action} / {op['operationName']} "
                          f"threw: {e}")
                last = {"error": str(e)}
        if verbose:
            print(f"[probe] {action}: NO candidate worked; last = "
                  + json.dumps(last)[:500])
        return None

    def me(self, verbose=False):
        d = self._try("me", verbose=verbose)
        if not d:
            return None
        node = d.get("me") or d.get("my_user") or {}
        return node

    def read(self, verbose=False) -> list[dict]:
        d = self._try("read", verbose=verbose,
                      parent_id=self.league_id, channel_id=self.league_id)
        if not d:
            return []
        msgs = (d.get("messages") or d.get("channel_messages") or [])
        return sorted(msgs, key=lambda m: m.get("created") or 0)

    def post(self, text: str) -> bool:
        import uuid
        d = self._try("post", parent_id=self.league_id, text=text,
                      client_id=str(uuid.uuid4()))
        return bool(d)


def load_knowledge() -> str:
    local = ROOT / "data" / "bot_knowledge.json"
    try:
        with urllib.request.urlopen(KNOWLEDGE_URL, timeout=20) as r:
            return r.read().decode()
    except Exception:                                    # noqa: BLE001
        if local.exists():
            print("[bot] knowledge fetch failed — using local copy")
            return local.read_text()
        raise


def answer(question: str, context: list[str], knowledge: str,
           api_key: str, model: str) -> str:
    res = _post_json(ANTHROPIC, {
        "model": model,
        "max_tokens": 400,
        "system": PERSONA + "\n\nTHE KNOWLEDGE PACK:\n" + knowledge,
        "messages": [{"role": "user", "content":
                      "Recent chat context:\n" + "\n".join(context[-8:])
                      + "\n\nAnswer this question from the chat:\n"
                      + question}],
    }, {"x-api-key": api_key, "anthropic-version": "2023-06-01"})
    return "".join(b.get("text", "") for b in res.get("content", [])).strip()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--probe", action="store_true",
                    help="verify token + endpoints, print diagnostics")
    ap.add_argument("--dry-run", action="store_true",
                    help="read + answer to stdout, never post")
    args = ap.parse_args()

    envf = Path(__file__).parent / ".env"
    if envf.exists():
        for line in envf.read_text().splitlines():
            if "=" in line and not line.strip().startswith("#"):
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip())

    token = os.environ.get("SLEEPER_BOT_TOKEN")
    if not token:
        sys.exit("SLEEPER_BOT_TOKEN not set (see docs/LEAGUE_BOT.md)")
    league = os.environ.get("LEAGUE_ID", DEFAULT_LEAGUE)
    trigger = os.environ.get("BOT_TRIGGER", "desk").lower()
    poll = int(os.environ.get("POLL_SECONDS", "5"))
    model = os.environ.get("ANTHROPIC_MODEL", "claude-haiku-4-5-20251001")

    state = json.loads(STATE.read_text()) if STATE.exists() else {}
    chat = SleeperChat(token, league, state)

    if args.probe:
        print("[probe] auth check…")
        me = chat.me(verbose=True)
        print(f"[probe] me = {me}")
        print("[probe] chat read check…")
        msgs = chat.read(verbose=True)
        print(f"[probe] read {len(msgs)} messages"
              + (f"; latest: {msgs[-1].get('text', '')[:80]!r}"
                 if msgs else ""))
        STATE.write_text(json.dumps(state))
        print("[probe] done. If auth or read failed, copy this output "
              "into a Claude session to get OPS fixed.")
        return

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key and not args.dry_run:
        sys.exit("ANTHROPIC_API_KEY not set (see docs/LEAGUE_BOT.md)")

    me = chat.me() or {}
    my_id = me.get("user_id")
    print(f"[bot] running as {me.get('display_name')} ({my_id}) in "
          f"league {league}; trigger '{trigger}'; "
          f"{'DRY RUN' if args.dry_run else 'live'}")

    knowledge = load_knowledge()
    k_loaded = time.time()
    seen: set[str] = set(state.get("seen", []))
    first_pass = True
    trig_re = re.compile(rf"(^|\W)@?{re.escape(trigger)}(\W|$)", re.I)

    while True:
        try:
            msgs = chat.read()
            for m in msgs:
                mid = m.get("message_id")
                if not mid or mid in seen:
                    continue
                seen.add(mid)
                if first_pass:
                    continue                # never answer the backlog
                text = m.get("text") or ""
                if m.get("user_id") == my_id or not trig_re.search(text):
                    continue
                q = text
                ctx = [x.get("text") or "" for x in msgs if x != m]
                print(f"[bot] Q: {q!r}")
                try:
                    a = answer(q, ctx, knowledge, api_key, model)
                except Exception as e:                   # noqa: BLE001
                    print(f"[bot] answer failed: {e}")
                    continue
                print(f"[bot] A: {a!r}")
                if not args.dry_run and a:
                    if not chat.post(a):
                        print("[bot] POST FAILED — run --probe and "
                              "check the 'post' op shape")
            first_pass = False
            if time.time() - k_loaded > 6 * 3600:
                knowledge = load_knowledge()
                k_loaded = time.time()
            state["seen"] = list(seen)[-500:]
            STATE.write_text(json.dumps(state))
        except KeyboardInterrupt:
            print("\n[bot] stopped")
            return
        except Exception as e:                           # noqa: BLE001
            print(f"[bot] loop error (continuing): {e}")
        time.sleep(poll)


if __name__ == "__main__":
    main()
