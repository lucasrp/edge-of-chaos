"""Executable trace for the default Artefato genus rite.

The canonical rite is not reader-visible process chatter. It is a proof-bound
authoring trace: enough structured evidence that the artefact was produced by
the old-edge-with-grounding movement, not only polished until a final reviewer
accepted it.
"""

import hashlib
from pathlib import Path
import re


TRACE_VERSION = "old-edge-grounded@1"

REPO = Path(__file__).resolve().parent.parent

REQUIRED_STAGES = (
    "old_edge_draft",
    "gap_gate",
    "post_gate_grounding",
    "final_rewrite",
    "fact_audit",
)

STAGE_DEPENDENCIES = {
    "old_edge_draft": set(),
    "gap_gate": {"old_edge_draft"},
    "post_gate_grounding": {"old_edge_draft", "gap_gate"},
    "final_rewrite": {"old_edge_draft", "post_gate_grounding"},
    "fact_audit": {"final_rewrite"},
}

CANONICAL_MOVES = frozenset({
    "thesis",
    "live_question",
    "setup",
    "lineage",
    "result",
    "mechanism",
    "interpretation",
    "mundo",
    "grounding_effect",
    "limits",
    "decision",
    "references",
})


def normalize_genus_rite(value):
    """Return the digest/event shape for a caller-supplied genus trace.

    Malformed input normalizes to `{}`. Well-formed input keeps only the fields
    the rite validator understands, with strings stripped and empty containers
    removed. The normalizer is deliberately conservative so proof digests bind
    the same shape that check/publish/eventlog see.
    """
    if not isinstance(value, dict):
        return {}
    out = {}
    version = _clean_str(value.get("version")) or TRACE_VERSION
    out["version"] = version
    for key in (
        "old_edge_draft",
        "reader_model",
        "narrative_arc",
        "fact_audit",
        "dossier",
        "reader_visible_agency",
    ):
        cleaned = _clean(value.get(key))
        if cleaned:
            out[key] = cleaned
    for key in (
        "gap_gate",
        "post_gate_grounding",
        "rewrite_delta",
        "canonical_journey",
        "mundo_effects",
    ):
        cleaned = _clean_list(value.get(key))
        if cleaned:
            out[key] = cleaned
    stage_trace = _clean_stage_trace(value.get("stage_trace"))
    if stage_trace:
        out["stage_trace"] = stage_trace
    if len(out) == 1 and out.get("version") == TRACE_VERSION:
        return {}
    return out


def rite_violations(value, *, content=None, cites=None):
    """Return missing-process violations for a normalized or raw trace."""
    trace = normalize_genus_rite(value)
    if not trace:
        return ["genus-rite:missing-trace"]
    violations = []
    cite_refs = _cite_refs(cites)
    final_text = _content_text(content)
    gap_ids = _gap_ids(trace.get("gap_gate"))
    resolved_gap_ids = _gap_ids(trace.get("gap_gate"), dispositions={"resolved"})
    grounded_gap_ids = _grounded_gap_ids(
        trace.get("post_gate_grounding"), resolved_gap_ids, cite_refs)
    if not _old_edge_draft_ok(trace.get("old_edge_draft")):
        violations.append("genus-rite:old-edge-draft")
    if not _dossier_ok(trace.get("dossier")):
        violations.append("genus-rite:dossier")
    stage_violations = _stage_trace_violations(trace.get("stage_trace"))
    violations.extend(stage_violations)
    if not _reader_model_ok(trace.get("reader_model")):
        violations.append("genus-rite:reader-model")
    if not _narrative_arc_ok(trace.get("narrative_arc")):
        violations.append("genus-rite:narrative-arc")
    if not _gap_gate_ok(trace.get("gap_gate")):
        violations.append("genus-rite:actionable-gap-gate")
    if not _gap_dispositions_ok(trace.get("gap_gate"), final_text):
        violations.append("genus-rite:gap-disposition")
    if not _post_gate_grounding_ok(trace.get("post_gate_grounding"), resolved_gap_ids, cite_refs):
        violations.append("genus-rite:post-gate-grounding")
    if not _rewrite_delta_ok(trace.get("rewrite_delta"), grounded_gap_ids, final_text):
        violations.append("genus-rite:visible-rewrite-delta")
    if not _canonical_journey_ok(trace.get("canonical_journey"), final_text):
        violations.append("genus-rite:canonical-journey")
    if not _mundo_effects_ok(trace.get("mundo_effects"), final_text, cite_refs):
        violations.append("genus-rite:distributed-mundo")
    if not _reader_visible_agency_ok(trace.get("reader_visible_agency"), final_text):
        violations.append("genus-rite:reader-visible-agency")
    if not _fact_audit_ok(trace.get("fact_audit")):
        violations.append("genus-rite:fact-audit")
    return violations


def _clean(value):
    if isinstance(value, str):
        return _clean_str(value)
    if isinstance(value, list):
        return _clean_list(value)
    if isinstance(value, dict):
        out = {}
        for k, v in sorted(value.items()):
            if not isinstance(k, str):
                continue
            cleaned = _clean(v)
            if cleaned:
                out[k] = cleaned
        return out
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return value
    if isinstance(value, bool):
        return value
    return None


def _clean_list(value):
    if not isinstance(value, list):
        return []
    out = []
    for item in value:
        cleaned = _clean(item)
        if cleaned:
            out.append(cleaned)
    return out


def _clean_stage_trace(value):
    if not isinstance(value, list):
        return []
    out = []
    for item in value:
        if not isinstance(item, dict):
            continue
        stage = {}
        for key in ("id", "path", "sha256", "summary"):
            cleaned = _clean_str(item.get(key))
            if cleaned:
                stage[key] = cleaned
        parent = _clean_str(item.get("parent_stage_id"))
        if parent:
            stage["parent_stage_id"] = parent
        inputs = item.get("input_stage_ids")
        if isinstance(inputs, list):
            stage["input_stage_ids"] = [
                cleaned for cleaned in (_clean_str(v) for v in inputs) if cleaned
            ]
        allowed = item.get("allowed_inputs")
        if isinstance(allowed, list):
            stage["allowed_inputs"] = [
                cleaned for cleaned in (_clean_str(v) for v in allowed) if cleaned
            ]
        hashes = item.get("input_hashes")
        if isinstance(hashes, dict):
            cleaned_hashes = {}
            for k, v in sorted(hashes.items()):
                key = _clean_str(k)
                digest = _clean_str(v)
                if key and digest:
                    cleaned_hashes[key] = digest
            if cleaned_hashes:
                stage["input_hashes"] = cleaned_hashes
        if stage:
            out.append(stage)
    return out


def _clean_str(value):
    if not isinstance(value, str):
        return ""
    return value.strip()


def _has_payload(value):
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, list):
        return any(_has_payload(v) for v in value)
    if isinstance(value, dict):
        return any(_has_payload(v) for v in value.values())
    return value is not None


def _has_fields(item, fields):
    return isinstance(item, dict) and all(_has_payload(item.get(f)) for f in fields)


def _any_item(items, required):
    return isinstance(items, list) and any(_has_fields(item, required) for item in items)


def _old_edge_draft_ok(draft):
    if not isinstance(draft, dict):
        return False
    # The first draft is itself a rite, not a free-form vibe marker.
    required = (
        "derived_thesis",
        "live_question",
        "reader_context",
        "lineage_seed",
        "worked_example",
        "lacunas",
        "outside_frame_candidates",
        "mentor_arc",
        "unknowns",
        "actionable_landing",
    )
    return all(_has_payload(draft.get(field)) for field in required)


def _dossier_ok(dossier):
    required = (
        "reader_model",
        "lineage",
        "object_identity",
        "anchors",
        "mechanism_evidence",
        "mundo_candidates",
        "unknowns",
    )
    return _has_fields(dossier, required)


def _stage_trace_violations(stages):
    if not isinstance(stages, list) or not stages:
        return ["genus-rite:stage-trace"]
    by_id = {}
    order = []
    for stage in stages:
        if not isinstance(stage, dict):
            return ["genus-rite:stage-trace"]
        stage_id = _clean_str(stage.get("id"))
        if stage_id in by_id:
            return ["genus-rite:stage-trace"]
        by_id[stage_id] = stage
        order.append(stage_id)

    violations = []
    if tuple(order[:len(REQUIRED_STAGES)]) != REQUIRED_STAGES:
        violations.append("genus-rite:stage-order")
    missing = [stage_id for stage_id in REQUIRED_STAGES if stage_id not in by_id]
    if missing:
        violations.append("genus-rite:stage-trace")
        return violations

    for stage_id in REQUIRED_STAGES:
        stage = by_id[stage_id]
        if not _stage_shape_ok(stage):
            violations.append(f"genus-rite:stage-shape:{stage_id}")
            continue
        if not _stage_provenance_ok(stage_id, stage):
            violations.append(f"genus-rite:stage-provenance:{stage_id}")
        deps = set(_clean_str(v) for v in stage.get("input_stage_ids") or [])
        if not STAGE_DEPENDENCIES[stage_id] <= deps:
            violations.append(f"genus-rite:stage-deps:{stage_id}")
        if not _stage_hash_ok(stage):
            violations.append(f"genus-rite:stage-hash:{stage_id}")
    return violations


def _stage_shape_ok(stage):
    if not _has_fields(stage, ("id", "path", "sha256", "summary")):
        return False
    if not isinstance(stage.get("input_stage_ids"), list):
        return False
    digest = _clean_str(stage.get("sha256"))
    return bool(re.fullmatch(r"[0-9a-f]{64}", digest))


def _stage_provenance_ok(stage_id, stage):
    if stage_id != "old_edge_draft" and not _has_payload(stage.get("parent_stage_id")):
        return False
    if not isinstance(stage.get("allowed_inputs"), list) or not stage.get("allowed_inputs"):
        return False
    hashes = stage.get("input_hashes")
    if not isinstance(hashes, dict) or not hashes:
        return False
    for key, digest in hashes.items():
        if not _clean_str(key):
            return False
        if not re.fullmatch(r"[0-9a-f]{64}", _clean_str(digest)):
            return False
    return True


def _stage_path(path):
    raw = _clean_str(path)
    if not raw:
        return None
    p = Path(raw)
    if not p.is_absolute():
        p = REPO / p
    try:
        resolved = p.resolve()
    except OSError:
        return None
    try:
        resolved.relative_to(REPO.resolve())
    except ValueError:
        # A stage trace is a genotype artifact, not an arbitrary filesystem attestation.
        return None
    return resolved


def _stage_hash_ok(stage):
    path = _stage_path(stage.get("path"))
    if path is None or not path.is_file():
        return False
    try:
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return False
    return actual == _clean_str(stage.get("sha256"))


def _reader_model_ok(model):
    if not isinstance(model, dict):
        return False
    if not _has_payload(model.get("reader")):
        return False
    calibrated = [
        "leveling",
        "interests",
        "decision_context",
        "growth_target",
        "utility_target",
    ]
    return all(_has_payload(model.get(field)) for field in calibrated)


def _narrative_arc_ok(arc):
    if not isinstance(arc, dict):
        return False
    if not _has_payload(arc.get("throughline")):
        return False
    beats = [
        "opening_stakes",
        "turning_point",
        "teaching_lesson",
        "landing_decision",
    ]
    return sum(1 for field in beats if _has_payload(arc.get(field))) >= 2


def _gap_ids(items, *, dispositions=None):
    if not isinstance(items, list):
        return set()
    out = set()
    allowed = {"resolved", "accepted_risk", "rejected"}
    selected = allowed if dispositions is None else set(dispositions)
    for item in items:
        if not isinstance(item, dict):
            continue
        gap_id = _clean_str(item.get("id"))
        disposition = _clean_str(item.get("disposition"))
        if (
            gap_id
            and _has_fields(item, ("id", "gap", "grounding_task", "disposition"))
            and disposition in selected
        ):
            out.add(gap_id)
    return out


def _gap_gate_ok(items):
    return bool(_gap_ids(items))


def _gap_dispositions_ok(items, final_text):
    if not isinstance(items, list) or not items:
        return False
    for item in items:
        if not isinstance(item, dict):
            return False
        disposition = _clean_str(item.get("disposition"))
        if disposition == "accepted_risk":
            if not _has_fields(item, ("risk_tag", "final_anchor")):
                return False
            anchor = _clean_str(item.get("final_anchor")).lower()
            if not anchor or not final_text or anchor not in final_text:
                return False
        elif disposition == "rejected":
            if not _has_payload(item.get("rationale")):
                return False
        elif disposition != "resolved":
            return False
    return True


def _grounding_item_ok(item, gap_ids, cite_refs):
    if not _has_fields(item, ("gap_id", "source_ref", "finding", "changed")):
        return False
    gap_id = _clean_str(item.get("gap_id"))
    source_ref = _clean_str(item.get("source_ref"))
    return gap_id in gap_ids and source_ref in cite_refs


def _grounded_gap_ids(items, gap_ids, cite_refs):
    if not isinstance(items, list):
        return set()
    return {
        _clean_str(item.get("gap_id"))
        for item in items
        if isinstance(item, dict) and _grounding_item_ok(item, gap_ids, cite_refs)
    }


def _post_gate_grounding_ok(items, gap_ids, cite_refs):
    if not gap_ids or not cite_refs:
        return False
    return gap_ids <= _grounded_gap_ids(items, gap_ids, cite_refs)


def _rewrite_item_ok(item, grounded_gap_ids, final_text):
    if not _has_fields(item, ("gap_id", "before", "after", "effect", "final_anchor")):
        return False
    gap_id = _clean_str(item.get("gap_id"))
    anchor = _clean_str(item.get("final_anchor")).lower()
    return gap_id in grounded_gap_ids and bool(anchor) and anchor in final_text


def _rewritten_gap_ids(items, grounded_gap_ids, final_text):
    if not isinstance(items, list):
        return set()
    return {
        _clean_str(item.get("gap_id"))
        for item in items
        if isinstance(item, dict) and _rewrite_item_ok(item, grounded_gap_ids, final_text)
    }


def _rewrite_delta_ok(items, grounded_gap_ids, final_text):
    if not grounded_gap_ids or not final_text:
        return False
    return grounded_gap_ids <= _rewritten_gap_ids(items, grounded_gap_ids, final_text)


def _canonical_journey_ok(items, final_text):
    if not isinstance(items, list) or not final_text:
        return False
    moves = set()
    for item in items:
        if not (
            isinstance(item, dict)
            and _has_payload(item.get("move"))
            and _has_payload(item.get("where"))
        ):
            continue
        where = _clean_str(item.get("where")).lower()
        if where and where in final_text:
            moves.add(str(item.get("move")).strip())
    return CANONICAL_MOVES <= {m for m in moves if m}


def _mundo_effects_ok(items, final_text, cite_refs):
    if not isinstance(items, list) or not items or not final_text or not cite_refs:
        return False
    for item in items:
        if not _has_fields(item, ("source_ref", "fit", "mismatch", "changes", "final_anchor")):
            return False
        if _clean_str(item.get("source_ref")) not in cite_refs:
            return False
        anchor = _clean_str(item.get("final_anchor")).lower()
        if not anchor or anchor not in final_text:
            return False
    return True


def _reader_visible_agency_ok(agency, final_text):
    required = ("decision_now", "do_not_overclaim", "risk_status", "next_validation")
    if not _has_fields(agency, required):
        return False
    anchor = _clean_str(agency.get("final_anchor")).lower()
    return bool(anchor and final_text and anchor in final_text)


def _fact_audit_ok(audit):
    if not isinstance(audit, dict):
        return False
    return (
        _has_payload(audit.get("external_claims_checked"))
        and _has_payload(audit.get("overclaim_guard"))
    )


def _cite_refs(cites):
    if not isinstance(cites, list):
        return set()
    refs = set()
    for cite in cites:
        if isinstance(cite, dict):
            ref = _clean_str(cite.get("ref"))
        else:
            ref = _clean_str(cite)
        if ref:
            refs.add(ref)
    return refs


def _content_text(content):
    parts = []
    _walk_content_text(content, parts)
    return " ".join(parts).lower()


def _walk_content_text(value, parts):
    if isinstance(value, str):
        stripped = value.strip()
        if stripped:
            parts.append(stripped)
        return
    if isinstance(value, list):
        for item in value:
            _walk_content_text(item, parts)
        return
    if not isinstance(value, dict):
        return
    for key, child in value.items():
        if key in {"url", "href", "style", "badge_class", "card_class", "_grounding"}:
            continue
        _walk_content_text(child, parts)
