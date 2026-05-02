"""Runtime publication bridge for skill-produced markdown artifacts."""

from __future__ import annotations

import hashlib
import html
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .skill_policy import canonical_skill_id, skill_accepts_stdout_artifact
from .telemetry import emit_shadow_event


ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]")
SLUG_RE = re.compile(r"[^a-z0-9]+")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _strip_ansi(value: str) -> str:
    return ANSI_RE.sub("", value or "")


def _slugify(value: str, *, fallback: str) -> str:
    slug = SLUG_RE.sub("-", value.lower()).strip("-")
    return (slug or fallback)[:80].strip("-") or fallback


def _json_string(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def _extract_markdown_artifact(output: str) -> tuple[str, str] | None:
    cleaned = _strip_ansi(output).replace("\r\n", "\n").replace("\r", "\n").strip()
    if not cleaned:
        return None
    lines = cleaned.splitlines()
    start = None
    title = ""
    for idx, line in enumerate(lines):
        if line.startswith("# "):
            start = idx
            title = line[2:].strip()
            break
    if start is None:
        return None
    body = "\n".join(lines[start:]).strip() + "\n"
    if len(body) < 80:
        return None
    return title or "Untitled artifact", body


def _extract_plaintext_artifact(output: str) -> tuple[str, str] | None:
    cleaned = _strip_ansi(output).replace("\r\n", "\n").replace("\r", "\n").strip()
    if not cleaned:
        return None
    words = re.findall(r"\w+", cleaned)
    if len(cleaned) < 120 or len(words) < 20:
        return None

    first_line = ""
    for line in cleaned.splitlines():
        candidate = line.strip().strip("#").strip()
        if candidate:
            first_line = candidate
            break
    title = first_line[:96].strip(" :-\t") or "Runtime captured artifact"
    body = f"# {title}\n\n{cleaned}\n"
    return title, body


def _unique_path(path: Path) -> Path:
    if not path.exists():
        return path
    stem = path.stem
    suffix = path.suffix
    for idx in range(2, 1000):
        candidate = path.with_name(f"{stem}-{idx}{suffix}")
        if not candidate.exists():
            return candidate
    raise RuntimeError(f"could not choose unique artifact path for {path}")


def _render_report_html(*, title: str, body: str, skill: str, cycle_id: str) -> str:
    escaped_title = html.escape(title)
    escaped_skill = html.escape(skill)
    escaped_cycle = html.escape(cycle_id)
    escaped_body = html.escape(body)
    return (
        "<!doctype html>\n"
        "<html lang=\"en\">\n"
        "<head>\n"
        "  <meta charset=\"utf-8\">\n"
        f"  <title>{escaped_title}</title>\n"
        "  <style>body{font-family:system-ui,sans-serif;max-width:920px;margin:40px auto;"
        "line-height:1.55;padding:0 20px}pre{white-space:pre-wrap;font:inherit}</style>\n"
        "</head>\n"
        "<body>\n"
        f"  <p><strong>Skill:</strong> {escaped_skill} · <strong>Cycle:</strong> {escaped_cycle}</p>\n"
        f"  <pre>{escaped_body}</pre>\n"
        "</body>\n"
        "</html>\n"
    )


def publish_stdout_artifact(
    *,
    skill: object,
    cycle_id: str | None,
    output: str,
    entries_dir: Path,
    reports_dir: Path,
    instance: object = "",
) -> dict[str, Any]:
    canonical_skill = canonical_skill_id(skill, instance=instance)
    if not cycle_id:
        return {"published": False, "reason": "missing_cycle_id", "skill": canonical_skill}
    if not skill_accepts_stdout_artifact(canonical_skill):
        return {"published": False, "reason": "skill_not_artifact_pipeline", "skill": canonical_skill}

    extracted = _extract_markdown_artifact(output) or _extract_plaintext_artifact(output)
    if not extracted:
        return {"published": False, "reason": "missing_markdown_artifact", "skill": canonical_skill}
    title, body = extracted

    now = _now()
    date = now.date().isoformat()
    slug_title = _slugify(title, fallback=cycle_id)
    entry_path = _unique_path(entries_dir / f"{date}-{canonical_skill}-{slug_title}.md")
    report_name = f"{entry_path.stem}.html"
    report_path = reports_dir / report_name
    artifact = f"blog/entries/{entry_path.name}"
    artifact_hash = "sha256:" + hashlib.sha256(body.encode("utf-8")).hexdigest()

    entries_dir.mkdir(parents=True, exist_ok=True)
    reports_dir.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        _render_report_html(title=title, body=body, skill=canonical_skill, cycle_id=cycle_id),
        encoding="utf-8",
    )
    entry_path.write_text(
        "---\n"
        f"date: {date}\n"
        f"title: {_json_string(title)}\n"
        f"report: {report_name}\n"
        "tags:\n"
        f"  - {canonical_skill}\n"
        "  - runtime-published\n"
        "status: approved\n"
        f"source_skill: {canonical_skill}\n"
        f"cycle_id: {cycle_id}\n"
        f"hash: {artifact_hash}\n"
        "---\n\n"
        f"{body}",
        encoding="utf-8",
    )

    phase_payload = {
        "pipeline": "runtime-stdout-artifact",
        "phase": "pipeline",
        "ok": True,
        "source_skill": canonical_skill,
        "artifact": artifact,
        "report": report_name,
        "auto_published": True,
    }
    emit_shadow_event(
        "PhaseCompleted",
        actor="edge-runner",
        artifact=artifact,
        cycle_id=cycle_id,
        payload=phase_payload,
    )
    emit_shadow_event(
        "ArtifactPublished",
        actor="continuity",
        artifact=artifact,
        cycle_id=cycle_id,
        payload={
            "title": title,
            "source_skill": canonical_skill,
            "hash": artifact_hash,
            "report": report_name,
            "auto_published": True,
            "pipeline": "runtime-stdout-artifact",
        },
    )
    return {
        "published": True,
        "artifact": artifact,
        "entry_path": str(entry_path),
        "report_path": str(report_path),
        "skill": canonical_skill,
        "hash": artifact_hash,
    }
