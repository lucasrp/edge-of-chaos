"""lineage — the single normalizer for authored typed lineage (Cortex v1, brick-1).

NEUTRAL, dependency-free, pure: imports NOTHING from the project, so it can sit BELOW close/eventlog
(close imports it; eventlog imports close) without a cycle.

Main's lineage is a LIST of typed-edge dicts — `[{"type": "builds_on"|"supersedes"|"contradicts",
"slug": <prior-slug>, "target"?: <prior-slug>}]` — which the publisher materializes into DIRECTED
graph edges. `normalize_lineage` sanitizes that list BEFORE the proof digest binds it
(`close.proof_digest`'s `json.dumps(..., default=str)`) and before the durable publish event
persists it, so a malformed item can never (a) be `str()`-coerced into the verification anchor nor
(b) ride into the log as junk. It DROPS bad items rather than coercing them — the same posture
`close.real_lineage` and the publisher's edge loop already take downstream.
"""
import re

# the authored typed-lineage relations (mirror of close/publisher LINEAGE handling). Any other type
# (e.g. the cosine-nominated RELATES_TO, which is NOT author-declared) is dropped.
_TYPES = frozenset({"builds_on", "supersedes", "contradicts"})


def normalize_lineage(lineage) -> list:
    """Return the well-formed authored lineage edges — order-preserving, deduped.

    None / non-list -> []. An item survives ONLY if it is a dict with `type` in the allowlist AND a
    NON-BLANK string `slug`; a non-dict, an unknown/blank type, or a blank/non-string slug is DROPPED
    (never str()-coerced). The optional `target` (an alternate prior-slug the publisher prefers) is
    carried only when it is a non-blank string. No other field survives — junk cannot ride into the
    digest. Dupes (same type+slug+target) collapse, keeping first occurrence.
    """
    if not isinstance(lineage, list):
        return []
    out = []
    seen = set()
    for item in lineage:
        if not isinstance(item, dict):
            continue
        typ = item.get("type")
        if typ not in _TYPES:
            continue
        # the prior is referenced by `slug` (close.real_lineage) and/or `target` (the publisher prefers
        # `target` then falls back to `slug`); an item survives iff it carries at least one as a non-blank
        # string. Both are kept when valid; a blank/non-string value is dropped, never coerced.
        slug, target = item.get("slug"), item.get("target")
        slug_ok = isinstance(slug, str) and slug.strip()
        target_ok = isinstance(target, str) and target.strip()
        if not (slug_ok or target_ok):
            continue
        edge = {"type": typ}
        if slug_ok:
            edge["slug"] = slug.strip()
        if target_ok:
            edge["target"] = target.strip()
        key = (typ, edge.get("slug"), edge.get("target"))
        if key in seen:
            continue
        seen.add(key)
        out.append(edge)
    return out


# Ticket A (episteme nativo, ontologia-cortex-v2 §2b) — the valenced bears_on declarations, same
# layer and same posture as normalize_lineage: sanitized HERE, once, before the proof digest binds
# them and before the durable publish event persists them. The valence enum mirrors episteme's
# canonical bearing valences (SUPPORTS≙apoia, REFUTES≙refuta, QUALIFIES, INCONCLUSIVE).
_VALENCES = frozenset({"supports", "refutes", "qualifies", "inconclusive"})


def normalize_bears_on(bears_on) -> list:
    """Return the well-formed bears_on declarations — order-preserving, deduped on
    (hypothesis, valence). An item survives ONLY if it is a dict with a NON-BLANK string
    `hypothesis` (ulid or slug of a declared :Hypothesis) and `valence` in the episteme enum;
    an optional non-blank string `rationale` is carried, everything else is DROPPED (never
    coerced) — junk cannot ride into the digest. Multivalence is native (one artefato → N
    entries, O-6). None / non-list -> []."""
    if not isinstance(bears_on, list):
        return []
    out, seen = [], set()
    for item in bears_on:
        if not isinstance(item, dict):
            continue
        hyp, valence = item.get("hypothesis"), item.get("valence")
        if not (isinstance(hyp, str) and hyp.strip() and valence in _VALENCES):
            continue
        key = (hyp.strip(), valence)
        if key in seen:
            continue
        seen.add(key)
        edge = {"hypothesis": hyp.strip(), "valence": valence}
        rationale = item.get("rationale")
        if isinstance(rationale, str) and rationale.strip():
            edge["rationale"] = rationale.strip()
        out.append(edge)
    return out


def normalize_para(para) -> list:
    """Return the well-formed `para` targets (ontologia §6: artefato-PARA->parceiro, the document
    MADE for the person) — non-blank strings, stripped, deduped, order-preserving. None /
    non-list (including a bare string — a single name still arrives as a list) -> []."""
    if not isinstance(para, list):
        return []
    out, seen = [], set()
    for name in para:
        if isinstance(name, str) and name.strip() and name.strip() not in seen:
            seen.add(name.strip())
            out.append(name.strip())
    return out


EXPERIMENT_ID_RE = re.compile(r"^exp[0-9]+$")


def normalize_reports_on(reports_on) -> list:
    """Return the well-formed Experiment ids an Artefato reports on.

    `Report` is still the human-readable Artefato and semantic bridge; `Experiment` is the
    scientific object. This list authors the structural edge
    (Artefato)-[:REPORTS_ON]->(Experiment). Experiment ids are canonical handles (`exp` +
    digits, e.g. `exp40`, `exp071`): loose folder/session names do not become experiment
    identities. Non-canonical ids are dropped rather than coerced, preserving the same
    fail-closed posture as `para`.
    """
    if not isinstance(reports_on, list):
        return []
    out, seen = [], set()
    for experiment_id in reports_on:
        if isinstance(experiment_id, str) and experiment_id.strip():
            clean = experiment_id.strip()
            if EXPERIMENT_ID_RE.fullmatch(clean) and clean not in seen:
                seen.add(clean)
                out.append(clean)
    return out


EXPERIMENT_TYPED_FIELDS = ("claim", "scope", "status", "caveat", "supports", "excludes", "next")
_EXPERIMENT_CURATION_FIELDS = frozenset(
    {"prose", "typed", "canonical_artifacts", "by", "relates"})


def _require_nonblank(value, field):
    if not (isinstance(value, str) and value.strip()):
        raise ValueError(f"experiment curation field {field!r} must be a non-blank string")
    return value.strip()


def _normalize_experiment_typed(typed):
    if not isinstance(typed, dict):
        raise ValueError("experiment canonical conclusion needs a typed dict")
    missing = [k for k in EXPERIMENT_TYPED_FIELDS if k not in typed]
    if missing:
        raise ValueError(f"experiment typed conclusion missing fields: {', '.join(missing)}")
    out = {}
    for k in ("claim", "scope", "status", "caveat", "next"):
        out[k] = _require_nonblank(typed.get(k), k)
    for k in ("supports", "excludes"):
        v = typed.get(k)
        if not isinstance(v, list) or not all(isinstance(x, str) and x.strip() for x in v):
            raise ValueError(f"experiment typed field {k!r} must be a list of non-blank strings")
        out[k] = [x.strip() for x in v]
    return out


def _normalize_canonical_artifacts(canonical_artifacts):
    if canonical_artifacts is None:
        return []
    if not isinstance(canonical_artifacts, list):
        raise ValueError("experiment canonical artifacts must be a list")
    out = []
    for a in canonical_artifacts:
        if not isinstance(a, dict):
            raise ValueError("experiment canonical artifacts must be dicts")
        item = {
            "ref": _require_nonblank(a.get("ref"), "canonical_artifacts[].ref"),
            "role": _require_nonblank(a.get("role"), "canonical_artifacts[].role"),
        }
        if isinstance(a.get("note"), str) and a["note"].strip():
            item["note"] = a["note"].strip()
        out.append(item)
    return out


def _has_finalization_report_artifact(artifacts):
    for item in artifacts:
        ref = item.get("ref")
        role = item.get("role")
        if (isinstance(ref, str) and ref.strip().startswith("artefato:")
                and isinstance(role, str) and role.strip().lower() == "report"):
            return True
    return False


def _looks_like_single_experiment_curation(value):
    return isinstance(value, dict) and bool(_EXPERIMENT_CURATION_FIELDS.intersection(value.keys()))


def normalize_experiment_curation(reports_on, experiment_curation, *, report_slug=None, by=None) -> list:
    """Return canonical `experiment.curated` payloads authored by a report.

    A report that closes an experiment carries explicit `experiment_curation` and `reports_on`.
    The report itself is automatically inserted as the first canonical audit artifact
    (`artefato:<slug>`), making the act of publishing the report the experiment finalization.
    The shape is either a single curation dict for one `reports_on` id, or a mapping
    `{experiment_id: curation}` for multiple ids. Malformed explicit curation raises loudly: unlike
    optional lineage fields, this is the scientific close event and must not fail dark.
    """
    if experiment_curation is None:
        return []
    experiment_ids = normalize_reports_on(reports_on)
    if not experiment_ids:
        raise ValueError("experiment_curation requires reports_on")
    if not isinstance(experiment_curation, dict):
        raise ValueError("experiment_curation must be a dict")
    if _looks_like_single_experiment_curation(experiment_curation):
        if len(experiment_ids) != 1:
            raise ValueError("single experiment_curation requires exactly one reports_on id")
        curations_by_id = {experiment_ids[0]: experiment_curation}
    else:
        curations_by_id = experiment_curation

    out = []
    for experiment_id in experiment_ids:
        raw = curations_by_id.get(experiment_id)
        if not isinstance(raw, dict):
            raise ValueError(f"missing experiment_curation for {experiment_id!r}")
        artifacts = []
        if isinstance(report_slug, str) and report_slug.strip():
            artifacts.append({"ref": f"artefato:{report_slug.strip()}",
                              "role": "report",
                              "note": "finalization report"})
        artifacts.extend(_normalize_canonical_artifacts(raw.get("canonical_artifacts")))
        if not artifacts:
            raise ValueError("experiment curation needs at least one canonical audit artifact")
        if not _has_finalization_report_artifact(artifacts):
            raise ValueError(
                "experiment curation requires a finalization report artifact "
                "(role='report', ref='artefato:<slug>')")

        by_value = raw.get("by") if isinstance(raw.get("by"), str) and raw.get("by").strip() else by
        relates = raw.get("relates") or []
        if not isinstance(relates, list) or not all(isinstance(x, dict) for x in relates):
            raise ValueError("experiment curation relates must be a list of dicts")
        out.append({
            "experiment_id": experiment_id,
            "canonical": {
                "prose": _require_nonblank(raw.get("prose"), "prose"),
                "typed": _normalize_experiment_typed(raw.get("typed")),
            },
            "canonical_artifacts": artifacts,
            "by": _require_nonblank(by_value, "by"),
            "relates": list(relates),
        })
    return out
