#!/usr/bin/env python3
"""Blog/Report integrity validator.

Detects:
- Orphan reports (no blog entry references them)
- Blog entries with missing/broken report fields
- Wrong report field format (paths instead of filename)

Usage:
  python3 validate.py          # Full report
  python3 validate.py --fix    # Fix auto-fixable issues
  python3 validate.py --recent # Only last 3 days
"""

import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

import yaml

ENTRIES_DIR = Path.home() / "edge/blog/entries"
REPORTS_DIR = Path.home() / "edge/reports"
RED = "\033[91m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
RESET = "\033[0m"
BOLD = "\033[1m"


def load_entries():
    """Load all blog entries with frontmatter."""
    entries = {}
    for fp in sorted(ENTRIES_DIR.glob("*.md")):
        raw = fp.read_text(encoding="utf-8")
        parts = raw.split("---", 2)
        if len(parts) < 3:
            continue
        try:
            fm = yaml.safe_load(parts[1])
        except Exception:
            continue
        entries[fp.stem] = {
            "path": fp,
            "frontmatter": fm,
            "report": fm.get("report", ""),
            "date": str(fm.get("date", "")),
            "title": fm.get("title", fp.stem),
            "tag": fm.get("tag", "") or (fm.get("tags", [""])[0] if fm.get("tags") else ""),
        }
    return entries


def normalize_report_ref(ref):
    """Extract just the filename from a report reference."""
    if not ref:
        return ""
    return os.path.basename(ref.rstrip("/"))


def validate(recent_only=False, fix=False):
    entries = load_entries()
    reports = {f.name for f in REPORTS_DIR.glob("*.html")}

    cutoff = ""
    if recent_only:
        cutoff = (datetime.now() - timedelta(days=3)).strftime("%Y-%m-%d")

    # Track all issues
    orphan_reports = []
    missing_report_field = []
    broken_report_refs = []
    wrong_format_refs = []
    # Build set of referenced reports (normalized)
    referenced = set()
    for slug, entry in entries.items():
        ref = entry["report"]
        if ref:
            normalized = normalize_report_ref(ref)
            referenced.add(normalized)

            # Check wrong format (path instead of filename)
            if ref != normalized:
                wrong_format_refs.append((slug, ref, normalized))

            # Check broken ref (file doesn't exist)
            if normalized not in reports:
                broken_report_refs.append((slug, normalized))

    # Orphan reports
    for rname in sorted(reports):
        if recent_only and not rname >= cutoff:
            continue
        if rname not in referenced:
            orphan_reports.append(rname)

    # ALL blog entries MUST have a report field
    for slug, entry in entries.items():
        if recent_only and entry["date"] < cutoff:
            continue
        if not entry["report"]:
            candidates = [r for r in reports if slug in r or r.startswith(entry["date"])]
            missing_report_field.append((slug, entry["tag"] or "no-tag", candidates[:3]))

    # --- OUTPUT ---
    print(f"\n{BOLD}=== Blog/Report Integrity Validation ==={RESET}")
    print(f"Entries: {len(entries)} | Reports: {len(reports)} | "
          f"{'Last 3 days only' if recent_only else 'All time'}\n")

    issues = 0

    if orphan_reports:
        issues += len(orphan_reports)
        print(f"{RED}{BOLD}ORPHAN REPORTS ({len(orphan_reports)}):{RESET} report without blog entry")
        for r in orphan_reports[-20:]:
            print(f"  {RED}-{RESET} {r}")
        if len(orphan_reports) > 20:
            print(f"  ... and {len(orphan_reports) - 20} more")

    if wrong_format_refs:
        issues += len(wrong_format_refs)
        print(f"\n{YELLOW}{BOLD}WRONG FORMAT ({len(wrong_format_refs)}):{RESET} report field has path instead of filename")
        for slug, wrong, correct in wrong_format_refs:
            print(f"  {YELLOW}-{RESET} {slug}")
            print(f"    current: {wrong}")
            print(f"    correct: {correct}")
            if fix:
                entry = entries[slug]
                fp = entry["path"]
                content = fp.read_text()
                content = content.replace(wrong, correct)
                fp.write_text(content)
                print(f"    {GREEN}FIXED{RESET}")

    if broken_report_refs:
        issues += len(broken_report_refs)
        print(f"\n{RED}{BOLD}BROKEN REFS ({len(broken_report_refs)}):{RESET} blog entry references report that does not exist")
        for slug, ref in broken_report_refs:
            print(f"  {RED}-{RESET} {slug} -> {ref}")

    if missing_report_field:
        issues += len(missing_report_field)
        print(f"\n{YELLOW}{BOLD}MISSING REPORT FIELD ({len(missing_report_field)}):{RESET} blog entry without report field")
        for slug, tag, candidates in missing_report_field[:15]:
            print(f"  {YELLOW}-{RESET} {slug} (tag: {tag})")
            if candidates:
                print(f"    candidates: {', '.join(candidates[:2])}")
                if fix and len(candidates) == 1:
                    entry = entries[slug]
                    fp = entry["path"]
                    content = fp.read_text()
                    # Add report field after date field
                    content = content.replace(
                        f"date: {entry['date']}",
                        f"date: {entry['date']}\nreport: {candidates[0]}"
                    )
                    fp.write_text(content)
                    print(f"    {GREEN}FIXED (added report: {candidates[0]}){RESET}")

    if issues == 0:
        print(f"{GREEN}{BOLD}ALL CLEAR{RESET} -- no issues found")
    else:
        print(f"\n{BOLD}Total: {issues} issues{RESET}")
        if not fix:
            print(f"Run with {CYAN}--fix{RESET} to auto-fix format issues")

    return issues


if __name__ == "__main__":
    fix = "--fix" in sys.argv
    recent = "--recent" in sys.argv
    issues = validate(recent_only=recent, fix=fix)
    sys.exit(1 if issues > 0 else 0)
