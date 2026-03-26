"""Shared service helpers for dashboard and action blueprints."""

import json
import re
import subprocess
from datetime import date, datetime, timezone
from pathlib import Path

import markdown
import yaml

import os as _os
ROOT = Path(_os.environ.get("EDGE_DIR", str(Path(__file__).resolve().parent.parent)))
STATE_DIR = ROOT / "state"
THREADS_DIR = ROOT / "threads"
LOGS_DIR = ROOT / "logs"
ENTRIES_DIR = ROOT / "blog" / "entries"

TASKS_SNAPSHOT = STATE_DIR / "tasks.snapshot.json"
TASKS_JSONL = STATE_DIR / "tasks.jsonl"
OPS_HOTSPOTS = STATE_DIR / "ops-hotspots.json"
GIT_SIGNALS = STATE_DIR / "git-signals.json"
CURADORIA_CANDIDATES = STATE_DIR / "curadoria-candidates.json"
EXECUTION_LEDGER = LOGS_DIR / "execution-ledger.jsonl"


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
    """Load materialized task snapshot."""
    return load_json_safe(TASKS_SNAPSHOT, {
        "tasks": [], "summary": {"total": 0, "by_status": {}, "by_priority": {}}
    })


def categorize_tasks(snap):
    """Categorize tasks from snapshot into status buckets."""
    tasks = snap.get("tasks", [])
    result = {"doing": [], "todo": [], "blocked": [], "done": []}
    for t in tasks:
        status = t.get("status", "todo")
        result.setdefault(status, []).append(t)
    return result


def task_age(task):
    """Return age in days of a task."""
    created = task.get("created_at", task.get("ts", ""))
    if not created:
        return 0
    try:
        dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
        return (datetime.now(timezone.utc) - dt).days
    except (ValueError, TypeError):
        return 0


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


# ─── Threads ───

def _build_entries_thread_index():
    """Build {thread_id: count} from entry frontmatter."""
    index = {}
    if not ENTRIES_DIR.exists():
        return index
    for fp in ENTRIES_DIR.glob("*.md"):
        try:
            raw = fp.read_text(encoding="utf-8", errors="replace")
            parts = raw.split("---", 2)
            if len(parts) < 3:
                continue
            fm = yaml.safe_load(parts[1])
            if not fm:
                continue
            threads = fm.get("threads", [])
            if isinstance(threads, str):
                threads = [t.strip() for t in threads.split(",")]
            if not isinstance(threads, list):
                continue
            for tid in threads:
                tid = str(tid).strip()
                if tid:
                    index[tid] = index.get(tid, 0) + 1
        except Exception:
            continue
    return index


def _parse_next_step(raw_body):
    """Extract first non-empty line after ## Próximo passo or ## Next."""
    match = re.search(r"^##\s+(?:Próximo passo|Next)\s*$", raw_body, re.MULTILINE | re.IGNORECASE)
    if not match:
        return None
    after = raw_body[match.end():]
    for line in after.splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            return stripped
    return None


def load_threads_enriched(status_filter=None):
    """Load threads with enriched metadata (entries_count, resurface_due, next_step)."""
    if not THREADS_DIR.exists():
        return {"threads": [], "stats": {"total": 0, "active": 0, "dormant": 0, "done": 0, "proposed": 0, "resurface_due": 0}}

    entries_index = _build_entries_thread_index()
    today = date.today()
    threads = []
    stats = {"total": 0, "active": 0, "dormant": 0, "done": 0, "proposed": 0, "resurface_due": 0}

    for fp in sorted(THREADS_DIR.glob("*.md")):
        try:
            raw = fp.read_text(encoding="utf-8", errors="replace")
            parts = raw.split("---", 2)
            if len(parts) < 3:
                continue
            fm = yaml.safe_load(parts[1])
            if not fm:
                continue

            thread_id = fm.get("id", fp.stem)
            status = fm.get("status", "active")
            entries_count = entries_index.get(thread_id, 0) or entries_index.get(fp.stem, 0)
            next_step = _parse_next_step(parts[2])

            # Resurface check
            resurface_str = fm.get("resurface")
            resurface_due = False
            if resurface_str:
                try:
                    rd = date.fromisoformat(str(resurface_str))
                    resurface_due = rd <= today
                except (ValueError, TypeError):
                    pass

            stats["total"] += 1
            if status in stats:
                stats[status] += 1
            if resurface_due and status == "active":
                stats["resurface_due"] += 1

            threads.append({
                "id": thread_id,
                "title": fm.get("title", fp.stem),
                "type": fm.get("type", "investigation"),
                "status": status,
                "owner": fm.get("owner", "unknown"),
                "created": str(fm.get("created", "")),
                "updated": str(fm.get("updated", "")),
                "resurface": str(resurface_str) if resurface_str else None,
                "goal": fm.get("goal"),
                "done_when": fm.get("done_when"),
                "entries_count": entries_count,
                "resurface_due": resurface_due,
                "next_step": next_step,
            })
        except Exception:
            continue

    if status_filter:
        threads = [t for t in threads if t["status"] == status_filter]

    return {"threads": threads, "stats": stats}


def load_thread_detail(thread_id):
    """Load full detail for a single thread: metadata, body, linked entries, reports, claims."""
    thread_path = THREADS_DIR / f"{thread_id}.md"
    if not thread_path.exists():
        return None

    raw = thread_path.read_text(encoding="utf-8", errors="replace")
    parts = raw.split("---", 2)
    if len(parts) < 3:
        return None
    fm = yaml.safe_load(parts[1]) or {}
    body_md = parts[2].strip()
    body_html = markdown.markdown(body_md, extensions=["tables", "fenced_code"])

    # Collect all entries linked to this thread
    entries = []
    all_claims = []
    reports_set = set()
    if ENTRIES_DIR.exists():
        for fp in sorted(ENTRIES_DIR.glob("*.md"), key=lambda p: p.name, reverse=True):
            try:
                eraw = fp.read_text(encoding="utf-8", errors="replace")
                eparts = eraw.split("---", 2)
                if len(eparts) < 3:
                    continue
                efm = yaml.safe_load(eparts[1])
                if not efm:
                    continue
                threads = efm.get("threads", [])
                if isinstance(threads, str):
                    threads = [t.strip() for t in threads.split(",")]
                if not isinstance(threads, list):
                    continue
                if thread_id not in [str(t).strip() for t in threads]:
                    continue
                entry_claims = efm.get("claims", [])
                if isinstance(entry_claims, str):
                    entry_claims = [entry_claims]
                if not isinstance(entry_claims, list):
                    entry_claims = []
                report_file = efm.get("report", "")
                note_file = efm.get("note", "")
                if report_file:
                    reports_set.add(report_file)
                entries.append({
                    "slug": fp.stem,
                    "title": efm.get("title", fp.stem),
                    "date": str(efm.get("date", "")),
                    "tags": efm.get("tags", []),
                    "claims": entry_claims,
                    "report": report_file,
                    "note": note_file,
                })
                all_claims.extend(entry_claims)
            except Exception:
                continue

    # Check which reports exist on disk
    reports = []
    for rf in sorted(reports_set):
        rpath = ROOT / "reports" / rf
        reports.append({
            "filename": rf,
            "exists": rpath.exists(),
            "url": f"/reports/{rf}" if rpath.exists() else None,
        })

    # Separate claims by type
    verified = [c for c in all_claims if not str(c).startswith("!")]
    gaps = [c for c in all_claims if str(c).startswith("!")]

    return {
        "id": fm.get("id", thread_id),
        "title": fm.get("title", thread_id),
        "type": fm.get("type", "investigation"),
        "status": fm.get("status", "active"),
        "owner": fm.get("owner", "unknown"),
        "created": str(fm.get("created", "")),
        "updated": str(fm.get("updated", "")),
        "resurface": str(fm.get("resurface", "")),
        "goal": fm.get("goal"),
        "done_when": fm.get("done_when"),
        "body_html": body_html,
        "entries": entries,
        "entries_count": len(entries),
        "reports": reports,
        "claims": all_claims,
        "claims_verified": verified,
        "claims_gaps": gaps,
        "claims_count": len(all_claims),
        "verified_count": len(verified),
        "gaps_count": len(gaps),
    }


_GENERIC_TAGS = {
    "pesquisa", "descoberta", "lazer", "reflexao", "execucao", "estrategia",
    "planejamento", "workflow", "anti-pattern", "relatorio", "calibracao",
    "blog", "heartbeat", "auditoria",
}


def compute_thread_candidates():
    """Detect recurring tags in entries that don't have a corresponding thread."""
    if not ENTRIES_DIR.exists():
        return []

    thread_ids = set()
    if THREADS_DIR.exists():
        for fp in THREADS_DIR.glob("*.md"):
            thread_ids.add(fp.stem)

    tag_entries = {}
    for fp in sorted(ENTRIES_DIR.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            raw = fp.read_text(encoding="utf-8", errors="replace")
            parts = raw.split("---", 2)
            if len(parts) < 3:
                continue
            fm = yaml.safe_load(parts[1])
            if not fm:
                continue
            tags = fm.get("tags", [])
            if isinstance(tags, str):
                tags = [t.strip() for t in tags.split(",")]
            if not isinstance(tags, list):
                continue
            entry_info = {
                "title": fm.get("title", fp.stem),
                "date": str(fm.get("date", "")),
                "slug": fp.stem,
            }
            for tag in tags:
                tag = str(tag).strip().lower()
                if tag and tag not in _GENERIC_TAGS and tag not in thread_ids:
                    tag_entries.setdefault(tag, []).append(entry_info)
        except Exception:
            continue

    candidates = []
    for tag, entries in sorted(tag_entries.items(), key=lambda x: -len(x[1])):
        if len(entries) >= 3:
            candidates.append({
                "tag": tag,
                "entry_count": len(entries),
                "recent_entries": entries[:3],
            })

    return candidates
