from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .config import RuntimeConfig
from .context import ContextPacket
from .llm_client import LLMClient
from .report_shape import report_section_titles, required_report_shape_text
from .reviewers import ReviewResult, summarize_reviews
from .search import SearchResult
from .util import truncate


@dataclass(frozen=True)
class ReportResult:
    text: str
    mode: str
    provider: str
    error: str = ""


def draft_report(packet: ContextPacket, searches: list[SearchResult], primary_thread: dict[str, str]) -> ReportResult:
    client = LLMClient(role="report")
    llm_report = _llm_draft_report(client, packet, searches, primary_thread)
    if llm_report:
        text = _ensure_workspace_evidence_used(packet, _normalize_report_text(packet, llm_report), searches)
        return ReportResult(text=text, mode="llm", provider=client.last_provider, error=client.last_error)
    return ReportResult(
        text=_ensure_workspace_evidence_used(packet, _normalize_report_text(packet, _deterministic_fallback_report(packet, searches, primary_thread)), searches),
        mode="deterministic-scaffold",
        provider=client.last_provider,
        error=client.last_error or "llm:no-report-text",
    )


def revise_report(packet: ContextPacket, searches: list[SearchResult], primary_thread: dict[str, str], draft: str, reviews: list[ReviewResult], *, stage: str) -> ReportResult:
    client = LLMClient(role="report")
    prompt = {
        "kind": packet.kind,
        "request": packet.request,
        "selected_thread": _selected_thread_payload(packet, primary_thread),
        "stage": stage,
        "required_workspace_evidence": _workspace_evidence_payload(searches, limit=10),
        "draft": draft[:14000],
        "review_feedback": [
            {
                "reviewer": review.reviewer,
                "status": review.status,
                "summary": review.summary,
                "data": review.data,
            }
            for review in reviews
        ],
        "observations": [obs.__dict__ for obs in packet.observations[:12]],
        "thread_candidates": packet.thread_candidates[:6],
        "report_candidates": packet.report_candidates[:6],
        "search_results": _search_payload(searches, limit=14),
        "authoritative_reads": packet.authoritative_reads[:10],
        "first_steps": packet.first_steps,
        "interests": packet.interests,
        "operator_pressure": packet.operator_pressure,
        "operator_messages": packet.operator_messages[:8],
    }
    text = client.complete_text(
        system=_report_system_prompt(packet.kind, revision=True),
        prompt=json.dumps(prompt, ensure_ascii=False)[:26000],
    )
    if not text:
        return ReportResult(
            text=draft,
            mode="unchanged",
            provider=client.last_provider,
            error=client.last_error or "llm:no-revised-text",
        )
    final_text = _ensure_workspace_evidence_used(packet, _normalize_report_text(packet, text), searches)
    return ReportResult(text=final_text, mode="llm", provider=client.last_provider, error=client.last_error)


def append_report_utility(config: RuntimeConfig, *, report_path: Path, utility: ReviewResult) -> Path:
    path = config.state_dir / "report-utility.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    row = {
        "report": str(report_path),
        "reviewer": utility.reviewer,
        "summary": utility.summary,
        "data": utility.data,
    }
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    return path


def _llm_draft_report(client: LLMClient, packet: ContextPacket, searches: list[SearchResult], primary_thread: dict[str, str]) -> str | None:
    prompt = {
        "kind": packet.kind,
        "request": packet.request,
        "selected_thread": _selected_thread_payload(packet, primary_thread),
        "required_workspace_evidence": _workspace_evidence_payload(searches, limit=10),
        "observations": [obs.__dict__ for obs in packet.observations[:12]],
        "thread_candidates": packet.thread_candidates[:6],
        "report_candidates": packet.report_candidates[:6],
        "first_steps": packet.first_steps,
        "seed_threads": packet.seed_threads,
        "interests": packet.interests,
        "routines": packet.routines,
        "authoritative_reads": packet.authoritative_reads[:10],
        "search_results": _search_payload(searches, limit=14),
        "operator_pressure": packet.operator_pressure,
        "operator_messages": packet.operator_messages[:8],
    }
    text = client.complete_text(
        system=_report_system_prompt(packet.kind, revision=False),
        prompt=json.dumps(prompt, ensure_ascii=False)[:22000],
    )
    return text or None


def _report_system_prompt(kind: str, *, revision: bool) -> str:
    shape = required_report_shape_text(kind)
    narrative = _kind_narrative_contract(kind)
    revision_line = "Revise the draft using the review feedback as input. " if revision else "Write the first full draft. "
    return (
        "You are edge-of-chaos v2 writing a private mentor artifact. "
        "The rite already exists in code. Do not spend report space narrating preflight, broad-search ritual, review choreography, publication steps, or state management unless that process itself is the subject of the artifact. "
        f"{revision_line}"
        f"{narrative} "
        "Use operator pressure, async chat, continuity, and search as background constraints. Mention them only when they materially change the topic, the judgement, or the confidence level. "
        "Use concrete evidence from fetched documents, workspace reads, prior reports, and authoritative thread reads. "
        "When required_workspace_evidence is present, treat it as the evidence floor: quote or paraphrase concrete fields and lines from those files in the subject sections, and do not merely say those files should be inspected. "
        "If those excerpts show dry-run commands, missing outputs, dirty repos, return codes, budgets, variants, or timestamps, make those facts part of the substantive judgement. "
        "When the evidence supports only one visible candidate rather than a real comparison among alternatives, call it the strongest candidate in the current evidence, not the proven best pattern. "
        "Treat unavailable or failed sources as limits on confidence, not as the main storyline. "
        "Do not claim no evidence when fetched entries, reading notes, or concrete local excerpts are present. "
        "If selected_thread.grounded is true, keep continuity consistent with that thread and excerpt, but do it inside the subject matter rather than creating meta chatter about the rite. "
        "Start with the exact Markdown title `# Private Mentor Report`. "
        "Use this exact section order and titles:\n"
        f"{shape}\n"
        "Return only the report."
    )


def _kind_narrative_contract(kind: str) -> str:
    normalized = (kind or "").strip().lower()
    if normalized == "research":
        return (
            "Produce a research artifact with the same substantive arc as the main branch: state the target, say what was already known, derive a first explanation, resolve the key gaps, teach the subject plainly, and end with practical recommendations, applications, risks, and next steps."
        )
    if normalized == "discovery":
        return (
            "Produce a discovery artifact with the same substantive arc as the main branch: frame the live friction, present one strong discovery, explain its original context, connect it to current work, show a before/after change, and end with practical getting-started advice plus risks."
        )
    return (
        "Produce a report artifact with the same substantive arc as the main branch: establish context, define the central question, present evidence, analyze it, compare alternatives when relevant, and land on a recommendation with visible risks and next steps."
    )


def _deterministic_fallback_report(packet: ContextPacket, searches: list[SearchResult], primary_thread: dict[str, str]) -> str:
    section_bodies = _fallback_sections(packet, searches, primary_thread)
    parts = ["# Private Mentor Report"]
    for title in report_section_titles(packet.kind):
        parts.append(f"\n## {title}\n")
        parts.append(section_bodies.get(title, "Evidence was thin in this beat, so this section stays explicit about the missing support instead of inventing confidence."))
    return "\n".join(parts).strip() + "\n"


def _fallback_sections(packet: ContextPacket, searches: list[SearchResult], primary_thread: dict[str, str]) -> dict[str, str]:
    normalized = (packet.kind or "").strip().lower()
    if normalized == "research":
        return _fallback_research_sections(packet, searches, primary_thread)
    if normalized == "discovery":
        return _fallback_discovery_sections(packet, searches, primary_thread)
    return _fallback_report_sections(packet, searches, primary_thread)


def _fallback_report_sections(packet: ContextPacket, searches: list[SearchResult], primary_thread: dict[str, str]) -> dict[str, str]:
    return {
        "Context": _join_paragraphs(
            _context_line(packet, primary_thread),
            _observations_paragraph(packet),
            _operator_constraint(packet),
        ),
        "Central Question": _join_paragraphs(
            f"The central question in this beat is: {_request_sentence(packet)}",
            _decision_pressure(packet, fallback="The report should reduce uncertainty enough to support the next concrete engineering move."),
        ),
        "Evidence": _join_paragraphs(
            "The evidence base should stay anchored in concrete artifacts rather than in a narration of the rite.",
            _markdown_list(_evidence_lines(packet, searches)),
        ),
        "Analysis": _join_paragraphs(
            _analysis_sentence(packet, searches),
            _confidence_line(searches),
        ),
        "Alternatives Or Comparisons": _join_paragraphs(
            "The main comparison is between acting on the live evidence now and defaulting back to a generic explanation that ignores the freshest project signals.",
            _markdown_list(_comparison_lines(packet, searches)),
        ),
        "Recommendation Or Synthesis": _join_paragraphs(
            "The best synthesis is to preserve the concrete subject matter that the latest workspace evidence makes visible, then tighten only the parts that remain weak under direct inspection.",
            _markdown_list(_recommendation_lines(packet, searches)),
        ),
        "Risks And Unknowns": _markdown_list(_risk_lines(packet, searches)),
        "Next Steps": _markdown_list(_next_step_lines(packet, searches)),
    }


def _fallback_research_sections(packet: ContextPacket, searches: list[SearchResult], primary_thread: dict[str, str]) -> dict[str, str]:
    return {
        "Research Target": _join_paragraphs(
            _context_line(packet, primary_thread),
            f"The research target for this beat is: {_request_sentence(packet)}",
        ),
        "Existing Knowledge": _join_paragraphs(
            "Before drawing conclusions, the research should separate what the local project history already knew from what the freshest evidence adds.",
            _markdown_list(_existing_knowledge_lines(packet)),
        ),
        "Initial Derivation": _join_paragraphs(
            _analysis_sentence(packet, searches),
            "This first derivation should remain simple enough to expose where the explanation still depends on missing reads or unresolved comparisons.",
        ),
        "Gaps and Resolutions": _markdown_list(_gap_resolution_lines(packet, searches)),
        "Explanation": _join_paragraphs(
            "The explanation should teach the subject itself, using the live evidence as support instead of turning the artifact into a diary of the process.",
            _markdown_list(_evidence_lines(packet, searches)),
        ),
        "Recommendations": _markdown_list(_recommendation_lines(packet, searches)),
        "Applications to Work": _join_paragraphs(
            "The project value comes from translating the research back into the current workspace rather than leaving it as detached background knowledge.",
            _markdown_list(_application_lines(packet)),
        ),
        "Risks and Open Questions": _markdown_list(_risk_lines(packet, searches)),
        "Next Steps": _markdown_list(_next_step_lines(packet, searches)),
    }


def _fallback_discovery_sections(packet: ContextPacket, searches: list[SearchResult], primary_thread: dict[str, str]) -> dict[str, str]:
    return {
        "The Problem Or Friction": _join_paragraphs(
            _context_line(packet, primary_thread),
            _decision_pressure(packet, fallback="The discovery should answer a real friction that showed up in the current project context."),
        ),
        "The Discovery": _join_paragraphs(
            "A useful discovery is one that changes what the operator can try next, not just something novel for its own sake.",
            _markdown_list(_evidence_lines(packet, searches)),
        ),
        "Original Context": _join_paragraphs(
            "The artifact should explain where the discovery comes from and what problem it solved in its native setting before mapping it onto the current work.",
            _markdown_list(_existing_knowledge_lines(packet)),
        ),
        "Application To Work": _join_paragraphs(
            "The main test is whether the discovery makes the current line of work more legible or more executable.",
            _markdown_list(_application_lines(packet)),
        ),
        "Before And After": _markdown_list(_comparison_lines(packet, searches)),
        "Getting Started": _markdown_list(_next_step_lines(packet, searches)),
        "Risks And Limits": _markdown_list(_risk_lines(packet, searches)),
    }


def _normalize_report_text(packet: ContextPacket, text: str) -> str:
    text = _strip_fallback_status(text.strip())
    first_line = next((line.strip() for line in text.splitlines() if line.strip()), "")
    if not first_line.startswith("# "):
        text = f"# Private Mentor Report\n\n{text}"
    return text


def _ensure_workspace_evidence_used(packet: ContextPacket, text: str, searches: list[SearchResult]) -> str:
    if "### Observed Artifact Evidence" in text:
        return text
    lines = _workspace_evidence_lines(searches)
    if not lines:
        return text
    block = "### Observed Artifact Evidence\n\n" + _markdown_list(lines)
    target_section = {
        "discovery": "Application To Work",
        "research": "Existing Knowledge",
        "report": "Evidence",
    }.get((packet.kind or "").strip().lower(), "Evidence")
    return _insert_section_block(text, target_section, block)


def _insert_section_block(text: str, section_title: str, block: str) -> str:
    lines = text.splitlines()
    heading = f"## {section_title}"
    for index, line in enumerate(lines):
        if line.strip() != heading:
            continue
        insert_at = index + 1
        while insert_at < len(lines) and lines[insert_at].strip() == "":
            insert_at += 1
        while insert_at < len(lines) and not lines[insert_at].startswith("## "):
            insert_at += 1
        before = lines[:insert_at]
        after = lines[insert_at:]
        return "\n".join(before + ["", block, ""] + after).strip() + "\n"
    return text.rstrip() + "\n\n" + block + "\n"


def _workspace_evidence_lines(searches: list[SearchResult]) -> list[str]:
    lines: list[str] = []
    for result in _workspace_evidence_results(searches):
        filename = Path(result.url).name
        content = _workspace_result_content(result)
        if not content:
            continue
        if filename == "run_manifest.json":
            line = _manifest_evidence_line(result.url, content)
        else:
            line = _log_evidence_line(filename, content)
        if line:
            lines.append(line)
        if len(lines) >= 6:
            break
    if lines:
        lines.append("Evidence boundary: these artifacts support orchestration, provenance, and dry-run status; they do not by themselves prove substantive output quality or eliminate every alternative pre-MCP pattern.")
    return lines


def _workspace_evidence_results(searches: list[SearchResult]) -> list[SearchResult]:
    def priority(result: SearchResult) -> tuple[int, int, str]:
        filename = Path(result.url).name.lower()
        if filename == "run_manifest.json":
            rank = 0
        elif filename == "aggregate.log":
            rank = 1
        elif filename.startswith("run_v8_b50000"):
            rank = 2
        elif filename.startswith("run_raw_b50000"):
            rank = 3
        elif filename.startswith("run_v8_"):
            rank = 4
        elif filename.startswith("run_raw_"):
            rank = 5
        else:
            rank = 9
        return (rank, -int(result.round_index or 0), result.url)

    candidates = sorted(
        [
            result
            for result in searches
            if result.source == "workspace-read"
            and result.fetch_status == "fetched"
            and result.status == "retrieved"
            and result.url
            and Path(result.url).name
        ],
        key=priority,
    )
    deduped: list[SearchResult] = []
    seen: set[str] = set()
    for result in candidates:
        if result.url in seen:
            continue
        seen.add(result.url)
        deduped.append(result)
    return deduped


def _workspace_result_content(result: SearchResult) -> str:
    path = Path(result.url)
    if path.exists() and path.is_file() and path.suffix.lower() in {".json", ".log", ".md", ".txt", ".yaml", ".yml"}:
        try:
            return path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            pass
    return result.fetched_excerpt or result.summary


def _manifest_evidence_line(path: str, content: str) -> str:
    try:
        payload = json.loads(content)
    except json.JSONDecodeError:
        excerpt = _first_nonempty_line(content)
        return f"`{Path(path).name}`: {truncate(_safe_scaffold_text(excerpt), 260)}" if excerpt else ""
    if not isinstance(payload, dict):
        return ""
    name = payload.get("name") or Path(path).parent.name
    description = str(payload.get("description") or "").strip()
    started_at = str(payload.get("started_at") or "").strip()
    matrix = payload.get("config", {}).get("matrix", {}) if isinstance(payload.get("config"), dict) else {}
    conditions = matrix.get("conditions") if isinstance(matrix, dict) else None
    budgets = matrix.get("budgets") if isinstance(matrix, dict) else None
    steps = payload.get("steps") if isinstance(payload.get("steps"), list) else []
    dry_runs = [step for step in steps if isinstance(step, dict) and step.get("dry_run") is True]
    returncodes = sorted({str(step.get("returncode")) for step in steps if isinstance(step, dict) and "returncode" in step})
    parts = [f"`run_manifest.json` names `{_safe_scaffold_text(str(name))}`"]
    if description:
        parts.append(truncate(_safe_scaffold_text(description), 160))
    if started_at:
        parts.append(f"started_at `{_safe_scaffold_text(started_at)}`")
    if conditions or budgets:
        parts.append(f"conditions `{conditions}` and budgets `{budgets}`")
    if dry_runs:
        parts.append(f"{len(dry_runs)}/{len(steps)} steps marked `dry_run: true`")
    if returncodes:
        parts.append(f"returncodes `{', '.join(returncodes)}`")
    return "; ".join(parts) + "."


def _log_evidence_line(filename: str, content: str) -> str:
    candidates = [
        line.strip()
        for line in content.splitlines()
        if line.strip() and any(token in line.lower() for token in ["dry run", "error", "returncode", "exit", "summary", "delta", "score", "budget", "condition"])
    ]
    line = candidates[0] if candidates else _first_nonempty_line(content)
    if not line:
        return ""
    return f"`{filename}` shows `{truncate(_safe_scaffold_text(line), 260)}`."


def _first_nonempty_line(content: str) -> str:
    return next((line.strip() for line in content.splitlines() if line.strip()), "")


def _strip_fallback_status(text: str) -> str:
    lines = []
    for line in text.splitlines():
        lower = line.lower()
        if lower.startswith("> status:") and ("fallback" in lower or "smoke-test" in lower):
            continue
        lines.append(line)
    return "\n".join(lines).strip()


def _safe_scaffold_text(text: str) -> str:
    value = str(text or "")
    value = value.replace("```", "'''")
    value = value.replace("`", "'")
    value = value.replace("**", "")
    value = value.replace("__", "")
    value = value.replace("\r\n", "\n").replace("\r", "\n")
    cleaned_lines = []
    for raw_line in value.splitlines():
        line = raw_line.replace("\t", " ").rstrip()
        if line.lstrip().startswith("#"):
            line = line.lstrip("#").strip()
        cleaned_lines.append(line)
    return "\n".join(cleaned_lines).strip()


def _selected_thread_payload(packet: ContextPacket, primary_thread: dict[str, str]) -> dict[str, object]:
    thread_id = str(primary_thread.get("thread_id") or "")
    thread_title = str(primary_thread.get("title") or thread_id)
    read = next((item for item in packet.authoritative_reads if str(item.get("path") or "").endswith(f"/state/threads/{thread_id}.md")), None)
    return {
        "action": str(primary_thread.get("action") or "create"),
        "thread_id": thread_id,
        "title": thread_title,
        "thread_candidate_count": len(packet.thread_candidates),
        "grounded": read is not None,
        "authoritative_excerpt": truncate(str((read or {}).get("excerpt") or ""), 500),
    }


def _search_payload(searches: list[SearchResult], *, limit: int) -> list[dict[str, Any]]:
    def priority(result: SearchResult) -> tuple[int, int, str]:
        if result.source == "workspace-read" and result.fetch_status == "fetched":
            rank = 0
        elif result.source == "search-digest":
            rank = 1
        elif result.fetch_status == "fetched" and result.reading_note:
            rank = 2
        elif result.fetch_status == "fetched":
            rank = 3
        elif result.source == "workspace-search" and result.status == "retrieved":
            rank = 4
        elif result.source == "local-state":
            rank = 5
        elif result.status in {"retrieved", "context"}:
            rank = 6
        else:
            rank = 9
        return (rank, -int(result.round_index or 0), result.source)

    payload: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str, int]] = set()
    local_state_count = 0
    telemetry_count = 0
    ordered = sorted(searches, key=priority)
    for result in ordered:
        key = (
            result.source,
            result.title,
            truncate(result.query or "", 120),
            int(result.round_index or 0),
        )
        if key in seen:
            continue
        seen.add(key)
        if result.source == "local-state":
            local_state_count += 1
            if local_state_count > 4:
                continue
        if result.status in {"failed", "no_results", "unavailable"}:
            telemetry_count += 1
            if telemetry_count > 4:
                continue
        payload.append(
            {
                "source": result.source,
                "title": result.title,
                "url": result.url,
                "query": result.query,
                "status": result.status,
                "round_index": result.round_index,
                "fetch_status": result.fetch_status,
                "summary": truncate(result.summary, 320),
                "fetched_excerpt": truncate(result.fetched_excerpt, 420),
                "reading_note": result.reading_note,
            }
        )
        if len(payload) >= limit:
            break
    return payload


def _workspace_evidence_payload(searches: list[SearchResult], *, limit: int) -> list[dict[str, Any]]:
    def priority(result: SearchResult) -> tuple[int, int, str]:
        path = result.url.lower()
        filename = Path(path).name
        if filename == "run_manifest.json":
            rank = 0
        elif filename == "aggregate.log":
            rank = 1
        elif filename.startswith("run_v8_"):
            rank = 2
        elif filename.startswith("run_raw_"):
            rank = 3
        elif result.url:
            rank = 4
        else:
            rank = 9
        return (rank, -int(result.round_index or 0), result.url)

    payload: list[dict[str, Any]] = []
    seen: set[str] = set()
    candidates = [
        result
        for result in searches
        if result.source == "workspace-read"
        and result.fetch_status == "fetched"
        and result.status == "retrieved"
        and result.fetched_excerpt
    ]
    for result in sorted(candidates, key=priority):
        if result.url in seen:
            continue
        seen.add(result.url)
        payload.append(
            {
                "title": result.title,
                "path": result.url,
                "round_index": result.round_index,
                "excerpt": truncate(result.fetched_excerpt, 1400),
                "reading_note": result.reading_note,
            }
        )
        if len(payload) >= limit:
            break
    return payload


def _context_line(packet: ContextPacket, primary_thread: dict[str, str]) -> str:
    thread_title = str(primary_thread.get("title") or primary_thread.get("thread_id") or "current work")
    request = _request_sentence(packet)
    return f"This artifact stays grounded in the thread '{_safe_scaffold_text(thread_title)}' while addressing the current focus: {request}"


def _request_sentence(packet: ContextPacket) -> str:
    request = _safe_scaffold_text(packet.request.strip() or f"{packet.kind} beat")
    return request if request.endswith((".", "?", "!")) else f"{request}."


def _observations_paragraph(packet: ContextPacket) -> str:
    lines = _observation_lines(packet)
    if not lines:
        return "Live workspace evidence was thin, so the artifact should remain conservative about claims that depend on direct local inspection."
    return "Recent workspace evidence highlights these live signals:\n" + _markdown_list(lines)


def _operator_constraint(packet: ContextPacket) -> str:
    pressure = _safe_scaffold_text(truncate(packet.operator_pressure, 320))
    if not pressure:
        return ""
    return f"Current operator pressure matters only insofar as it changes the subject-level priority: {pressure}"


def _decision_pressure(packet: ContextPacket, *, fallback: str) -> str:
    if packet.operator_messages:
        latest = packet.operator_messages[0]
        text = _safe_scaffold_text(truncate(str(latest.get("text") or ""), 260))
        if text:
            return f"The latest operator message sharpens the decision pressure: {text}"
    return fallback


def _analysis_sentence(packet: ContextPacket, searches: list[SearchResult]) -> str:
    evidence_count = len([item for item in searches if item.fetch_status == "fetched"])
    if evidence_count >= 3:
        return "The strongest reading of the current evidence is that the report should privilege the freshest inspected artifacts over generic prior framing."
    if evidence_count >= 1:
        return "The current evidence base is usable but still narrow, so the explanation should stay concrete without pretending the coverage is complete."
    if packet.observations:
        return "The workspace observations are enough to frame the issue, but the argument still needs more direct evidence than a purely generic summary would provide."
    return "The explanation should remain narrow and honest because the current beat exposed more uncertainty than verified detail."


def _confidence_line(searches: list[SearchResult]) -> str:
    unavailable = [item for item in searches if item.status in {"failed", "no_results", "unavailable"}]
    if unavailable:
        return f"Confidence is limited by {len(unavailable)} search surfaces or attempts that did not produce usable evidence."
    return "Confidence is highest where the report can point to fetched documents, direct workspace reads, or repeated signals across the evidence bundle."


def _observation_lines(packet: ContextPacket) -> list[str]:
    lines: list[str] = []
    for obs in packet.observations[:6]:
        detail = _safe_scaffold_text(truncate(obs.detail, 180))
        lines.append(f"{obs.title}: {detail}")
    return lines


def _existing_knowledge_lines(packet: ContextPacket) -> list[str]:
    lines: list[str] = []
    for item in packet.report_candidates[:4]:
        title = _safe_scaffold_text(str(item.get("title") or "previous report"))
        summary = _safe_scaffold_text(truncate(str(item.get("summary") or ""), 180))
        lines.append(f"{title}: {summary}")
    for item in packet.authoritative_reads[:3]:
        excerpt = _safe_scaffold_text(truncate(str(item.get("excerpt") or ""), 180))
        title = _safe_scaffold_text(str(item.get("title") or item.get("path") or "authoritative read"))
        lines.append(f"{title}: {excerpt}")
    if not lines:
        lines.append("No strong prior local artifact was recovered, so the explanation has to rely more heavily on the current beat's direct evidence.")
    return lines[:6]


def _evidence_lines(packet: ContextPacket, searches: list[SearchResult]) -> list[str]:
    lines: list[str] = []
    for result in searches:
        if result.fetch_status == "fetched":
            note = result.reading_note if isinstance(result.reading_note, dict) else {}
            summary = note.get("summary") if isinstance(note, dict) else ""
            excerpt = summary or result.fetched_excerpt or result.summary
            if excerpt:
                lines.append(f"{result.source}: {truncate(_safe_scaffold_text(str(excerpt)), 220)}")
        elif result.status in {"retrieved", "context"} and result.summary:
            lines.append(f"{result.source}: {truncate(_safe_scaffold_text(result.summary), 220)}")
        if len(lines) >= 6:
            break
    if not lines:
        lines.extend(_observation_lines(packet)[:4])
    if not lines:
        lines.append("No concrete evidence bundle was recovered beyond the request itself, so the report should stay explicit about that limit.")
    return lines


def _comparison_lines(packet: ContextPacket, searches: list[SearchResult]) -> list[str]:
    lines = [
        "Use the freshest inspected artifact as the default anchor instead of retelling the workflow that produced it.",
        "Prefer subject-level evidence over generic background advice when the two pull in different directions.",
    ]
    if any(item.fetch_status == "fetched" for item in searches):
        lines.append("Use fetched documents and direct reads to break ties between plausible interpretations instead of relying on prior assumptions.")
    if packet.report_candidates:
        lines.append("Compare the new evidence against the last durable report to isolate what truly changed rather than merely what was repeated.")
    return lines[:4]


def _recommendation_lines(packet: ContextPacket, searches: list[SearchResult]) -> list[str]:
    lines = [
        "Keep the artifact centered on the subject matter that the live evidence actually supports.",
        "Trim any paragraph that explains the rite unless the process itself is the thing under investigation.",
    ]
    if any(item.fetch_status == "fetched" for item in searches):
        lines.append("Quote the strongest inspected artifact in the relevant section instead of summarizing it only at a distance.")
    if packet.thread_candidates:
        lines.append("Continue the thread that is hottest in current evidence rather than defaulting to a stale generic continuity line.")
    return lines[:4]


def _application_lines(packet: ContextPacket) -> list[str]:
    lines: list[str] = []
    if packet.first_steps:
        lines.extend(str(step) for step in packet.first_steps[:3] if str(step).strip())
    if packet.interests:
        for item in packet.interests[:2]:
            area = _safe_scaffold_text(str(item.get("area") or "interest"))
            connection = _safe_scaffold_text(str(item.get("connection") or ""))
            lines.append(f"{area}: {connection}")
    if not lines:
        lines.append("Tie the insight back to the current workspace, recent artifacts, and the next engineering action instead of leaving it as detached theory.")
    return lines[:4]


def _gap_resolution_lines(packet: ContextPacket, searches: list[SearchResult]) -> list[str]:
    lines = [
        "Gap: identify which claim depends on a direct local read rather than on general memory or template knowledge.",
        "Resolution: use fetched documents, workspace excerpts, or authoritative thread reads to answer that claim when possible.",
    ]
    if any(item.fetch_status == "fetched" for item in searches):
        lines.append("Gap: decide whether the new evidence changes the initial model materially or only adds color.")
        lines.append("Resolution: promote only the evidence that changes judgement into the final explanation.")
    if packet.operator_messages:
        lines.append("Gap: confirm whether the latest operator instruction changes scope, confidence, or urgency.")
    return lines[:5]


def _risk_lines(packet: ContextPacket, searches: list[SearchResult]) -> list[str]:
    lines: list[str] = []
    unavailable = [item for item in searches if item.status in {"failed", "no_results", "unavailable"}]
    if unavailable:
        lines.append("Source coverage is incomplete, so some conclusions may be narrower than the topic itself.")
    if not any(item.fetch_status == "fetched" for item in searches):
        lines.append("The report risks sounding more certain than the evidence bundle warrants if it does not mark thin coverage plainly.")
    if not packet.observations:
        lines.append("Live workspace context is thin, so continuity may overweight older artifacts.")
    lines.append("A generic explanation would erase the actual project delta and make the artifact less useful than the main-branch standard.")
    return lines[:4]


def _next_step_lines(packet: ContextPacket, searches: list[SearchResult]) -> list[str]:
    lines: list[str] = []
    for step in packet.first_steps[:3]:
        text = _safe_scaffold_text(str(step))
        if text:
            lines.append(text)
    if any(item.fetch_status == "fetched" for item in searches):
        lines.append("Update the next artifact to quote the most decisive inspected evidence directly in the section where it matters.")
    lines.append("Remove any remaining process-heavy prose that does not change the substantive judgement.")
    return lines[:4]


def _join_paragraphs(*parts: str) -> str:
    return "\n\n".join(part.strip() for part in parts if part and part.strip())


def _markdown_list(items: list[str]) -> str:
    cleaned = [item.strip() for item in items if item and item.strip()]
    return "\n".join(f"- {item}" for item in cleaned)
