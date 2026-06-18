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
