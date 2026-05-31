# Changelog

All notable changes to `wdist` are documented here. This project follows [Semantic Versioning](https://semver.org/) and the [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) format.

To pull the latest version: `/plugin update wdist@wdist`. Auto-update on Claude Code startup is opt-in — enable it via `/plugin` → Marketplaces → `wdist`.

## [Unreleased]

### Added
- **Learnings mode — `/wdist what i learned`.** A second recap that answers *what did I learn* (discovered facts and gotchas) rather than what shipped. Triggered by a natural-language phrase (`what i learned`, `what did i learn`, `learnings`) or the `--learned` flag, under the existing single `/wdist` command — it composes with all the usual dates and ranges (`/wdist what i learned last week`).
  - **Default output is a specifics-rich personal log** for future-you — it *keeps* file paths, function names, and root causes (the inverse of the shipped recap, which strips identifiers for Slack). Learnings are grouped by **topic**, not session, with user-confirmed learnings ("you're right") surfaced first. `--share` produces a condensed, redacted TIL for posting to a team channel.
  - `recap-day.py` gains a `--learnings` flag that emits a per-session, order-preserving interleaved dump of user + assistant turns (so a confirmation stays attached to the claim it answers), keep-every-turn with asymmetric per-turn caps and shrink-don't-drop budgeting. Learnings mode skips the `gh` delivery/releases joins (pure "shipped" signal), so it's faster and network-free. The default shipped output is byte-for-byte unchanged.
  - Learnings recaps are written to `~/claude-recaps/{LABEL}-learnings.md` — the `-learnings` suffix guarantees they never overwrite a shipped recap.
  - Synthesis lives in a dedicated `prompts/learned.md`, kept separate from the shipped synthesis in `commands/wdist.md`. Design rationale is recorded in `docs/adr/0001` and `docs/adr/0002`; project glossary in `CONTEXT.md`.

## [0.4.2] - 2026-05-30

### Changed
- History backfill (`load_history_backfill`) now early-exits once the chronological prompt log passes the target window instead of scanning the whole `~/.claude/history.jsonl` — faster on large logs. The window filter and early-exit compare epoch timestamps (not local-time strings), so they stay correct across a DST fall-back, where a local-time ISO string can repeat an hour and break the chronological assumption. Output is unchanged in normal operation (verified equivalent to a full scan across 193 days of a real log).
- Internal cleanup: shared `MAX_PROMPTS` / `MAX_PROMPT_CHARS` constants across the transcript and backfill paths, and simplified the cwd dedup.

## [0.4.1] - 2026-05-30

### Changed
- Added a demo GIF to the README showing `/wdist` generating a daily recap (with a weekly range as a bonus scene). Docs only — no behavior change.

## [0.4.0] - 2026-05-28

### Added
- **Date ranges and natural-language dates.** Beyond a single day, `/wdist` now accepts `yesterday`, `this week`, `last week`, `this month`, `last month` (a.k.a. `monthly`), and explicit ranges like `2026-05-05 to 2026-05-10`. Relative phrases resolve calendar-aligned (`last week` = previous Mon–Sun; `last month` = previous full calendar month). `recap-day.py` takes an inclusive `START [END]`; single-day behavior is unchanged.
- **Multi-day format.** A week or month is synthesized into themes (not a daily log) with the terminal delivery state per theme, split into Shipped vs Still-moving, a TL;DR led by the delivery tally, and — for long spans — the top themes in full with the minor tail rolled up.
- **History backfill past retention.** Claude Code deletes per-session transcripts older than `cleanupPeriodDays` (default 30). For ranges that reach further back, wdist reconstructs those days from the long-lived `~/.claude/history.jsonl` prompt log (a `history` array: project + prompts per day) combined with **live GitHub delivery** (PRs/CI/releases aren't retention-bound). Reconstructed days are thinner — what was worked on + what shipped — and marked as such.

### Notes
- Reconstructed days carry no titles or assistant narrative, only your prompts + delivery state. To keep more full transcripts going forward, raise `cleanupPeriodDays` in `~/.claude/settings.json`.
- Range recaps are written to `~/claude-recaps/{START}_to_{END}.md`.

## [0.3.0] - 2026-05-28

### Added
- **Delivery state.** The recap now answers "did it ship?", not just "what did I do?". The extractor emits a top-level `delivery` array of pull requests **personally authored by the current `gh` user** (server-side author filter), touched on the target date plus a 24-hour forward grace window — so a PR you open today and merge tomorrow morning still counts toward today. Teammates' and bots' PRs are filtered out.
- Each delivery entry carries the PR's `state` / `merged` flag, timestamps, branch, and a `ci` array of the GitHub Actions runs on its head commit (`status` + `conclusion`).
- `commands/wdist.md` classifies each outcome by delivery state — **merged**, **PR open**, **CI failed**, **local-only**, or **released** — with inline `(merged)` / `(PR open)` / `(CI failed)` markers in short mode and a Shipped/In-progress split in verbose. CI is reported as pass/fail/running only; there is no prod/"shipped to prod" marker yet.

### Changed
- Short-mode TL;DR may end with a brief delivery clause (e.g. "2 merged, 1 in review"); markers count toward the ~90-char bullet budget. On a local-only day the recap reads exactly as it did before — no markers, no clause.

### Notes
- Requires `gh` installed and authenticated for delivery state. Without it, `delivery` is empty and every outcome is treated as local-only — the recap degrades gracefully, never errors.

## [0.2.0] - 2026-05-12

### Added
- Recap output now surfaces GitHub Releases published on the target date. The extractor walks each session's cwd for a `github.com` origin and queries `gh release list`, emitting a top-level `releases` array. Skipped silently if `gh` is unavailable or the cwd has no GitHub remote — the rest of the recap is unaffected.
- Release flow: `CHANGELOG.md`, `scripts/release.sh`, and a "Releasing" section in `CLAUDE.md`. Installed copies auto-update on Claude Code startup whenever `version` bumps.

### Changed
- Short-mode format is tighter: 3–7 bullets (down from 3–10), aim for under ~90 characters per bullet, and strip all identifiers (commit hashes, PR numbers, CI run IDs, URLs, branch/file/ticket paths). Identifiers remain in verbose mode where they belong.
- Synthesis rules in `commands/wdist.md` now split between format-shared and short-only, so the "quote concrete references" rule no longer contradicts short mode.

## [0.1.0] - 2026-05-06

### Added
- Initial release. `/wdist` produces a short Slack-friendly daily recap of your Claude Code sessions; `--verbose` produces the full structured report.
- Recap is also written to `~/claude-recaps/YYYY-MM-DD.md` for later reuse.
