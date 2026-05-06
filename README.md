# wdist — What did I shipped today?

A Claude Code plugin that generates a shareable daily recap of your Claude Code sessions. Designed to land in the sweet spot between a standup update and a highlight reel — concrete, scannable, ready to paste into Slack for your manager or teammates.

## What you get

Run `/wdist` at the end of the day and Claude reads every session you ran today (across every project), groups them by outcome, and produces something shaped like this (fictional example):

```markdown
# What I shipped on 2026-04-15 (Wednesday)

**TL;DR:** Mostly cart-checkout work — landed the new tax calculator,
fixed two regressions in the address form, and unblocked the mobile team
on the payment SDK upgrade.

## Shipped
- **Tax calculator v2** — committed `1a2b3c4`; replaces the legacy
  rate-table lookup with the new vendor SDK. Handles the EU VAT cases the
  old one was rounding wrong.
- **Address form regression fix** — PR #482, the autocomplete dropdown
  was eating the first character on Safari.
- **Payment SDK upgrade unblocked for mobile** — published the migration
  notes to the team wiki; mobile can pick up `4.x` now.

## In progress
- **Checkout funnel A/B** — wiring still mid-flight; test harness done
  but the variant assignment isn't reading the cookie correctly yet.

## Notes & followups
- We're still seeing the duplicate-charge edge case on stripe webhook
  retries; not a regression but worth a focused session.

---
*7 Claude Code sessions across `web` and `mobile`.*
```

Output is also written to `~/claude-recaps/YYYY-MM-DD.md` so you can copy it later without re-running.

## Install

```
/plugin marketplace add oksr/wdist
/plugin install wdist@wdist
```

Restart Claude Code if the command doesn't show up immediately.

## Usage

```
/wdist                  # recap of today
/wdist 2026-04-15       # recap of a specific date
```

## How it works

Claude Code stores per-session JSONL transcripts at `~/.claude/projects/<encoded-cwd>/<session-id>.jsonl`. The plugin's extractor walks those files, filters to records with timestamps inside the target date (so continued multi-day sessions don't pollute the result), and emits a compact JSON document. The `/wdist` command then asks Claude to synthesize it into the format above.

The extractor is dependency-free Python 3 — no `pip install` needed.

## What gets read vs. shared

- **Read locally:** session titles, your prompts, Claude's final message per session, message counts, project paths.
- **Written locally:** `~/claude-recaps/YYYY-MM-DD.md`.
- **Sent anywhere:** nothing automatic. You copy and paste.

The synthesis prompt instructs Claude to redact obvious sensitive bits (ARNs, tenant URLs, customer IDs) before producing the markdown, but **review the output before sharing externally** — your sessions almost certainly contain things you don't want in a public Slack channel.

## Tweaking the format

The output format lives in `commands/wdist.md`. Edit the "Synthesize the recap" section to change tone, structure, or what counts as "shipped" vs. "in progress." The extractor is intentionally dumb — all the editorial logic is in the prompt.

## License

MIT — see [LICENSE](LICENSE).
