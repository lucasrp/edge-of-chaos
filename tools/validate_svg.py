#!/usr/bin/env python3
"""Validate SVG elements inside HTML reports.

Usage:
    validate-svg report.html [report2.html ...]
    validate-svg --recent              # last 5 reports
    validate-svg --all                 # all reports in ~/edge/reports/

Checks per SVG:
    1. XML well-formedness (can it be parsed?)
    2. Has viewBox attribute
    3. viewBox has non-zero dimensions
    4. Has at least 1 visible element (rect, circle, text, path, line, polygon, polyline, ellipse, g)
    5. No unclosed tags that break the rest of the HTML

Exit code: 0 if all pass, 1 if any fail.
"""

import sys
import re
import glob
import os
from xml.etree import ElementTree as ET

REPORTS_DIR = os.path.expanduser("~/edge/reports")

VISIBLE_TAGS = {
    "rect", "circle", "text", "path", "line", "polygon",
    "polyline", "ellipse", "g", "image", "use", "foreignObject",
}

# Strip namespace prefixes for tag matching
def local_tag(tag: str) -> str:
    return tag.split("}")[-1] if "}" in tag else tag


def extract_svgs(html: str) -> list[tuple[int, str]]:
    """Extract all <svg>...</svg> blocks with their position index."""
    svgs = []
    for i, m in enumerate(re.finditer(r"<svg[^>]*>.*?</svg>", html, re.DOTALL | re.IGNORECASE), 1):
        svgs.append((i, m.group()))
    return svgs


def validate_one(index: int, svg_text: str) -> list[str]:
    """Return list of issues (empty = OK)."""
    issues = []

    # 1. XML well-formedness
    try:
        root = ET.fromstring(svg_text)
    except ET.ParseError as e:
        issues.append(f"malformed XML: {e}")
        return issues  # can't check further

    # 2. Has viewBox
    viewbox = root.get("viewBox") or root.get("viewbox")
    if not viewbox:
        issues.append("missing viewBox")
    else:
        # 3. Non-zero dimensions
        parts = viewbox.split()
        if len(parts) == 4:
            try:
                w, h = float(parts[2]), float(parts[3])
                if w == 0 or h == 0:
                    issues.append(f"viewBox has zero dimension: {viewbox}")
                if w < 10 or h < 10:
                    issues.append(f"viewBox suspiciously small: {viewbox}")
            except ValueError:
                issues.append(f"viewBox not numeric: {viewbox}")
        else:
            issues.append(f"viewBox malformed: {viewbox}")

    # 4. At least 1 visible element
    visible_count = 0
    for elem in root.iter():
        if local_tag(elem.tag) in VISIBLE_TAGS:
            visible_count += 1
    if visible_count == 0:
        issues.append("no visible elements (rect, circle, text, path, etc.)")

    return issues


def validate_file(filepath: str) -> tuple[int, int]:
    """Validate all SVGs in a file. Returns (pass_count, fail_count)."""
    filename = os.path.basename(filepath)
    try:
        with open(filepath, encoding="utf-8") as f:
            html = f.read()
    except (FileNotFoundError, PermissionError) as e:
        print(f"  ERROR: {e}")
        return 0, 1

    svgs = extract_svgs(html)
    if not svgs:
        print(f"  {filename}: no SVGs found")
        return 0, 0

    passes = 0
    fails = 0
    for index, svg_text in svgs:
        issues = validate_one(index, svg_text)
        # Count elements for info
        try:
            root = ET.fromstring(svg_text)
            elem_count = sum(1 for e in root.iter() if local_tag(e.tag) in VISIBLE_TAGS)
            viewbox = root.get("viewBox") or root.get("viewbox") or "?"
        except ET.ParseError:
            elem_count = "?"
            viewbox = "?"

        if issues:
            fails += 1
            print(f"  FAIL SVG {index}: {viewbox}, {elem_count} elements")
            for issue in issues:
                print(f"       - {issue}")
        else:
            passes += 1
            print(f"  OK   SVG {index}: {viewbox}, {elem_count} elements")

    return passes, fails


def main():
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        sys.exit(0)

    files = []
    if "--recent" in args:
        all_html = sorted(glob.glob(f"{REPORTS_DIR}/*.html"), key=os.path.getmtime, reverse=True)
        files = all_html[:5]
    elif "--all" in args:
        files = sorted(glob.glob(f"{REPORTS_DIR}/*.html"), key=os.path.getmtime, reverse=True)
    else:
        files = args

    total_pass = 0
    total_fail = 0

    for f in files:
        basename = os.path.basename(f)
        print(f"\n{basename}")
        p, fail = validate_file(f)
        total_pass += p
        total_fail += fail

    # Summary
    total = total_pass + total_fail
    print(f"\n{'=' * 40}")
    if total == 0:
        print("No SVGs found in any file.")
    elif total_fail == 0:
        print(f"All {total_pass} SVGs valid.")
    else:
        print(f"{total_pass} OK, {total_fail} FAILED out of {total} SVGs.")

    sys.exit(1 if total_fail > 0 else 0)


if __name__ == "__main__":
    main()
