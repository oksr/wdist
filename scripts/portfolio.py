#!/usr/bin/env python3
"""Extract a behavioral *portfolio* from Claude Code sessions — a prototype.

An evidence-first mirror of how a person drives an agent. Built on wdist's
`recap-day.py` machinery (top-level session walk, is_meta_user filter, byte
truncation) pointed at a different question: not "what did I ship today" but
"how do I work WITH Claude — and where could I be sharper."

Design stance (decided after pressure-testing the metrics — see CONTEXT.md):

  - EVIDENCE OVER GAUGE. The numbers are vanity/artifact at any realistic N and
    invite Goodhart (stuff keyword-y prompts to move a ratio). So this leads with
    REDACTED, CONTRASTED evidence — your sharpest vs vaguest openings, your real
    drift-catches vs cosmetic nits — and demotes every number to a `provenance`
    block you read for honesty, not optimize. It's a mirror you grade, not a
    dashboard that grades you.

  - HUMAN-ATTRIBUTED ONLY. We surface what the person typed/chose. Model-dominated
    signal (tool errors, verify behaviour) is parked, unscored, under provenance —
    it measures Claude and drifts with the `version` field.

  - DUMB EXTRACTOR. Heuristics only sort evidence into buckets; the judgment is
    yours (or a downstream prompt's). Same split as recap-day.py.

Carried-over constraints: stdlib only, top-level *.jsonl only, redact before emit.

Usage:  portfolio.py [START [END]]   # default: all time. Dates are YYYY-MM-DD.
"""
import json, os, sys, glob, datetime, re, hashlib

START = sys.argv[1] if len(sys.argv) > 1 else None
END = sys.argv[2] if len(sys.argv) > 2 else START
if START:
    lo = datetime.datetime.fromisoformat(START + "T00:00:00").isoformat()
    hi = (datetime.datetime.fromisoformat(END + "T00:00:00")
          + datetime.timedelta(days=1)).isoformat()
else:
    lo, hi = None, None  # all time

PROJECTS_DIR = os.path.expanduser("~/.claude/projects")
EVIDENCE_CHARS = 280
SHOW = 4  # excerpts per contrasted bucket


# ---- shared with recap-day.py -------------------------------------------------
def extract_text(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(
            b["text"] for b in content
            if isinstance(b, dict) and b.get("type") == "text" and b.get("text"))
    return ""


def is_meta_user(text):
    if not text:
        return True
    return text.lstrip().startswith((
        "<system-reminder>", "<command-", "<local-command-", "[Request interrupted",
    ))


# ---- redaction (tier-2 free text -> entity-stripped) --------------------------
_REDACTORS = [
    (re.compile(r"https?://\S+"), "<url>"),
    (re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b"), "<email>"),
    (re.compile(r"arn:aws:\S+"), "<arn>"),
    (re.compile(r"(/[\w.-]+){2,}/?"), "<path>"),
    (re.compile(r"\b[0-9a-f]{12,40}\b"), "<hash>"),
    (re.compile(r"\b\d{4,}\b"), "<num>"),
]


def redact(text):
    for rx, repl in _REDACTORS:
        text = rx.sub(repl, text)
    return re.sub(r"\s+", " ", text).strip()[:EVIDENCE_CHARS]


# ---- evidence-ranking heuristics ----------------------------------------------
# NOTE: these only BUCKET evidence (strong vs weak) so the contrast is legible.
# They are not a score. The re.I-on-CamelCase bug from the first cut is fixed:
# the code-reference test below is case-sensitive where it must be.
_CONSTRAINT = re.compile(
    r"\b(must|should|don'?t|do not|instead|exactly|only|without|avoid|ensure|"
    r"keep|prefer|make sure|so that|because|never|always|not)\b", re.I)
# concrete locus: backtick span, file.ext, snake_case, REAL CamelCase (needs an
# actual capital — no re.I), dotted ref, or a line number.
_CODE_REF = re.compile(
    r"`[^`]+`"
    r"|\b\w+\.(?:py|js|ts|tsx|jsx|go|rs|rb|md|json|sh|ya?ml|sql|css|html)\b"
    r"|\b[a-z][a-z0-9]*_[a-z0-9_]+\b"
    r"|\b[a-z]+[A-Z][a-zA-Z]*\b"
    r"|\b[a-zA-Z_]+\.[a-zA-Z_]{2,}\b"
    r"|\bline\s*\d+\b")
# describes a problem/behaviour, not just a request
_SYMPTOM = re.compile(
    r"\b(wrong|fails?|failing|failed|broken|breaks?|bug|race|deadlock|leak|"
    r"regression|crash|double[- ]?charg|rounds?|off by|edge case|hangs?|"
    r"timeout|incorrect|stale|duplicat)\b", re.I)
_CORRECTION_OPEN = re.compile(
    r"^\s*(no\b|no,|nope|actually|wait|revert|undo|stop|that'?s wrong|"
    r"not quite|don'?t|instead)\b", re.I)
# cosmetic / copy / visual nit (vs a behavioural drift-catch)
_EMOJI = re.compile(
    "[\U0001F000-\U0001FAFF☀-➿←-⇿⬀-⯿️]")
_COSMETIC = re.compile(
    r"\b(emoji|emoticon|icon|colou?r|wording|phrasing|copy|text|label|caption|"
    r"capitali[sz]e|rename|spelling|typo|font|spacing|looks?)\b", re.I)

_EXT_LANG = {
    ".py": "python", ".js": "javascript", ".ts": "typescript", ".tsx": "typescript",
    ".jsx": "javascript", ".go": "go", ".rs": "rust", ".rb": "ruby", ".java": "java",
    ".sh": "shell", ".md": "markdown", ".sql": "sql", ".css": "css", ".html": "html",
    ".json": "json", ".yaml": "yaml", ".yml": "yaml", ".swift": "swift",
}


def in_window(ts_norm):
    return lo is None or (ts_norm is not None and lo <= ts_norm < hi)


def cold_start_signals(t):
    """Return (present, missing) label lists describing an opening prompt."""
    present, missing = [], []
    (present if _CONSTRAINT.search(t) else missing).append("states a constraint")
    (present if _CODE_REF.search(t) else missing).append("names a concrete locus")
    (present if _SYMPTOM.search(t) else missing).append("describes the symptom")
    (present if len(t) >= 80 else missing).append("gives enough context")
    return present, missing


def classify_correction(t):
    if _EMOJI.search(t) or _COSMETIC.search(t):
        return "cosmetic"
    if _SYMPTOM.search(t) or _CODE_REF.search(t):
        return "drift_catch"
    return "minor"


def config_sophistication(cwd):
    """'Knows the harness' evidence — durable, human, not in transcript."""
    if not cwd or not os.path.isdir(cwd):
        return None
    j = lambda *p: os.path.join(cwd, *p)
    checks = {
        "claude_md": os.path.isfile(j("CLAUDE.md")),
        "custom_commands": os.path.isdir(j(".claude", "commands"))
            and bool(glob.glob(j(".claude", "commands", "*"))),
        "mcp": os.path.isfile(j(".mcp.json")),
        "settings": os.path.isfile(j(".claude", "settings.json"))
            or os.path.isfile(j(".claude", "settings.local.json")),
        "authors_plugin": os.path.isdir(j(".claude-plugin")),
    }
    return {"score": sum(checks.values()), **checks}


def walk_session(path):
    cwd = session_id = first_prompt = None
    versions, languages = set(), set()
    prompts, first_ts, last_ts = [], None, None
    tool_results = tool_errors = edits = bash_after_edit = 0
    saw_edit = False

    with open(path) as f:
        for line in f:
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                continue
            t = d.get("type")
            ts = d.get("timestamp")
            ts_norm = ts[:-1] if ts and ts.endswith("Z") else ts
            if d.get("cwd") and not cwd:
                cwd = d["cwd"]
            if d.get("sessionId") and not session_id:
                session_id = d["sessionId"]
            if d.get("version"):
                versions.add(d["version"])
            if not in_window(ts_norm):
                continue
            if ts and (first_ts is None or ts < first_ts):
                first_ts = ts
            if ts and (last_ts is None or ts > last_ts):
                last_ts = ts

            if t == "user":
                msg = d.get("message", {})
                if not isinstance(msg, dict):
                    continue
                content = msg.get("content", "")
                text = extract_text(content).strip()
                if not is_meta_user(text):
                    prompts.append(text)
                    if first_prompt is None:
                        first_prompt = text
                if isinstance(content, list):
                    for b in content:
                        if isinstance(b, dict) and b.get("type") == "tool_result":
                            tool_results += 1
                            tool_errors += 1 if b.get("is_error") else 0
            elif t == "assistant":
                msg = d.get("message", {})
                if not isinstance(msg, dict):
                    continue
                for b in (msg.get("content") or []):
                    if not isinstance(b, dict) or b.get("type") != "tool_use":
                        continue
                    name = b.get("name")
                    ext = os.path.splitext((b.get("input") or {}).get("file_path", ""))[1].lower()
                    if ext in _EXT_LANG:
                        languages.add(_EXT_LANG[ext])
                    if name in ("Edit", "Write"):
                        edits += 1; saw_edit = True
                    elif name == "Bash" and saw_edit:
                        bash_after_edit += 1; saw_edit = False

    if first_ts is None and lo is not None:
        return None
    if not prompts and first_ts is None:
        return None
    return {
        "session_id": session_id, "cwd": cwd, "versions": sorted(versions),
        "start": first_ts, "end": last_ts, "prompts": prompts,
        "first_prompt": first_prompt, "languages": sorted(languages),
        "tool_results": tool_results, "tool_errors": tool_errors,
        "edits": edits, "bash_after_edit": bash_after_edit,
    }


# ---- walk ---------------------------------------------------------------------
sessions = []
for project_dir in sorted(glob.glob(os.path.join(PROJECTS_DIR, "*"))):
    if not os.path.isdir(project_dir):
        continue
    for jsonl in glob.glob(os.path.join(project_dir, "*.jsonl")):
        s = walk_session(jsonl)
        if s:
            sessions.append(s)
sessions.sort(key=lambda s: s["start"] or "")

# ---- build the mirror ---------------------------------------------------------
all_prompts = [p for s in sessions for p in s["prompts"]]
first_prompts = [s["first_prompt"] for s in sessions if s["first_prompt"]]

# Cold-starts: rank by how many quality signals are present, then contrast the
# top against the bottom so you can ask "would I still open this way?"
ranked = []
for fp in first_prompts:
    present, missing = cold_start_signals(fp)
    ranked.append({"text": redact(fp), "has": present, "missing": missing,
                   "_score": len(present)})
ranked.sort(key=lambda r: r["_score"], reverse=True)
sharpest = [r for r in ranked if r["_score"] >= 2][:SHOW]
vaguest = [r for r in reversed(ranked) if r["_score"] <= 1][:SHOW]
for r in ranked:
    r.pop("_score")

# Corrections: separate real drift-catches from cosmetic nits.
corr = {"drift_catch": [], "cosmetic": [], "minor": []}
for p in all_prompts:
    if _CORRECTION_OPEN.match(p):
        corr[classify_correction(p)].append(redact(p))

# Tool fluency: where you've actually invested in the harness.
fluency = []
seen_cwd = set()
for s in sessions:
    cwd = s["cwd"]
    if not cwd or cwd in seen_cwd:
        continue
    seen_cwd.add(cwd)
    cfg = config_sophistication(cwd)
    if cfg and cfg["score"]:
        invested = [k for k, v in cfg.items() if k != "score" and v]
        fluency.append({"project": "proj_" + hashlib.sha1(cwd.encode()).hexdigest()[:8],
                        "score": cfg["score"], "invested_in": invested})
fluency.sort(key=lambda f: f["score"], reverse=True)

active_days = sorted({(s["start"] or "")[:10] for s in sessions if s["start"]})
versions_seen = sorted({v for s in sessions for v in s["versions"]})


def ratio(n, d):
    return round(n / d, 2) if d else None


portfolio = {
    "schema_version": "0.2.0-proto",
    "window": "all-time" if lo is None else f"{START}..{END}",

    # ====================== THE MIRROR (the payload) ==========================
    "mirror": {
        "cold_starts": {
            "reflect": "Your opening prompt sets up the whole session. Read your "
                       "vaguest next to your sharpest — would you still open the "
                       "vague ones that way?",
            "sharpest": sharpest,
            "vaguest": vaguest,
        },
        "course_corrections": {
            "reflect": "When Claude drifts, do you point at the real problem or "
                       "just nudge the surface? Lots of cosmetic nits + few "
                       "drift-catches can mean great specs — or that you're not "
                       "scrutinising the logic.",
            "drift_catches": corr["drift_catch"][:SHOW],
            "cosmetic_nits": corr["cosmetic"][:SHOW],
            "mix": {"drift_catches": len(corr["drift_catch"]),
                    "cosmetic": len(corr["cosmetic"]),
                    "minor": len(corr["minor"])},
        },
        "harness_investment": {
            "reflect": "Where you've shaped the tool (CLAUDE.md, commands, MCP, "
                       "settings, authoring plugins) is durable 'knows the grain' "
                       "evidence — the part that doesn't drift with model versions.",
            "projects": fluency,
        },
    },

    # ============ PROVENANCE: numbers you read, do NOT optimize ===============
    "provenance": {
        "_note": "These are soft heuristics on small N, and the joint-signal block "
                 "measures Claude (drifts with version) — kept for honesty/trend, "
                 "not for ranking or self-optimising. Improve the evidence above; "
                 "these follow.",
        "counts": {"sessions": len(sessions), "active_days": len(active_days),
                   "prompts": len(all_prompts), "cold_starts": len(first_prompts)},
        "soft_proxies": {
            "spec_ratio": ratio(sum(1 for p in all_prompts if _CONSTRAINT.search(p)),
                                len(all_prompts)),
            "well_specified_cold_starts": ratio(len(sharpest), len(first_prompts)),
        },
        "joint_signal_unscored": {
            "versions_seen": versions_seen,
            "tool_error_rate": ratio(sum(s["tool_errors"] for s in sessions),
                                     sum(s["tool_results"] for s in sessions)),
            "edits": sum(s["edits"] for s in sessions),
            "bash_after_edit": sum(s["bash_after_edit"] for s in sessions),
        },
        "caveats": [
            f"N={len(sessions)} sessions — a wiring check, not a measurement.",
            "Heuristics only BUCKET evidence for contrast; the judgment is yours.",
            "Free text is entity-redacted before emit; raw transcripts never leave.",
            "Label each project's sensitivity before sharing outside this machine.",
        ],
    },
}

print(json.dumps(portfolio, indent=2, ensure_ascii=False))
