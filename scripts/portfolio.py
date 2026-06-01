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
import json, os, sys, glob, datetime, re, hashlib, math
from collections import Counter

START = sys.argv[1] if len(sys.argv) > 1 else None
END = sys.argv[2] if len(sys.argv) > 2 else START
if START:
    _start_dt = datetime.datetime.fromisoformat(START + "T00:00:00")
    _end_dt = datetime.datetime.fromisoformat(END + "T00:00:00") + datetime.timedelta(days=1)
    lo, hi = _start_dt.isoformat(), _end_dt.isoformat()
    lo_epoch, hi_epoch = _start_dt.timestamp(), _end_dt.timestamp()  # for history.jsonl
else:
    lo, hi = None, None  # all time
    lo_epoch = hi_epoch = None

PROJECTS_DIR = os.environ.get("CLAUDE_PROJECTS_DIR") or os.path.expanduser("~/.claude/projects")
HISTORY_FILE = os.environ.get("CLAUDE_HISTORY_FILE") or os.path.expanduser("~/.claude/history.jsonl")
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
# STOPGAP, not a guarantee. A denylist of known secret shapes plus an entropy
# sweep for opaque tokens. The first real-data run leaked a Bearer JWT and an
# Outlook thread_id straight through the old version, so this raises the floor —
# but the real answer is the LLM paraphrase layer (raw text is never safe to
# ship). Order matters: structural patterns first, then the entropy sweep mops up
# whatever didn't match a known format.
_STRUCTURAL = [
    # secrets / auth — most specific first
    (re.compile(r"eyJ[A-Za-z0-9_-]{6,}\.[A-Za-z0-9_-]{6,}(?:\.[A-Za-z0-9_-]+)?"), "<jwt>"),
    (re.compile(r"(?i)\b(authorization|auth|cookie|set-cookie)\b\s*[:=]\s*\S+"), r"\1: <redacted>"),
    (re.compile(r"(?i)\bbearer\s+\S+"), "bearer <redacted>"),
    (re.compile(r"(?i)\b(api[_-]?key|secret|token|password|passwd|pwd|"
                r"access[_-]?key|client[_-]?secret|private[_-]?key)\b\s*[:=]\s*\S+"),
     r"\1=<redacted>"),
    # well-known key prefixes (github, openai, slack, aws, gcp, gitlab, stripe...)
    (re.compile(r"\b(?:sk|pk|rk)-[A-Za-z0-9_-]{12,}"), "<key>"),
    (re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr|github_pat)_[A-Za-z0-9_]{20,}"), "<key>"),
    (re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}"), "<key>"),
    (re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{12,}"), "<key>"),
    (re.compile(r"\bAIza[A-Za-z0-9_-]{20,}"), "<key>"),
    (re.compile(r"\bglpat-[A-Za-z0-9_-]{12,}"), "<key>"),
    # structured identifiers
    (re.compile(r"https?://\S+"), "<url>"),
    (re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b"), "<email>"),
    # scoped package refs (@org/pkg) carry the org/company name in plain words —
    # a denylist can't reach it, but the @scope/ shape can.
    (re.compile(r"@[A-Za-z0-9][\w.-]*/[\w.-]*"), "<pkg>"),
    (re.compile(r"arn:aws:\S+"), "<arn>"),
    (re.compile(r"\b(?:[0-9]{1,3}\.){3}[0-9]{1,3}\b"), "<ip>"),
    (re.compile(r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
                r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b"), "<uuid>"),
    (re.compile(r"(/[\w.-]+){2,}/?"), "<path>"),
    (re.compile(r"\b[0-9a-f]{12,}\b"), "<hash>"),
    (re.compile(r"\b\d{5,}\b"), "<num>"),
]
# A lowercase snake/kebab identifier is signal (critical_gap, quote_ready), not a
# secret — keep it even when long. Everything else long+random gets swept.
_LC_IDENT = re.compile(r"^[a-z0-9]+(?:[_-][a-z0-9]+)*$")
_SECRETY_CHARS = re.compile(r"^[A-Za-z0-9+/=_-]+$")


def _entropy(s):
    n = len(s)
    if n < 2:
        return 0.0
    return -sum((c / n) * math.log2(c / n) for c in Counter(s).values())


def _looks_secret(tok):
    """High-entropy opaque token (key/id/blob) that no structural rule caught."""
    if len(tok) < 16 or not _SECRETY_CHARS.match(tok):
        return False
    if _LC_IDENT.match(tok) and _entropy(tok) < 3.2:
        return False  # long lowercase identifier — behavioural signal, keep
    mixed = any(c.isupper() for c in tok) and any(c.islower() for c in tok) \
        and any(c.isdigit() for c in tok)
    return _entropy(tok) >= 3.5 or (mixed and len(tok) >= 20)


def redact(text):
    for rx, repl in _STRUCTURAL:
        text = rx.sub(repl, text)
    # entropy sweep over remaining tokens (strip surrounding punctuation per token)
    swept = []
    for tok in re.split(r"(\s+)", text):
        core = tok.strip("'\"`(),;:[]{}<>|\\")
        swept.append(tok.replace(core, "<token>") if core and _looks_secret(core) else tok)
    text = "".join(swept)
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


# Agentic-pattern tool names -> the capability they evidence. Structured harness
# fluency, read straight off tool_use names (no NLP, low sensitivity).
_AGENTIC_PATTERNS = {
    "Agent": "subagents", "Task": "subagents",
    "TaskCreate": "task-tracking", "TaskUpdate": "task-tracking", "TaskList": "task-tracking",
    "Workflow": "multi-agent workflows", "TeamCreate": "multi-agent workflows",
    "SendMessage": "multi-agent workflows",
    "EnterWorktree": "parallel worktrees", "ExitWorktree": "parallel worktrees",
    "ExitPlanMode": "plan-first", "Monitor": "background monitoring",
    "ScheduleWakeup": "scheduling/automation", "CronCreate": "scheduling/automation",
    "RemoteTrigger": "scheduling/automation",
}


def walk_session(path):
    cwd = session_id = first_prompt = None
    versions, languages = set(), set()
    prompts, first_ts, last_ts = [], None, None
    tool_results = tool_errors = edits = bash_after_edit = 0
    saw_edit = False
    mcp_servers, skills, patterns = set(), [], {}

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
                    # harness fluency — structured, low-sensitivity
                    if name and name.startswith("mcp__"):
                        seg = name.split("__")
                        if len(seg) > 1 and seg[1]:
                            mcp_servers.add(seg[1])
                    elif name == "Skill":
                        sk = (b.get("input") or {}).get("command") \
                            or (b.get("input") or {}).get("skill")
                        if sk:
                            skills.append(str(sk).split()[0])
                    elif name in _AGENTIC_PATTERNS:
                        patterns[name] = patterns.get(name, 0) + 1

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
        "mcp_servers": sorted(mcp_servers), "skills": skills, "patterns": patterns,
    }


def load_history(path=HISTORY_FILE):
    """Reconstruct prompt-only sessions from the long-lived global prompt log.

    history.jsonl outlives transcripts (Claude Code deletes those past
    cleanupPeriodDays, default 30), so it gives the *prompt-craft* signal a far
    longer horizon. It's also CLEANER: `display` is the typed prompt only —
    pasted blobs live in a separate `pastedContents` field — so cold-starts here
    aren't polluted by pasted file/skill content the way transcript first-prompts
    are. No tool_use is recorded here, so the harness signal still comes from
    transcripts. Records carry epoch `timestamp`, `project`, `sessionId`.
    """
    if not os.path.exists(path):
        return []
    by_sid, order = {}, []
    try:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    d = json.loads(line)
                except json.JSONDecodeError:
                    continue
                disp = (d.get("display") or "").strip()
                if not disp or disp.startswith("/") or is_meta_user(disp):
                    continue  # blank, slash-command, or wrapped meta record
                ts = d.get("timestamp")
                if ts is None:
                    continue
                secs = ts / 1000 if ts > 1e11 else ts
                if lo_epoch is not None and not (lo_epoch <= secs < hi_epoch):
                    continue
                sid = d.get("sessionId") or f"_ts{int(secs)}"
                if sid not in by_sid:
                    by_sid[sid] = {"cwd": d.get("project"), "prompts": []}
                    order.append(sid)
                by_sid[sid]["prompts"].append((secs, disp))
    except OSError:
        return []
    out = []
    for sid in order:
        ps = sorted(by_sid[sid]["prompts"], key=lambda p: p[0])
        if not ps:
            continue
        out.append({
            "session_id": sid, "cwd": by_sid[sid]["cwd"],
            "first_prompt": ps[0][1], "prompts": [p[1] for p in ps],
            "start_epoch": ps[0][0],
        })
    return out


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
# Prompt-craft layer (cold-starts, corrections, spec quality) is sourced from the
# long-lived, cleaner history log; harness layer stays on transcripts (below).
# Fall back to transcript prompts if history.jsonl is absent.
hist_sessions = load_history()
if hist_sessions:
    craft_source = "history.jsonl (long-horizon prompt log)"
    craft_prompts = [p for s in hist_sessions for p in s["prompts"]]
    first_prompts = [s["first_prompt"] for s in hist_sessions if s["first_prompt"]]
    craft_n_sessions = len(hist_sessions)
    craft_days = sorted({datetime.date.fromtimestamp(s["start_epoch"]).isoformat()
                         for s in hist_sessions})
else:
    craft_source = "transcripts (history.jsonl absent — prompt horizon limited to retention)"
    craft_prompts = [p for s in sessions for p in s["prompts"]]
    first_prompts = [s["first_prompt"] for s in sessions if s["first_prompt"]]
    craft_n_sessions = len(sessions)
    craft_days = sorted({(s["start"] or "")[:10] for s in sessions if s["start"]})

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
for p in craft_prompts:
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

# Harness usage — the toolset/workflows you command, straight off tool_use names.
# Structured, low-sensitivity, version-robust: the headline "how I drive Claude".
mcp_used, skills_used, patterns_used = Counter(), Counter(), Counter()
for s in sessions:
    mcp_used.update(s.get("mcp_servers", []))
    skills_used.update(s.get("skills", []))
    for tool_name, n in (s.get("patterns") or {}).items():
        patterns_used[_AGENTIC_PATTERNS[tool_name]] += n


def _top(counter):
    return [{"name": k, "n": v} for k, v in counter.most_common()]


def ratio(n, d):
    return round(n / d, 2) if d else None


portfolio = {
    "schema_version": "0.2.0-proto",
    "window": "all-time" if lo is None else f"{START}..{END}",

    # ====================== THE MIRROR (the payload) ==========================
    "mirror": {
        "harness_usage": {
            "reflect": "The toolset and workflows you actually command — MCP "
                       "servers, skills, agentic patterns. Structured, "
                       "low-sensitivity, version-robust: the headline 'how I "
                       "drive Claude'. Generalise any clearly-internal MCP name.",
            "mcp_servers": _top(mcp_used),
            "skills": _top(skills_used),
            "agentic_patterns": _top(patterns_used),
        },
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
        "horizons": {
            "prompt_craft": {
                "source": craft_source,
                "active_days": len(craft_days),
                "sessions": craft_n_sessions,
                "prompts": len(craft_prompts),
                "span": f"{craft_days[0]}..{craft_days[-1]}" if craft_days else None,
            },
            "harness": {
                "source": "transcripts (tool_use required)",
                "active_days": len(active_days),
                "sessions": len(sessions),
                "span": f"{active_days[0]}..{active_days[-1]}" if active_days else None,
                "note": "bounded by Claude Code transcript retention (cleanupPeriodDays)",
            },
        },
        "soft_proxies": {
            "spec_ratio": ratio(sum(1 for p in craft_prompts if _CONSTRAINT.search(p)),
                                len(craft_prompts)),
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
            "Two horizons: prompt-craft (cold-starts/corrections/spec) from the "
            "long-lived history log; harness/tooling from recent transcripts only. "
            "They cover different spans — see `horizons`.",
            "Heuristics only BUCKET evidence for contrast; the judgment is yours.",
            "Free text is entity-redacted before emit; raw transcripts never leave.",
            "Label each project's sensitivity before sharing outside this machine.",
        ],
    },
}

print(json.dumps(portfolio, indent=2, ensure_ascii=False))
