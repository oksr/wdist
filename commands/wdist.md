---
description: What did I shipped today? — generate a shareable daily recap of your Claude Code sessions
argument-hint: "[YYYY-MM-DD]   (defaults to today)"
---

You are generating a daily work recap from the user's Claude Code session
transcripts. The recap is intended to be **shared with the user's manager
and a few colleagues** (paste into Slack), so write it for a human reader,
not a log dump.

## Step 1 — Extract the data

Run the extractor script. If `$ARGUMENTS` is provided, pass it as the date;
otherwise default to today.

```bash
mkdir -p ~/claude-recaps
DATE="${ARGUMENTS:-$(date +%F)}"
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/recap-day.py" "$DATE" > "/tmp/recap-${DATE}.json"
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

Write a single markdown document in the **format below**. The tone is
between a standup update and a highlight reel: concrete, scannable, with
verifiable references (commit hashes, PR/run IDs, file paths) when the
session output mentions them.

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
*{N} Claude Code sessions across {project list}. Generated from local
transcripts; references and commit hashes pulled from session output and
should be verified before quoting externally.*
```

### Synthesis rules

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
5. **Keep it tight.** Aim for 5–10 bullets across all sections. If you have
   more, you're being too granular — collapse harder.
6. **Redact lightly for sharing.** Keep commit hashes, PR numbers, file
   paths, and feature names. Drop or generalize: customer/account IDs,
   ARNs, internal API URLs with tenant identifiers, anything that looks
   like a secret. When in doubt, generalize.

## Step 3 — Write the file and report

Write the synthesized markdown to `~/claude-recaps/{DATE}.md` (overwrite
if it exists — re-runs are expected).

Then in your final reply to the user:
1. Print a one-line summary: `Recap for {DATE} written to ~/claude-recaps/{DATE}.md ({N} sessions, {M} bullets).`
2. Show the rendered markdown inline so they can copy directly without
   opening the file.
3. Do not narrate the steps you took — just deliver the recap.
