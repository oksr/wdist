# Learnings synthesis (`/wdist what i learned`)

You were routed here from `commands/wdist.md` because the user asked **what they
learned**, not what they shipped. The shared preamble has already resolved the
date window, run the extractor with `--learnings`, and written the JSON to
`/tmp/recap-{LABEL}-learnings.json` (`{LABEL}` is the single date, or
`{START}_to_{END}` for a range). Read that file now.

This recap is for **future-you** — a durable, specifics-rich knowledge log — not a
Slack broadcast. That is the opposite optimization from the shipped recap: where
shipped *strips* identifiers because nobody clicks them, here you **keep** the
file path, the function name, the root cause. The specificity is the whole point.

## What a learning is

A **learning** is a piece of knowledge the user did **not** have at the start of a
session and had by the end. Exactly two kinds count:

- **Discovered fact** — newly-established knowledge about how a system actually
  works: a root cause, a real behavior, what a library does under the hood.
  *("The session cookie wasn't scoped to the tenant — `buildSessionKey()` omitted
  the org ID, so two tenants with the same user-id collided in the cache.")*
- **Gotcha** — a surprise or a corrected assumption: something believed true that
  wasn't, a footgun hit and understood. *("Assumed `gh api` 404s on a missing
  scope; it returns an empty 200.")*

**Out of scope** (do not list these as learnings): plain decisions + rationale
(those are a *shipped*-recap concern), and bare how-to/technique notes unless they
carry a discovered fact. When unsure whether something is a learning or just
"work that happened," ask: *did the user's understanding of how something works
change?* If no, it's not a learning.

### Confirmed learnings weigh more

The data is an **interleaved, order-preserving** dialogue — each session has a
`turns` array of `{role, text}` in conversation order. Adjacency is the signal:
when a `user` turn right after an assistant claim says *"you're right" / "yes,
exactly" / "that's it"* — or corrects the assistant with the real answer (*"no,
it's actually the tenant key"*) — that learning is **confirmed**. The user
validated it in the moment.

Confirmation is a **strength signal, not a gate**: a fact the assistant explained
and the user simply accepted and moved on from still counts. But surface confirmed
learnings **first** within their topic and phrase them more **confidently**; mark
clearly-unconfirmed-but-plausible ones with a hedge if you keep them. Never invent
a confirmation that isn't in the turns.

## How to find them

Read each session's `turns` in order. Learnings live in the **body** —
substantive `assistant` turns that explain a cause/behavior — and crystallize in
the **back-and-forth** around them. A long stretch of assistant turns followed by
a short user "you're right" is a prime learning site. Skim the prompts/titles for
context, but the learning text itself comes from the assistant explanation, tested
against the user's response.

## Organize by topic, not by session

The organizing unit is the **topic** — a subject ("Auth / session security"), not
a Claude Code session. A single investigation spread across several sessions is
**one topic** with several learnings underneath, *regardless of which session each
came from* (the same way the shipped recap groups by outcome, not by tab). Cluster
across sessions. Within a topic: confirmed learnings first, then the rest.

## Default format — the personal log

The default (no `--share`). Rich, specifics kept. `--verbose` is a no-op here —
the log is already the detailed form; if `--verbose` is present, produce this same
log.

```markdown
# What I learned — {LABEL} ({weekday for a single day, or "week of …" / month for a range})

## {Topic}{ — project tag, e.g. "wdist", when it aids recall}
- {A discovered fact, stated plainly, keeping the function/file/root cause.}
  {(confirmed) when the user validated it in the dialogue.}
- **Gotcha:** {a corrected assumption / footgun, phrased as a warning to future-you.}
- ...

## {Next topic}
- ...
```

Rules:

1. **Keep the specifics.** File paths, function names, error codes, the actual
   root cause — they make the log useful months later. This is the inverse of the
   shipped recap's identifier-stripping.
2. **Mark gotchas** with a leading `**Gotcha:**` (or unmistakable warning
   phrasing) so future-you reads them as cautions, not trivia. Discovered facts
   read as plain statements.
3. **Confirmed first, confidently.** Order within a topic by strength; tag
   `(confirmed)` where the dialogue validated it.
4. **One topic per `##`,** learnings as bullets. A four-session investigation is
   one topic, not four headings.
5. **Don't pad.** If a session yielded no real learning (routine edits, no
   understanding changed), it contributes nothing. A short, true log beats a long,
   inflated one. If *nothing* was learned in the window, say so in one line.

## `--share` format — the postable TIL

Only when `$ARGUMENTS` contains `--share`. A condensed, shareable version for a
team channel — drops per-topic structure and most specifics, keeps the insight.

```markdown
*TIL — {one-phrase theme of the day/period}*
• {Learning, generalized to be legible to someone who wasn't in the session.}
• {Gotcha, as a one-line heads-up.}
```

`--share` rules: a handful of bullets (not every learning — the sharpest few);
generalize so a teammate understands without the session context; redact harder
(see below); Slack-style single-asterisk bold; no headers/footer.

## Redaction

Even in the personal log, drop or generalize true secrets and tenant-identifying
details: customer/account IDs, ARNs, internal URLs with tenant identifiers,
tokens/keys. Function names, file paths, and public library names are **kept** —
they're the value, not a leak. `--share` redacts more aggressively (assume a wider
audience). And, as in shipped mode: **never invent** an identifier, a root cause,
or a confirmation that isn't in the source `turns`.

## Honesty about gaps

- **Past retention.** The JSON's `history` array lists days whose transcripts were
  deleted by `cleanupPeriodDays` — these carry **only prompts, no assistant
  narrative**, so **no learnings are recoverable** from them. For a range that
  includes such days, add a one-line note (e.g. _"May 1–9 past transcript
  retention — no learnings recoverable for those days"_) rather than inventing
  any. Don't manufacture learnings from bare prompts.
- **Truncated sessions.** A session with `"truncated": true` had its dialogue
  clipped (an extreme-length span). Don't claim its learnings are complete; if it
  matters, note the topic may be partial.

## Write the file and report

Write the synthesized markdown to `~/claude-recaps/{LABEL}-learnings.md`
(`{LABEL}` = the date for a single day, `{START}_to_{END}` for a range). The
`-learnings` suffix guarantees it never overwrites a shipped recap at
`~/claude-recaps/{LABEL}.md`. Overwrite re-runs of the *learnings* file is
expected.

Then in your final reply:

1. One-line summary: `Learnings for {LABEL} written to ~/claude-recaps/{LABEL}-learnings.md ({N} sessions).`
2. Show the rendered markdown inline for copy-paste.
3. Don't narrate the steps — just deliver the log.
