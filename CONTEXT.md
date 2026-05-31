# wdist

The language of `wdist`, a Claude Code plugin that turns local session transcripts into shareable recaps. This glossary names the domain concepts the `/wdist` command and its extractor reason about — not implementation details.

## Recap modes

**Recap**:
A synthesized, human-readable summary of a window of Claude Code activity. Always for a date or date range; always written for a reader, not a log dump.

**Shipped recap**:
The default recap: what *got done* in the window — outcomes that landed. Its signal lives in session titles, final assistant messages, and durable delivery state (PRs, CI, releases) pulled live from `gh`.
_Avoid_: "work recap" (too vague — every recap is about work).

**Learnings recap**:
A recap of what was *learned* in the window, distinct from what shipped. Answers "what do I know now that I didn't this morning."
_Avoid_: "TIL recap", "knowledge dump".

## Within a learnings recap

**Learning**:
A piece of knowledge gained during a session that the user did not have at its start. Scoped to two kinds only: a **discovered fact** and a **gotcha**. A learning is *knowledge gained*, categorically distinct from a **shipped** outcome (something delivered).
_Avoid_: "insight", "takeaway", "lesson" (too broad — they invite decisions and opinions, which are not learnings here).

**Discovered fact**:
Newly-established knowledge about how a system actually works — a root cause, a behavior, what a library does under the hood. ("The cache key didn't include the tenant, so cross-tenant reads collided.")

**Gotcha**:
A surprise or corrected assumption — something believed to be true that wasn't, a footgun hit and understood. ("Assumed the retry was idempotent; it wasn't.")

A learning can be **confirmed** — the user explicitly validated it in the dialogue ("you're right", "yes, exactly", or correcting the assistant with the real answer). Confirmation is a *strength signal*, not a requirement: an assistant-asserted learning the user accepted and moved on from still counts. Confirmed learnings are surfaced more prominently and phrased more confidently. The signal lives in the **call-and-response** between user and assistant turns, so it is only legible when turn **adjacency** is preserved.

Explicitly **out of scope** for a learning (as of the initial design): a **decision + rationale** (overlaps with the shipped recap's "Notes & followups") and a bare **technique/how-to** unless it carries a discovered fact.

**Topic**:
The organizing unit of a learnings recap — a subject that learnings cluster under ("Auth / session security"), independent of which session each learning came from. A single investigation spread across several sessions is one topic, not several. Mirrors how the shipped recap groups by *outcome* rather than by session.
_Avoid_: "session", "thread" (a topic is not a session — session boundaries are incidental).
