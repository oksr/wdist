---
description: What did I ship today? — generate a shareable daily recap of your Claude Code sessions
argument-hint: "[YYYY-MM-DD] [--verbose]   (defaults to today, short Slack-friendly format)"
---

You are generating a daily work recap from the user's Claude Code session
transcripts. The recap is intended to be **pasted into Slack** for a
manager, team lead, or colleague — so write it for a human reader, not a
log dump.

## Step 1 — Parse arguments and extract data

`$ARGUMENTS` may contain a date (`YYYY-MM-DD`), a `--verbose` flag, both,
or neither. Default mode is **short** (Slack-friendly). `--verbose`
switches to the long form.

Run the extractor:

```bash
mkdir -p ~/claude-recaps
ARGS="$ARGUMENTS"
VERBOSE=0
DATE=""
for tok in $ARGS; do
  case "$tok" in
    --verbose|-v) VERBOSE=1 ;;
    *) DATE="$tok" ;;
  esac
done
DATE="${DATE:-$(date +%F)}"
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/recap-day.py" "$DATE" > "/tmp/recap-${DATE}.json"
echo "VERBOSE=$VERBOSE DATE=$DATE"
```

Then read `/tmp/recap-${DATE}.json`. It contains one entry per session
that had activity on the target date, with:

- `title` — auto-generated session title (the best summary signal)
- `cwd` — which project the session ran in
- `start` / `end` — ISO timestamps (use these to build a timeline)
- `user_turns` / `assistant_turns` — rough effort proxy
- `first_user` — the opening prompt (the ask)
- `last_assistant` — Claude's final message (often the outcome)
- `user_prompts` — up to 20 user prompts in order (for theme synthesis)

## Step 2 — Synthesize the recap

Pick the format based on `VERBOSE`.

### Short format (default — for Slack)

A scannable message someone can read in 10 seconds. No big headers, no
section dividers, no footer. Plain prose + a few tight bullets.

```markdown
_What I shipped — {DATE} ({weekday})_
{One-sentence TL;DR naming the day's main thread.}

• _{Outcome}_ — {one short clause}. {`abc1234` / PR #123 if mentioned.}
• _{Outcome}_ — {one short clause}.
• _{Outcome}_ — {one short clause}.

_In progress:_ {one line, only if there's something mid-flight worth flagging — otherwise omit this line entirely.}
```

Short-format rules:

1. **3–10 bullets max.** If you have more, collapse harder. The reader is
   skimming on their phone.
2. **One short clause per bullet.** No sub-bullets, no parentheticals
   stacked on parentheticals. If it doesn't fit on one line in Slack,
   it's too long.
3. **Use Slack-style bold** (`*text*`, single asterisks) for the title
   and bullet leads, since this is meant to paste into Slack.
4. **Drop the "In progress" line entirely** if there's nothing meaningful
   in flight. Don't write "_In progress:_ nothing".
5. **No "Notes & followups" section in short mode.** If a followup is
   important enough to mention, fold it into a bullet or the TL;DR.
6. **No footer / session count / generation note.** This is a chat
   message, not a report.

### Verbose format (`--verbose`)

The full report — for when the user wants the detailed version.

```markdown
# What I shipped on {DATE} ({weekday})

**TL;DR:** {one or two sentences naming the day's dominant themes and
biggest outcomes — the line a manager would skim first.}

## Shipped

- **{Outcome in plain English}** — {one-line context}. {Commit `abc1234`
  / PR #123 / run ID if mentioned in `last_assistant`.}
- ...

## In progress

- **{What's still moving}** — {where it stands, what's next.}
- ...

## Notes & followups

- {Decisions made, gotchas surfaced, things to revisit. Skip the section
  if there's nothing worth flagging.}

---

_{N} Claude Code sessions across {project list}. Generated from local
transcripts; references and commit hashes pulled from session output and
should be verified before quoting externally._
```

### Synthesis rules (both formats)

1. **Group by outcome, not by session.** Multiple sessions on the same
   feature collapse into one bullet. The reader cares about what got done,
   not how many tabs you had open.
2. **Lead with verbs and outcomes.** "Shipped X", "Fixed Y", "Decided Z" —
   not "Worked on X" or "Discussed Y".
3. **Quote concrete references** (commit hashes, PR numbers, CI run IDs,
   file paths) when they appear in `last_assistant`. They make the recap
   verifiable. Do not invent any.
4. **"Shipped" means it landed** — committed, deployed, or merged.
   Investigations, debugging that ended in a finding, and design docs also
   count as shipped if they reached a conclusion. Mid-flight work goes in
   "In progress".
5. **Redact lightly for sharing.** Keep commit hashes, PR numbers, file
   paths, and feature names. Drop or generalize: customer/account IDs,
   ARNs, internal API URLs with tenant identifiers, anything that looks
   like a secret. When in doubt, generalize.

## Step 3 — Write the file and report

Write the synthesized markdown to `~/claude-recaps/{DATE}.md` (overwrite
if it exists — re-runs are expected). In short mode, also write the
verbose file path is the same — short mode replaces it.

Then in your final reply to the user:

1. Print a one-line summary: `Recap for {DATE} written to ~/claude-recaps/{DATE}.md ({N} sessions{, verbose if applicable}).`
2. Show the rendered markdown inline so they can copy directly without
   opening the file.
3. Do not narrate the steps you took — just deliver the recap.
