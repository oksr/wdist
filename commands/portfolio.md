---
description: How I drive Claude — generate a shareable, redacted portfolio of how you work with agents (doubles as a self-improvement mirror)
argument-hint: "[all | YYYY-MM-DD | START to END] [--show-vendors]   (defaults to all-time, vendor names generalized)"
---

You are generating a **portfolio of how this person drives Claude** — an
evidence-led, redacted artifact that is *both* something they'd link in a job
application *and* an honest mirror they open to get sharper. The audience is a
recruiter or peer who wants to know: can this person actually specify problems,
catch the agent drifting, and command a real toolset — without ever learning
anything confidential about their employer.

Two non-negotiables, baked into every step below:

- **PRIVACY.** This is built on *work* sessions. Never emit a company / product /
  customer / internal-service name, domain jargon, internal ID, URL, file path,
  branch, ticket, or secret. The *agentic-method* layer (which MCP, which skills,
  workflows, how they specified/debugged) is the signal and is safe; the
  *business-domain* layer is pure risk. Keep the method, dissolve the domain.
  When unsure, generalize. A leak is a product-ending failure — treat it that way.
- **HONESTY.** Brutally honest, balanced judgment. Represent only what's in the
  evidence; never inflate or invent competence. Show weaknesses next to
  strengths — the contrast is the credibility mechanism, not a flaw to hide.

## Step 1 — Extract

`$ARGUMENTS` is an optional window: nothing or `all` (= all-time, the default and
the usual choice — a portfolio is a body of work), a single ISO date, or a range
`START to END` (accept `to`, `..`, or `-` between two ISO dates). Resolve to
literal dates if given; otherwise run all-time.

`$ARGUMENTS` may also contain **`--show-vendors`**. **Vendor generalization is ON
by default** — safe-by-default, because the artifact is built from confidential
work sessions, so naming a third party's stack is a deliberate opt-in, not the
baseline. With `--show-vendors`, keep concrete public-vendor names. Record which
mode is active; Pass A consumes it (the "Vendor dial" rule).

```bash
mkdir -p ~/claude-portfolio
# all-time:
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/portfolio.py" > "/tmp/portfolio-all.json"
# or a range:  python3 "${CLAUDE_PLUGIN_ROOT}/scripts/portfolio.py" 2026-03-01 2026-05-31 > "/tmp/portfolio-2026-03-01_to_2026-05-31.json"
```

Set `LABEL` to `all` for all-time, the date for a single day, or `START_to_END`
for a range. Then read the JSON you wrote. **The extractor has already
regex+entropy-scrubbed every free-text excerpt** (this is privacy gate #1) — but
that catches only token-shaped secrets, not domain meaning, which is your job in
Step 2. Structure:

- `mirror.harness_usage` — the headline. Read straight off `tool_use` names, so
  it's structured and low-sensitivity:
  - `mcp_servers` — `[{name, n}]`, MCP servers used (n = sessions). E.g.
    `datadog-mcp`, `shortcut`, `chrome-devtools`.
  - `skills` — `[{name, n}]`, skills invoked (e.g. `superpowers:systematic-debugging`).
  - `agentic_patterns` — `[{name, n}]`, capabilities exercised: `subagents`,
    `multi-agent workflows`, `parallel worktrees`, `plan-first`, `task-tracking`,
    `scheduling/automation`, `background monitoring`.
- `mirror.cold_starts` — `sharpest` / `vaguest`, each `[{text, has[], missing[]}]`.
  `text` is the (scrubbed) opening prompt; `has`/`missing` are quality signals
  (states a constraint / names a concrete locus / describes the symptom / gives
  enough context). **Heuristic ranking only — re-judge it in Pass B.** Sourced
  from the long-lived history log (typed prompts only, ~months), not the
  ~1-month transcripts — so this signal spans far more sessions than the harness.
- `mirror.course_corrections` — `drift_catches` / `cosmetic_nits` (scrubbed
  excerpts) and a `mix` count. The bucketing is a rough heuristic; trust the text.
  Also history-sourced (long horizon).
- `mirror.harness_investment` — `[{project, score, invested_in[]}]`, durable
  config evidence (CLAUDE.md, custom commands, MCP config, settings, authoring
  plugins). Projects are opaque hashes — never try to name them.
- `provenance.horizons` — the two spans this portfolio draws on: `prompt_craft`
  (cold-starts/corrections/spec, from the history log — the long span) and
  `harness` (tooling, from transcripts — bounded by retention). Use these to
  write an honest footer that states both.
- `provenance` — also `soft_proxies`, `joint_signal_unscored` (`versions_seen`
  etc.), `caveats`. **Numbers to footnote, not to headline or optimize.** The
  `joint_signal` block measures Claude, not the person — never rank on it.

## Step 2 — Synthesize (four sub-passes, in order — ordering is correctness)

### Pass A — Launder (privacy)

Rewrite each evidence excerpt you'll use (`cold_starts`, `course_corrections`)
into a faithful behavioral statement that **preserves the harness/method and
dissolves the domain**:

- **Preserve:** tool names that are public and generic (Datadog MCP, Playwright,
  Chrome DevTools, git worktrees), skills, workflow shapes (subagent-driven, plan
  then execute), the *engineering shape* (what kind of bug, what method, what
  judgment), and generic stack (Python, React, TypeScript).
- **Dissolve:** company / product / customer / internal-service names, domain
  jargon (e.g. a specific business object or screen), internal identifiers, URLs,
  paths, branches, tickets. Raise the description to a level where many companies'
  work would map to the same sentence (k-anonymity test).
- **Vendor dial (mode set in Step 1).** A *clearly-internal* MCP/skill name (e.g.
  `mcp__acme_billing__`) is **always** generalized to a category ("an internal
  billing MCP") — it can identify the employer. For *public third-party* names
  (Datadog, Shortcut, Slack, Chrome DevTools, the LangChain/LangSmith/LangFuse
  family, etc.):
  - **Default — generalized:** replace each with its capability category —
    Datadog → "observability/APM MCP", Shortcut → "issue/project-tracker MCP",
    Slack → "team-chat MCP", LangChain family → "LLM-evaluation & orchestration
    frameworks". Reveals the *transferable* skill, not the employer's stack.
  - **`--show-vendors`:** keep concrete public-vendor names (a searchable résumé
    credential); still generalize only the clearly-internal ones.
  Apply in `harness_usage` (the MCP/skills lists), in any laundered "How I work"
  line, and in the headline — wherever a vendor name would otherwise appear.

Example transform:
> scrubbed: *"trace the quote creation for `<token>`, datadog mcp, prod env, total
> price differs from the quote editor"*
> laundered: *"Used the Datadog MCP to trace a production request and isolate a
> data-integrity bug — a computed total diverging from its source of truth."*

Pass A only ever sees already-scrubbed text, so it cannot reintroduce a raw
secret — its job is the *semantic* laundering the regex can't do.

### Pass B — Curate (balanced judgment, brutally honest)

From the laundered material, write the artifact (shape below). Apply real
judgment the heuristics couldn't:

- **Re-judge cold-starts.** A long pasted skill-doc or file is *not* a sharp
  prompt — but it *is* evidence of harness sophistication, so move it to *Harness
  & workflows*, not *How I work*. A genuine "sharp" opening states the problem +
  a constraint + a concrete (now-laundered) locus.
- **Re-judge corrections.** A real drift-catch points at a specific wrong
  behavior/condition; a cosmetic nit tweaks copy/emoji/spacing. Count honestly.
- **Balanced bar:** neither credit every prompt nor dismiss everything — about as
  generous as a fair senior reviewer.
- **No inflation.** Every claim must trace to an evidence item. If the evidence is
  thin, say so plainly. Don't manufacture a narrative.

### Pass B.5 — Leak-audit (gates the write)

Before writing anything, scan your drafted artifact end to end and list any
residual: company / product / customer / internal-service name, domain term that
could identify the employer, internal identifier, URL, path, or secret. **If the
list is non-empty, fix the artifact and re-audit — do not write a leaky file.**
Then mentally re-apply the deterministic redaction rules as a mechanical backstop
(anything token-shaped and high-entropy → cut). Only a clean audit proceeds.

## The artifact shape

One combined Markdown doc — strengths and growth edge together (the honest
version reads as more credible):

```markdown
# How I drive Claude

{2–3 sentence headline: the strongest, true, domain-free summary — toolset
commanded + working style. e.g. "Drives Claude with heavy observability MCP and
multi-agent workflows across worktrees; plans before executing and debugs
systematically; catches the agent acting on stale state and names the exact
faulty condition."}

## Harness & workflows
The toolset and workflows I command (the part that doesn't drift with model
versions):
- **MCP:** {public/generalized servers, with rough usage weight}
- **Skills & workflows:** {e.g. systematic-debugging, subagent-driven development,
  writing/executing plans, parallel worktrees}
- **Agentic patterns:** {subagents, multi-agent workflows, plan-first, automation —
  from `agentic_patterns`}
- **Tooling I've shaped:** {from `harness_investment` — CLAUDE.md, custom
  commands, MCP config, authoring plugins — generalized, no project names}

## How I work
{2–4 laundered, concrete examples that show specification + judgment}
- **{Sharp opening}** — {one laundered line showing how a problem was framed}.
- **{Drift-catch}** — {how the agent was redirected at the real fault, not the surface}.

## Where I'm sharpening
{Brutally honest, from the vaguest openings / cosmetic-only corrections / thin
spec_ratio. 2–3 specific, non-defensive lines — this is the mirror edge and it
makes the rest believable.}
- {e.g. "Too many openings are one-liners ('open a PR', 'why did this fail') that
  make the agent guess — tightening cold-start specs is the active work."}

---
_Specification & judgment signal from {prompt_craft.sessions} sessions over
{prompt_craft.active_days} active days ({prompt_craft.span}); tooling signal from
{harness.sessions} recent sessions ({harness.active_days} days, transcript
retention). Evidence-led and redacted — a portrait of how I work with agents, not
a score. Business context removed; tooling and method preserved._
```

Rules for the artifact:

1. **`harness_usage` leads** — it's the headline signal and the safest. Don't bury
   it under prose.
2. **Every "How I work" bullet is laundered** — if you can't say it without a
   domain term, cut the bullet rather than leak.
3. **"Where I'm sharpening" is mandatory and real** — drawn from the actual weak
   evidence (vaguest cold-starts, cosmetic-only corrections, low spec_ratio). No
   humble-brags; name a genuine gap.
4. **Numbers stay in the footer, generalized** — "N sessions across M projects."
   Never print the `joint_signal` metrics as achievement; they measure Claude.
5. **No identifiers anywhere** — no project names (they're hashes for a reason), no
   PR/commit/ticket, no URLs. This is stricter than wdist verbose mode.

## Step 3 — Write the file and report

Write the artifact to `~/claude-portfolio/{LABEL}.md` (overwrite on re-run). Then
in your final reply:

1. One line: `Portfolio for {LABEL} written to ~/claude-portfolio/{LABEL}.md ({N} sessions, vendors {generalized | shown}).`
2. State the leak-audit result explicitly: `Leak-audit: clean (no domain terms,
   identifiers, or secrets).` — if you had to fix anything, say what class you
   caught.
3. Show the rendered Markdown inline so they can read/copy it directly.
4. Don't narrate the passes — just deliver the portfolio and the audit line.
