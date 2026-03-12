"""Shared service helpers for dashboard and action blueprints."""

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import markdown

ROOT = Path.home() / "continuum"
STATE_DIR = ROOT / "state"
THREADS_DIR = ROOT / "threads"
LOGS_DIR = ROOT / "logs"

TASKS_SNAPSHOT = STATE_DIR / "tasks.snapshot.json"
TASKS_JSONL = STATE_DIR / "tasks.jsonl"
OPS_HOTSPOTS = STATE_DIR / "ops-hotspots.json"
GIT_SIGNALS = STATE_DIR / "git-signals.json"
CURADORIA_CANDIDATES = STATE_DIR / "curadoria-candidates.json"
EXECUTION_LEDGER = LOGS_DIR / "execution-ledger.jsonl"
ENTRIES_DIR = ROOT / "blog" / "entries"


def load_json_safe(path, default=None):
    """Load a JSON file, returning default on any error."""
    if default is None:
        default = {}
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return default


def load_tasks_snapshot():
    return load_json_safe(TASKS_SNAPSHOT, {})


def load_hotspots():
    return load_json_safe(OPS_HOTSPOTS, {
        "incidents": [], "top_pain": [],
        "recovered_but_unstable": [], "codify_now": []
    })


def load_git_signals():
    return load_json_safe(GIT_SIGNALS, {
        "fix_chains": [], "duplicate_slugs": [],
        "pipeline_failures": [], "state_violations": [],
        "thread_coverage": {}, "skill_distribution": {},
        "claims_summary": {}, "persistent_gaps": []
    })


def load_curadoria():
    return load_json_safe(CURADORIA_CANDIDATES, {
        "total_docs": 0, "stale_candidates": 0,
        "archive_auto": [], "merge_review": [],
        "strengthen_targets": []
    })


def task_age(created_at):
    """Human-readable age from ISO timestamp."""
    try:
        dt = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
        delta = datetime.now(timezone.utc) - dt
        hours = delta.total_seconds() / 3600
        if hours < 1:
            return f"{int(delta.total_seconds() / 60)}m"
        if hours < 24:
            return f"{int(hours)}h"
        return f"{int(hours / 24)}d"
    except Exception:
        return "?"


def categorize_tasks(snap):
    """Categorize tasks by status, sorted by priority."""
    prio_order = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}
    all_tasks = sorted(
        snap.values(),
        key=lambda t: (prio_order.get(t.get("priority", "P3"), 9), t.get("updated_at", ""))
    )
    now = datetime.now(timezone.utc)
    stale = []
    for t in all_tasks:
        if t.get("status") in ("done", "dropped"):
            continue
        updated = t.get("updated_at", "")
        if updated:
            try:
                dt = datetime.fromisoformat(updated.replace("Z", "+00:00"))
                if (now - dt).total_seconds() > 48 * 3600:
                    stale.append(t["task_id"])
            except Exception:
                pass

    return {
        "doing": [t for t in all_tasks if t.get("status") == "doing"],
        "blocked": [t for t in all_tasks if t.get("status") == "blocked"],
        "todo": [t for t in all_tasks if t.get("status") == "todo"],
        "done": [t for t in all_tasks if t.get("status") == "done"],
        "stale_ids": stale,
        "total": len(all_tasks),
    }


def get_publish_commits(limit=10):
    """Get last N git commits matching 'publish:' pattern."""
    try:
        result = subprocess.run(
            ["git", "-C", str(ROOT), "log", "--all", "--oneline",
             "--grep=publish:", f"-{limit}", "--format=%H|%s|%aI"],
            capture_output=True, text=True, timeout=5
        )
        commits = []
        for line in result.stdout.strip().splitlines():
            if not line:
                continue
            parts = line.split("|", 2)
            if len(parts) < 3:
                continue
            hash_val, subject, timestamp = parts
            # Parse status from subject: publish: slug [state:ok|partial|failed]
            status = "ok"
            if "[state:partial]" in subject:
                status = "partial"
            elif "[state:failed]" in subject:
                status = "failed"
            # Extract slug
            slug = subject.replace("publish:", "").strip()
            slug = slug.split("[")[0].strip()

            commits.append({
                "hash": hash_val,
                "slug": slug,
                "status": status,
                "subject": subject,
                "timestamp": timestamp,
            })
        return commits
    except Exception:
        return []


def get_error_pressure_24h():
    """Count failures in last 24h from execution-ledger.jsonl."""
    failures = 0
    tool_failures = {}
    try:
        if not EXECUTION_LEDGER.exists():
            return {"failures_24h": 0, "top_failing_tool": None}
        now = datetime.now(timezone.utc)
        for line in EXECUTION_LEDGER.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                entry = json.loads(line)
                ts = datetime.fromisoformat(entry["ts"].replace("Z", "+00:00"))
                if (now - ts).total_seconds() > 86400:
                    continue
                if not entry.get("ok", True):
                    failures += 1
                    tool = entry.get("tool", "unknown")
                    tool_failures[tool] = tool_failures.get(tool, 0) + 1
            except Exception:
                continue
    except Exception:
        pass

    top_tool = None
    if tool_failures:
        top_tool = max(tool_failures, key=tool_failures.get)

    return {"failures_24h": failures, "top_failing_tool": top_tool}


def get_production_stats():
    """Count entries, reports, and today's publications."""
    total_entries = 0
    total_reports = 0
    published_today = 0
    today_str = datetime.now().strftime("%Y-%m-%d")
    try:
        if ENTRIES_DIR.exists():
            for fp in ENTRIES_DIR.glob("*.md"):
                total_entries += 1
                raw = fp.read_text(encoding="utf-8", errors="replace")
                parts = raw.split("---", 2)
                if len(parts) >= 3:
                    try:
                        import yaml
                        fm = yaml.safe_load(parts[1])
                        if fm and fm.get("report"):
                            total_reports += 1
                        if fm and str(fm.get("date", "")) == today_str:
                            published_today += 1
                    except Exception:
                        pass
    except Exception:
        pass
    return {
        "entries_total": total_entries,
        "reports_total": total_reports,
        "published_today": published_today,
    }


BRIEFING_FILE = ROOT / "briefing.md"


def get_briefing_html(max_lines=50):
    """Load first max_lines of briefing.md and render as HTML. Returns None if missing."""
    try:
        if not BRIEFING_FILE.exists():
            return None
        lines = BRIEFING_FILE.read_text(encoding="utf-8").splitlines()[:max_lines]
        md_text = "\n".join(lines)
        return markdown.markdown(md_text, extensions=["tables", "fenced_code"])
    except Exception:
        return None


def get_heartbeat_status():
    """Check heartbeat health: healthy/late/stalled."""
    try:
        result = subprocess.run(
            ["systemctl", "--user", "is-active", "claude-heartbeat.timer"],
            capture_output=True, text=True, timeout=3
        )
        if result.stdout.strip() == "active":
            return {"status": "healthy", "color": "green"}
    except Exception:
        pass
    # Check last heartbeat log file timestamp
    try:
        logs = sorted(LOGS_DIR.glob("heartbeat-*.log"), reverse=True)
        if logs:
            mtime = datetime.fromtimestamp(logs[0].stat().st_mtime, tz=timezone.utc)
            hours = (datetime.now(timezone.utc) - mtime).total_seconds() / 3600
            if hours < 3:
                return {"status": "healthy", "color": "green"}
            elif hours < 6:
                return {"status": "late", "color": "yellow"}
            else:
                return {"status": "stalled", "color": "red"}
    except Exception:
        pass
    return {"status": "unknown", "color": "yellow"}
