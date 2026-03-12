#!/usr/bin/env python3
"""ledger_rollup.py — Aggregate execution ledger into ops-hotspots.json.

Usage:
  ledger_rollup.py              # default 48h window
  ledger_rollup.py --since 7d   # 7-day window (for manual reflexao)
  ledger_rollup.py --since 24h  # 24h window

Reads ~/edge/logs/execution-ledger.jsonl and produces
~/edge/state/ops-hotspots.json with aggregated telemetry:
incidents, top_pain, recovered_but_unstable, codify_now.

Cross-references ~/.claude/projects/-home-vboxuser/memory/debugging.md
to mark workaround_known=true when an error fingerprint matches a known entry.
"""

import argparse
import json
import re
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

LEDGER_FILE = Path.home() / "edge" / "logs" / "execution-ledger.jsonl"
OUTPUT_FILE = Path.home() / "edge" / "state" / "ops-hotspots.json"
DEBUGGING_MD = (
    Path.home()
    / ".claude"
    / "projects"
    / "-home-vboxuser"
    / "memory"
    / "debugging.md"
)


def parse_since(since_str):
    """Parse a duration string like '48h', '7d', '2w' into a timedelta."""
    m = re.match(r"^(\d+)\s*([hdwm])$", since_str.strip())
    if not m:
        print(
            f"ERROR: invalid --since format '{since_str}'. Use e.g. 48h, 7d, 2w",
            file=sys.stderr,
        )
        sys.exit(1)
    val, unit = int(m.group(1)), m.group(2)
    if unit == "h":
        return timedelta(hours=val)
    elif unit == "d":
        return timedelta(days=val)
    elif unit == "w":
        return timedelta(weeks=val)
    elif unit == "m":
        return timedelta(days=val * 30)


def read_events(since_td):
    """Read events from the ledger within the time window."""
    if not LEDGER_FILE.exists():
        return []

    now = datetime.now(timezone.utc)
    cutoff = now - since_td
    events = []

    with open(LEDGER_FILE) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                ev = json.loads(line)
            except json.JSONDecodeError:
                continue
            try:
                ts = datetime.fromisoformat(ev["ts"])
                if ts < cutoff:
                    continue
            except (KeyError, ValueError):
                continue
            events.append(ev)

    return events


def load_debugging_md():
    """Load debugging.md content for cross-referencing error fingerprints."""
    if not DEBUGGING_MD.exists():
        return ""
    return DEBUGGING_MD.read_text(errors="replace")


def make_signature(ev):
    """Create an incident signature from tool + error_class + phase."""
    tool = ev.get("tool", "unknown")
    error_class = ev.get("error_class", "") or "success"
    phase = ev.get("phase", "") or "default"
    return f"{tool}:{error_class}:{phase}"


def group_incidents(events, debugging_content):
    """Group events into incidents by tool+phase+error_fingerprint."""
    now = datetime.now(timezone.utc)
    cutoff_24h = now - timedelta(hours=24)
    cutoff_7d = now - timedelta(days=7)

    # Group by signature + error_fingerprint
    groups = defaultdict(list)
    for ev in events:
        sig = make_signature(ev)
        fp = ev.get("error_fingerprint", "") or ""
        key = f"{sig}|{fp}"
        groups[key].append(ev)

    incidents = []
    for key, evts in groups.items():
        sig, fp = key.rsplit("|", 1)

        timestamps = []
        for e in evts:
            try:
                timestamps.append(datetime.fromisoformat(e["ts"]))
            except (KeyError, ValueError):
                pass

        first_seen = min(timestamps).isoformat() if timestamps else ""
        last_seen = max(timestamps).isoformat() if timestamps else ""

        count = len(evts)
        count_24h = sum(
            1
            for e in evts
            if _parse_ts(e) and _parse_ts(e) >= cutoff_24h
        )
        count_7d = sum(
            1
            for e in evts
            if _parse_ts(e) and _parse_ts(e) >= cutoff_7d
        )

        # success_after_retry_rate: of events with attempt > 1, what fraction succeeded
        retry_events = [e for e in evts if e.get("attempt", 1) > 1]
        if retry_events:
            retry_successes = sum(1 for e in retry_events if e.get("ok", False))
            success_after_retry_rate = round(retry_successes / len(retry_events), 4)
        else:
            success_after_retry_rate = 0.0

        # total_wasted_ms: sum of duration_ms for failed events
        total_wasted_ms = sum(
            e.get("duration_ms", 0) for e in evts if not e.get("ok", True)
        )

        # workaround_known: check if fingerprint or signature appears in debugging.md
        workaround_known = False
        if fp and fp in debugging_content:
            workaround_known = True
        elif sig.split(":")[1] != "success" and sig.split(":")[1] in debugging_content:
            workaround_known = True

        incidents.append(
            {
                "signature": sig,
                "error_fingerprint": fp,
                "first_seen": first_seen,
                "last_seen": last_seen,
                "count": count,
                "count_24h": count_24h,
                "count_7d": count_7d,
                "success_after_retry_rate": success_after_retry_rate,
                "total_wasted_ms": total_wasted_ms,
                "workaround_known": workaround_known,
            }
        )

    return incidents


def _parse_ts(event):
    """Parse timestamp from event, return None on failure."""
    try:
        return datetime.fromisoformat(event["ts"])
    except (KeyError, ValueError):
        return None


def compute_top_pain(incidents, n=5):
    """Top N incidents by total_wasted_ms."""
    return sorted(incidents, key=lambda i: -i["total_wasted_ms"])[:n]


def compute_recovered_but_unstable(incidents):
    """Incidents that succeeded on retry but have retry_rate > 40%."""
    return [
        i
        for i in incidents
        if i["success_after_retry_rate"] > 0.4 and i["count"] > 1
    ]


def compute_codify_now(incidents):
    """Incidents with count >= 3 that aren't already in debugging.md."""
    return [
        i
        for i in incidents
        if i["count"] >= 3 and not i["workaround_known"]
    ]


def main():
    parser = argparse.ArgumentParser(
        description="Aggregate execution ledger into ops-hotspots.json"
    )
    parser.add_argument(
        "--since",
        default="48h",
        help="Time window (e.g. 48h, 7d). Default: 48h",
    )
    args = parser.parse_args()

    since_td = parse_since(args.since)
    events = read_events(since_td)
    debugging_content = load_debugging_md()

    incidents = group_incidents(events, debugging_content)
    top_pain = compute_top_pain(incidents)
    recovered = compute_recovered_but_unstable(incidents)
    codify = compute_codify_now(incidents)

    output = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "window": args.since,
        "incidents": incidents,
        "top_pain": top_pain,
        "recovered_but_unstable": recovered,
        "codify_now": codify,
    }

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_FILE.write_text(json.dumps(output, indent=2, ensure_ascii=False) + "\n")

    print(
        f"OK: {len(incidents)} incidents, {len(top_pain)} top_pain, "
        f"{len(recovered)} recovered_unstable, {len(codify)} codify_now → {OUTPUT_FILE}"
    )


if __name__ == "__main__":
    main()
