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
array (GitHub releases **personally authored by the current `gh` user**
on the target date, in repos a session ran in — CI-bot releases and
teammates' releases are filtered out).

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
- `author` — the GitHub login that cut the release (always the current
  user; filtering happens in the extractor)

The `releases` array may be empty — and most days it will be. Reasons:
no manual release, `gh` unavailable/unauth'd, or every release in the
relevant repos was cut by CI/teammates. **Empty `releases` is normal,
not a signal something's wrong** — do not mention deploys in that case.

The JSON also contains a `delivery` array: **pull requests personally
authored by the current `gh` user** that saw activity on the target date,
plus a 24-hour forward grace window (a PR you open today and merge tomorrow
morning still counts toward today). Teammates' and bots' PRs are filtered
out in the extractor. Each entry:

- `repo` — `owner/name`; join to a session by matching its `cwd`'s repo
- `number` / `title` / `url` — PR number, title, link (number + url are
  verbose-only)
- `state` — `open`, `closed`, or `merged`
- `merged` — true if it actually merged
- `head_ref` — the PR's branch (use `title` + `head_ref` to match the PR
  to a piece of work)
- `created_at` / `merged_at` / `closed_at` / `updated_at` — ISO timestamps
- `ci` — GitHub Actions runs on the PR's head commit, each with `name`,
  `path`, `status` (`queued` / `in_progress` / `completed`), `conclusion`
  (`success` / `failure` / `timed_out` / `cancelled` / `skipped` / null),
  `event`, and `url`. May be empty (no CI on that commit yet).

Empty `delivery` is normal — no PRs, `gh` unavailable/unauth'd, or only
teammates'/bots' PRs in the relevant repos. **When it's empty, classify
every outcome as local-only and don't mention PR or CI state at all** —
the recap reads exactly as it did before delivery state existed.

## Step 2 — Synthesize the recap

Pick the format based on `VERBOSE`.

### Short format (default — for Slack)

A scannable message someone can read in 10 seconds. No big headers, no
section dividers, no footer. Plain prose + a few tight bullets.

```markdown
_What I shipped — {DATE} ({weekday})_
{One-sentence TL;DR naming the day's main thread}{ — short delivery clause, e.g. "2 merged, 1 in review"; include only when there's delivery state to report, omit entirely on a local-only day}.

• _{Outcome}_ {(merged) | (PR open) | (CI failed) — only when a PR confidently matches this work; omit the marker for local-only} — {one short clause}.
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
   These belong in verbose mode. Slack readers don't click them. The
   delivery-state markers `(merged)` / `(PR open)` / `(CI failed)` are
   *states, not identifiers* — keep them; just strip the PR number, URL,
   and branch behind them.
4. **Use Slack-style bold** (`*text*`, single asterisks) for the title
   and bullet leads, since this is meant to paste into Slack.
5. **Drop the "In progress" line entirely** if there's nothing meaningful
   in flight. Don't write "_In progress:_ nothing".
6. **No "Notes & followups" section in short mode.** If a followup is
   important enough to mention, fold it into a bullet or the TL;DR.
7. **No footer / session count / generation note.** This is a chat
   message, not a report.
8. **Delivery markers are inline and terse.** Append at most one state
   marker to a bullet's outcome lead — `*Outcome* (merged) — clause` —
   following the matching and precedence rules in synthesis rule 5. The
   marker counts toward the ~90-char budget (rule 2); if it pushes a bullet
   over, tighten the clause. Local-only work gets no marker.
9. **When over the 3–7 bullet budget, cut by delivery priority.** Keep, in
   order: released/merged (landed) → CI-failed (a blocker worth flagging) →
   PR-open (in flight) → local-only. Drop from the bottom. Lead with wins;
   don't bury a red pipeline.
10. **TL;DR delivery clause.** When there's delivery state to report, end the
    TL;DR with a short clause summarizing it (e.g. "— 2 merged, 1 in
    review"). Keep it thematic first, counts second. On a local-only day,
    omit the clause entirely — the TL;DR stays exactly as it was pre-v0.3.0.

### Verbose format (`--verbose`)

The full report — for when the user wants the detailed version.

```markdown
# What I shipped on {DATE} ({weekday})

**TL;DR:** {one or two sentences naming the day's dominant themes and
biggest outcomes — the line a manager would skim first.}

## Shipped

- **{Outcome in plain English}** {(merged) if a PR for it merged} —
  {one-line context}. {PR #123 / commit `abc1234` / run ID when present in
  `last_assistant` or the delivery entry.}
  - _failed: {run name}_ [{url}] — only if a merged PR's own CI then went
    red (see synthesis rule 5); omit otherwise.
- ...

### Released

- **{repo}** `{tag}` — {what shipped, in plain English}. [{url}]
- ... _(Omit this subsection if `releases` is empty.)_

## In progress

- **{What's still moving}** {(PR open) | (CI failed)} — {where it stands,
  what's next; for CI failed, name the failing run and link it [{url}]}.
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
5. **Classify each outcome's delivery state** from the `delivery` array.
   Match a PR to an outcome using its `title` and `head_ref`. **If you
   can't confidently match a PR to a piece of work, attach no marker —
   never guess.** The states, in terminal-precedence order (when one
   outcome touched several PRs or runs, show only the most-terminal):

   - **merged** (`merged: true`) — the strongest "did it ship" signal after
     a release. Short: inline `(merged)`. Verbose: under **Shipped**.
   - **CI failed** — an **open** PR whose `ci` has a run with `conclusion`
     `failure` or `timed_out`. Ignore `cancelled` / `skipped` (often
     intentional); treat `in_progress` / `queued` as *running*, not failed.
     Short: inline `(CI failed)`. Verbose: under **In progress**, as blocked.
   - **PR open** — an open PR with no failing run (passing or still running).
     Short: inline `(PR open)`. Verbose: under **In progress**.
   - **local-only** — work with no matching PR (or only a closed-unmerged
     one — see below). No marker; reads exactly as it did pre-v0.3.0.

   **Precedence: merged > CI failed > PR open > local-only.** A single PR
   that merged but whose own CI then went red shows `(merged)` in short
   mode; in verbose, add a sub-line under the merged entry naming the failed
   run with its `url`. **There is no prod / "shipped to prod" marker in
   v0.3.0** — CI is pass/fail/running only; don't invent one.

   - **Closed without merging:** default to local-only and don't mention the
     PR. Surface a closed PR *only* when the **session transcript** shows you
     deliberately closed / abandoned / superseded it — then give it one line
     phrased as the decision ("Dropped the X approach — Y won out"), not a
     bare "(closed)". If a closed PR was superseded by a **merged** PR in the
     same window (similar `title` / `head_ref`), the work shipped — fold it
     into the merged bullet and never show "closed".
   - **Merged with no same-day session** (the grace window surfaced a PR you
     merged today but coded earlier): give it its own "shipped" bullet,
     described from the PR `title`. A merge is a real ship event even when
     the work predates today.

6. **Redact lightly for sharing.** Whatever identifiers your chosen
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
