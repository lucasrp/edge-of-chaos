from __future__ import annotations

from pathlib import Path
from typing import Any

from .config import RuntimeConfig
from .util import now_iso, slugify, truncate


def primary_thread_from_review(review_data: dict[str, Any], request: str) -> dict[str, str]:
    raw = review_data.get("primary_thread") if isinstance(review_data, dict) else None
    if isinstance(raw, dict):
        title = str(raw.get("title") or raw.get("thread_id") or request or "General Continuity")
        thread_id = slugify(str(raw.get("thread_id") or title), "general-continuity")[:90]
        action = str(raw.get("action") or "continue")
        return {"action": action, "thread_id": thread_id, "title": title}
    if isinstance(raw, str) and raw.strip():
        title = raw.strip()
        return {"action": "continue", "thread_id": slugify(title, "general-continuity")[:90], "title": title}
    title = request or "General Continuity"
    return {"action": "create", "thread_id": slugify(title, "general-continuity")[:90], "title": title}


def initial_seed_thread(config: RuntimeConfig) -> dict[str, str]:
    seeds = [item for item in (config.agent.get("seed_threads") or []) if isinstance(item, dict)]
    if seeds:
        title = str(seeds[0].get("title") or "Ajudar o mentorado na melhor forma possivel com o trabalho atual dele")
    else:
        title = "Ajudar o mentorado na melhor forma possivel com o trabalho atual dele"
    return {"action": "create", "thread_id": slugify(title, "mentor-general-thread")[:90], "title": title}


def update_thread(config: RuntimeConfig, *, thread_id: str, title: str, report_path: Path, summary: str, decisions: list[str], next_steps: list[str]) -> Path:
    config.threads_dir.mkdir(parents=True, exist_ok=True)
    path = config.threads_dir / f"{thread_id}.md"
    if path.exists():
        existing = path.read_text(encoding="utf-8")
    else:
        existing = f"# {title}\n\n## Current Understanding\n\n\n## Decisions\n\n\n## Open Questions\n\n\n## Reports\n\n\n## Next Steps\n\n\n## Timeline\n\n"
    entry = [
        f"- {now_iso()}: {truncate(summary, 500)}",
    ]
    report_line = f"- [{report_path.name}](../../reports/{report_path.name})"
    text = existing.rstrip() + "\n\n"
    text += "## Latest Update\n\n"
    text += truncate(summary, 1200) + "\n\n"
    if decisions:
        text += "## Latest Decisions\n\n" + "\n".join(f"- {item}" for item in decisions) + "\n\n"
    if next_steps:
        text += "## Latest Next Steps\n\n" + "\n".join(f"- {item}" for item in next_steps) + "\n\n"
    text += "## Latest Report\n\n" + report_line + "\n\n"
    text += "## Timeline Entry\n\n" + "\n".join(entry) + "\n"
    path.write_text(text, encoding="utf-8")
    return path


def rebuild_digest(config: RuntimeConfig) -> Path:
    config.digests_dir.mkdir(parents=True, exist_ok=True)
    lines = ["# Mentor Briefing", "", "## Active Threads", ""]
    for path in sorted(config.threads_dir.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True)[:10]:
        text = path.read_text(encoding="utf-8", errors="ignore")
        lines.append(f"### {path.stem}")
        lines.append("")
        lines.append(truncate(text, 900))
        lines.append("")
    digest = config.digests_dir / "mentor-briefing.md"
    digest.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return digest
