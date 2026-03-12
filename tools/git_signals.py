#!/usr/bin/env python3
"""git_signals.py — Extract structured signals from git log for reflection.

Usage:
  python3 git_signals.py                  # default: 7d window
  python3 git_signals.py --since 12h      # 12-hour window (heartbeat)
  python3 git_signals.py --since 30d      # 30-day window (deep analysis)

Reads git log from ~/edge/, parses structured commit fields,
and outputs ~/edge/state/git-signals.json with:
fix chains, duplicate slugs, pipeline failures, state violations,
thread coverage, skill distribution, claims summary.
"""

import argparse
import json
import re
import subprocess
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

EDGE_DIR = Path.home() / "edge"
OUTPUT_FILE = EDGE_DIR / "state" / "git-signals.json"
SEPARATOR = "---SEPARATOR---"


def parse_since(since_str):
    """Parse duration for display (git handles the actual filtering)."""
    m = re.match(r"^(\d+)\s*([hdwm])$", since_str.strip())
    if not m:
        print(
            f"ERROR: invalid --since format '{since_str}'. Use e.g. 12h, 7d, 2w",
            file=sys.stderr,
        )
        sys.exit(1)
    val, unit = int(m.group(1)), m.group(2)
    # Convert to git --since format
    units = {"h": "hours", "d": "days", "w": "weeks", "m": "months"}
    return f"{val} {units[unit]} ago"


def get_commits(since_git):
    """Get commits from git log with full body."""
    cmd = [
        "git", "-C", str(EDGE_DIR), "log",
        f"--since={since_git}",
        f"--format=%H%n%aI%n%s%n%b%n{SEPARATOR}",
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    except subprocess.CalledProcessError as e:
        print(f"ERROR: git log failed: {e.stderr}", file=sys.stderr)
        return []

    commits = []
    for block in result.stdout.split(SEPARATOR + "\n"):
        block = block.strip()
        if not block:
            continue
        lines = block.split("\n")
        if len(lines) < 3:
            continue
        commit_hash = lines[0]
        date = lines[1]
        subject = lines[2]
        body = "\n".join(lines[3:])
        commits.append({
            "hash": commit_hash,
            "date": date,
            "subject": subject,
            "body": body,
        })

    return commits


def parse_structured_fields(body):
    """Parse structured fields from commit body."""
    fields = {}

    # pipeline-status
    m = re.search(r"^pipeline-status:\s*(.+)$", body, re.MULTILINE)
    if m:
        fields["pipeline_status"] = m.group(1).strip()

    # state-status
    m = re.search(r"^state-status:\s*(.+)$", body, re.MULTILINE)
    if m:
        fields["state_status"] = m.group(1).strip()

    # failures (indented list)
    failures = []
    m = re.search(r"^failures:\s*\n((?:\s+-\s+.+\n?)+)", body, re.MULTILINE)
    if m:
        for line in m.group(1).strip().split("\n"):
            line = line.strip().lstrip("- ").strip()
            if line:
                failures.append(line)
    fields["failures"] = failures

    # learned (N):
    learned = []
    m = re.search(r"^learned\s*\(\d+\):\s*\n((?:\s+-\s+.+\n?)+)", body, re.MULTILINE)
    if m:
        for line in m.group(1).strip().split("\n"):
            line = line.strip().lstrip("- ").strip()
            if line:
                learned.append(line)
    fields["learned"] = learned

    # gaps (N):
    gaps = []
    m = re.search(r"^gaps\s*\(\d+\):\s*\n((?:\s+-\s+.+\n?)+)", body, re.MULTILINE)
    if m:
        for line in m.group(1).strip().split("\n"):
            line = line.strip().lstrip("- ").strip()
            if line:
                gaps.append(line)
    fields["gaps"] = gaps

    # threads
    m = re.search(r"^threads:\s*(.+)$", body, re.MULTILINE)
    if m:
        threads = [t.strip() for t in m.group(1).split(",") if t.strip()]
        fields["threads"] = threads
    else:
        fields["threads"] = []

    # tags
    m = re.search(r"^tags:\s*(.+)$", body, re.MULTILINE)
    if m:
        tags = [t.strip() for t in m.group(1).split(",") if t.strip()]
        fields["tags"] = tags
    else:
        fields["tags"] = []

    return fields


def extract_slug(subject):
    """Extract slug from publish: subject."""
    m = re.match(r"^publish:\s+(.+?)(?:\s+\[.*\])?$", subject)
    if m:
        return m.group(1).strip()
    return None


def detect_fix_chains(commits):
    """Detect sequences of publish+fix+fix on same slug within 24h."""
    # Find all publish commits with their slugs and dates
    publishes = {}
    for c in commits:
        slug = extract_slug(c["subject"])
        if slug:
            try:
                dt = datetime.fromisoformat(c["date"])
                publishes[slug] = {"hash": c["hash"], "date": dt}
            except ValueError:
                pass

    # Find fix commits that reference a slug
    chains = []
    fix_pattern = re.compile(r"^fix:\s+(.+)$", re.IGNORECASE)
    for c in commits:
        m = fix_pattern.match(c["subject"])
        if not m:
            continue
        fix_desc = m.group(1)
        try:
            fix_dt = datetime.fromisoformat(c["date"])
        except ValueError:
            continue

        # Check if any published slug is referenced in the fix description
        for slug, pub_info in publishes.items():
            slug_parts = slug.split("-")
            # Match if slug (or significant part) appears in fix subject
            if slug in fix_desc or any(
                part in fix_desc.lower()
                for part in slug_parts
                if len(part) > 4
            ):
                hours_diff = abs((fix_dt - pub_info["date"]).total_seconds()) / 3600
                if hours_diff <= 24:
                    chains.append({
                        "slug": slug,
                        "publish_hash": pub_info["hash"],
                        "fix_hash": c["hash"],
                        "fix_subject": c["subject"],
                        "hours_after_publish": round(hours_diff, 1),
                    })

    return chains


def detect_duplicate_slugs(commits):
    """Detect same slug published 2+ times."""
    slug_counts = defaultdict(int)
    for c in commits:
        slug = extract_slug(c["subject"])
        if slug:
            slug_counts[slug] += 1

    return [
        {"slug": slug, "count": count}
        for slug, count in slug_counts.items()
        if count >= 2
    ]


def detect_pipeline_failures(commits):
    """Detect commits with pipeline-status: partial or failures."""
    failures = []
    for c in commits:
        fields = parse_structured_fields(c["body"])
        if fields.get("pipeline_status") == "partial" or fields["failures"]:
            failures.append({
                "hash": c["hash"],
                "subject": c["subject"],
                "pipeline_status": fields.get("pipeline_status", ""),
                "failures": fields["failures"],
            })
    return failures


def detect_state_violations(commits):
    """Detect commits with state-status != ok."""
    violations = []
    for c in commits:
        fields = parse_structured_fields(c["body"])
        status = fields.get("state_status", "")
        if status and status != "ok":
            violations.append({
                "hash": c["hash"],
                "subject": c["subject"],
                "state_status": status,
            })
    return violations


def compute_thread_coverage(commits):
    """Count how often each thread was fed."""
    thread_counts = defaultdict(int)
    for c in commits:
        fields = parse_structured_fields(c["body"])
        for thread in fields["threads"]:
            thread_counts[thread] += 1
    return dict(sorted(thread_counts.items(), key=lambda x: -x[1]))


def compute_skill_distribution(commits):
    """Count publishes by tag/skill type."""
    tag_counts = defaultdict(int)
    for c in commits:
        slug = extract_slug(c["subject"])
        if not slug:
            continue
        fields = parse_structured_fields(c["body"])
        for tag in fields["tags"]:
            tag_counts[tag] += 1
        if not fields["tags"]:
            tag_counts["untagged"] += 1
    return dict(sorted(tag_counts.items(), key=lambda x: -x[1]))


def compute_claims_summary(commits):
    """Compute total learned, total gaps, persistent gaps."""
    total_learned = 0
    total_gaps = 0
    gap_occurrences = defaultdict(int)

    for c in commits:
        fields = parse_structured_fields(c["body"])
        total_learned += len(fields["learned"])
        total_gaps += len(fields["gaps"])
        for gap in fields["gaps"]:
            # Normalize gap text for dedup (first 60 chars, lowered)
            key = gap[:60].lower().strip()
            gap_occurrences[key] += 1

    return {
        "total_learned": total_learned,
        "total_gaps": total_gaps,
    }, gap_occurrences


def main():
    parser = argparse.ArgumentParser(
        description="Extract structured signals from git log for reflection"
    )
    parser.add_argument(
        "--since",
        default="7d",
        help="Time window (e.g. 12h, 7d, 30d). Default: 7d",
    )
    args = parser.parse_args()

    since_git = parse_since(args.since)
    commits = get_commits(since_git)

    fix_chains = detect_fix_chains(commits)
    duplicate_slugs = detect_duplicate_slugs(commits)
    pipeline_failures = detect_pipeline_failures(commits)
    state_violations = detect_state_violations(commits)
    thread_coverage = compute_thread_coverage(commits)
    skill_distribution = compute_skill_distribution(commits)
    claims_summary, gap_occurrences = compute_claims_summary(commits)

    persistent_gaps = [
        {"gap_prefix": gap, "occurrences": count}
        for gap, count in sorted(gap_occurrences.items(), key=lambda x: -x[1])
        if count >= 3
    ]

    output = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "window": args.since,
        "total_commits": len(commits),
        "fix_chains": fix_chains,
        "duplicate_slugs": duplicate_slugs,
        "pipeline_failures": pipeline_failures,
        "state_violations": state_violations,
        "thread_coverage": thread_coverage,
        "skill_distribution": skill_distribution,
        "claims_summary": claims_summary,
        "persistent_gaps": persistent_gaps,
    }

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_FILE.write_text(json.dumps(output, indent=2, ensure_ascii=False) + "\n")

    print(
        f"OK: {len(commits)} commits, {len(fix_chains)} fix_chains, "
        f"{len(pipeline_failures)} pipeline_failures, "
        f"{len(persistent_gaps)} persistent_gaps -> {OUTPUT_FILE}"
    )


if __name__ == "__main__":
    main()
