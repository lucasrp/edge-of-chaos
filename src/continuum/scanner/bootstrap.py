"""Write sanitized heuristics data as bootstrap memory files.

Generates:
- user_profile.md       Human-readable summary
- preferences.json      Detected preferences
- corrections.json      Detected corrections
- tech_stack.json        Technology mentions
- topics.json            Recurring topics
- bootstrap_summary.md   Overview with confidence levels
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from continuum.scanner.heuristics import HeuristicsResult


def _write_json(path: Path, data: object) -> None:
    """Write data as formatted JSON."""
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _format_preferences(result: HeuristicsResult) -> list[dict]:
    """Convert preferences to serializable dicts."""
    return [
        {
            "category": p.category,
            "value": p.value,
            "occurrences": p.occurrences,
            "confidence": p.confidence,
        }
        for p in result.preferences
    ]


def _format_corrections(result: HeuristicsResult) -> list[dict]:
    """Convert corrections to serializable dicts."""
    return [
        {
            "user_text": c.user_text,
            "preceding_assistant_text": c.preceding_assistant_text,
            "pattern_matched": c.pattern_matched,
        }
        for c in result.corrections
    ]


def _generate_user_profile(result: HeuristicsResult) -> str:
    """Generate a human-readable user profile summary."""
    lines = [
        "# User Profile (Bootstrap)",
        "",
        f"*Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}*",
        "",
    ]

    # Language preferences
    lang_prefs = [p for p in result.preferences if p.category == "language"]
    if lang_prefs:
        lines.append("## Language")
        for p in lang_prefs:
            lines.append(f"- **{p.value}** (confidence: {p.confidence}, seen {p.occurrences}x)")
        lines.append("")

    # Style preferences
    style_prefs = [p for p in result.preferences if p.category == "style"]
    if style_prefs:
        lines.append("## Communication Style")
        for p in style_prefs:
            lines.append(f"- **{p.value}** (confidence: {p.confidence}, seen {p.occurrences}x)")
        lines.append("")

    # Tech stack (top 15)
    if result.tech_stack:
        lines.append("## Technology Stack")
        top_tech = list(result.tech_stack.items())[:15]
        for tech, count in top_tech:
            lines.append(f"- {tech} ({count} mentions)")
        lines.append("")

    # Corrections summary
    if result.corrections:
        lines.append("## Corrections Pattern")
        lines.append(f"- {len(result.corrections)} correction(s) detected")
        lines.append("- See corrections.json for details")
        lines.append("")

    # Topics (top 10)
    if result.topics:
        lines.append("## Common Topics")
        top_topics = list(result.topics.items())[:10]
        for topic, count in top_topics:
            lines.append(f"- {topic} ({count})")
        lines.append("")

    return "\n".join(lines) + "\n"


def _generate_bootstrap_summary(result: HeuristicsResult, mode: str) -> str:
    """Generate a summary of what was extracted and confidence levels."""
    lines = [
        "# Bootstrap Summary",
        "",
        f"*Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}*",
        f"*Sanitization mode: {mode}*",
        "",
        "## Extraction Results",
        "",
        f"| Category | Count | Confidence |",
        f"|----------|-------|------------|",
    ]

    # Preferences
    if result.preferences:
        avg_conf = sum(p.confidence for p in result.preferences) / len(result.preferences)
        lines.append(f"| Preferences | {len(result.preferences)} | {avg_conf:.2f} avg |")
    else:
        lines.append("| Preferences | 0 | — |")

    # Corrections
    lines.append(f"| Corrections | {len(result.corrections)} | — |")

    # Tech stack
    if result.tech_stack:
        top_count = max(result.tech_stack.values())
        lines.append(f"| Tech stack | {len(result.tech_stack)} items | top: {top_count} mentions |")
    else:
        lines.append("| Tech stack | 0 | — |")

    # Structure patterns
    if result.structure_patterns:
        lines.append(f"| Structure patterns | {len(result.structure_patterns)} | — |")
    else:
        lines.append("| Structure patterns | 0 | — |")

    # Topics
    if result.topics:
        lines.append(f"| Topics | {len(result.topics)} | — |")
    else:
        lines.append("| Topics | 0 | — |")

    lines.extend([
        "",
        "## Files Written",
        "",
        "- `user_profile.md` — Human-readable summary of detected profile",
        "- `preferences.json` — Language and style preferences with confidence",
        "- `corrections.json` — User corrections after assistant output",
        "- `tech_stack.json` — Technology mentions with counts",
        "- `topics.json` — Recurring topics by frequency",
        "- `bootstrap_summary.md` — This file",
        "",
        "## Notes",
        "",
        "- Confidence scores are based on frequency relative to total messages",
        "- Higher confidence = more consistent signal across sessions",
        "- Review user_profile.md for a quick overview",
        "",
    ])

    return "\n".join(lines) + "\n"


def write_bootstrap(
    result: HeuristicsResult,
    root: Path | None = None,
    mode: str = "balanced",
    dry_run: bool = False,
) -> dict[str, str]:
    """Write bootstrap memory files from heuristics results.

    Args:
        result: Sanitized HeuristicsResult.
        root: Project root (default: cwd).
        mode: Sanitization mode used (for summary).
        dry_run: If True, generate content but don't write files.

    Returns:
        Dict mapping filename -> content (useful for dry-run display).
    """
    if root is None:
        root = Path.cwd()

    bootstrap_dir = root / ".continuum" / "memory" / "bootstrap"

    files: dict[str, str] = {}

    # Generate all content
    files["user_profile.md"] = _generate_user_profile(result)
    files["preferences.json"] = json.dumps(_format_preferences(result), indent=2, ensure_ascii=False) + "\n"
    files["corrections.json"] = json.dumps(_format_corrections(result), indent=2, ensure_ascii=False) + "\n"
    files["tech_stack.json"] = json.dumps(result.tech_stack, indent=2, ensure_ascii=False) + "\n"
    files["topics.json"] = json.dumps(result.topics, indent=2, ensure_ascii=False) + "\n"
    files["bootstrap_summary.md"] = _generate_bootstrap_summary(result, mode)

    if not dry_run:
        bootstrap_dir.mkdir(parents=True, exist_ok=True)
        for filename, content in files.items():
            (bootstrap_dir / filename).write_text(content, encoding="utf-8")

    return files
