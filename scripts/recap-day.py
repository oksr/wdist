#!/usr/bin/env python3
"""Extract a compact JSON recap of Claude Code sessions for a date or range.

Usage: recap-day.py [START [END]]   (defaults to today; END defaults to START,
local time). START/END are YYYY-MM-DD and the range is inclusive.

Reads ~/.claude/projects/*/*.jsonl (top-level session files only — skips
subagent transcripts) and emits a JSON document with one entry per session
that contained activity within the target date range.
"""
import json, os, sys, glob, datetime, subprocess, re

# Accept a single date or an inclusive START END range, plus optional flags.
# END defaults to START, so `recap-day.py YYYY-MM-DD` (or no arg = today) behaves
# exactly as before. `--learnings` switches to the learnings dump (see below);
# without it the output is byte-for-byte the original shipped recap.
_args = sys.argv[1:]
LEARNINGS = "--learnings" in _args
_positional = [a for a in _args if not a.startswith("--")]
START = _positional[0] if _positional else datetime.date.today().isoformat()
END = _positional[1] if len(_positional) > 1 else START
range_start_dt = datetime.datetime.fromisoformat(START + "T00:00:00")
# Exclusive end: midnight after the last day in the range.
range_end_dt = datetime.datetime.fromisoformat(END + "T00:00:00") + datetime.timedelta(days=1)
if range_end_dt <= range_start_dt:
    sys.exit(f"END ({END}) must be on or after START ({START})")
range_start_iso = range_start_dt.isoformat()
range_end_iso = range_end_dt.isoformat()
# Epoch bounds for the history-backfill scan. That log carries real epoch
# timestamps, so it filters and early-breaks on epoch seconds — strictly
# monotonic even across a DST fall-back, where local-time ISO strings repeat
# an hour and would break the chronological early-exit.
range_start_epoch = range_start_dt.timestamp()
range_end_epoch = range_end_dt.timestamp()
# Delivery events (PRs/CI) get a 24h forward grace window (D1): work in the range
# may land its PR the next morning and still belong to this recap.
grace_end_iso = (range_end_dt + datetime.timedelta(days=1)).isoformat()

PROJECTS_DIR = os.path.expanduser("~/.claude/projects")

# Prompt-collection limits, shared by the transcript and history-backfill paths so
# the two prompt lists (which feed the same recap prompt) stay in sync.
MAX_PROMPTS = 20        # cap on prompts collected per session / backfilled day
MAX_PROMPT_CHARS = 400  # per-prompt truncation

# Learnings-mode dump limits (only used under --learnings). A "learning" — a
# discovered fact or a gotcha — lives in the *body* of a session and crystallizes
# in the call-and-response between turns, so learnings mode emits an interleaved,
# order-preserving dump of both sides rather than the shipped recap's outcome
# fields. See docs/adr/0001. Caps are asymmetric: assistant turns carry the
# root-cause depth; user turns ("you're right, it's the tenant key") are short.
# The rule is keep-every-turn / shrink-don't-drop: every non-meta turn survives,
# and only a genuinely huge span (a month) shrinks per-turn caps toward a floor
# (and, in the extreme, drops middle turns with a `truncated` flag).
LEARN_ASSISTANT_CHARS = 600   # per assistant-turn cap at full size
LEARN_USER_CHARS = 250        # per user-turn cap at full size
LEARN_FLOOR_CHARS = 200       # caps never shrink below this
LEARN_TURN_SAFETY_CHARS = 2000  # memory bound while collecting (pre-final-cap)
LEARN_GLOBAL_BUDGET = 500_000   # total turn-text chars before uniform shrink kicks in
LEARN_KEEP_HEAD = 1           # turns kept from the start when an extreme span forces a drop
LEARN_KEEP_TAIL = 12          # turns kept from the end (where understanding consolidates)


def extract_text(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        out = []
        for block in content:
            if isinstance(block, dict):
                if block.get("type") == "text" and block.get("text"):
                    out.append(block["text"])
                elif block.get("type") == "tool_use":
                    out.append(f"[tool:{block.get('name','?')}]")
        return "\n".join(out)
    return ""


def is_meta_user(text):
    """Skip wrapped non-prompt user records (hooks, command output)."""
    if not text:
        return True
    return text.lstrip().startswith((
        "<system-reminder>",
        "<command-",
        "<local-command-",
        "[Request interrupted",
    ))


def summarize_session(path, learnings=False):
    title = None
    cwd = None
    session_id = None
    first_user_in_range = None
    last_user_in_range = None
    last_assistant_in_range = None
    user_turns_in_range = 0
    assistant_turns_in_range = 0
    first_ts_in_range = None
    last_ts_in_range = None
    user_msgs_in_range = []
    # Ordered interleaved dialogue for learnings mode (empty otherwise). Adjacency
    # is load-bearing: a "you're right" only means something next to the claim it
    # answers, so user and assistant turns share one list in conversation order.
    turns_in_range = []

    with open(path) as f:
        for line in f:
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                continue
            t = d.get("type")
            ts = d.get("timestamp")
            # Strip trailing 'Z' so timestamps compare lexicographically against
            # the naive ISO window (cheaper than parsing each line).
            ts_norm = ts[:-1] if ts and ts.endswith("Z") else ts

            if d.get("cwd") and not cwd:
                cwd = d["cwd"]
            if d.get("sessionId") and not session_id:
                session_id = d["sessionId"]
            if t == "ai-title":
                title = d.get("aiTitle") or title

            if not ts_norm or not (range_start_iso <= ts_norm < range_end_iso):
                # JSONL transcripts are append-only chronological; once we've
                # entered and exited the window, the rest can't contribute.
                if first_ts_in_range is not None and ts_norm and ts_norm >= range_end_iso:
                    break
                continue

            if first_ts_in_range is None or ts < first_ts_in_range:
                first_ts_in_range = ts
            if last_ts_in_range is None or ts > last_ts_in_range:
                last_ts_in_range = ts

            if t == "user":
                msg = d.get("message", {})
                if isinstance(msg, dict):
                    text = extract_text(msg.get("content", ""))
                    if not is_meta_user(text):
                        user_turns_in_range += 1
                        text = text.strip()
                        if first_user_in_range is None:
                            first_user_in_range = text
                        last_user_in_range = text
                        if len(user_msgs_in_range) < MAX_PROMPTS:
                            user_msgs_in_range.append(text[:MAX_PROMPT_CHARS])
                        if learnings:
                            turns_in_range.append(
                                {"role": "user", "text": text[:LEARN_TURN_SAFETY_CHARS]})
            elif t == "assistant":
                msg = d.get("message", {})
                if isinstance(msg, dict):
                    text = extract_text(msg.get("content", ""))
                    if text.strip():
                        assistant_turns_in_range += 1
                        text = text.strip()
                        last_assistant_in_range = text
                        if learnings:
                            turns_in_range.append(
                                {"role": "assistant", "text": text[:LEARN_TURN_SAFETY_CHARS]})

    if first_ts_in_range is None:
        return None

    if learnings:
        # Outcome fields (first_user/last_assistant/user_prompts) are replaced by
        # the interleaved `turns` dump; per-turn caps and the global budget are
        # applied after all sessions are collected (apply_learnings_budget).
        return {
            "session_id": session_id,
            "cwd": cwd,
            "title": title,
            "start": first_ts_in_range,
            "end": last_ts_in_range,
            "user_turns": user_turns_in_range,
            "assistant_turns": assistant_turns_in_range,
            "turns": turns_in_range,
        }

    return {
        "session_id": session_id,
        "cwd": cwd,
        "title": title,
        "start": first_ts_in_range,
        "end": last_ts_in_range,
        "user_turns": user_turns_in_range,
        "assistant_turns": assistant_turns_in_range,
        "first_user": (first_user_in_range or "")[:800],
        "last_user": (last_user_in_range or "")[:400],
        "last_assistant": (last_assistant_in_range or "")[:800],
        "user_prompts": user_msgs_in_range,
    }


sessions = []
for project_dir in sorted(glob.glob(os.path.join(PROJECTS_DIR, "*"))):
    if not os.path.isdir(project_dir):
        continue
    for jsonl in glob.glob(os.path.join(project_dir, "*.jsonl")):
        if os.path.getmtime(jsonl) < range_start_epoch:
            continue
        s = summarize_session(jsonl, learnings=LEARNINGS)
        if s:
            sessions.append(s)

sessions.sort(key=lambda s: s["start"])


def _turn_cost(turn, a_cap, u_cap):
    cap = a_cap if turn["role"] == "assistant" else u_cap
    return min(len(turn["text"]), cap)


def apply_learnings_budget(sessions):
    """Apply per-turn caps and the global char budget to the collected `turns`,
    in place. Policy (docs/adr/0001): keep every turn at full caps when the recap
    fits the budget — the common single-day/week case. Only a span large enough to
    blow LEARN_GLOBAL_BUDGET shrinks the caps uniformly toward LEARN_FLOOR_CHARS;
    and only if it still overflows at the floor do we drop middle turns (keeping
    head + tail) and flag the session `truncated`. No mid-session turn is ever
    dropped on a normal day or week."""
    def total(a_cap, u_cap):
        return sum(_turn_cost(t, a_cap, u_cap) for s in sessions for t in s["turns"])

    a_cap, u_cap = LEARN_ASSISTANT_CHARS, LEARN_USER_CHARS
    full = total(a_cap, u_cap)
    if full > LEARN_GLOBAL_BUDGET:
        # Uniform shrink: scale both caps by the same factor, floored.
        scale = LEARN_GLOBAL_BUDGET / full
        a_cap = max(LEARN_FLOOR_CHARS, int(a_cap * scale))
        u_cap = max(LEARN_FLOOR_CHARS, int(u_cap * scale))

    for s in sessions:
        for t in s["turns"]:
            cap = a_cap if t["role"] == "assistant" else u_cap
            t["text"] = t["text"][:cap]

    # Extreme span: even flooring every turn overflows. Drop middle turns from the
    # largest sessions (keep first turn = topic anchor, and the tail where
    # understanding consolidates) until under budget, flagging each clipped session.
    if total(a_cap, u_cap) > LEARN_GLOBAL_BUDGET:
        keep = LEARN_KEEP_HEAD + LEARN_KEEP_TAIL
        for s in sorted(sessions, key=lambda s: len(s["turns"]), reverse=True):
            if len(s["turns"]) > keep:
                s["turns"] = s["turns"][:LEARN_KEEP_HEAD] + s["turns"][-LEARN_KEEP_TAIL:]
                s["truncated"] = True
            if sum(len(t["text"]) for ss in sessions for t in ss["turns"]) <= LEARN_GLOBAL_BUDGET:
                break


if LEARNINGS:
    apply_learnings_budget(sessions)


GITHUB_URL_RE = re.compile(r"github\.com[:/]([^/]+)/([^/]+?)(?:\.git)?/?$")


def repo_slug_for_cwd(cwd):
    """Return 'owner/name' for a cwd whose git origin points to github.com, else None."""
    if not cwd or not os.path.isdir(cwd):
        return None
    try:
        r = subprocess.run(
            ["git", "-C", cwd, "remote", "get-url", "origin"],
            capture_output=True, text=True, timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if r.returncode != 0:
        return None
    m = GITHUB_URL_RE.search(r.stdout.strip())
    return f"{m.group(1)}/{m.group(2)}" if m else None


def current_gh_user():
    """Return the authenticated gh user's login, or None if unavailable."""
    try:
        r = subprocess.run(
            ["gh", "api", "user", "--jq", ".login"],
            capture_output=True, text=True, timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if r.returncode != 0:
        return None
    return r.stdout.strip() or None


def releases_for_repo(slug, gh_user):
    """Return today's published, non-draft releases authored by gh_user, or []."""
    try:
        r = subprocess.run(
            ["gh", "api", f"repos/{slug}/releases?per_page=30"],
            capture_output=True, text=True, timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    if r.returncode != 0:
        return []
    try:
        data = json.loads(r.stdout)
    except json.JSONDecodeError:
        return []
    out = []
    for rel in data:
        if rel.get("draft"):
            continue
        author = (rel.get("author") or {}).get("login")
        if author != gh_user:
            continue
        pub = rel.get("published_at") or ""
        pub_norm = pub[:-1] if pub.endswith("Z") else pub
        if not (range_start_iso <= pub_norm < range_end_iso):
            continue
        tag = rel.get("tag_name") or ""
        out.append({
            "repo": slug,
            "tag": tag,
            "name": rel.get("name") or tag,
            "url": rel.get("html_url") or (f"https://github.com/{slug}/releases/tag/{tag}" if tag else None),
            "published_at": pub,
            "prerelease": bool(rel.get("prerelease")),
            "author": author,
        })
    return out


def ci_runs_for_sha(slug, head_sha):
    """Return GitHub Actions workflow runs for a commit, raw fields only — the prompt
    rolls these into CI pass/fail/running. [] on missing sha or any gh error (D4).

    No prod/staging flag: GitHub's only structured prod signal is the Environments API,
    which most repos (incl. wisor) don't configure, and workflow-name heuristics are
    unreliable ('Deploy to ci' is staging). Deferred to a future Environments-based pass.
    """
    if not head_sha:
        return []
    try:
        r = subprocess.run(
            ["gh", "api", f"repos/{slug}/actions/runs?head_sha={head_sha}&per_page=20"],
            capture_output=True, text=True, timeout=15,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    if r.returncode != 0:
        return []
    try:
        data = json.loads(r.stdout)
    except json.JSONDecodeError:
        return []
    runs = []
    for run in data.get("workflow_runs", []):
        runs.append({
            "name": run.get("name"),
            "path": run.get("path"),
            "status": run.get("status"),
            "conclusion": run.get("conclusion"),
            "event": run.get("event"),
            "url": run.get("html_url"),
            "updated_at": run.get("updated_at"),
        })
    return runs


def prs_for_repo(slug, gh_user):
    """Return PRs in `slug` authored by gh_user whose latest activity falls within
    the target window plus the 24h forward grace window (D1). Raw fields only —
    delivery-state classification is the prompt's job. [] on any gh error (D4).

    Uses `gh pr list --search author:` (server-side author filter) rather than the
    REST pulls list: on a busy team repo the 30 most-recently-updated PRs across all
    authors bury the user's own older PRs past the page limit, silently dropping them.
    """
    try:
        r = subprocess.run(
            ["gh", "pr", "list", "--repo", slug, "--state", "all", "--limit", "30",
             "--search", f"author:{gh_user} sort:updated-desc",
             "--json", "number,title,state,createdAt,updatedAt,closedAt,mergedAt,"
                       "url,headRefName,headRefOid,baseRefName,isDraft"],
            capture_output=True, text=True, timeout=15,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    if r.returncode != 0:
        return []
    try:
        data = json.loads(r.stdout)
    except json.JSONDecodeError:
        return []
    out = []
    for pr in data:
        upd = pr.get("updatedAt") or ""
        upd_norm = upd[:-1] if upd.endswith("Z") else upd
        # Sorted newest-activity-first: once we fall below the window start,
        # nothing remaining can be in-window.
        if upd_norm and upd_norm < range_start_iso:
            break
        if not (range_start_iso <= upd_norm < grace_end_iso):
            continue
        merged_at = pr.get("mergedAt")
        head_sha = pr.get("headRefOid")
        out.append({
            "repo": slug,
            "number": pr.get("number"),
            "title": pr.get("title") or "",
            "state": (pr.get("state") or "").lower(),
            "merged": bool(merged_at),
            "draft": bool(pr.get("isDraft")),
            "created_at": pr.get("createdAt"),
            "merged_at": merged_at,
            "closed_at": pr.get("closedAt"),
            "updated_at": pr.get("updatedAt"),
            "url": pr.get("url"),
            "head_ref": pr.get("headRefName"),
            "head_sha": head_sha,
            "base_ref": pr.get("baseRefName"),
            "author": gh_user,
            "ci": ci_runs_for_sha(slug, head_sha),
        })
    return out


def load_history_backfill(covered, path=None):
    """Surface lightweight activity from the long-lived global prompt log
    (~/.claude/history.jsonl) for (cwd, date) pairs in range that have NO
    per-session transcript — days whose transcripts were deleted by the
    `cleanupPeriodDays` retention. Returns [{cwd, date, prompts, count}] grouped
    by (cwd, date); slash-commands / meta prompts are dropped. [] if absent.

    The log records {display, project, timestamp} and outlives transcripts, so it
    backfills cleaned days. The rich narrative (titles, assistant output) is gone,
    but delivery state for those days is still recoverable live from gh.
    """
    path = path or os.path.expanduser("~/.claude/history.jsonl")
    if not os.path.exists(path):
        return []
    by_key = {}
    entered = False  # have we reached an in-range entry yet?
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
                ts = d.get("timestamp")
                proj = d.get("project")
                disp = (d.get("display") or "").strip()
                if not ts or not proj or not disp or disp.startswith("/"):
                    continue  # missing fields, or a slash-command / meta entry
                secs = ts / 1000 if ts > 1e11 else ts
                # The log is append-only chronological: once we've entered and
                # exited the window, nothing further can contribute (mirrors the
                # session-transcript scan). Compare on epoch seconds, which stay
                # monotonic across a DST fall-back unlike local-time ISO strings.
                if secs >= range_end_epoch:
                    if entered:
                        break
                    continue
                if secs < range_start_epoch:
                    continue
                try:
                    when = datetime.datetime.fromtimestamp(secs)
                except (OverflowError, OSError, ValueError):
                    continue
                entered = True
                date_str = when.date().isoformat()
                if (proj, date_str) in covered:
                    continue  # a transcript already covers this cwd + day
                by_key.setdefault((proj, date_str), []).append(disp[:MAX_PROMPT_CHARS])
    except OSError:
        return []
    out = [
        {"cwd": proj, "date": date_str, "prompts": prompts[:MAX_PROMPTS], "count": len(prompts)}
        for (proj, date_str), prompts in by_key.items()
    ]
    out.sort(key=lambda h: (h["date"], h["cwd"]))
    return out


# (cwd, date) pairs already covered by a rich transcript — don't backfill those.
covered = set()
for s in sessions:
    cwd = s.get("cwd")
    start = s.get("start")
    if not cwd or not start:
        continue
    try:
        a = datetime.date.fromisoformat(start[:10])
        b = datetime.date.fromisoformat((s.get("end") or start)[:10])
    except ValueError:
        covered.add((cwd, start[:10]))
        continue
    cur = a
    while cur <= b:
        covered.add((cwd, cur.isoformat()))
        cur += datetime.timedelta(days=1)

history = load_history_backfill(covered)

# Collect repos from transcript sessions AND history-backfilled days, so cleaned
# days still get their (durable, gh-sourced) PR/CI/release delivery state.
cwds = [c for c in dict.fromkeys(item.get("cwd") for item in sessions + history) if c]

if LEARNINGS:
    # Learnings mode skips the gh delivery/releases joins entirely (pure "shipped"
    # signal — see docs/adr/0001): faster, network-free, leaner JSON. `history` is
    # still emitted so the prompt can flag days past transcript retention as
    # learning-blind (those days carry only prompts, no assistant narrative).
    print(json.dumps(
        {"date": START if START == END else f"{START}..{END}",
         "start": START, "end": END, "mode": "learnings",
         "count": len(sessions), "sessions": sessions,
         "history": history},
        indent=2, ensure_ascii=False,
    ))
    sys.exit(0)

releases = []
delivery = []
gh_user = current_gh_user()
if gh_user:
    seen_repos = set()
    for c in cwds:
        slug = repo_slug_for_cwd(c)
        if not slug or slug in seen_repos:
            continue
        seen_repos.add(slug)
        releases.extend(releases_for_repo(slug, gh_user))
        delivery.extend(prs_for_repo(slug, gh_user))

releases.sort(key=lambda r: r.get("published_at") or "")
delivery.sort(key=lambda p: (p.get("repo") or "", p.get("updated_at") or ""))

print(json.dumps(
    {"date": START if START == END else f"{START}..{END}",
     "start": START, "end": END,
     "count": len(sessions), "sessions": sessions,
     "history": history,
     "releases": releases, "delivery": delivery},
    indent=2, ensure_ascii=False,
))
