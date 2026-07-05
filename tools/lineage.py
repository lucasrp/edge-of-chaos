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
