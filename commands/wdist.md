---
description: What did I ship today? — generate a shareable daily recap of your Claude Code sessions
argument-hint: "[YYYY-MM-DD] [--verbose] | what i learned [--share]   (defaults to today's shipped recap)"
---

You are generating a daily work recap from the user's Claude Code session
transcripts. The recap is intended to be **pasted into Slack** for a
manager, team lead, or colleague — so write it for a human reader, not a
log dump.

## Step 1 — Parse arguments, resolve dates, extract data

First, **detect the recap mode.** `$ARGUMENTS` selects one of two modes:

- **Learnings mode** — if `$ARGUMENTS` contains `--learned`/`--learnings` *or* a
  natural-language learnings phrase (`what i learned`, `what did i learn`,
  `learnings`, `what i've learned`). This recap answers *what did I learn*
  (discovered facts and gotchas), not what shipped.
- **Shipped mode** — anything else (the default). The original recap: *what did
  I ship*.

If **learnings mode**, still resolve the date expression below (resolution is
shared between modes), but run the extractor with the `--learnings` flag and then
**follow `${CLAUDE_PLUGIN_ROOT}/prompts/learned.md` instead of Steps 2–3 here** —
read that file and do exactly what it says. Steps 2–3 of *this* file are the
**shipped**-mode synthesis only.

`$ARGUMENTS` may also contain a `--verbose` flag and an optional date expression:
nothing (= today), a single ISO date (`2026-05-15`), a relative phrase
(`yesterday`, `this week`, `last week`, `this month`, `last month` / `monthly`),
or an explicit range (`2026-05-05 to 2026-05-10`). Default shipped mode is
**short** (Slack-friendly); `--verbose` switches to the long form. (The
learnings-phrase words above are mode selectors, **not** part of the date
expression — strip them before resolving dates. `--share` is a learnings-only
flag, handled in `learned.md`.)

Resolve the date expression to a concrete `START` and `END` (both `YYYY-MM-DD`,
inclusive — equal for a single day). First print today's calendar anchors. This
gets month lengths and leap years right and is portable across macOS/Linux —
**don't compute month/week boundaries by hand:**

```bash
mkdir -p ~/claude-recaps
python3 - <<'PY'
import datetime
t = datetime.date.today()
mon = t - datetime.timedelta(days=t.weekday())          # Monday of this week
this_month = t.replace(day=1)
lm_end = this_month - datetime.timedelta(days=1)         # last day of last month
print("today      ", t, t)
print("yesterday  ", t - datetime.timedelta(days=1), t - datetime.timedelta(days=1))
print("this_week  ", mon, t)
print("last_week  ", mon - datetime.timedelta(days=7), mon - datetime.timedelta(days=1))
print("this_month ", this_month, t)
print("last_month ", lm_end.replace(day=1), lm_end)
PY
```

Map `$ARGUMENTS` to START/END using those anchor rows (calendar-aligned):

- nothing / `today` → today; `yesterday` → yesterday
- a single ISO date → that date (START == END)
- `this week` / `last week` / `this month` / `last month` (a.k.a. `monthly`) →
  the matching anchor row
- `X to Y` (two ISO dates, separated by `to`, `..`, or `-`) → X through Y
- any other span (e.g. `last 2 weeks`, `last 30 days`) → compute it with a
  one-line `python3 -c`, never by hand

`monthly` is a one-shot recap of the previous calendar month — not a recurring
schedule. Then run the extractor with the resolved literal dates:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/recap-day.py" START END > "/tmp/recap-START_to_END.json"
```

substituting the actual dates (e.g. `... 2026-05-19 2026-05-25 > /tmp/recap-2026-05-19_to_2026-05-25.json`).
For a single day `START == END` and the result matches prior single-date
behavior. Note whether `--verbose` was in `$ARGUMENTS`.

**Learnings mode** runs the same extractor with `--learnings` appended and writes
to a distinct `-learnings` file (so it never clobbers a shipped recap), then hands
off to `learned.md`:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/recap-day.py" START END --learnings > "/tmp/recap-START_to_END-learnings.json"
```

Once you've written that file, **stop following this file and read
`${CLAUDE_PLUGIN_ROOT}/prompts/learned.md`** — it owns the rest of learnings mode.

Then read the JSON file you just wrote. Its `start` / `end` fields bound the
recap (equal for a single day; see Step 2 for the single-day vs range split). It
contains a `sessions` array (one entry per session with activity in the range)
and a `releases` array (GitHub releases **personally authored by the current
`gh` user** in the range, in repos a session ran in — CI-bot releases and
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

The JSON also contains a `history` array: lightweight activity recovered from
Claude Code's long-lived global prompt log for days whose **per-session
transcripts have been cleaned up** (Claude Code deletes transcripts older than
`cleanupPeriodDays`, default 30). Each entry — `{cwd, date, prompts, count}` —
is one project on one day with the prompts you typed, but **no titles or
assistant output**, so it's thinner than a `sessions` entry. It's populated only
for ranges that reach past the retention window; recent ranges and single days
have an empty `history` (their `sessions` are complete). Delivery state for these
days is still in `delivery` (gh isn't retention-bound), so a cleaned day can
still show what shipped.

## Step 2 — Synthesize the recap

First decide the span. If the JSON's `start` equals `end`, this is a **single
day** — use the short/verbose formats immediately below. If `start` and `end`
differ, it's a **date range** (a week, month, or custom span) — use the
**Multi-day format** further down. Within either, pick short (default) vs
verbose from `VERBOSE`.

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

### Multi-day format (date ranges)

Used when `start != end` (e.g. `/wdist last week`, `/wdist 2026-05-05 to
2026-05-10`). The delivery-state classification and redaction rules are
unchanged (synthesis rules 5 and 6) — only the shape changes: you're
synthesizing a span, not a day.

Core moves:

1. **Synthesize into themes, not a daily log.** Collapse every session in the
   span into the handful of threads that actually moved. A thread that spanned
   Mon–Thu is ONE bullet, not four. The reader wants "what got done", not a replay.
2. **Roll delivery state up to the terminal state per theme** across the whole
   span (precedence from rule 5: merged > CI failed > PR open > local-only). A
   theme whose PR opened Tuesday and merged Friday is `(merged)`.
3. **Split into Shipped vs Still-moving.** Landed work (merged, released, or
   committed-and-done) goes under *Shipped*; work that's still open, CI-red, or
   mid-flight **as of the end of the range** goes under *Still moving*.
4. **Flat across projects, tag inline.** One Shipped / Still-moving list across
   all repos; note the project on a bullet only where it adds clarity
   (`— mobile`). Don't break into per-project blocks.
5. **Lead the TL;DR with the delivery tally.** One thematic clause + the span's
   tally — the tally is the headline for a range, so always include it.
6. **For long spans, surface the top themes and roll up the tail.** A month can
   have 20+ threads; lead with the most significant in full, then collapse the
   rest into one line. Keep it scannable.
7. **Period header.** Title the recap with the span in human form: "week of
   May 26–30", "May 2026", "May 5–10".
8. **Reconstructed (older) days.** `history` entries are days past transcript
   retention — synthesize them from their `prompts` plus the durable `delivery`
   state (joined by repo) as real work, but **don't fabricate outcomes you can't
   see**: with no assistant narrative, describe what was *worked on* (from the
   prompts) and what *shipped* (from delivery), and skip confident "fixed/landed
   X" phrasing unless delivery confirms it. If a span mixes rich and
   reconstructed days, add a light note — e.g. _"(earlier weeks reconstructed
   from prompt history; full transcripts past retention)"_ — so the reader knows
   the older detail is thinner.

#### Short (default)

```markdown
*What I shipped — {period header}*
{One thematic clause} *{tally — e.g. "6 merged, 2 in review, 1 released"}.*

*Shipped*
• *{Theme}* ({merged} | {released}) — {one short clause}{ — project if useful}.
• ...

*Still moving*
• *{Theme}* ({PR open} | {CI failed}) — {where it stands}.
• ...
_+ {N} smaller fixes across {projects}._   ← only when a long span has a rolled-up tail
```

The short-format *style* rules still apply (Slack bold, ~90-char bullets, strip
identifiers, markers are states not identifiers) — but **not** the single-day
3–7 bullet cap; a span should be as complete as it is scannable. List every
theme that shipped or is materially in flight, folding only minor/routine items
into the rolled-up tail. Soft ceiling: up to ~10 bullets for a week, ~15 for a
month, then roll up the rest. Drop *Still moving* if nothing is mid-flight; drop
the tail line unless there is one.

#### Verbose (`--verbose`)

Same structure as the single-day verbose report — `## Shipped` (with the
`### Released` subsection), `## In progress`, `## Notes & followups`, and the
footer — but theme-grouped across the span, and the footer names the period and
the project list. Identifiers (PR #, commit, run IDs) are allowed and encouraged
where present in the source, same as synthesis rule 3.

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

Write the synthesized markdown to `~/claude-recaps/{LABEL}.md`, where `{LABEL}`
is the date for a single day or `{START}_to_{END}` for a range (overwrite if it
exists — re-runs are expected). Both formats write to the same path; re-running
with `--verbose` replaces the short version and vice versa.

Then in your final reply to the user:

1. Print a one-line summary: `Recap for {LABEL} written to ~/claude-recaps/{LABEL}.md ({N} sessions{, verbose if applicable}).`
2. Show the rendered markdown inline so they can copy directly without
   opening the file.
3. Do not narrate the steps you took — just deliver the recap.
