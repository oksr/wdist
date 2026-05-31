# Learnings is one NL-routed `/wdist`, not a `/wdist-learned` command, with a separate `prompts/learned.md`

`/wdist what i learned` is handled by the *existing* `/wdist` command via natural-language routing (alias `--learned`), mirroring how `/wdist` already routes NL dates ("last week"). The learnings *synthesis* prompt, however, lives in its own `prompts/learned.md`, read by the command when in learnings mode; only a thin shared preamble (parse arguments, resolve dates, run the extractor) stays in `commands/wdist.md`.

## Considered Options

- **A second slash command, `/wdist-learned`** — rejected: it breaks the plugin's "ships a single slash command" identity and doubles the discovery/docs/versioning surface. The user invocation we're designing for is literally `/wdist what i learned`.
- **One branched `wdist.md`** holding both syntheses — rejected: shipped-synthesis and learnings-synthesis share almost no editorial rules (different unit — outcome vs knowledge; different format — Slack-terse vs specifics-rich; opposite redaction — strip identifiers vs *keep* them; learnings has no delivery-state machinery). Co-locating them invites "I tuned shipped and learnings drifted."
- **Chosen: single command, separate synthesis file.** Preserves the one-command surface while keeping each synthesis prompt cohesive and independently tunable, at the cost of one runtime `Read` and a few shared rules (output dir, "never invent identifiers", baseline redaction) to keep in sync across two files.
