from __future__ import annotations

from dataclasses import dataclass
import re


REPORT_SECTION_TITLES = [
    "Lineage",
    "Situated Delta",
    "Problem Framing and Open Gaps",
    "Simple Model",
    "Feynman Derivation",
    "Why This Matters Now",
    "Broad Search",
    "Adversarial Pushback",
    "Recommended Next Steps",
    "What I Don't Know",
    "Contextualization and Glossary",
]

_TITLE_RE = re.compile(r"^#\s+(.+?)\s*$")
_SECTION_RE = re.compile(r"^##\s+(.+?)\s*$")
_WS_RE = re.compile(r"\s+")
_LIST_ITEM_RE = re.compile(r"^(?:[-*]\s+|\d+\.\s+)")


@dataclass(frozen=True)
class ReportShapeCheck:
    passed: bool
    issues: list[str]
    title: str
    sections: list[tuple[str, str]]

    def section_map(self) -> dict[str, str]:
        return {title: body for title, body in self.sections}


def validate_report_markdown(report: str) -> ReportShapeCheck:
    title, sections = extract_report_sections(report)
    issues: list[str] = []
    if not title:
        issues.append("missing report title")
    if "deterministic scaffold fallback" in report.lower():
        issues.append("deterministic fallback marker is still present")

    section_titles = [_canonicalize(title) for title, _body in sections]
    cursor = -1
    for required in REPORT_SECTION_TITLES:
        canonical = _canonicalize(required)
        try:
            cursor = section_titles.index(canonical, cursor + 1)
        except ValueError:
            issues.append(f"missing section: {required}")

    section_map = {_canonicalize(item[0]): item[1].strip() for item in sections}
    for required in REPORT_SECTION_TITLES:
        body = section_map.get(_canonicalize(required), "")
        if not body:
            issues.append(f"empty section: {required}")
        elif len(_WS_RE.sub(" ", body).strip()) < 40:
            issues.append(f"thin section: {required}")
        else:
            issues.extend(validate_section_body(required, body))

    return ReportShapeCheck(
        passed=not issues,
        issues=issues,
        title=title,
        sections=sections,
    )


def extract_report_sections(report: str) -> tuple[str, list[tuple[str, str]]]:
    title = ""
    sections: list[tuple[str, str]] = []
    current_title = ""
    current_lines: list[str] = []

    for raw_line in (report or "").replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        title_match = _TITLE_RE.match(raw_line.strip())
        if title_match and not title and not current_title:
            title = title_match.group(1).strip()
            continue
        section_match = _SECTION_RE.match(raw_line.strip())
        if section_match:
            if current_title and _canonicalize(current_title) != "reviews":
                sections.append((current_title.strip(), "\n".join(current_lines).strip()))
            current_title = section_match.group(1).strip()
            current_lines = []
            if _canonicalize(current_title) == "reviews":
                break
            continue
        if current_title:
            current_lines.append(raw_line)

    if current_title and _canonicalize(current_title) != "reviews":
        sections.append((current_title.strip(), "\n".join(current_lines).strip()))
    return title, sections


def _canonicalize(value: str) -> str:
    return _WS_RE.sub(" ", (value or "").strip().lower())


def validate_section_body(title: str, body: str) -> list[str]:
    issues: list[str] = []
    normalized = (body or "").strip()
    if not normalized:
        return issues

    if normalized.count("```") % 2:
        issues.append(f"unclosed code fence: {title}")
    if normalized.count("**") % 2:
        issues.append(f"unbalanced bold marker: {title}")
    if normalized.count("`") % 2:
        issues.append(f"unbalanced inline code marker: {title}")

    tail_issue = _tail_issue(title, normalized)
    if tail_issue:
        issues.append(tail_issue)
    return issues


def _tail_issue(title: str, body: str) -> str | None:
    lines = [line.strip() for line in body.splitlines() if line.strip()]
    if not lines:
        return None
    last_line = lines[-1]
    tail = _WS_RE.sub(" ", body).strip()
    if tail.endswith((":", ";", ",", "(", "[", "{", "/", " -")):
        return f"suspicious ending punctuation: {title}"

    if re.search(r"\b(?:and|or|but|because|which|that|the|a|an|to|of|with|for|when|while|whether)$", tail.lower()):
        return f"suspicious sentence fragment: {title}"

    if _LIST_ITEM_RE.match(last_line):
        return None

    words = re.findall(r"[A-Za-z][A-Za-z'-]*", last_line)
    if last_line[-1].isalnum() and len(last_line) < 24 and 1 <= len(words) <= 4:
        return f"suspicious short tail: {title}"
    return None
