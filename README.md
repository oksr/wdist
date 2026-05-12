# What did I ship today?

A Claude Code plugin that generates a shareable daily recap of your Claude Code sessions. The default output is short and Slack-friendly — a few bullets you can paste straight into a DM with your manager or team lead. Pass `--verbose` when you want the full report.

## What you get

Run `/wdist` at the end of the day and Claude reads every session you ran today (across every project), groups them by outcome, and produces something shaped like this (fictional example):

```
*What I shipped — 2026-04-15 (Wednesday)*
Mostly cart-checkout work — landed the new tax calculator, fixed two address-form regressions, unblocked mobile on the payment SDK.

• *Tax calculator v2* — committed `1a2b3c4`, handles the EU VAT cases the old lookup rounded wrong.
• *Address form regression* — PR #482, Safari autocomplete was eating the first character.
• *Payment SDK upgrade unblocked for mobile* — migration notes published, mobile can pick up 4.x.

_In progress:_ checkout funnel A/B — variant assignment isn't reading the cookie correctly yet.
```

Run `/wdist --verbose` for the full structured report (TL;DR, Shipped / In progress / Notes & followups sections, session footer):

```markdown
# What I shipped on 2026-04-15 (Wednesday)

**TL;DR:** Mostly cart-checkout work - landed the new tax calculator,
fixed two regressions in the address form, and unblocked the mobile team
on the payment SDK upgrade.

## Shipped

- **Tax calculator v2** - committed `1a2b3c4`; replaces the legacy
  rate-table lookup with the new vendor SDK. Handles the EU VAT cases the
  old one was rounding wrong.
- **Address form regression fix** - PR #482, the autocomplete dropdown
  was eating the first character on Safari.
- **Payment SDK upgrade unblocked for mobile** - published the migration
  notes to the team wiki; mobile can pick up `4.x` now.

## In progress

- **Checkout funnel A/B** - wiring still mid-flight; test harness done
  but the variant assignment isn't reading the cookie correctly yet.

## Notes & followups

- We're still seeing the duplicate-charge edge case on stripe webhook
  retries; not a regression but worth a focused session.

---

_7 Claude Code sessions across `web` and `mobile`._
```

Output is also written to `~/claude-recaps/YYYY-MM-DD.md` so you can copy it later without re-running.

## Install

```
/plugin marketplace add oksr/wdist
/plugin install wdist@wdist
/reload-plugins
```

Restart Claude Code if the command doesn't show up immediately after /reload-plugins.

## Usage

```
/wdist                            # short Slack-friendly recap of today
/wdist 2026-04-15                 # short recap of a specific date
/wdist --verbose                  # full structured report for today
/wdist 2026-04-15 --verbose       # full report for a specific date
```

## How it works

Claude Code stores per-session JSONL transcripts at `~/.claude/projects/<encoded-cwd>/<session-id>.jsonl`. The plugin's extractor walks those files, filters to records with timestamps inside the target date (so continued multi-day sessions don't pollute the result), and emits a compact JSON document. The `/wdist` command then asks Claude to synthesize it into the format above.

The extractor is dependency-free Python 3 - no `pip install` needed.

## What gets read vs. shared

- **Read locally:** session titles, your prompts, Claude's final message per session, message counts, project paths.
- **Written locally:** `~/claude-recaps/YYYY-MM-DD.md`.
- **Sent anywhere:** nothing automatic. You copy and paste.

The synthesis prompt instructs Claude to redact obvious sensitive bits (ARNs, tenant URLs, customer IDs) before producing the markdown, but **review the output before sharing externally** - your sessions almost certainly contain things you don't want in a public Slack channel.

## Tweaking the format

The output format lives in `commands/wdist.md`. Edit the "Synthesize the recap" section to change tone, structure, or what counts as "shipped" vs. "in progress." The extractor is intentionally dumb - all the editorial logic is in the prompt.

## Updates

Installed plugins auto-update on Claude Code startup, so you'll pick up new versions automatically. To force an update right now:

```
/plugin update wdist@wdist
```

See [CHANGELOG.md](CHANGELOG.md) for what's new in each release.

## License

MIT - see [LICENSE](LICENSE).
