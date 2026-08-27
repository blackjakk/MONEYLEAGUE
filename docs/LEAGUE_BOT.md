# The League Desk — Sleeper chat bot

A Q&A bot for the MONEYLEAGUE Sleeper chat. Anyone in the league types
a message containing **desk** (e.g. *"desk, who's won the most
money?"*) and it answers from the league record — champions,
standings, the purse and tax ledgers, tank years, biggest trades,
head-to-heads, rules. It knows ONLY what the Almanac already
publishes: no draft plans, no keeper predictions, no edges.

It runs on your own computer. While the machine is awake it answers
within seconds; when the machine sleeps, the bot sleeps (it never
answers old backlog when it wakes, so no spam).

## One-time setup (~15 minutes)

### 1. Make the bot its own Sleeper account
Create a fresh Sleeper account (new email) named something like
**League Desk**. Then add it to the league so it can read/post chat:
easiest is inviting it as a **co-owner of your team** (Team Settings →
add co-owner) — chat access, no roster slot.

Never run the bot on your own personal account token.

### 2. Get the bot account's token
Log into sleeper.com in a browser **as the bot account**, open
DevTools (F12) → Application/Storage → Local Storage →
`https://sleeper.com` → copy the value of the `token` entry.
(Alternatively: Network tab, any `graphql` request, copy the
`authorization` header.)

Treat this token like a password. It expires rarely; if the bot ever
401s, grab a fresh one the same way.

### 3. Get an Anthropic API key
console.anthropic.com → API keys. The bot uses Haiku; a chatty league
costs pennies per week. Put $5 on the account and forget it.

### 4. Configure
Create `scripts/.env` (this file is gitignored — never commit it):

```
SLEEPER_BOT_TOKEN=eyJ...
ANTHROPIC_API_KEY=sk-ant-...
# optional overrides:
# LEAGUE_ID=1364055104709230592
# BOT_TRIGGER=desk
# POLL_SECONDS=5
```

### 5. Probe first (important)
The chat API is Sleeper's **private, undocumented** API — the public
one is read-only. The exact request shapes can drift. Verify yours
works before going live:

```
python3 scripts/league_bot.py --probe
```

You want to see your bot's display name and a page of real chat
messages. **If either fails, paste the probe output into a Claude
session** — the operation shapes live in one `OPS` dict at the top of
`scripts/league_bot.py` and get fixed in one pass.

### 6. Dry run, then live

```
python3 scripts/league_bot.py --dry-run   # answers print locally only
python3 scripts/league_bot.py             # live
```

Leave it running in a terminal. On a Mac, `caffeinate -i python3
scripts/league_bot.py` keeps the machine from idling mid-session; on
Windows, a plain terminal window is fine.

## How it stays current

The knowledge pack (`data/bot_knowledge.json`) is rebuilt by the
weekly pipeline and committed; the bot re-fetches it from GitHub every
6 hours, so a bot running on your laptop self-updates as the season
progresses — 2026 standings, tax tape, and stories fold in once the
season is live, with zero bot maintenance.

## Honest caveats

- Private API: Sleeper can change or close these endpoints whenever.
  The bot fails quiet (logs, keeps polling) — if it stops answering,
  run `--probe` again.
- The token is a real login credential for the bot account. Keep it in
  `.env`, nowhere else.
- The bot answers anyone in the league, so its knowledge boundary is
  the point: Almanac facts only. Don't add desk intel to the pack.
