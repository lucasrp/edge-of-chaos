"""The shared rich producer protocol — Phase 0 seam (docs/plans/shared-rich-producer-protocol.md).

A per-producer DESCRIPTOR declares ADDITIONAL presentation obligations over a small, stable PREDICATE
VOCABULARY. `evaluate_floor` is the GENERIC, capability-aware evaluator the close calls — it has no
per-producer branches. The descriptor adds presentation obligations ON TOP of the genus floor; it can
NEVER express or weaken the rich rite (that stays the content-relative genus gate in `close._check_rich_rite`).

Adding a producer = registering a descriptor. A producer with no descriptor fails loud (`require_descriptor`)
— it never silently inherits another form's floor.
"""
import render
from render import _BLOCK_TYPE_ALIASES  # one shared source of truth

# --- capability registry: block type -> the capability its renderer needs (absent => block
# unavailable). The visual recipe set unifies chart + diagram on `vl-convert` (a pure-pip wheel,
# no system binary, no root) — the capability key is "vl-convert", checked by importability. ---
VL_CONVERT = "vl-convert"
CAPABILITY = {
    "diagram": VL_CONVERT,   # full Vega (graph-layout family: dag/force)
    "chart": VL_CONVERT,     # Vega-Lite (data-chart family)
}

# --- predicate evaluation statuses ---
_SATISFIED, _WRITER_UNSAT, _ENV_UNSAT = "satisfied", "writer-unsat", "env-unsat"

# --- per-producer descriptors. PRESENTATION obligations only — additive over the genus rich rite,
# which stays the unconditional, content-relative gate (close._check_rich_rite). report/research declare
# no presentation floor: their depth IS the rich rite. map/plan/discovery owe form-specific illustration
# /structure/framing. R1 (S6): the floor demands the RENDERABLE visual (diagram/chart) — `ascii-diagram`
# is DROPPED (S7: an ungroundable authored visual), so it no longer satisfies any floor. When `vl-convert`
# is ABSENT the renderable type isn't environmentally available → the floor degrades to ENV_UNSAT (not
# owed: the relation goes in grounded prose), never to an ascii substitute. ---
DESCRIPTORS = {
    "report": {"require": []},
    "research": {"require": []},
    "map": {"require": [
        {"pred": "min_blocks_of", "types": ["diagram", "chart"], "n": 2},
    ]},
    "plan": {"require": [
        {"pred": "has_structure", "id": "framed_steps"},
        {"pred": "min_blocks_of", "types": ["diagram", "chart"], "n": 1},
    ]},
    "discovery": {"require": [
        {"pred": "contextual_framing"},
    ]},
    # mentor is the renamed grill producer. It publishes insight Artefatos under the same rich rite,
    # with no extra presentation floor. `grill` stays below as a legacy producer name so existing
    # artefacts and old invocations can still replay.
    "mentor": {"require": []},
    "grill": {"require": []},
    # critique — a NEW producer added by declaration only (Phase 4). Its floor is novel: a critique
    # owes a side-by-side COMPARISON (the verdict surface) AND a marked UNCERTAINTY (what it could not
    # settle) — two independent min_blocks_of obligations over block types no other descriptor names
    # (comparison/comparison-table, gap-table/gap-marker), proving the generic evaluator enforces a new
    # SHAPE from the declaration alone.
    "critique": {"require": [
        {"pred": "min_blocks_of", "types": ["comparison-table", "comparison"], "n": 1},
        {"pred": "min_blocks_of", "types": ["gap-table", "gap-marker"], "n": 1},
    ]},
    # prototype (ticket C) — the interactive single-file HTML+JS genus. Its companion ENTRY
    # declares no presentation floor: the standalone page (publisher.publish_prototype_page)
    # carries the form, and the bar there is structural (single-file/zero-dep, enforced at that
    # seam) + semantic ("a interatividade ensina?", the skill's converge — never a keyword check).
    "prototype": {"require": []},
    # lazer (ticket 05) — puro lazer, exploração livre (distinct from discovery's directed
    # serendipity). No presentation floor by design: the form is free (the exemplar is the
    # single-file interactive edge-of-chaos netlify blog); the genus rich rite still applies.
    "lazer": {"require": []},
}

# The MIGRATED producers — the prose/visual genus the rito rollout closed the legacy publish road for
# (docs/rito-runtime.md §Producer adoption). Their ONLY road to publication is the rite
# (rito.run_rito → publisher.publish_rito); the legacy close (close.run_close → publisher.publish) is
# REFUSED for them, at BOTH the publisher.publish seam AND the eventlog.publish_artefato_atomic
# commit primitive (only publish_rito passes the internal rite authorization). `prototype`/`lazer`
# (interactive single-file) stay legacy by operator decision and are NOT here. This is the single
# tools-side source of truth for the publish-guard split — the publish tests (test_publisher) derive
# their expectations from THIS tuple, not a hardcoded copy. (mentor publishes its insight through the
# rite with skill='mentor', so it is refused at the legacy seam like the rest; the doc-iteration
# tuples in test_producers / test_lineage_producer_docs cover the 5 canonical prose skill-DOC files
# and are a separate concern.)
RITO_PRODUCERS = ("report", "research", "map", "plan", "discovery", "mentor")

_STRUCTURE_BLOCKS = {"framed_steps": {"next-steps-grid", "numbered-card"}}


def _iter_blocks(content):
    for key in ("sections", "additional_sections"):
        for sec in content.get(key, []) or []:
            for b in sec.get("blocks", []) or []:
                yield b


def _canon(block):
    t = block.get("type", "paragraph")
    return _BLOCK_TYPE_ALIASES.get(t, t)


def _capability_available(capability, capabilities):
    """Is a renderer capability present? A test-supplied `capabilities` dict overrides (mock); else
    probe the real environment. The only capability is `vl-convert` (importable iff installed)."""
    if capabilities is not None and capability in capabilities:
        return bool(capabilities[capability])
    if capability == VL_CONVERT:
        return render.diagram_available()  # vl-convert importable
    return False


def _type_available(block_type, capabilities):
    """A block type is environmentally available unless its renderer's capability is missing."""
    capability = CAPABILITY.get(block_type)
    return True if capability is None else _capability_available(capability, capabilities)


# Presentation-CHROME fields — never "content". A countable block has payload iff some CONTENT field
# (its schema's required+optional+synonym fields MINUS chrome) is non-blank. Schema-derived, so it is
# complete-by-construction: a new block type's content fields count automatically (no hand-maintained
# allowlist to keep chasing — the empty-ascii/empty-callout cases still fail because their content
# fields are blank, while comparison `before/after`, gap-table `gaps`, grid `now/next/later`, etc. count).
_CHROME_FIELDS = frozenset({
    "type", "title", "label", "headers", "header", "style", "variant", "badge", "badge_class",
    "badge_variant", "orientation", "v", "note", "card_class", "highlight_rows", "score_row",
    "input_label", "output_label", "left_title", "right_title", "id", "name",
})


def _content_fields(canon):
    schema = render.BLOCK_SCHEMAS.get(canon)
    if schema is None:
        return None  # unknown type → caller checks any non-chrome field
    fields = set(schema.get("required", [])) | set(schema.get("optional", [])) | set(schema.get("synonyms", {}))
    return fields - _CHROME_FIELDS


def _has_payload(block):
    canon = _canon(block)
    fields = _content_fields(canon)
    keys = fields if fields is not None else (set(block) - _CHROME_FIELDS)
    for f in keys:
        v = block.get(f)
        if isinstance(v, str) and v.strip():
            return True
        if isinstance(v, (list, dict)) and v:
            return True
    return False


# The renderable-gated visuals (chart + diagram): a block of these types counts ONLY if it would
# actually render — capability present AND the recipe validates AND vl-convert succeeds. Maps the
# canonical type to (authoritative renderable check, recipe spec builder for the mocked path).
# canon -> (renderable-fn name on `render`, builder name on `render.visual_recipes`). Names, not captured
# references, so the lookup is LIVE — `mock.patch.object(render, "diagram_renderable", ...)` is honored.
_RENDERABLE_VISUALS = {
    "diagram": ("diagram_renderable", "build_diagram"),
    "chart": ("chart_renderable", "build_chart"),
}


def _block_counts(block, canon, capabilities):
    """A block satisfies a floor only if it would actually RENDER something substantive: its type's
    capability is available, it carries a non-blank payload, AND (for a chart/diagram) the recipe
    actually renders — so an empty/garbage block, or a chart/diagram on a host without vl-convert,
    never counts."""
    if not _has_payload(block):
        return False
    if canon in _RENDERABLE_VISUALS:
        rname, bname = _RENDERABLE_VISUALS[canon]
        renderable = getattr(render, rname)            # live lookup — honors mocks
        # In production (no capabilities dict) the renderable check is the SOLE authority — it
        # encapsulates vl-convert availability AND that the recipe validates and renders. In a
        # capability-mocked unit test vl-convert can't be exercised against the mock, so use the
        # caps dict for availability and the recipe VALIDATOR (error is None) for validity.
        if capabilities is None:
            return renderable(block)
        _spec, error = getattr(render.visual_recipes, bname)(block)
        return _type_available(canon, capabilities) and error is None
    return _type_available(canon, capabilities)


def _eval_predicate(pred, blocks, capabilities):
    """Return (status, label) for one predicate. status in {satisfied, writer-unsat, env-unsat}."""
    kind = pred["pred"]
    if kind == "min_blocks_of":
        types, n = pred["types"], pred.get("n", 1)
        # count only RENDERABLE blocks — a capability-backed type whose binary is absent (a `diagram`
        # with no `dot`) cannot render, so it must NOT satisfy the floor; that forces the any_of
        # fallback / env-unsat path instead of passing an unrenderable block.
        present = sum(1 for b in blocks
                      if _canon(b) in types and _block_counts(b, _canon(b), capabilities))
        if present >= n:
            return _SATISFIED, ""
        label = f"min_blocks_of({'/'.join(types)},{n})"
        # writer could have satisfied it iff at least one required type is environmentally available
        if any(_type_available(t, capabilities) for t in types):
            return _WRITER_UNSAT, label
        return _ENV_UNSAT, label
    if kind == "any_of":
        results = [_eval_predicate(o, blocks, capabilities) for o in pred["options"]]
        statuses = [s for s, _ in results]
        if _SATISFIED in statuses:
            return _SATISFIED, ""
        label = "any_of(" + ",".join(lbl for _, lbl in results if lbl) + ")"
        return (_WRITER_UNSAT if _WRITER_UNSAT in statuses else _ENV_UNSAT), label
    if kind == "has_structure":
        wanted = _STRUCTURE_BLOCKS.get(pred["id"], set())
        present = any(_canon(b) in wanted and _has_payload(b) for b in blocks)  # non-empty steps, not just presence
        return (_SATISFIED, "") if present else (_WRITER_UNSAT, f"has_structure({pred['id']})")
    if kind == "contextual_framing":
        present = any(_canon(b) == "callout" and _has_payload(b) for b in blocks)  # non-empty framing
        return (_SATISFIED, "") if present else (_WRITER_UNSAT, "contextual_framing")
    raise ValueError(f"unknown presentation predicate: {kind!r}")


def evaluate_floor(content, require, capabilities=None):
    """Evaluate a producer's declared presentation floor against an artefato's blocks.

    Returns (violations, env_skipped):
      - violations  — writer-unsatisfiable obligations (a real shortfall the writer COULD fix → bounce);
      - env_skipped — environment-unsatisfiable obligations (a required capability absent with no fallback;
        the close marks these unsatisfied for an environmental reason and must NOT retry generation).
    `capabilities` maps binary name -> bool (test override); None probes the real PATH.
    """
    blocks = list(_iter_blocks(content))
    violations, env_skipped = [], []
    for pred in require:
        status, label = _eval_predicate(pred, blocks, capabilities)
        if status == _WRITER_UNSAT:
            violations.append(f"presentation:{label}")
        elif status == _ENV_UNSAT:
            env_skipped.append(f"presentation:{label}")
    return violations, env_skipped


def descriptor_for(skill):
    """The descriptor for a producer skill, or None if unregistered (caller decides)."""
    return DESCRIPTORS.get(skill)


def require_descriptor(skill):
    """Fail loud: a producer MUST declare a descriptor — it never inherits another form's floor."""
    if skill not in DESCRIPTORS:
        raise KeyError(f"producer {skill!r} has no descriptor (the protocol requires one — declare it)")
    return DESCRIPTORS[skill]


def presentation_violations(artefato, capabilities=None):
    """The close hook: the writer-unsatisfiable presentation violations for this artefato's producer.
    No-op for an unregistered skill or a permissive (empty) floor — so it adds nothing until a producer
    declares a real floor (Phase 3). The rich rite is enforced separately and unconditionally."""
    desc = DESCRIPTORS.get(artefato.get("skill"))
    if not desc or not desc.get("require"):
        return []
    violations, _env_skipped = evaluate_floor(artefato.get("content", {}), desc["require"], capabilities)
    return violations
