# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

A Claude Code plugin (`wdist`) that ships a single slash command, `/wdist`, which generates a shareable daily recap of the user's Claude Code sessions. The directory layout is dictated by Claude Code's plugin spec — `.claude-plugin/plugin.json` and `.claude-plugin/marketplace.json` are the entry points, `commands/*.md` are slash commands, `scripts/` holds anything those commands shell out to.

## Architecture: dumb extractor + smart prompt

The plugin is deliberately split into two pieces that should stay decoupled:

- **`scripts/recap-day.py`** — a dependency-free Python 3 extractor. Walks `~/.claude/projects/<encoded-cwd>/<session-id>.jsonl` (Claude Code's per-session transcripts), filters records to those with timestamps inside the target local-day window, and emits a compact JSON document to stdout. **No summarization happens here.** Its job is purely to surface raw signal (titles, first/last messages, prompt list, counts, cwd) with sensitive payloads truncated to fixed byte limits.

- **`commands/wdist.md`** — the slash command. Parses `$ARGUMENTS` (an optional `YYYY-MM-DD` date and an optional `--verbose` flag), runs the extractor, reads the JSON from `/tmp/recap-${DATE}.json`, then instructs Claude to synthesize the recap. **All editorial logic — tone, what counts as "shipped" vs. "in progress", redaction rules, short-vs-verbose format — lives in this prompt.** If you're tempted to add summarization logic to the Python script, push it into the prompt instead; if you're tempted to add a heavy dependency, find another way.

Output is written to `~/claude-recaps/YYYY-MM-DD.md` (overwrite on re-run is expected) and also rendered inline in the chat for copy-paste.

## Working on the extractor

Run it directly to iterate without going through the slash command:

```bash
python3 scripts/recap-day.py                # today
python3 scripts/recap-day.py 2026-04-15     # specific date
python3 scripts/recap-day.py 2026-04-15 | jq '.sessions[0]'
```

Constraints to preserve:

- **No `pip install`.** Standard library only. Users install the plugin and it must run on whatever Python 3 they have.
- **Top-level session JSONLs only.** The glob is `~/.claude/projects/*/*.jsonl` — don't recurse into subdirectories (those hold subagent transcripts and would double-count).
- **Day-window filtering is per-record, not per-file.** Sessions can span multiple days; filtering by file mtime alone is wrong. The mtime check is only a cheap pre-filter to skip files that can't possibly contain target-day records.
- **Timestamp comparison is lexicographic against naive ISO strings.** `recap-day.py` strips the trailing `Z` and compares against `day_start_iso`/`day_end_iso` rather than parsing every line. Keep it that way — parsing per line was measurably slower on large transcript directories.
- **`is_meta_user` filter.** Wrapped non-prompt user records (system reminders, slash-command invocations, interrupt notices) must not count as user turns or land in `first_user` / `user_prompts`. If you see real prompts being filtered or meta records leaking through, that's the place to look.

## Working on the prompt

`commands/wdist.md` has two output formats — **short** (default, Slack-friendly, no headers/footers/identifiers) and **verbose** (`--verbose`, full markdown report). When changing format rules:

- The short-mode rules (3–7 bullets, strip identifiers, no footer, Slack-style single-asterisk bold) are load-bearing — they're what makes the output paste-able into a DM without editing. Don't loosen them casually.
- Verbose mode is where commit hashes, PR numbers, and run IDs are allowed and encouraged — but only when they appear in `last_assistant`. The prompt explicitly forbids inventing them.
- Both formats redact lightly (drop ARNs, tenant URLs, customer IDs); keep that rule when adding new format guidance.

## Releasing

Version lives in **two** places that must stay in sync:

- `.claude-plugin/plugin.json` → `version`
- `.claude-plugin/marketplace.json` → both `metadata.version` and `plugins[0].version`

After editing the plugin, end users need to `/reload-plugins` (and sometimes restart Claude Code) for the command to pick up changes.
