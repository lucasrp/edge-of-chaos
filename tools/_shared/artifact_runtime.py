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
HEADING_RE = re.compile(r"^#{1,6}\s+")
LIST_RE = re.compile(r"^\s*(?:[-*+]\s+|\d+[.)]\s+)")
BANNER_RE = re.compile(r"^\*\*(?:map mode|scope|mode|status|frame|evidence|gap|next)\b", re.I)
BOLD_LABEL_RE = re.compile(r"^\*\*[^*]{1,80}:\*\*")
PROCESS_CHATTER_RE = re.compile(
    r"\b(?:Now I have what I need\.?|Writing (?:the )?(?:map|report)\.?|End of (?:map|report)\.?)",
    re.I,
)
TECH_TOKEN_RE = re.compile(
    r"\b(?:cycle-\d+|GAP-\d+|G\d+[a-z]?|P\d+|sha256:[a-f0-9]+|[a-f0-9]{7,40})\b|`[^`]+`",
    re.I,
)


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


def _norm_title(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip().strip("#").strip().lower()


def _without_leading_title(body: str, title: str) -> str:
    lines = body.replace("\r\n", "\n").replace("\r", "\n").strip().splitlines()
    if not lines:
        return ""
    first = lines[0].strip()
    if first.startswith("# ") and _norm_title(first[2:]) == _norm_title(title):
        lines = lines[1:]
        while lines and not lines[0].strip():
            lines = lines[1:]
    return "\n".join(lines).strip()


def _paragraph_blocks(markdown: str) -> list[str]:
    return [block.strip() for block in re.split(r"\n\s*\n", markdown.strip()) if block.strip()]


def _is_reader_paragraph(block: str) -> bool:
    lines = [line.strip() for line in block.splitlines() if line.strip()]
    if not lines:
        return False
    first = lines[0]
    if first == "---" or first.startswith("```") or first.startswith("|"):
        return False
    if HEADING_RE.match(first) or LIST_RE.match(first) or BANNER_RE.match(first) or BOLD_LABEL_RE.match(first):
        return False
    if len(lines) > 4:
        return False
    text = " ".join(lines)
    if len(text) > 760:
        return False
    if text.count("|") >= 4 or text.count("`") >= 8:
        return False
    return True


def _technical_density(text: str) -> float:
    words = re.findall(r"\w+", text)
    if not words:
        return 0.0
    return len(TECH_TOKEN_RE.findall(text)) / max(len(words), 1)


def _trim_sentence(text: str, *, limit: int = 420) -> str:
    value = PROCESS_CHATTER_RE.sub("", text or "")
    value = re.sub(r"\s+", " ", value).strip()
    if len(value) <= limit:
        return value
    clipped = value[:limit].rstrip()
    end = max(clipped.rfind("."), clipped.rfind("!"), clipped.rfind("?"))
    if end >= 120:
        return clipped[: end + 1]
    return clipped.rstrip(" ,;:") + "."


def _reader_title(title: str) -> str:
    value = re.sub(r"^(report|research|strategy|discovery|autonomy|map)\s*:\s*", "", title or "", flags=re.I)
    return _trim_sentence(value.strip() or "este artefato", limit=180)


def _build_entry_body(title: str, body: str) -> str:
    """Return the public feed invitation; keep the full artifact in the report."""
    content = _without_leading_title(body, title)
    blocks = _paragraph_blocks(content)
    reader_blocks = [block for block in blocks if _is_reader_paragraph(block)]
    dense = len(blocks) > 4 or any(not _is_reader_paragraph(block) for block in blocks)
    dense = dense or _technical_density(" ".join(reader_blocks[:2])) > 0.035

    if not dense and 1 <= len(reader_blocks) <= 4:
        return "\n\n".join(reader_blocks).strip() + "\n"

    selected = [_trim_sentence(block) for block in reader_blocks[:2]]
    if not selected:
        selected = [
            f"Este ciclo registrou {_reader_title(title)}.",
            "A entrada curta fica aqui como porta de entrada; o relatório preserva a evidência e os detalhes técnicos.",
        ]
    elif len(selected) == 1:
        selected.append("O relatório preserva a evidência completa, as decisões e os detalhes técnicos.")
    selected = selected[:3]
    selected.append("Abra o relatório para ver a evidência, os detalhes técnicos e os próximos passos.")
    return "\n\n".join(selected).strip() + "\n"


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
    entry_body = _build_entry_body(title, body)

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
        f"{entry_body}",
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
