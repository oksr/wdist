# The learnings extractor surfaces raw interleaved dialogue, not cue-selected snippets

To support `/wdist what i learned`, `recap-day.py` gains a `--learnings` mode that emits a per-session, order-preserving dump of both user and assistant turns (`{role, text}`, mechanically truncated — assistant ~600 chars, user ~250, never dropped except under extreme-range overflow, which sets a `truncated` flag). This *looks like* a violation of the repo's "keep the extractor dumb, push all editorial logic into the prompt" rule, so the reasoning is recorded here: a learning (a discovered fact or a gotcha) lives in the *body* of a conversation and crystallizes in the call-and-response (a "you're right" only means something attached to the claim it answers), which the default shipped extractor — tuned for outcomes via `last_assistant` + `gh` delivery state — throws away.

## Considered Options

- **Cue-phrase selection in the extractor** (keep only turns containing "root cause", "turns out", etc.) — rejected: it smuggles meaning-based editorial selection into the dumb script (exactly what CLAUDE.md warns against) and a hardcoded cue list is brittle (misses + false positives).
- **Prompt reads the raw JSONL itself** — rejected: it re-implements the day-window filtering and `is_meta_user` logic the extractor already got right, and spawns a parallel data path.
- **Chosen: mechanical interleaved dump.** The extractor stays mechanical (truncation by fixed byte limits, not meaning); "find the learnings" stays 100% in the prompt where editorial logic belongs.

## Consequences

The learnings JSON is much larger than the shipped JSON, so the dump is gated behind `--learnings` and the default shipped path is byte-for-byte unchanged (no bloat, no regression). Learnings mode also drops the `gh` delivery/releases joins (pure shipped signal) — making it faster and network-free. Adjacency between turns is load-bearing and must be preserved by any future change to the dump shape.
