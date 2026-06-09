"""The Close protocol — the shared dispatch exit (ADR-0012/0013).

Every producer funnels through the close: the genus conformance contract (S6, here),
then the blind review gates (S7), then the bounded bounce (S8). This module is the
testable spine of that protocol — pure Python, import-clean on the runtime python.

S6 — the genus conformance contract (OUTPUT-enforced, SECTIONS FREE):
`check_genus(artefato)` returns the list of genus violations ([] iff conformant). It
pins the artefato field shapes against the real `eventlog.publish_artefato` + `kernel`
signatures and checks **visual-coverage** content-relatively: quantitative/multi-value
material with no visual element from the palette is flagged; prose-only content owes no
visual and is never falsely failed. It never checks for any named or ordered section.

The visual palette below is pinned to the block types in tools/render.py.
"""
import hashlib
import json
import secrets

from render import BLOCK_SCHEMAS, _BLOCK_TYPE_ALIASES

# ---------------------------------------------------------------------------
# Genus contract constants — the pinned field shapes + the visual palette
# ---------------------------------------------------------------------------

# The visual element types from the render palette (tools/render.py). A `table` is
# tabular data, NOT itself a visual — the genus owes a visual *alongside* dense tables.
# `comparison-table` is treated as visual (it is a styled side-by-side, not a raw grid).
VISUAL_BLOCK_TYPES = frozenset({
    "raw-html", "svg", "html", "custom-html",   # chart / svg escape hatch
    "ascii-diagram",
    "metrics-grid", "metrics", "metric-card", "metric-cards", "kpi-row", "kpi-grid", "stats",
    "next-steps-grid", "steps",
    "comparison", "pros-cons", "compare",
    "comparison-table",
    "flow-example",
    "diff-block",
    "concept-grid",
})

# Block types that carry quantitative/multi-value material. A plain `table` (and its
# aliases) with enough data rows is the trigger; the threshold mirrors the task spec.
DATA_TABLE_TYPES = frozenset({"table", "key-value", "kv", "data-table", "stat-row"})
QUANTITATIVE_ROW_THRESHOLD = 3

# ---------------------------------------------------------------------------
# The rich-rite floor (#30) — content-relative property gates on the cognitive
# moves the rich old reports forced. MIRRORS _check_visual_coverage: a TRIGGER
# (here: a DEVELOPED PROSE synthesis) owes the moves; a non-prose/terse form owes
# none and is NEVER falsely failed. NEVER a named section, NEVER a word floor —
# the trigger is a STRUCTURAL count of prose blocks (mirrors QUANTITATIVE_ROW_THRESHOLD),
# and each move is satisfied by a dedicated palette block OR a content marker ANYWHERE.
# ---------------------------------------------------------------------------

# Prose-bearing block types (after alias canonicalization). A synthesis carrying enough of
# these is a "developed prose synthesis" — the trigger that owes the four cognitive moves.
# A map (ascii-diagram + table) or a terse plan (next-steps-grid) carries none and owes nothing.
PROSE_BLOCK_TYPES = frozenset({"paragraph", "callout", "subsection"})
# The structural trigger threshold — NOT a word count. Below it, the artefato is too terse to
# be a developed synthesis and owes none of the moves (content-relative, like visual-coverage).
RICH_RITE_PROSE_THRESHOLD = 3

# Palette blocks that, by their mere presence, satisfy a cognitive move (the move is present
# ANYWHERE — never a named section). Mirrors how a metrics-grid satisfies visual-coverage.
DERIVATION_BLOCK_TYPES = frozenset({"derivation"})
BOUNDARY_BLOCK_TYPES = frozenset({"gap-marker", "gap-table", "gap-resolution"})

# Content markers — the move carried in prose rather than a dedicated block. Conservative on
# purpose: a present, specific marker, not a length proxy. Matched case-insensitively anywhere
# in the artefato's prose text.
DERIVATION_MARKERS = (
    "first principle", "from first principles", "derive", "derivation",
    "because ", "therefore", "it follows", "follows that", "reason ", "reasoning",
)
BOUNDARY_MARKERS = (
    "what i don't know", "what i do not know", "i don't know", "i do not know",
    "unknown", "uncertain", "unverified", "inferred", "not sure", "open question",
    "knowledge boundary", "blind spot", "untested",
)
LINEAGE_MARKERS = (
    "builds on", "build on", "building on", "prior", "lineage", "earlier work",
    "previous report", "previously", "extends", "extending", "we already",
    "already know", "already wrote",
)


# ---------------------------------------------------------------------------
# Genus contract — check_genus
# ---------------------------------------------------------------------------

def check_genus(artefato: dict) -> list[str]:
    """Return the genus violations of a finished artefato ([] iff conformant).

    Checks the OUTPUT contract only — never a named/ordered section:
      - every cite carries a `ref` and a `snippet`;
      - every proposes item carries a `body`;
      - `intent` (the kernel) is present and non-empty;
      - visual-coverage: if the content has quantitative/multi-value material but no
        visual palette element, "visual-coverage" is flagged (content-relative).
    """
    violations = []
    violations += _check_cites(artefato.get("cites", []))
    violations += _check_proposes(artefato.get("proposes", []))
    violations += _check_intent(artefato.get("intent"))
    violations += _check_block_schemas(artefato.get("content", {}))
    violations += _check_visual_coverage(artefato.get("content", {}))
    violations += _check_rich_rite(artefato)
    return violations


def _check_cites(cites: list) -> list[str]:
    if not isinstance(cites, list):
        return [f"cites must be a list, got {type(cites).__name__}: {cites!r}"]
    violations = []
    for cite in cites:
        if not isinstance(cite, dict):
            violations.append(f"cite must be a dict, got {type(cite).__name__}: {cite!r}")
            continue
        ref = cite.get("ref")
        snippet = cite.get("snippet")
        label = ref if isinstance(ref, str) and ref.strip() else "(cite with no ref)"
        # ref and snippet must each be a STRING with non-empty .strip() content — a non-string
        # (e.g. an int ref or a dict snippet) or a whitespace-only string is a violation, so a
        # malformed cite field can never mint a proof (Codex round-6).
        if not (isinstance(ref, str) and ref.strip()):
            violations.append(f"cite missing ref: {label}")
        if not (isinstance(snippet, str) and snippet.strip()):
            violations.append(f"cite missing snippet: {label}")
    return violations


def _check_proposes(proposes: list) -> list[str]:
    violations = []
    for i, item in enumerate(proposes):
        if not isinstance(item, dict) or not item.get("body"):
            violations.append(f"proposes item {i} missing body")
    return violations


def _check_intent(intent) -> list[str]:
    if not intent or not str(intent).strip():
        return ["intent is empty (the kernel — the durable why — is required)"]
    return []


def _check_block_schemas(content: dict) -> list[str]:
    """Validate every block's required fields against render.BLOCK_SCHEMAS (#7), so a malformed
    block fails the genus here instead of crashing render later. A required field may be carried
    directly OR via one of the schema's synonyms (render normalizes those before rendering).

    The block type is first normalized to its CANONICAL form via render's shared alias map
    (`_BLOCK_TYPE_ALIASES`, imported — never duplicated) so that an alias block (e.g. text→paragraph,
    note→callout) is checked against the canonical schema's required fields. Otherwise an alias would
    skip the required-field check, pass genus, then CRASH when render_block canonicalizes it (Codex
    round-6). Block types still not in BLOCK_SCHEMAS after canonicalization (genuinely unknown) are
    skipped — render degrades those to an HTML comment without raising."""
    violations = []
    for block in _iter_blocks(content):
        block_type = block.get("type", "paragraph")
        block_type = _BLOCK_TYPE_ALIASES.get(block_type, block_type)
        schema = BLOCK_SCHEMAS.get(block_type)
        if schema is None:
            continue
        synonyms = schema.get("synonyms", {})
        syn_for = {}  # canonical -> [synonym names that map to it]
        for syn, canonical in synonyms.items():
            syn_for.setdefault(canonical, []).append(syn)
        for field in schema.get("required", []):
            if field in block:
                continue
            if any(syn in block for syn in syn_for.get(field, [])):
                continue
            violations.append(f"block {block_type!r} missing required field {field!r}")
    return violations


def _check_visual_coverage(content: dict) -> list[str]:
    """Flag "visual-coverage" iff the content has quantitative/multi-value material
    but no visual palette element. Content with no quantitative material owes none.
    Traverses the FULL render tree (#7): top-level metrics is itself a visual; dense tables
    anywhere render touches — sections AND additional_sections — count."""
    has_quantitative = False
    has_visual = bool(content.get("metrics"))  # top-level metrics grid is a visual
    for block in _iter_blocks(content):
        block_type = block.get("type", "paragraph")
        if block_type in VISUAL_BLOCK_TYPES:
            has_visual = True
        if _is_dense_table(block, block_type):
            has_quantitative = True
    if has_quantitative and not has_visual:
        return ["visual-coverage"]
    return []


def _is_dense_table(block: dict, block_type: str) -> bool:
    if block_type not in DATA_TABLE_TYPES:
        return False
    return len(block.get("rows", [])) >= QUANTITATIVE_ROW_THRESHOLD


def _block_text(block: dict) -> str:
    """The human-readable text a block carries, for marker scanning — flattens the string
    values render reads (text/title/bullets/items/...). Type-tolerant: only strings are
    joined, nested lists are walked one level (bullets, items). The `type` key is EXCLUDED — it
    is the block's tag, not content, so a bare `{"type":"derivation"}` placeholder carries no
    text (it must not self-clear the derivation move via its own type name)."""
    parts = []
    for k, v in block.items():
        if k == "type":
            continue
        if isinstance(v, str):
            parts.append(v)
        elif isinstance(v, list):
            for it in v:
                if isinstance(it, str):
                    parts.append(it)
                elif isinstance(it, dict):
                    parts.extend(s for s in it.values() if isinstance(s, str))
    return " ".join(parts)


def _check_rich_rite(artefato: dict) -> list[str]:
    """The rich-rite floor (#30). CONTENT-RELATIVE, mirroring `_check_visual_coverage`: only a
    DEVELOPED PROSE synthesis (the trigger — `>= RICH_RITE_PROSE_THRESHOLD` prose blocks, a
    STRUCTURAL count, NEVER a word floor) owes the four cognitive moves the rich old reports
    forced. A diagram-form map, a terse plan, or a short bite carries too little prose to be a
    developed synthesis and owes NONE — never falsely failed (exactly as prose-only content owes
    no visual).

    Each move is satisfied by its dedicated palette block OR by a content marker present ANYWHERE
    in the artefato — NEVER a named or ordered section (ADR-0012/0013):
      - derivation        — a `derivation` block, or a first-principles/reasoning marker;
      - what-i-dont-know  — a `gap-*` block, or a knowledge-boundary/uncertainty marker;
      - external-frame    — a non-empty `cites` (a sourced benchmark) or a `bibliography` block,
                            or a benchmark marker (extends the sourcing strike);
      - lineage           — a non-empty `distills` (the threads it builds on), or a lineage marker.

    Returns `rich-rite:<move>` for each missing move ([] when none owed or all present)."""
    content = artefato.get("content", {}) or {}
    blocks = list(_iter_blocks(content))
    # render renders top-level `executive_summary` as prose too (Codex P2), so it counts toward the
    # trigger AND toward the marker text — a report whose moves live in the summary is not falsely
    # flagged, and a summary-heavy report cannot evade the floor with < threshold section paragraphs.
    summary = content.get("executive_summary") or []
    summary_items = [s for s in summary if isinstance(s, str) and s.strip()]
    prose_count = len(summary_items)
    prose_count += sum(
        1 for b in blocks
        if _BLOCK_TYPE_ALIASES.get(b.get("type", "paragraph"), b.get("type", "paragraph"))
        in PROSE_BLOCK_TYPES
    )
    if prose_count < RICH_RITE_PROSE_THRESHOLD:
        return []  # not a developed prose synthesis — owes none of the prose moves

    text = (" ".join(_block_text(b) for b in blocks) + " " + " ".join(summary_items)).lower()

    def marked(markers):
        return any(m in text for m in markers)

    def has_filled_block(types):
        # a palette block satisfies a move ONLY if it carries actual payload (Codex P2): a bare
        # placeholder block (no text/items/refs) must not clear the strike.
        return any(
            _BLOCK_TYPE_ALIASES.get(b.get("type", "paragraph"), b.get("type", "paragraph")) in types
            and _block_text(b).strip()
            for b in blocks
        )

    # external-frame requires an OUTSIDE benchmark (Codex P2): an `atividade` (internal provenance)
    # cite is the mentee's own work, not an external frame — only an external (`mundo`) cite or a
    # non-empty bibliography clears it. A cite with no/unknown kind is treated conservatively as
    # external (the reviewer's sourcing strike catches a hallucinated one).
    external_cite = any(
        isinstance(c, dict) and c.get("kind") != "atividade"
        for c in (artefato.get("cites") or [])
    )
    bibliography = bool(content.get("bibliography"))

    has_derivation = has_filled_block(DERIVATION_BLOCK_TYPES) or marked(DERIVATION_MARKERS)
    has_boundary = has_filled_block(BOUNDARY_BLOCK_TYPES) or marked(BOUNDARY_MARKERS)
    has_frame = external_cite or bibliography
    has_lineage = bool(artefato.get("distills")) or marked(LINEAGE_MARKERS)

    violations = []
    if not has_derivation:
        violations.append("rich-rite:derivation")
    if not has_boundary:
        violations.append("rich-rite:what-i-dont-know")
    if not has_frame:
        violations.append("rich-rite:external-frame")
    if not has_lineage:
        violations.append("rich-rite:lineage")
    return violations


def _iter_blocks(content: dict):
    """Yield every block across EVERY part render.spec_to_html renders (#7): `sections` and
    `additional_sections` (sections are FREE — order and names are irrelevant; the genus reads
    the blocks, not the layout), plus the top-level `bibliography` render wraps as a block.
    The top-level `metrics` and `executive_summary` are handled by the callers (a metrics grid
    is a visual; the summary is prose) — not block-shaped, so not yielded here."""
    for key in ("sections", "additional_sections"):
        for section in content.get(key, []):
            for block in section.get("blocks", []):
                yield block
    if content.get("bibliography"):
        yield {"type": "bibliography", "references": content["bibliography"]}


# ---------------------------------------------------------------------------
# S7 — the two blind review gates (ADR-0013: blind by evidence-and-session,
# property-not-section, cross-provider). Kept cleanly separate from the genus
# above and from the S8 bounce that will follow.
# ---------------------------------------------------------------------------

# The review dimensions — the legacy 9-dim DIMENSIONS (review-gate.py), depth dims RESTORED.
# The rewrite had dropped the two report-welded dims (structural_completeness, storytelling) for
# "SECTIONS FREE" — and with them went the gate's only reward for depth, so honest cited bites
# passed. They are back as `development_completeness` and `narrative_depth`, but reworded
# PROPERTY-NOT-SECTION: the gate checks the depth/arc is present ANYWHERE, genuine and specific,
# never whether a named section exists or in what order. Plenitude is the bar (scaffold.md): a
# thin honest bite that left the thinking undone FAILS.
DIMENSIONS = {
    "development_completeness": (
        "The theme is DEVELOPED TO PLENITUDE for the form at hand — a report's claims reasoned "
        "through and their implications drawn out, a map's connections richly traced, a plan's "
        "dependencies worked out — not merely gestured at. Depth is the bar; an artefato that leaves "
        "the thinking undone fails even when honest and cited. A property of the whole, never section "
        "count or order."
    ),
    "narrative_depth": (
        "CONTENT-RELATIVE (like visualization): where the form carries a developed LINE — a report's "
        "or research's argument — the artefato has an ARC, not a list: a through-line the reader can "
        "follow (tension/question → derivation → synthesis → the open next-bet), present ANYWHERE, "
        "never a mandated section order. A genuinely non-narrative form (a map's diagram, a terse "
        "plan) owes no prose arc and is NEVER failed for lacking one. A report that dumps flat "
        "findings, or a bite that states a conclusion without earning it, fails."
    ),
    "content_depth": (
        "Substance, not placeholders: concrete details, data, numbers, real examples. "
        "No empty or stub content; tables carry real data."
    ),
    "frame_enrichment": (
        "Did the artefato ENRICH the mentee's frame — import a definition, benchmark, named "
        "pattern, or industry best-practice from OUTSIDE the mentee's current frame and fit it "
        "to their live work, so their MODEL/VISION of what they are doing got better? The "
        "litmus: did the mentee's frame/modelagem/visão IMPROVE? Naming what they do in the "
        "field's vocabulary, locating their work among external approaches, bringing an outside "
        "benchmark or best-practice — these enrich. RE-APPLYING the mentee's OWN existing "
        "vocabulary/data to itself is NOT enrichment (that is frame application); a closed "
        "internal diagnosis that brings nothing the mentee could not derive from what they "
        "already know does not enrich the frame. Content-relative in VEHICLE — a map may enrich "
        "via a genuinely non-obvious structural insight rather than an external cite — but never "
        "escapable by relabeling internal restatement as insight. SOURCING GUARD: an imported "
        "external reference (benchmark, pattern, author, framework) MUST carry a verifiable cite "
        "or be explicitly marked inferred/unverified — naming an outside authority WITHOUT a "
        "cite, or overextending an attribution, is HALLUCINATED enrichment and fails (the "
        "blindfold applies to these external claims like any fact)."
    ),
    "contextualization": (
        "CONTEXTUALIZED to the mentee's LIVE WORK: the artefato produces knowledge/insight APPLIED to "
        "what they are actually building and deciding — framed in their Idiom, tied to their portfolio "
        "and mission — not a self-contained exercise. The litmus: could the mentee ACT on this, or does "
        "it only DESCRIBE a system? A generic survey, an internal DATA-MODEL / schema dump, or a topology "
        "described for its own sake — rigorous but never touching the mentee's decisions — FAILS. The "
        "inward complement of frame_enrichment: enrichment brings the world IN, contextualization applies "
        "it to the mentee's live work."
    ),
    "feynman_method": (
        "Derivation-first thinking is visible ANYWHERE in the artefato: reasoning from "
        "first principles before reaching for a source. The knowledge boundary is explicit "
        "and location-agnostic — where the author's understanding stopped and the cite began "
        "is marked (derived vs repeated vs unknown), genuine and specific, not boilerplate. "
        "Concepts are taught as to someone intelligent but unfamiliar; no jargon left undefined."
    ),
    "intellectual_honesty": (
        "Uncertainty and the derived/repeated/unknown knowledge-boundary are explicit, "
        "specific (not boilerplate), and present ANYWHERE in the artefato — NOT confined to "
        "any named section. Blind spots and untested assumptions are acknowledged in place. "
        "Absent OR boilerplate uncertainty blocks."
    ),
    "didactic_clarity": (
        "Every term, acronym, and tool name is comprehensible SOMEWHERE in the artefato — "
        "explained in place or wherever it best lands — so a smart newcomer never has to guess. "
        "This is a property of the whole text, not the presence of a glossary block."
    ),
    "internal_consistency": (
        "The artefato agrees with itself: summary matches body, numbers are consistent "
        "throughout, the title matches the actual scope, cited prior work is real not generic."
    ),
    "visualization": (
        "Content-relative: did the artefato visualize what the content deserved? Quantitative "
        "or multi-value material (3+ compared values, relationships, flows) earns a chart, "
        "diagram, or grid. Genuinely non-visual prose owes no visual and is never failed for it."
    ),
    "writing_quality": (
        "Prose flows where prose is used: transitions between ideas, a reflective (not robotic) "
        "tone, evocative titles. A visual or terse artefato is not penalized for being non-prose."
    ),
}

# Weights as a {dim: weight} dict (NOT a positional list — the legacy
# `DIMENSION_WEIGHTS[:len(scores)]` slicing silently mis-paired weights to dims once the
# dim set changed).
# NOTE: the weighted `overall` is ADVISORY — it does NOT gate. An LLM 0-5 score is too noisy
# to threshold (gating on it would be theatre); the gate is the reviewer's `pass` + any STRIKE,
# and the actionable signal is the per-dimension RATIONALE (feedback), not the number. Weights
# are kept for color and to keep the dims/weights sets in sync. The depth cluster
# (development_completeness + narrative_depth + content_depth + feynman_method) plus the
# outward-vector dim (frame_enrichment) carry the most weight — what we most want surfaced in
# the rationale-feedback. Rescaled by the sum so all weights sum to 1.0.
_LEGACY_KEPT_WEIGHTS = {
    "development_completeness": 0.18,
    "narrative_depth": 0.14,
    "content_depth": 0.16,
    "feynman_method": 0.14,
    "frame_enrichment": 0.15,
    "contextualization": 0.14,
    "intellectual_honesty": 0.10,
    "didactic_clarity": 0.10,
    "internal_consistency": 0.06,
    "visualization": 0.06,
    "writing_quality": 0.06,
}
_KEPT_SUM = sum(_LEGACY_KEPT_WEIGHTS.values())  # 1.0
DIMENSION_WEIGHTS = {dim: w / _KEPT_SUM for dim, w in _LEGACY_KEPT_WEIGHTS.items()}

# The shared blind-reviewer instruction. Each reviewer prepends its own focus. The reviewer
# sees the FINAL Artefato text + its cites ONLY — evidence, session, and briefing are denied.
_BLIND_PREAMBLE = (
    "You are a blind quality reviewer for a published Artefato. You see ONLY the artefato's "
    "final content and its cites — you have NO access to the evidence the author read, the "
    "session/transcript, or the briefing. Judge only what is in front of you. Score each "
    "dimension 0-5 AND give a one-sentence `rationale` for each score — the rationale is the "
    "actionable FEEDBACK (what is missing and concretely how to improve it); the bare number is "
    "advisory and is not what gates. Put any blocking, specific defect in `strikes` — a strike "
    "forces a revision, so be concrete about what is wrong and what would fix it. Respond with "
    "ONLY a JSON object: "
    '{"pass": bool, "scores": {dim: int}, "rationales": {dim: str}, "strikes": [str], '
    '"overall": float}.'
)

_FEYNMAN_FOCUS = (
    "FOCUS: rigor and intellectual honesty. The BLINDFOLD test applies to FACTUAL CLAIMS — a "
    "fact, datum, quote, or external assertion must be re-sourceable from its cite; a factual "
    "claim that cannot be traced to a cite is struck (add it to `strikes` and fail). A REASONING "
    "step — a derivation, or an inference from premises already present in the artefato — is NOT "
    "struck for lacking a cite: judge it by its INTERNAL VALIDITY (do the stated premises support "
    "it?). Do not amputate thinking-out-loud — derivation-first reasoning is REWARDED by the depth "
    "dims, never penalized for being uncited. Check the derived/repeated/unknown knowledge-boundary "
    "is explicit, specific, and present anywhere — not boilerplate."
)

_REGULAR_FOCUS = (
    "FOCUS: clarity, craft, and FRAME-ENRICHMENT. Substance, didactic clarity (every term "
    "comprehensible somewhere), flowing prose, internal consistency, and content-relative "
    "visualization. CRUCIAL — the outward vector: STRIKE when the artefato is a CLOSED internal "
    "diagnosis that re-applies only the mentee's own frame/vocabulary and brings NO outside "
    "definition, benchmark, named field-pattern, or industry best-practice to enrich it — a "
    "deep recap of the mentee's own model that names nothing in the field and brings nothing "
    "they could not have derived themselves does NOT enrich the frame and must be struck (say "
    "what outside frame/benchmark/best-practice it should have brought). ALSO STRIKE hallucinated "
    "enrichment — a NAMED-BUT-UNSOURCED external (a field/benchmark/author/framework invoked "
    "without a verifiable cite, or an attribution that looks overextended or inaccurate): naming "
    "the field without sourcing it is worse than a closed diagnosis. AND STRIKE a self-contained "
    "exercise that never CONTEXTUALIZES to the mentee's live work — an internal data-model / schema "
    "dump, a topology described for its own sake, or a generic survey that describes a system "
    "without insight the mentee could act on. A genuinely internal form (a connections map) that "
    "still reveals a non-obvious structure AND ties it to the mentee's work is NOT struck."
)


def _published_view(artefato: dict) -> dict:
    """The blind view a reviewer is allowed: the final content + cites ONLY. Strips every
    non-published field (evidence, session, briefing) so the reviewer cannot see them — the
    last rung of the context-denial ladder (ADR-0013)."""
    return {
        "slug": artefato.get("slug"),
        "content": artefato.get("content", {}),
        "cites": artefato.get("cites", []),
    }


def _dimension_text() -> str:
    return "\n".join(f"- {name}: {desc}" for name, desc in DIMENSIONS.items())


def _build_prompt(focus: str, artefato: dict) -> str:
    view = _published_view(artefato)
    return (
        f"{_BLIND_PREAMBLE}\n\n{focus}\n\n"
        f"Dimensions:\n{_dimension_text()}\n\n"
        f"Artefato (content + cites only):\n{json.dumps(view, ensure_ascii=False)}"
    )


def _failing_verdict(strike: str, scores=None) -> dict:
    """A well-shaped FAILING verdict (pass:false) carrying one explanatory strike. Every
    shape violation funnels through here so a degraded reviewer ALWAYS yields a bounded
    failing verdict of the canonical shape — never a raise, never a half-built dict."""
    return {
        "pass": False,
        "scores": scores if isinstance(scores, dict) else {},
        "rationales": {},
        "strikes": [strike],
        "overall": 0.0,
    }


def _genus_feedback(violations: list) -> dict:
    """A synthetic FAILING verdict carrying the genus violations (incl. the rich-rite floor's
    `rich-rite:<move>` strikes) as `strikes`, so `improve_fn` is handed the NAMED gap and can
    re-produce richer — the floor forces depth, not only a hard-fail (Codex P2, #30). Shaped
    exactly like a reviewer verdict so improve_fn reads it uniformly."""
    return {
        "pass": False,
        "scores": {},
        "rationales": {},
        "strikes": list(violations),
        "overall": 0.0,
    }


def _parse_verdict(raw: str) -> dict:
    """Parse the reviewer's JSON verdict into {pass, scores, strikes, overall}, computing the
    weighted overall from the dim scores when the model omits/garbles it.

    FAILS CLOSED on ANY shape violation and NEVER RAISES for any input shape (Codex round-7
    [high] + round-8 [medium]). A degraded/schema-drifted reviewer response can NEVER mint a
    pass AND can never crash the close. The verdict passes ONLY iff EVERY shape invariant
    holds: parseable JSON; `result` is a dict; `result["pass"] is True` (exact boolean
    identity — `bool("false")` is True, so coercion is forbidden); `scores` is a dict; every
    score present is a real int/float (bool excluded); `strikes` is a list. ANY violation —
    non-bool `pass`, `scores` null/list/string, a malformed score, `strikes` null/non-list, a
    non-dict `result` (a bare JSON list/string/number/null), or unparseable JSON — returns a
    well-shaped FAILING verdict with an explanatory strike. This kills the WHOLE degraded-
    output class at the source, not just `scores:null`; `run_close` wraps this too (defense in
    depth) so even an unforeseen shape can only ever become a bounded failing verdict."""
    text = raw.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        if text.endswith("```"):
            text = text[:-3].strip()
    try:
        result = json.loads(text)
    except (ValueError, TypeError) as e:
        return _failing_verdict(f"unparseable reviewer verdict JSON: {e}")
    # `result` must be a dict — a bare JSON list/string/number/null is a schema violation.
    if not isinstance(result, dict):
        return _failing_verdict(
            f"verdict is not a JSON object, got {type(result).__name__}: {result!r}")
    # `scores` must be a dict — null/list/string would crash `.get()` and is a shape violation.
    scores = result.get("scores", {})
    if not isinstance(scores, dict):
        return _failing_verdict(
            f"scores is not an object, got {type(scores).__name__}: {scores!r}")
    # `strikes` must be a list — null/non-list is a shape violation that must fail closed.
    strikes = result.get("strikes", [])
    if not isinstance(strikes, list):
        return _failing_verdict(
            f"strikes is not a list, got {type(strikes).__name__}: {strikes!r}", scores)
    # `rationales` is the per-dimension FEEDBACK (the actionable signal). It is NON-gating: a
    # missing/malformed rationales map never fails the verdict (the gate is pass + strikes, not
    # the feedback) — it degrades to {} and the verdict still parses. Carried through so the
    # improve-loop (run_close's improve_fn) and the operator can read WHY each dim scored as it did.
    rationales = result.get("rationales", {})
    if not isinstance(rationales, dict):
        rationales = {}
    # Exact boolean identity — `bool("false")` is True, so coercion is forbidden here — AND a
    # struck verdict can never pass (Codex round-9 [high]): a non-empty `strikes` list makes the
    # verdict FAIL even when `pass` is True. The close protocol is that ANY reviewer strike must
    # bounce/fail, so `{"pass":true,"strikes":["uncited claim"]}` is a FAILING verdict; only
    # `pass is True AND no strikes` passes. The strikes are preserved below for the bounce.
    passed = (result.get("pass") is True) and not strikes
    # Score hardening: any non-numeric / malformed score (a string, an object, a bool) fails
    # closed — it does NOT pass and is NOT silently coerced. We strike it and recompute the
    # overall from only the numeric scores so the weighted overall never crashes.
    strikes = list(strikes)
    overall = 0.0
    for dim, w in DIMENSION_WEIGHTS.items():
        score = scores.get(dim, 0)
        if isinstance(score, bool) or not isinstance(score, (int, float)):
            passed = False
            strikes.append(f"malformed score for {dim!r}: {score!r}")
            continue
        overall += score * w
    return {
        "pass": passed,
        "scores": scores,
        "rationales": rationales,
        "strikes": strikes,
        "overall": round(float(overall), 2),
    }


def _review(focus: str, artefato: dict, complete_fn) -> dict:
    """Run one blind reviewer: build the blind prompt, hand it to the injected completer,
    parse the verdict. `complete_fn(prompt) -> str` is injectable so tests run offline;
    real runs pass a make_client-backed completer on the review router (Grok)."""
    raw = complete_fn(_build_prompt(focus, artefato))
    return _parse_verdict(raw)


# The canonical reviewer IDENTITIES (Codex re-review #3). A passing proof must carry verdicts
# from BOTH of these named reviewers; verify_proof requires both. run_close stamps the identity
# onto each verdict from the canonical reviewer's `.identity` attribute — a fake/injected
# reviewer has none, so its verdict carries no canonical identity and the proof fails identity
# verification. The identity is the reviewer's role name (not its provider), so swapping the
# review router does not invalidate proofs.
FEYNMAN_REVIEWER_ID = "feynman_review"
REGULAR_REVIEWER_ID = "regular_review"


def feynman_review(artefato: dict, complete_fn) -> dict:
    """The feynman gate (rigor + honesty), blind. Returns {pass, scores, strikes, overall}."""
    return _review(_FEYNMAN_FOCUS, artefato, complete_fn)


def regular_review(artefato: dict, complete_fn) -> dict:
    """The regular gate (clarity + craft), blind. Returns {pass, scores, strikes, overall}."""
    return _review(_REGULAR_FOCUS, artefato, complete_fn)


# Stamp each canonical reviewer with its identity so run_close can record WHO reviewed (only
# the canonical reviewers carry one; an injected fake reviewer does not).
feynman_review.identity = FEYNMAN_REVIEWER_ID
regular_review.identity = REGULAR_REVIEWER_ID


# ---------------------------------------------------------------------------
# S8 — the bounce loop + the loop-2 brake. The bound lives HERE, in the
# protocol constants — never in the producer's discretion. That bound is what
# separates a gate from the retry-envelope ADR-0003 killed (which let a producer
# retry at will). BOUNCE_MAX caps reviewer→producer re-produces; LOOP2_MAX_REOPENS
# caps serendipity's advisory loop-1 reopens. Neither loop can ever run unbounded.
# ---------------------------------------------------------------------------

BOUNCE_MAX = 1            # reviewer strike → re-produce, at most this many times
LOOP2_MAX_REOPENS = 1     # serendipity may reopen loop-1 at most this many times
IMPROVE_ROUNDS = 2        # unconditional review→improve refinement passes before the gating close


# ---------------------------------------------------------------------------
# The proof contract — UNFORGEABLE and BOUND (Codex re-review #2).
#
# A passing review is no longer a shape-only dict the publisher trusts on sight (a forged or
# stale `{pass: True, verdicts: [...]}` published unreviewed/different content). The proof
# `run_close` mints is bound to a sha256 DIGEST of the EXACT publish payload (slug + spec +
# intent + cites + proposes + distills + skill — EVERY state/page-affecting publish arg, #3),
# carries BOTH reviewer verdicts each stamped with its CANONICAL reviewer identity (#3), and is
# stamped with a `run_close`-only secret token minted ONCE per process — a caller cannot
# fabricate one because the token never leaves this module. The mint itself is module-PRIVATE
# (`_mint_proof`, #3): only run_close (and the explicit test seam) can reach it. `verify_proof`
# (called at the publish seam) refuses unless the token is run_close's, the digest matches the
# payload actually being published (so distills/skill cannot be altered post-mint), the
# configured number of reviewers all passed, AND both canonical reviewer identities are present.
#
# RESIDUAL (architecture, not a code fix): a producer agent with in-process code execution can
# still call the private `_mint_proof` or fabricate the canonical identities. FULL enforcement
# requires the close to run OUTSIDE the producer's context — a real trust boundary / blind
# reviewer subagents the producer cannot reach. This module raises the in-process bar; it does
# not (and cannot, in-process) close that residual.
# ---------------------------------------------------------------------------

# The run_close-only secret: a fresh per-process token. It is module-private and is stamped
# onto every minted proof; the publisher checks it via verify_proof. A hand-built dict cannot
# carry it (the value is unknowable to a caller), so the publisher can never be back-doored.
_PROOF_TOKEN = secrets.token_hex(32)


def proof_digest(*, slug, spec, intent, cites, proposes, distills=None, skill=None) -> str:
    """The sha256 digest BINDING a proof to the EXACT publish payload. Canonical JSON
    (sorted keys) so the same payload always digests identically and the publisher can
    recompute it from the args it is about to publish — any difference (different slug, spec,
    intent, cites, proposes, distills, or skill) yields a different digest and is rejected.

    Codex re-review #3: `distills` and `skill` are page/state-affecting publish arguments
    (they ride the durable `artefato.published` event), so they MUST be bound — otherwise a
    proof-holder could alter them at publish time without invalidating the proof (poisoning
    provenance)."""
    payload = {
        "slug": slug,
        "spec": spec,
        "intent": intent,
        "cites": cites or [],
        "proposes": proposes or [],
        "distills": distills or [],
        "skill": skill,
    }
    blob = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _mint_proof(verdicts, *, slug, spec, intent, cites, proposes,
                distills=None, skill=None) -> dict:
    """Mint the bound, token-stamped proof for a passing close. Carries BOTH reviewer
    verdicts (each stamped by run_close with its canonical reviewer identity), the digest of
    the exact payload (now including distills + skill), and the run_close-only token.

    Codex re-review #3: this is module-PRIVATE — ONLY `run_close` (and the explicit test-only
    seam standing in for it) calls it. It is no longer a public function a producer could call
    to stamp the valid token onto a verdict list of its own choosing."""
    return {
        "pass": True,
        "verdicts": list(verdicts),
        "digest": proof_digest(slug=slug, spec=spec, intent=intent,
                               cites=cites, proposes=proposes,
                               distills=distills, skill=skill),
        "token": _PROOF_TOKEN,
    }


def _verdict_clean(verdict) -> bool:
    """A verdict mints/verifies a passing proof ONLY iff it is a dict, `pass is True`, AND it
    carries NO strikes (Codex round-9 [high]). A struck verdict — even one whose `pass` slipped
    through as True (an injected reviewer, an unforeseen shape) — can never mint or verify a
    proof, enforcing the close protocol that ANY reviewer strike must bounce/fail. A non-list
    `strikes` is treated as non-empty (fail-closed), so a degraded shape can never sneak a pass."""
    if not isinstance(verdict, dict) or verdict.get("pass") is not True:
        return False
    strikes = verdict.get("strikes", [])
    return isinstance(strikes, list) and not strikes


def verify_proof(proof, *, slug, spec, intent, cites, proposes,
                 distills=None, skill=None, reviewer_count=2):
    """Verify a proof BINDS to the payload being published — raise ValueError otherwise,
    BEFORE any state/HTML is written. Refuses unless: the token is run_close's (not a
    fabricated one), the digest matches THIS payload — now including distills + skill, so a
    proof-holder cannot alter the persisted distills/skill (#3) — all `reviewer_count`
    reviewers passed (a single-reviewer proof is rejected), AND the verdicts carry BOTH
    canonical reviewer identities (a proof built from fake/injected reviewers is rejected on
    identity grounds, #3)."""
    if not isinstance(proof, dict):
        raise ValueError(f"cannot publish artefato {slug!r}: no proof (#2)")
    if not secrets.compare_digest(str(proof.get("token", "")), _PROOF_TOKEN):
        raise ValueError(
            f"cannot publish artefato {slug!r}: forged/absent proof token — "
            "publish only through close.run_close (#2)")
    expected = proof_digest(slug=slug, spec=spec, intent=intent,
                            cites=cites, proposes=proposes,
                            distills=distills, skill=skill)
    if not secrets.compare_digest(str(proof.get("digest", "")), expected):
        raise ValueError(
            f"cannot publish artefato {slug!r}: proof digest does not bind to this "
            "payload (minted for a different artefato, or distills/skill altered) (#3)")
    verdicts = proof.get("verdicts") or []
    if len(verdicts) != reviewer_count or not all(_verdict_clean(v) for v in verdicts):
        raise ValueError(
            f"cannot publish artefato {slug!r}: proof lacks {reviewer_count} passing "
            "reviewer verdicts with no strikes (#2/#9)")
    identities = {v.get("reviewer") for v in verdicts}
    if not {FEYNMAN_REVIEWER_ID, REGULAR_REVIEWER_ID} <= identities:
        raise ValueError(
            f"cannot publish artefato {slug!r}: proof lacks both canonical reviewer "
            "identities — built from fake/injected reviewers (#3)")


def run_close(artefato, produce_fn, reviewers=(feynman_review, regular_review),
              complete_fn=None, publish_fn=None, improve_fn=None, improve_rounds=None):
    """The ONE enforced close path (#2): run the genus gate, then BOTH blind review gates,
    bounded; ONLY on pass mint the bound proof and call `publish_fn(artefato, proof)` to
    publish. This is the only way to publish — `publisher.publish` refuses without the bound
    `proof` this mints (it `verify_proof`s the token + digest), so a producer can never reach
    the publisher directly around the gate.

    IMPROVE STAGE (the two improve-gates, one after the other): when `improve_fn` is given,
    BEFORE the gating close run `improve_rounds` (default IMPROVE_ROUNDS=2) UNCONDITIONAL passes
    of review→improve. Each pass runs BOTH reviewers purely to PRODUCE FEEDBACK — the
    per-dimension `rationales` and the `strikes` (the LLM 0-5 score is too noisy to gate on, so
    the feedback is the signal) — and hands that feedback to `improve_fn(artefato, feedback)`,
    which REVISES the artefato (it improves the existing draft, it does not re-produce from
    scratch). These passes NEVER mint or publish; they only refine. The gating close below then
    runs on the REFINED artefato, so the minted proof binds to the final improved text — the
    reviewers' pass is always of exactly what publishes. With no `improve_fn` the stage is
    skipped and behaviour is unchanged.

    Genus runs FIRST, every iteration (Codex re-review #2): `check_genus(artefato)` violations
    are a BLOCKING strike that bounces through `produce_fn` BEFORE any reviewer runs or any
    proof is minted — so a genus-invalid artefato can NEVER yield a pass proof, even with a
    custom/omitted publish_fn. The reviewer gates run only on a genus-conformant artefato.

    The gate is bounded: any genus violation / reviewer strike/fail BOUNCES — `produce_fn()`
    re-produces the artefato and the gate re-runs — up to `BOUNCE_MAX` times, then HARD-FAILS;
    it never loops unbounded (that would resurrect ADR-0003's retry envelope).

    `produce_fn`, `reviewers`, the reviewers' `complete_fn`, and `publish_fn` are injectable
    so the gate runs offline in tests; real runs pass the make_client-backed completer and a
    publisher.publish-backed publish_fn.

    Returns the minted bound proof {pass: True, verdicts, digest, token} when both reviewers
    pass (after publishing if a publish_fn was given), else {pass: False, artefato, verdicts}
    after the bound is exhausted (publish_fn is NEVER called on a failing gate). On a genus
    bounce the returned failure carries `genus_violations`."""
    # IMPROVE STAGE — the two improve-gates, run in sequence (no minting/publishing here). Each
    # gate reviews the draft purely for FEEDBACK (rationales + strikes) and hands it to
    # improve_fn, which returns a revised draft. The gating close (below) seals the proof on the
    # final, twice-improved artefato. A reviewer that raises degrades to a feedback strike here —
    # the refine never crashes (the gating close enforces correctness afterwards).
    if improve_fn is not None:
        rounds = IMPROVE_ROUNDS if improve_rounds is None else improve_rounds
        for _ in range(rounds):
            feedback = []
            # the genus violations (incl. the rich-rite floor strikes) are FED to improve_fn too
            # (Codex P2, #30): the floor forces depth only if the named gap reaches the reviser —
            # a synthetic verdict carries them alongside the reviewers' feedback.
            gv = check_genus(artefato)
            if gv:
                feedback.append(_genus_feedback(gv))
            for r in reviewers:
                try:
                    v = r(artefato, complete_fn)
                except Exception as e:  # noqa: BLE001 — feedback only; never crash the refine
                    v = {"pass": False, "scores": {}, "rationales": {},
                         "strikes": [f"reviewer raised: {type(e).__name__}: {e}"], "overall": 0.0}
                feedback.append(v)
            artefato = improve_fn(artefato, feedback)

    bounces = 0
    while True:
        violations = check_genus(artefato)
        if violations:
            if bounces >= BOUNCE_MAX:
                return {"pass": False, "artefato": artefato, "verdicts": [],
                        "genus_violations": violations}
            bounces += 1
            # re-produce from the NAMED gap: when improve_fn is wired, hand it the genus
            # violations so the draft is enriched (the floor forces depth); else the unchanged
            # static produce_fn bounce (Codex P2, #30).
            if improve_fn is not None:
                artefato = improve_fn(artefato, [_genus_feedback(violations)])
            else:
                artefato = produce_fn()
            continue
        verdicts = []
        for r in reviewers:
            # Defense in depth (Codex round-8 [medium]): ANY exception from a reviewer or its
            # parser (`_parse_verdict`) becomes a FAILING verdict — a controlled bounce, never
            # an unhandled close crash. _parse_verdict already fails closed on every known
            # degraded shape; this wrap also catches an unforeseen shape or a reviewer callable
            # that itself raises, so schema drift can only ever cost a bounded failing verdict.
            try:
                v = r(artefato, complete_fn)
            except Exception as e:  # noqa: BLE001 — bound the failure, never crash the close
                v = {"pass": False, "scores": {},
                     "strikes": [f"reviewer raised: {type(e).__name__}: {e}"], "overall": 0.0}
            # stamp the canonical reviewer identity (#3) — only the canonical reviewers carry
            # an `.identity`; an injected fake reviewer leaves the verdict unstamped, so the
            # minted proof will fail verify_proof's identity check.
            identity = getattr(r, "identity", None)
            if identity is not None:
                v = {**v, "reviewer": identity}
            verdicts.append(v)
        if all(_verdict_clean(v) for v in verdicts):
            proof = _mint_proof(
                verdicts,
                slug=artefato.get("slug"), spec=artefato.get("content"),
                intent=artefato.get("intent"), cites=artefato.get("cites"),
                proposes=artefato.get("proposes"),
                distills=artefato.get("distills"), skill=artefato.get("skill"))
            if publish_fn is not None:
                publish_fn(artefato, proof)
            return proof
        if bounces >= BOUNCE_MAX:
            return {"pass": False, "artefato": artefato, "verdicts": verdicts}
        bounces += 1
        artefato = produce_fn()


def run_loop2(artefato, critic_fn, serendipity_fn, reopen_fn):
    """The producer-loop brake. The critic (converge) emits a verdict with a `ship`
    boolean; serendipity (diverge) is ADVISORY — it may request a reopen, which
    triggers `reopen_fn()` (re-gather loop-1) AT MOST `LOOP2_MAX_REOPENS` times. The
    loop STOPS the moment `critic.ship` is True OR the reopens are exhausted.

    Serendipity NEVER gates: a critic that ships ends the loop immediately even while
    serendipity still wants to diverge — it can never hold the loop hostage.

    Returns the final critic verdict (carrying `ship`)."""
    reopens = 0
    while True:
        verdict = critic_fn(artefato)
        if verdict.get("ship"):
            return verdict
        if reopens >= LOOP2_MAX_REOPENS:
            return verdict
        advice = serendipity_fn(artefato)
        if not advice.get("reopen"):
            return verdict
        reopens += 1
        artefato = reopen_fn()
