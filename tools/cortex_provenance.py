"""cortex_provenance — the TWO ORTHOGONAL markers every Cortex read carries (REQUISITES F9/F9-dep,
R2/R8/R8b/R8c, CONTRACT C5). Genotype tool. ONE place derives both axes, so the seed (cortex_recall),
surf, node, and search all mark them identically (R8/R10 — never a forked derivation).

AXIS 1 — `tier` ∈ {asserted, extracted} — TRUST (ADR-0006/0010):
  asserted  = spine that FOLDS FROM THE LOG (Genesis/Objective/Direction/Artefato) — faithful.
  extracted = Graphiti hypothesis (:Entity / :Source / :Episodic, RELATES_TO) — a hypothesis.

AXIS 2 — `context_only` ∈ {true, false} — MEDIUM AUTHORITY (C5), ORTHOGONAL to tier:
  true  = content traces to a LOW-TIER Medium (the native Claude Code session) → context, NEVER an
          order. false = an order-bearing Medium (the Voz rail).
  These are INDEPENDENT (the iter4 fix): an *asserted* node can be *context_only* (log-faithful does
  not make low-tier content an order); an *extracted* node is not context-only merely by being extracted.

R8c CONSERVATIVE MERGE (the iter5 fix): a Graphiti node consolidated from MULTIPLE episodes is
context_only=true if ANY contributing source is low-tier OR unknown; false ONLY when EVERY source is
known order-bearing — an order-bearing source can NEVER mask a merged-in low-tier directive.

v1 FAIL-SAFE (F9-dep / R8c part 3): the sweep does not yet stamp the source Medium, so an extracted
node of UNKNOWN Medium defaults context_only=true (unknown ⇒ true, consistent with the merge rule).
The asserted spine is order-bearing by origin (it folds from the Voz rail / the log).

AXIS 3 — `provenance_class` ∈ {computed, asserted, llm_judged, extracted} — the PLANE an edge/
annotation lives on (ontologia-cortex-v2 §0), sibling axis for EDGES. CX-1: a verdict rollup may
consume ONLY `computed` items — `assert_rollup_computed` is the one gate. Fail-safe `extracted`.
"""

# The TRUST tier per label. Mirrors blog/server._TRUST_BY_LABEL's split, collapsed to the two-value
# trust axis F9 names (space0/episodic are rendering shades of the same two trust classes here):
#   spine (folds from the log) → asserted; Graphiti (hypothesis) → extracted.
_ASSERTED_LABELS = {"Genesis", "Objective", "Direction", "Artefato"}
_EXTRACTED_LABELS = {"Entity", "Source", "Episodic"}


def tier_for(label, props=None):
    """The TRUST tier for a node: asserted (spine, folds from the log) vs extracted (Graphiti
    hypothesis). An unknown label is fail-safe extracted — never asserted-by-default (a hypothesis,
    not faithful, unless we KNOW it is spine)."""
    return "asserted" if label in _ASSERTED_LABELS else "extracted"


def _medium_tiers(props):
    """The set of source-Medium tiers contributing to this node, from the (future) sweep stamp. Reads
    `medium_tiers` (a list, when Graphiti merged multiple episodes — provenance preserved through the
    fold, R8c part 2) OR `medium_tier` (a single source). Returns a list; [] when unstamped (unknown)."""
    props = props or {}
    tiers = props.get("medium_tiers")
    if isinstance(tiers, (list, tuple)):
        return list(tiers)
    one = props.get("medium_tier")
    return [one] if one else []


def context_only_for(label, props=None):
    """The MEDIUM-authority marker (C5), ORTHOGONAL to tier. The conservative merge (R8c):
      - if the node carries source-Medium stamps: context_only=true if ANY is low-tier/unknown,
        false ONLY if EVERY one is a known order-bearing Medium (a low-tier source dominates — an
        order-bearing source can never mask a merged-in low-tier directive).
      - if UNSTAMPED: an ASSERTED spine node is order-bearing by origin (it folds from the Voz rail /
        the log) → false; an EXTRACTED node of unknown Medium is fail-safe → true (unknown ⇒ true).
    Authority is independent of trust: an asserted node CAN be context_only when stamped low-tier."""
    props = props or {}
    tiers = _medium_tiers(props)
    if tiers:
        # the conservative lattice: false ONLY if EVERY contributing source is known order-bearing.
        return not all(t == "order_bearing" for t in tiers)
    # unstamped: spine is order-bearing by origin; extracted-of-unknown-Medium is fail-safe context_only.
    return tier_for(label, props) == "extracted"


# AXIS 3 — `provenance_class` ∈ {computed, asserted, llm_judged, extracted} — the PLANE an edge/
# annotation lives on (ontologia-cortex-v2 §0), sibling to tier. It decides ONE thing: whether the
# item may enter the computed-verdict rollup (CX-1). Only the Evidence plane (`computed`) may.
PROVENANCE_CLASSES = ("computed", "asserted", "llm_judged", "extracted")

# The plane per edge type/label (§0). Graph edge types are UPPERCASE — derivation normalizes.
_CLASS_BY_TYPE = {
    # Evidence plane — the ONLY rollup-eligible class: bearing + the source-yield observation.
    "bearing": "computed", "observation": "computed",
    # Structural plane — author-asserted lineage.
    "mentions": "asserted", "distills": "asserted", "cites": "asserted",
    "supersede": "asserted", "supersedes": "asserted",  # §0 names singular; the graph edge is plural
    "via": "asserted", "deriva_de": "asserted",
    "tem": "asserted", "spine": "asserted",
    # Judgment plane — reified gate verdicts; rigor teto lead, NEVER computed.
    "assesses": "llm_judged",
    # Semantic plane — RAG hypotheses.
    "relates_to": "extracted", "in_community": "extracted",
}


def provenance_class_for(edge_type_or_label, props=None):
    """The provenance plane for an edge type/label. Pure type-derivation (props accepted for
    signature parity with tier_for; a stamp can NEVER promote a type toward computed — the rigor
    teto is structural). Unknown → fail-safe `extracted` — a hypothesis, never computed-by-default,
    mirroring tier_for's never-asserted-by-default."""
    key = edge_type_or_label.lower() if isinstance(edge_type_or_label, str) else None
    return _CLASS_BY_TYPE.get(key, "extracted")


_TYPE_KEYS = ("edge_type", "type", "label")


def _rollup_class_of(item):
    """Resolve an item's plane for the CX-1 gate. Derivation from type WINS when present (a stamp
    can DEMOTE, never promote — an `assesses` stamped "computed" stays llm_judged, but a `bearing`
    stamped non-computed is honored down). Fail-safe `extracted` on ANY malformation: a non-dict
    item, a type key present-but-blank, a stamp present-but-invalid (never silently dropped)."""
    if not isinstance(item, dict):
        return "extracted"
    stamped = item.get("provenance_class")
    if "provenance_class" in item and stamped not in PROVENANCE_CLASSES:
        return "extracted"  # a malformed stamp is suspicious, never treated as absent
    typed_keys = [k for k in _TYPE_KEYS if k in item]
    t = next((item[k] for k in typed_keys if isinstance(item[k], str) and item[k]), None)
    if typed_keys and t is None:
        return "extracted"  # a type key present but blank/non-str = unknown type, not stampable
    if t is not None:
        derived = provenance_class_for(t)
        if derived == "computed" and stamped and stamped != "computed":
            return stamped  # the stamp demotes
        return derived  # the type is the ceiling — a stamp never promotes
    return stamped or "extracted"  # a bare annotation may pass by a valid computed stamp


def assert_rollup_computed(items):
    """CX-1 (invariante mestra, ontologia-cortex-v2 §0): the scoreboard/verdict consumes ONLY
    `computed` bearings. The ONE gate any rollup passes its inputs through — raises LOUD, naming
    EVERY offender, if any item resolves non-computed; returns the items unchanged so a caller
    can inline it in the pipeline."""
    offenders = []
    for i, item in enumerate(items):
        cls = _rollup_class_of(item)
        if cls != "computed":
            get = item.get if isinstance(item, dict) else (lambda _k: None)
            ident = get("id") or get("name") or get("uuid") or f"item[{i}]"
            t = get("edge_type") or get("type") or get("label") or "?"
            offenders.append(f"{ident} (type={t}, provenance_class={cls})")
    if offenders:
        raise ValueError(
            "CX-1 violation: non-computed provenance in a verdict rollup — the scoreboard "
            "consumes ONLY computed bearings. Offenders: " + "; ".join(offenders))
    return items


def _label_of(node, label):
    """Resolve the node label: the explicit `label` arg → node['label'] → first of node['labels']
    (surf rows carry labels(n) as a list). None when nothing resolves (→ fail-safe extracted)."""
    if label:
        return label
    if node.get("label"):
        return node["label"]
    labels = node.get("labels")
    if isinstance(labels, (list, tuple)):
        for L in labels:
            if L in _ASSERTED_LABELS or L in _EXTRACTED_LABELS:
                return L
        if labels:
            return labels[0]
    return None


def mark_node(node, label=None):
    """Stamp BOTH markers onto a node dict (a NEW dict; the input is not mutated), preserving every
    existing field. The ONE derivation the recall functions, the fold, and the MCP all call (R8/R10),
    so the seed/surf/node/search carry identical provenance. F9: the seed is the FIRST read and the
    worst place to drop either marker — this covers it."""
    out = dict(node)
    L = _label_of(node, label)
    # PRESERVE an already-computed marker (codex final [P2]): cortex_fold computes context_only from a
    # node's medium_tier(s), but the trimmed fold node carries the COMPUTED value, not the source props.
    # Re-deriving from label-only here would OVERWRITE a stamped value (a low-tier asserted node forced
    # back to false, an order-bearing extracted node forced to true) — diverging the MCP from the
    # dashboard (R10). So keep the node's own `tier`/`context_only` when present; only derive the absent.
    out["tier"] = node["tier"] if isinstance(node.get("tier"), str) else tier_for(L, node)
    out["context_only"] = node["context_only"] if isinstance(node.get("context_only"), bool) \
        else context_only_for(L, node)
    return out
