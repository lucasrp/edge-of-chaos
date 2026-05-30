"""Structural validator for the Artifact Rite (the uniform format floor).

`validate_rite(spec)` is a pure function: a loaded report YAML spec in, a list
of violation codes out (empty list == conforms). It owns *form* deterministically;
*merit* stays with the LLM review gate.

Mandatory sections are identified by an explicit `role` on the section
(`lineage` | `gaps` | `glossary`) plus a position co-assertion, not by title
(titles drift across PT/EN). Wiring this into the publish pipeline, emitting
`role` from the skills, and trimming the review-gate prompt are a separate step.
"""
from __future__ import annotations

from typing import Any

VISUAL_BLOCK_TYPES = {"bar-chart", "line-chart"}
_RAW_HTML_FIELDS = ("html", "content", "svg", "raw")


def _has_svg(sections: list[dict[str, Any]]) -> bool:
    for section in sections:
        for block in section.get("blocks") or []:
            if not isinstance(block, dict):
                continue
            btype = str(block.get("type") or "").strip()
            if btype in VISUAL_BLOCK_TYPES:
                return True
            if btype == "raw-html":
                blob = " ".join(str(block.get(field) or "") for field in _RAW_HTML_FIELDS)
                if "<svg" in blob.lower():
                    return True
    return False


def _role_index(sections: list[dict[str, Any]], role: str) -> int:
    for index, section in enumerate(sections):
        if str(section.get("role") or "").strip() == role:
            return index
    return -1


def validate_rite(spec: dict[str, Any]) -> list[str]:
    """Return the list of Rite violation codes for a report spec (empty == ok)."""
    violations: list[str] = []

    if not spec.get("executive_summary"):
        violations.append("missing_executive_summary")
    if not spec.get("metrics"):
        violations.append("missing_metrics")
    if not spec.get("bibliography"):
        violations.append("missing_bibliography")

    sections = [s for s in (spec.get("sections") or []) if isinstance(s, dict)]
    n = len(sections)
    # (role, expected position, code-if-misplaced, code-if-absent)
    positioned = [
        ("lineage", 0, "lineage_not_first", "missing_lineage"),
        ("gaps", n - 2, "gaps_not_penultimate", "missing_gaps"),
        ("glossary", n - 1, "glossary_not_last", "missing_glossary"),
    ]
    for role, expected_index, misplaced_code, absent_code in positioned:
        index = _role_index(sections, role)
        if index < 0:
            violations.append(absent_code)
        elif index != expected_index:
            violations.append(misplaced_code)

    if not _has_svg(sections):
        violations.append("no_svg")

    return violations
