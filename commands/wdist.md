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

Then read `/tmp/recap-${DATE}.json`. It contains a `sessions` array (one
entry per session with activity on the target date) and a `releases`
array (GitHub releases published on the target date in any repo a
session ran in).

Per session:

- `title` — auto-generated session title (the best summary signal)
- `cwd` — which project the session ran in
- `start` / `end` — ISO timestamps (use these to build a timeline)
- `user_turns` / `assistant_turns` — rough effort proxy
- `first_user` — the opening prompt (the ask)
- `last_assistant` — Claude's final message (often the outcome)
- `user_prompts` — up to 20 user prompts in order (for theme synthesis)

Per release:

- `repo` — `owner/name`
- `tag` / `name` — release tag and display name
- `url` — link to the release page (verbose mode only)
- `published_at` — ISO timestamp
- `prerelease` — true for GitHub prereleases (often staging/RC builds)

The `releases` array may be empty (no deploys, or `gh` unavailable/unauth'd).

## Step 2 — Synthesize the recap

Pick the format based on `VERBOSE`.

### Short format (default — for Slack)

A scannable message someone can read in 10 seconds. No big headers, no
section dividers, no footer. Plain prose + a few tight bullets.

```markdown
_What I shipped — {DATE} ({weekday})_
{One-sentence TL;DR naming the day's main thread.}

• _{Outcome}_ — {one short clause}.
• _{Outcome}_ — {one short clause}.
• _{Outcome}_ — {one short clause}.

_In progress:_ {one line, only if there's something mid-flight worth flagging — otherwise omit this line entirely.}
```

Short-format rules:

1. **3–7 bullets max.** If you have more, collapse harder. The reader is
   skimming on their phone. When in doubt, cut.
2. **One short clause per bullet.** No sub-bullets, no parentheticals
   stacked on parentheticals. If it doesn't fit on one line in Slack,
   it's too long. Aim for under ~90 characters per bullet.
3. **Strip identifiers and links.** No commit hashes, no PR numbers, no
   CI run IDs, no URLs, no branch names, no file paths, no ticket IDs.
   These belong in verbose mode. Slack readers don't click them.
4. **Use Slack-style bold** (`*text*`, single asterisks) for the title
   and bullet leads, since this is meant to paste into Slack.
5. **Drop the "In progress" line entirely** if there's nothing meaningful
   in flight. Don't write "_In progress:_ nothing".
6. **No "Notes & followups" section in short mode.** If a followup is
   important enough to mention, fold it into a bullet or the TL;DR.
7. **No footer / session count / generation note.** This is a chat
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

### Released

- **{repo}** `{tag}` — {what shipped, in plain English}. [{url}]
- ... _(Omit this subsection if `releases` is empty.)_

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

### Synthesis rules

These apply to both formats unless a rule explicitly scopes itself.

1. **Group by outcome, not by session.** Multiple sessions on the same
   feature collapse into one bullet. The reader cares about what got done,
   not how many tabs you had open.
2. **Lead with verbs and outcomes.** "Shipped X", "Fixed Y", "Decided Z" —
   not "Worked on X" or "Discussed Y".
3. **Quote concrete references** (commit hashes, PR numbers, CI run IDs,
   file paths) when they appear in `last_assistant` — **verbose mode
   only**. They make the long-form recap verifiable. Short mode strips
   them (see short-format rule 3). Do not invent any.
4. **"Shipped" means it landed** — committed, deployed, or merged.
   Investigations, debugging that ended in a finding, and design docs also
   count as shipped if they reached a conclusion. Mid-flight work goes in
   "In progress".
   - **GitHub releases in `releases` are the strongest "shipped" signal** —
     a release means code actually went out. Always surface them. In short
     mode, lead with them when present (e.g. a `*Released:*` bullet near the
     top, repo + tag, no URL). In verbose mode, give them their own
     "Released" subsection under Shipped with tag and URL. Treat
     `prerelease: true` as shipped-to-staging — mention with a
     "(prerelease)" or "(RC)" tag, don't bury it.
   - If a release's tag/name reveals nothing about *what* shipped (e.g. a
     timestamp-only tag like `20260512_0658-prod`), pair it with the
     matching session's `title` or `last_assistant` to describe the change
     in plain English — don't just quote the tag.
5. **Redact lightly for sharing.** Whatever identifiers your chosen
   format keeps (see short-format rule 3 and verbose synthesis rule 3),
   drop or generalize: customer/account IDs, ARNs, internal API URLs
   with tenant identifiers, anything that looks like a secret. When in
   doubt, generalize.

## Step 3 — Write the file and report

Write the synthesized markdown to `~/claude-recaps/{DATE}.md` (overwrite
if it exists — re-runs are expected). Both formats write to the same
path; re-running with `--verbose` replaces the short version and vice
versa.

Then in your final reply to the user:

1. Print a one-line summary: `Recap for {DATE} written to ~/claude-recaps/{DATE}.md ({N} sessions{, verbose if applicable}).`
2. Show the rendered markdown inline so they can copy directly without
   opening the file.
3. Do not narrate the steps you took — just deliver the recap.
