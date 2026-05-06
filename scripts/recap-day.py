#!/usr/bin/env python3
"""Extract a compact JSON recap of Claude Code sessions for a given date.

Usage: recap-day.py [YYYY-MM-DD]   (defaults to today, local time)

Reads ~/.claude/projects/*/*.jsonl (top-level session files only — skips
subagent transcripts) and emits a JSON document with one entry per session
that contained activity on the target date.
"""
import json, os, sys, glob, datetime

DATE = sys.argv[1] if len(sys.argv) > 1 else datetime.date.today().isoformat()
day_start_dt = datetime.datetime.fromisoformat(DATE + "T00:00:00")
day_end_dt = day_start_dt + datetime.timedelta(days=1)
day_start_iso = day_start_dt.isoformat()
day_end_iso = day_end_dt.isoformat()
day_start_epoch = day_start_dt.timestamp()

PROJECTS_DIR = os.path.expanduser("~/.claude/projects")


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
    t = text.lstrip()
    return (
        t.startswith("<system-reminder>")
        or t.startswith("<command-")
        or t.startswith("<local-command-")
        or t.startswith("[Request interrupted")
    )


def in_day(ts):
    """Compare ISO-8601 timestamps lexicographically against the day window."""
    if not ts:
        return False
    return day_start_iso <= ts < day_end_iso or (
        ts.endswith("Z")
        and day_start_iso <= ts[:-1] < day_end_iso
    )


def summarize_session(path):
    title = None
    cwd = None
    session_id = None
    first_user_today = None
    last_user_today = None
    last_assistant_today = None
    user_turns_today = 0
    assistant_turns_today = 0
    first_ts_today = None
    last_ts_today = None
    user_msgs_today = []

    with open(path) as f:
        for line in f:
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                continue
            t = d.get("type")
            ts = d.get("timestamp")

            if d.get("cwd") and not cwd:
                cwd = d["cwd"]
            if d.get("sessionId") and not session_id:
                session_id = d["sessionId"]
            if t == "ai-title":
                title = d.get("aiTitle") or title

            if not in_day(ts):
                continue

            if first_ts_today is None or ts < first_ts_today:
                first_ts_today = ts
            if last_ts_today is None or ts > last_ts_today:
                last_ts_today = ts

            if t == "user":
                msg = d.get("message", {})
                if isinstance(msg, dict):
                    text = extract_text(msg.get("content", ""))
                    if not is_meta_user(text):
                        user_turns_today += 1
                        text = text.strip()
                        if first_user_today is None:
                            first_user_today = text
                        last_user_today = text
                        user_msgs_today.append(text[:400])
            elif t == "assistant":
                msg = d.get("message", {})
                if isinstance(msg, dict):
                    text = extract_text(msg.get("content", ""))
                    if text.strip():
                        assistant_turns_today += 1
                        last_assistant_today = text.strip()

    if first_ts_today is None:
        return None

    return {
        "session_id": session_id,
        "cwd": cwd,
        "title": title,
        "start": first_ts_today,
        "end": last_ts_today,
        "user_turns": user_turns_today,
        "assistant_turns": assistant_turns_today,
        "first_user": (first_user_today or "")[:800],
        "last_user": (last_user_today or "")[:400],
        "last_assistant": (last_assistant_today or "")[:800],
        "user_prompts": user_msgs_today[:20],
    }


sessions = []
for project_dir in sorted(glob.glob(os.path.join(PROJECTS_DIR, "*"))):
    if not os.path.isdir(project_dir):
        continue
    for jsonl in glob.glob(os.path.join(project_dir, "*.jsonl")):
        if os.path.getmtime(jsonl) < day_start_epoch:
            continue
        s = summarize_session(jsonl)
        if s:
            sessions.append(s)

sessions.sort(key=lambda s: s["start"])
print(json.dumps({"date": DATE, "count": len(sessions), "sessions": sessions}, indent=2, ensure_ascii=False))
