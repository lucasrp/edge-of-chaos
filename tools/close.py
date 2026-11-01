"""The Close protocol — the shared dispatch exit (ADR-0012/0013).

Every producer funnels through the close: the genus conformance contract (S6, here),
then ONE advisory reviewer (S7, ADR-0025) whose furos the producer fixes or keeps as
"Notas do revisor" — the review never blocks; only the mechanical genus bounces (bounded). This module is the
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
import re
import secrets

import _envconf  # loads the repo-root .env and provides typed EDGE_* reads
import _llm      # issue #55: LLMTransportError — infra do completer, nunca veredito de conteúdo
import runstore  # internal-evidence (R8) verification: runstore.attest_value
import visual_grounding  # S7/R2: per-visual unforgeable grounding attestation (verify is blind-safe)
# sanitize authored declarations (lineage, bears_on, para) before the proof digest binds them
from lineage import (normalize_bears_on, normalize_experiment_curation, normalize_lineage,
                     normalize_para, normalize_reports_on)

from render import BLOCK_SCHEMAS, _BLOCK_TYPE_ALIASES
import render
import visible  # Modulo 5 (Publicacao) visible-text adapter — reader-visible HTML/CSS/glyph machinery
import producer_descriptor
import blocks as block_validation
import yaml_rite

# ---------------------------------------------------------------------------
# Genus contract constants — the pinned field shapes + the visual palette
# ---------------------------------------------------------------------------

# The visual element types from the render palette (tools/render.py). A `table` is
# tabular data, NOT itself a visual — the genus owes a visual *alongside* dense tables.
# `comparison-table` is treated as visual (it is a styled side-by-side, not a raw grid).
VISUAL_BLOCK_TYPES = frozenset({
    "raw-html", "svg", "html", "custom-html",   # chart / svg escape hatch
    "ascii-diagram", "diagram", "chart",
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

# D5 — the numeric-density quant-prose trigger. Prose carrying >= this many DISTINCT numeric
# magnitudes owes a visual just as a dense table does (the conductor's failure mode: quantitative
# PROSE, no tables). Numeric-density ONLY — years and version tokens are excluded so dates/versions
# never falsely trip; there is NO comparison-word branch (comparison structure is the writer's job).
QUANT_PROSE_TOKENS = 3
# A numeric magnitude: a number with an optional unit suffix. The leading \b and the requirement of
# a digit-led token keep it from matching mid-word.
_MAGNITUDE_RE = re.compile(
    r"\b\d[\d.,]*\s?(?:%|x|×|k|m|bn|ms|s|kb|mb|gb)?\b", re.IGNORECASE)
# Excluded magnitudes: 4-digit years and TRUE version tokens — v-prefixed (v1.9 / v1.9.0) or
# 3+-component semver (1.9.0). A bare decimal like 0.91 or 1.5% is a MAGNITUDE, not a version.
_YEAR_RE = re.compile(r"\b(?:19\d\d|20\d\d)\b")
_VERSION_RE = re.compile(r"\bv\d+(?:\.\d+)+\b|\b\d+\.\d+\.\d+\b", re.IGNORECASE)
# Full dates — stripped WHOLE so their day/month components (01, 15) never count as magnitudes.
_DATE_RE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b|\b\d{1,2}/\d{1,2}/\d{2,4}\b|\b\d{4}-\d{2}\b")

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
# `subsection` is EXCLUDED (Codex P2): it renders only an <h3> heading, not developed prose — a
# map/plan using subsection headings around diagrams must NOT be falsely pulled over the threshold.
PROSE_BLOCK_TYPES = frozenset({"paragraph", "callout"})
# The structural trigger threshold — NOT a word count. Below it, the artefato is too terse to
# be a developed synthesis and owes none of the moves (content-relative, like visual-coverage).
RICH_RITE_PROSE_THRESHOLD = 3

# Palette blocks that, by their mere presence, satisfy a cognitive move (the move is present
# ANYWHERE — never a named section). Mirrors how a metrics-grid satisfies visual-coverage.
DERIVATION_BLOCK_TYPES = frozenset({"derivation"})
BOUNDARY_BLOCK_TYPES = frozenset({"gap-marker", "gap-table", "gap-resolution"})

# The SUBSTANTIVE content fields per palette block — the move-bearing payload, NOT a heading/label
# (Codex P2): a derivation `title` or a gap-table `headers` is a placeholder, not the actual
# reasoning/gap. A block satisfies its move only if at least one of THESE fields is non-blank.
SUBSTANTIVE_BLOCK_FIELDS = {
    "derivation": ("text", "bullets", "steps", "conclusion", "code"),
    "gap-marker": ("text", "description", "label"),
    "gap-table": ("gaps", "rows"),
    "gap-resolution": ("text", "answer", "resolution", "gap", "question"),
}

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

def check_genus(artefato: dict, attest=None) -> list[str]:
    """Return the genus violations of a finished artefato ([] iff conformant).

    Checks the OUTPUT contract only — never a named/ordered section:
      - every cite carries a `ref` and a `snippet` (OR is a verified internal-evidence cite, R8/S3);
      - every proposes item carries a `body`;
      - `intent` (the kernel) is present and non-empty;
      - visual-coverage: if the content has quantitative/multi-value material but no
        visual palette element, "visual-coverage" is flagged (content-relative).
    `attest` (the R8 internal-evidence verifier) is injectable for offline tests; default = runstore.
    """
    violations = []
    _claim_spans_set = _claim_spans(artefato.get("content"))
    violations += _check_cites(artefato.get("cites", []), attest=attest, claim_spans=_claim_spans_set)
    violations += _check_proposes(artefato.get("proposes", []))
    violations += _check_intent(artefato.get("intent"))
    violations += _check_block_schemas(artefato.get("content", {}))
    violations += _check_visual_coverage(artefato.get("content", {}))
    violations += _check_evidence_anchors(artefato.get("content", {}))
    violations += _check_rich_rite(artefato)
    r0_violations = _check_storytelling_floor(artefato.get("content", {}))  # R0 (S2): explain, don't label
    r0_violations += _check_structured_visual_values(artefato.get("content", {}))  # R0-for-values (S7): no
    #   number hides ONLY in a structured visual — same family as R0, so it likewise suppresses the floor.
    violations += r0_violations
    violations += _check_visual_grounding(artefato.get("content", {}))    # R2/R3 (S7): grounding boundary
    # The shared producer protocol's PRESENTATION floor (R1/S6) — the producer's declared visual
    # obligations. SUBORDINATE to R0 (gate v-reframe F2): the visual floor does NOT fire as a failure while
    # R0 fails — don't fight render-vs-degradation on an artefato that has already lost its storytelling
    # (visual is additive to R0, never a substitute). It re-surfaces once R0 is clean.
    if not r0_violations:
        violations += producer_descriptor.presentation_violations(artefato)
    return violations


# the grounding-claim corpus is PROSE ONLY (Codex S3 #7): a numeric claim must be EXPLAINED in flowing
# prose, never merely shown in a table cell / heading / chart label / list / visual block (R0:
# explain-not-label — the storytelling floor this whole effort exists to hold). It uses the SAME canonical
# prose predicate as rich-rite (`PROSE_BLOCK_TYPES` = paragraph + callout, both reader-visible prose), so
# the internal-evidence corpus and rich-rite's prose definition can never disagree (Codex S3 #7 callout).


def _prose_blocks(content):
    """Yield each PROSE block at a REAL render slot. Mirrors render topology EXACTLY via `_iter_blocks`
    (`sections[].blocks` / `additional_sections[].blocks` — the only slots `render_section` actually
    renders), keeping a block ONLY when its canonical type is in the shared `PROSE_BLOCK_TYPES`. It does
    NOT recurse into a block's payload fields, so a paragraph-shaped dict buried in a non-prose block's
    metadata — which the real page never renders — cannot sneak into the corpus (Codex S3 #7
    nested-metadata). The corpus thus equals what the reader actually sees (ADR-0013)."""
    if not isinstance(content, dict):
        return
    for block in _iter_blocks(content):
        # _iter_blocks yields only REAL block slots, so canonical_block speaks for the renderer: a dict
        # with no `type` is an IMPLICIT paragraph (render_block defaults to paragraph) and IS reader-visible
        # prose, so it must be in the corpus too (Codex S3 #7 implicit-paragraph); a non-string type
        # canonicalizes to None and is safely excluded.
        if isinstance(block, dict) and render.canonical_block(block)[0] in PROSE_BLOCK_TYPES:
            yield block


# S7 (R2) — the GROUNDING BOUNDARY for DRAWN visuals. A drawn visual carries free-form data/relations
# (chart data, diagram nodes+edges) that go through the `add_visuals` grounding seam and must each trace to
# an evidence span. GROUNDABLE = `chart`/`diagram` (the renderable recipes whose data is structurally
# attributable). Every other authored-visual path — `raw-html`/`svg`/`html`/`custom-html` (too free-form)
# AND `ascii-diagram` (operator decision: free-form ascii relations can't be soundly grounded and add
# nothing over the renderable recipes) — is UNGROUNDABLE and rejected.
# R2-structured — STRUCTURED data visuals (metrics-grid / comparison / comparison-table) are not DRAWN, so
# they don't go through this attestation seam; their soundness is split:
#   • CLOSED here (the silent-in-a-grid hole codex flagged): `_check_structured_visual_values` (R0-for-values)
#     forbids any numeric magnitude that lives ONLY inside such a block and never appears in the prose. The
#     number is forced into the reader-visible corpus, where the BLIND reviewer, the cite layer, and R8 all
#     reach it — so it can no longer hide where R0 (labels) and R8 (prose-only) used to miss it.
#   • OPEN follow-on (documented, parallel to R8-prov): per-datum PROVENANCE grounding of a structured value
#     to a specific evidence span. Once forced into prose the value is reviewable, but it isn't HMAC-bound to
#     a cite the way a drawn chart's data is. Closing that soundly needs the conductor's structured-visual
#     grounding seam + the richer explorer-evidence pipeline (P1); token-matching authored values against
#     paraphrased cite snippets is too fragile to be the mechanism.
# The DRAWN-visual boundary below + R0-for-values together are the sound, shippable part.
_GROUNDABLE_VISUAL_TYPES = frozenset({"chart", "diagram"})
_UNGROUNDABLE_AUTHORED_VISUAL_TYPES = frozenset({"raw-html", "svg", "html", "custom-html", "ascii-diagram"})


def _check_visual_grounding(content) -> list[str]:
    """R2/R3: every reader-visible DRAWN visual is claim-bearing (default-deny). An ungroundable authored
    visual (raw-html/svg/ascii-diagram) is REJECTED. A chart/diagram must carry a valid grounding
    attestation (`visual_grounding.verify`) — a visual drawn directly in the spec (never grounded) has none
    and is rejected here, by the SAME check the publisher runs (blind: verify needs only the secret + the
    block)."""
    violations = []
    for block in _iter_blocks(content if isinstance(content, dict) else {}):
        if not isinstance(block, dict):
            continue
        bt = render.canonical_block(block)[0]
        if bt in _UNGROUNDABLE_AUTHORED_VISUAL_TYPES:
            violations.append(f"visual-grounding:ungroundable-authored-visual:{bt}")
        elif bt in _GROUNDABLE_VISUAL_TYPES and not visual_grounding.verify(block):
            violations.append(f"visual-grounding:ungrounded:{bt}")
    return violations


# structured data visuals whose NUMERIC values must be explained in prose (R0 extended to values — the
# partial, sound close for the R2-structured gap: a number cannot hide ONLY inside a grid/table; it must
# be stated in the explanatory prose, where the reader sees it and the cite / R8 / reviewer layer can act).
_STRUCTURED_DATA_VISUAL_TYPES = frozenset({"metrics-grid", "comparison", "comparison-table"})
# R0-for-values is a COMPLETENESS argument, not a leaky type-allowlist (Codex S7 re-gate #3/#4/#5/#6): EVERY
# reader-visible numeric magnitude falls into exactly one bucket, and none can hide unexplained —
#   1. DATA-CELL block (_DATA_CELL_TYPES): a metrics-grid / comparison / table / risk-table. Every magnitude
#      in a reader-visible field — value, cell, row, AND visible label/title/badge/header (re-gate #4: a
#      number in a visible label of a data block is a data claim, not free chrome) — MUST appear in the
#      explanatory corpus. Only NON-visible structural keys and sentence subfields are exempt on this side.
#   2. EXPLANATORY TEXT -> the CORPUS, harvested from RENDER-TRUTH (the actual reader-visible text the
#      renderer emits — re-gate #6): executive_summary + every non-data, non-code, non-grounded block's
#      rendered text (callout, derivation, gap-marker, card, list, next-steps, concept, quote, paragraph …
#      ALL count) + data blocks' rendered sentence numbers (risk/mitigation/note) MINUS their data values.
#      Render-truth means UNRENDERED metadata can never launder a value, and no field skip-list can
#      mis-classify a visible field. A number in readable text is the reader's/BLIND reviewer's to judge
#      (ADR-0013: the structural floor guards STRUCTURE; the reviewer judges adequacy/preservation).
#   3. CODE (_CODE_BLOCK_TYPES + the code body): code literals / line numbers are not claimed data — exempt
#      FIELD-specifically (the code body is blanked before rendering; the block's visible label/header still
#      flows into the corpus), per Codex's guidance that the exemption be the code field, not the block type.
#   4. DRAWN visual data (chart/diagram) + BANNED authored visuals (raw-html/svg/ascii): handled by the
#      grounding seam (chart/diagram bound to evidence by HMAC; the rest rejected) — excluded from BOTH the
#      value check and the corpus harvest so their data never leaks in as "explanation".
_DATA_CELL_TYPES = _STRUCTURED_DATA_VISUAL_TYPES | DATA_TABLE_TYPES | frozenset({"risk-table"})
_CODE_BLOCK_TYPES = frozenset({"code-block", "diff-block", "template-block"})
# the CODE-content fields of a code block (canonical `content` = the code/template; diff `lines`) — blanked
# before rendering for the corpus so code literals stay exempt while the visible label/title/header still count.
_CODE_CONTENT_KEYS = frozenset({"content", "code", "lines", "template", "diff", "source", "snippet"})
# truly NON-visible structural / class / flag keys of a DATA block — each AUDITED against render.py to emit
# NO reader-visible text (badge_class/badge_variant/card_class/style are CSS; variant/layout/direction are
# structural hints; ordered is a list flag; highlight_rows is row indices). A number under one of these is
# never reader-visible, so the VALUE walk skips it. (The corpus side is render-truth, so it needs no such
# skip-list at all.)
_NONVISIBLE_KEYS = frozenset({
    "type", "variant", "layout", "direction", "badge_class", "badge_variant", "card_class",
    "ordered", "style", "highlight_rows",
})
# sentence subfields that can sit INSIDE a data block (risk-table risk/mitigation, a table note) — readable
# prose, so skipped on the value side (their rendered numbers reach the corpus via render-truth instead).
_SENTENCE_SUBFIELDS = frozenset({"note", "risk", "mitigation", "description", "caption", "summary", "detail"})
# value walk (data cells): skip the non-visible keys + sentence subfields. What remains — values/cells/rows
# AND reader-visible titles/labels/badges/headers/name/id — is data that owes a corpus echo.
_VALUE_WALK_SKIP = _NONVISIBLE_KEYS | _SENTENCE_SUBFIELDS


# A numeric MAGNITUDE grammar for the R0-for-values check — DISTINCT from `_NUM_TOKEN` (the S3 prose-claim
# grammar, deliberately strict to avoid fragment-grounding and left untouched). This one is GENEROUS by
# design: the visual-extraction side must recognize every form a renderer can DISPLAY, and the prose side
# must recognize the same forms so a legitimately-stated value matches. Covers (Codex S7 re-gate) plain,
# negative, PLUS-signed, thousands-grouped, decimal, LEADING-DECIMAL (.75), and EXPONENT (1e3) numbers.
# Left boundary `(?<![\w.])` blocks starting mid-token (so `v8`/`COVID` digits glued to letters before the
# number are excluded and `85` never starts inside `185`); the match is GREEDY (consumes the whole int+frac
# +exp) so substrings can't be picked, and there is intentionally NO right boundary — a trailing unit (`3x`,
# `99ms`), ordinal (`5th`), or sentence period (`0.9.`) does not suppress the magnitude. Comparison is
# numeric (float), so `+99`/`99`/`99.0` all equal and a value stated with any of these forms matches.
_MAGNITUDE_RE = re.compile(
    r"(?<![\w.])[+-]?(?:(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?|\.\d+)(?:[eE][+-]?\d+)?")


def _magnitudes(text) -> set:
    """Every numeric magnitude (as a float) appearing in `text`, per the generous _MAGNITUDE_RE grammar."""
    out = set()
    if not isinstance(text, str):
        return out
    for tok in _MAGNITUDE_RE.findall(text):
        try:
            out.add(float(tok.replace(",", "")))
        except ValueError:
            pass
    return out


def _collect_magnitudes(v, out, skip_keys):
    """Recursively gather every numeric magnitude in `v` into `out` (a set of floats), descending into lists
    and dicts and skipping the dict keys in `skip_keys`. Direct ints/floats and magnitudes inside string
    values (per the generous _MAGNITUDE_RE: '42%'→42.0, '+99'→99.0, '.75'→0.75, '1e3'→1000.0) both count."""
    if isinstance(v, bool):
        return
    if isinstance(v, (int, float)):
        out.add(float(v))
    elif isinstance(v, str):
        out.update(_magnitudes(v))
    elif isinstance(v, list):
        for it in v:
            _collect_magnitudes(it, out, skip_keys)
    elif isinstance(v, dict):
        for k, val in v.items():
            if k not in skip_keys:
                _collect_magnitudes(val, out, skip_keys)


def _structured_visual_numbers(block) -> set:
    """Every numeric magnitude a data-cell block displays in its DATA payload — non-visible structural keys
    and sentence subfields are skipped (their numbers are CSS/prose, not bare data cells), so what remains is
    the genuine value/cell/row/label/title content that could otherwise hide a fabricated number."""
    nums = set()
    _collect_magnitudes(block, nums, _VALUE_WALK_SKIP)
    return nums


def _check_structured_visual_values(content) -> list[str]:
    """R0-for-values (S7 close of R2-structured, hardened): a numeric magnitude shown in a BARE DATA CELL
    (metrics-grid/comparison/comparison-table/table-and-aliases/risk-table — including the top-level
    executive `metrics` dashboard) must ALSO appear in the reader-visible EXPLANATORY corpus — paragraphs,
    executive_summary, and the readable sentences of narrative/labeled blocks (cards, lists, next-steps,
    concepts, gaps, risk/mitigation lines). A number can never live ONLY inside a bare data cell. Code
    literals are exempt (the code field, not the block type); drawn chart/diagram data is bound to evidence
    by the stronger HMAC grounding seam. Full per-datum PROVENANCE grounding of structured values remains the
    documented R2-structured follow-on."""
    if not isinstance(content, dict):
        return []
    blocks = list(_iter_blocks(content))
    # the top-level executive `metrics` grid renders as a metrics-grid but is NOT block-shaped (so it is
    # absent from _iter_blocks) — fold it in so a number can't hide in the executive dashboard either.
    top_metrics = content.get("metrics")
    if isinstance(top_metrics, list) and top_metrics:
        blocks.append({"type": "metrics-grid", "items": top_metrics})

    # The EXPLANATORY corpus: every magnitude that counts as explained, harvested from RENDER-TRUTH — the
    # actual reader-visible text the renderer emits (so UNRENDERED metadata can never launder a value, and a
    # field skip-list can never mis-classify a visible field — Codex S7 re-gate #6). executive_summary (not
    # block-shaped) is plain producer strings. Then, per block:
    #   • grounded (chart/diagram) / banned authored visuals → skipped (data handled by the grounding seam);
    #   • code blocks → render with the code BODY blanked, so the visible label/title/header counts but code
    #     literals stay exempt (field-specific);
    #   • data-cell blocks → their rendered sentence numbers count (risk/mitigation/note), but the data
    #     VALUES are SUBTRACTED so a cell can never self-satisfy;
    #   • every other block → its full rendered visible text.
    corpus = set()

    def _add_rendered_text(s):
        # RENDER-TRUTH for a producer string rendered as inline text (exec-summary item / heading): keep only
        # reader-visible text, so a number in a Markdown link's URL (href, never shown) cannot launder a value.
        if isinstance(s, str) and s.strip():
            try:
                corpus.update(_magnitudes(visible.visible_text(s, trusted=True)))
            except Exception:  # noqa: BLE001 — malformed item → contributes nothing
                pass

    summary = content.get("executive_summary")
    if isinstance(summary, list):
        for item in summary:
            _add_rendered_text(item)
    # rendered HEADINGS are reader-visible too (Codex re-gate #8): the executive_summary title and each
    # section/additional_section title render as h2/heading text → harvest them into the corpus.
    _add_rendered_text(content.get("executive_summary_title"))
    for _key in ("sections", "additional_sections"):
        for _sec in content.get(_key) or []:
            if isinstance(_sec, dict):
                _add_rendered_text(_sec.get("title"))
    for block in blocks:
        if not isinstance(block, dict):
            continue
        btype, norm = render.canonical_block(block)
        if btype in _GROUNDABLE_VISUAL_TYPES or btype in _UNGROUNDABLE_AUTHORED_VISUAL_TYPES:
            continue
        if btype in _CODE_BLOCK_TYPES:
            blanked = {**norm, **{k: "" for k in _CODE_CONTENT_KEYS if k in norm}}
            corpus.update(_block_corpus_magnitudes(blanked))
        elif btype in _DATA_CELL_TYPES:
            corpus.update(_block_corpus_magnitudes(block) - _structured_visual_numbers(norm))
        else:
            corpus.update(_block_corpus_magnitudes(block))

    # The value check: every bare DATA-cell magnitude must appear in that corpus.
    violations = []
    for block in blocks:
        if not isinstance(block, dict):
            continue
        btype, norm = render.canonical_block(block)
        if btype not in _DATA_CELL_TYPES:
            continue
        for val in sorted(_structured_visual_numbers(norm)):
            if val not in corpus:
                violations.append(f"r0:visual-value-not-in-prose:{val}")
    return violations


def _grounding_evidence(artefato):
    """The evidence a visual must resolve against at the close seam: the artefato's CITE snippets (the
    reader-visible evidence spans) PLUS any `findings` it carries (the conductor path grounds against
    findings). Both are present in the artefato at close, so a re-ground at verify time is reproducible."""
    cites = artefato.get("cites") or []
    snippets = [c.get("snippet", "") for c in cites
                if isinstance(c, dict) and isinstance(c.get("snippet"), str)]
    findings = artefato.get("findings") if isinstance(artefato.get("findings"), list) else []
    provenance = [{"source": s} for s in snippets if s.strip()]
    return {"text": " ".join(s for s in snippets if s.strip()), "findings": findings}, provenance


def ground_visuals(artefato):
    """S7 (R2) — the GROUNDING STEP (close-side, has the evidence) AND the anti-replay guard (Codex S7 #1).
    For each chart/diagram in the content it STRIPS any incoming `_grounding` (never trusts a token the
    producer/a transplant carried in) and RE-GROUNDS from scratch against the artefato's OWN evidence
    (`_grounding_evidence`); only a visual whose data is `visuals.attributable` NOW gets a fresh
    attestation. A replayed/transplanted visual whose data the current evidence does not support is left
    unsigned → `_check_visual_grounding` flags it. MUTATES blocks in place, never raises. Lazy-imports
    visuals (cycle break)."""
    if not isinstance(artefato, dict):
        return artefato
    content = artefato.get("content")
    if not isinstance(content, dict):
        return artefato
    evidence, provenance = _grounding_evidence(artefato)
    try:
        import visuals as _visuals  # noqa: PLC0415 — lazy: visuals imports close
    except Exception:  # noqa: BLE001
        return artefato
    for section in _sections(content):
        blocks = section.get("blocks")
        if not isinstance(blocks, list):
            continue
        for i, b in enumerate(blocks):
            if not isinstance(b, dict):
                continue
            if render.canonical_block(b)[0] not in _GROUNDABLE_VISUAL_TYPES:
                continue
            stripped = {k: v for k, v in b.items() if k != visual_grounding.ATTEST_FIELD}  # never trust incoming
            try:
                ok, _reason = _visuals.attributable(stripped, provenance, evidence)
            except Exception:  # noqa: BLE001 — a grounding failure leaves the visual unsigned, never crashes
                ok = False
            blocks[i] = visual_grounding.sign(stripped) if ok else stripped
    return artefato


def _block_corpus_magnitudes(block) -> set:
    """Magnitudes in the ACTUAL reader-visible text the renderer emits for `block` (RENDER-TRUTH): render it,
    then keep only the text a reader sees (`visible.visible_text(trusted=True)` credits benign renderer styling, drops real
    hiding). This is what makes the corpus exhaustive WITHOUT a field skip-list — unrendered metadata never
    appears in the renderer's output, so it cannot launder a value (Codex S7 re-gate #6). Fail-closed to
    empty on any render error (the block then contributes nothing — the safe, over-strict direction)."""
    try:
        return _magnitudes(visible.visible_text(block, trusted=True))
    except Exception:  # noqa: BLE001 — malformed block / renderer error → contributes nothing
        return set()


def _visible_prose_units(content) -> list:
    """The reader-visible text of EACH prose unit, SEPARATELY (so spans never fuse across units): every
    paragraph block at a real render slot, plus every `executive_summary` item — render renders the summary
    as prose and rich-rite already counts it as prose (Codex S3 #7 exec-summary). Each unit is rendered on
    its own and passed through the hidden/styled-dropping parser. Fail-closed to [] on any error."""
    units = []
    if not isinstance(content, dict):
        return units
    try:
        for blk in _prose_blocks(content):
            units.append(visible.visible_text(blk, trusted=False))
        summary = content.get("executive_summary")
        if isinstance(summary, list):
            for item in summary:
                if isinstance(item, str) and item.strip():
                    units.append(visible.visible_text(item, trusted=False))
    except Exception:  # noqa: BLE001 — malformed spec / renderer → no prose, fail closed
        return []
    return [u for u in units if u and u.strip()]


def _norm_span(s: str) -> str:
    """Normalize a prose span for boundary-aligned comparison: collapse internal whitespace and strip
    surrounding whitespace + trailing terminal punctuation (so a unit ending `…set.` matches a claim
    written `…set`)."""
    return " ".join(s.split()).strip().rstrip(".!?").strip()


def _claim_spans(content) -> set:
    """The set of normalized full-prose-UNIT spans a grounding claim may equal — one entry per whole prose
    unit (paragraph / executive_summary item). A claim must equal a WHOLE unit, never a substring or a
    sub-sentence: this closes the fragment-selection attack (`the run did NOT score AUC 85.0` can't be
    grounded by `score AUC 85.0`) WITHOUT a sentence tokenizer — regex/abbreviation sentence-splitting is
    itself an unbounded fragment source (`e.g.` / `i.e.` / `No.` / decimals / ellipses fabricate false
    boundaries, Codex S3 #7), so the decisive rule is whole-unit equality: a grounded number must be
    EXPLAINED in its own prose unit. Boundary == the reader-visible render (ADR-0013: corpus == output)."""
    return {_norm_span(unit) for unit in _visible_prose_units(content) if _norm_span(unit)}


# a standalone numeric token: a number not glued to a word char, dot, or comma on either side. The
# integer part is EITHER a thousands-grouped run (\d{1,3}(,\d{3})+) OR a plain ungrouped run (\d+) — so
# ungrouped values >= 1000 (1000 / 12345 / -5000) are recognized (Codex S3 #7 numeric), while 85 still
# does NOT match inside 185.0 / 85th and a grouped number is ONE token so 85 does NOT match 1,085.0 or
# 85,000 (Codex S3 #2/#3). The grouped alternative is tried first so a comma number is never split. The
# trailing `(?!,\d)` rejects a plain run that is actually the PREFIX of a (malformed) comma number —
# `1000,000`/`1,0000`/`12,3456` yield NO token, so a value can't bind to a prefix of a different run
# (Codex S3 #7), while a sentence comma (`85, then`) still allows the token.
_NUM_TOKEN = re.compile(r"(?<![\w.,])-?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?(?![\w.])(?!,\d)")


def _claim_states_value(claim, value) -> bool:
    """True iff `claim` contains a STANDALONE numeric token (thousands-commas allowed) NUMERICALLY equal
    to `value` — parsed and compared as floats, never substring-matched."""
    try:
        target = float(value)
    except (TypeError, ValueError):
        return False
    for tok in _NUM_TOKEN.findall(claim):
        try:
            if float(tok.replace(",", "")) == target:
                return True
        except ValueError:
            continue
    return False


def _check_cites(cites: list, attest=None, claim_spans=None) -> list[str]:
    # `attest` (R8 internal-evidence verifier) is injectable so the genus gate runs offline in tests;
    # real runs use runstore.attest_value (deref + value-match against the durable eventlog).
    if attest is None:
        attest = runstore.attest_value
    if claim_spans is None:
        claim_spans = set()
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
        # INTERNAL-EVIDENCE cite (R8/S3): a numeric internal claim grounded by a content-addressed
        # runstore ref instead of an external snippet. It MUST be kind 'atividade' (internal) so it can
        # NEVER count toward rich-rite:external-frame, and its {address, metric, value} must verify via
        # `attest` (which fails closed on every malformed/forged/tampered input — slice S3a). Verified →
        # the claim is grounded, no snippet owed; not verifiable → a violation.
        ie = cite.get("internal_evidence")
        if ie is not None:
            if cite.get("kind") != "atividade":
                violations.append(f"internal-evidence cite must be kind 'atividade' (internal): {label}")
                continue
            if not isinstance(ie, dict):
                violations.append(f"internal_evidence must be a dict: {label}")
                continue
            address = ie.get("address")
            value = ie.get("value")
            # the public `ref` MUST be the canonical runstore handle for the SAME address that is
            # verified — else the displayed/projected citation dereferences a different run than the one
            # attested (Codex S3 #5). Binds ref ↔ attested address.
            if cite.get("ref") != f"runstore:{address}":
                violations.append(
                    f"internal-evidence ref must be 'runstore:<address>' matching the attested address: {label}")
                continue
            ok, reason = attest(address, ie.get("metric"), value)
            if not ok:
                violations.append(f"internal-evidence not verifiable ({reason}): {label}")
                continue
            # BIND to the content (Codex S3 #1/#7): the cite names the exact `claim` it grounds, that claim
            # must equal a WHOLE reader-visible prose UNIT (a full paragraph / summary item, NOT an
            # arbitrary substring or sub-sentence — so a producer can't cite a fragment of a larger, e.g.
            # negated, unit), AND the attested value must be stated in that claim — so a verified runstore
            # value can't be attached to a divergent, absent, or fragment-selected in-content number.
            claim = ie.get("claim")
            if not (isinstance(claim, str) and claim.strip()):
                violations.append(f"internal-evidence cite missing `claim`: {label}")
                continue
            if _norm_span(claim) not in claim_spans:
                violations.append(f"internal-evidence claim not found in content: {label}")
                continue
            if not _claim_states_value(claim, value):
                violations.append(f"internal-evidence value {value!r} not stated in its claim: {label}")
                continue
            continue   # grounded by the runstore + bound to its in-content claim, no snippet owed
        # a `runstore:` ref is ONLY valid as a verified internal-evidence cite (handled+continued above).
        # Reaching here with one means it was relabeled (e.g. kind 'mundo' with no internal_evidence) to
        # sneak onto the normal external-cite path / external-frame — reject it (Codex S3 #3).
        if isinstance(ref, str) and ref.startswith("runstore:"):
            violations.append(f"runstore ref must be a verified internal-evidence cite (kind atividade): {label}")
            continue
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


def _check_evidence_anchors(content: dict) -> list[str]:
    """Every evidence block must pass anchor integrity (quote_text matches its sha256 anchor) — so a
    block with a mismatched/forged anchor cannot pass genus and render as 'evidence'. Source-corpus
    authenticity needs the corpus (unavailable here); the anchor-integrity floor is always enforceable."""
    violations = []
    for block in _iter_blocks(content):
        raw_type = block.get("type", "paragraph")
        if _BLOCK_TYPE_ALIASES.get(raw_type, raw_type) == "evidence":
            ok, reason = render.verify_evidence(block)  # sources=None => anchor-integrity only
            if not ok:
                violations.append(f"evidence-anchor: {reason}")
    return violations


def _type(block: dict) -> str:
    """The block's CANONICAL type (alias-resolved), defaulting to paragraph."""
    raw = block.get("type", "paragraph") if isinstance(block, dict) else "paragraph"
    return _BLOCK_TYPE_ALIASES.get(raw, raw)


def _visual_substantive(block: dict, block_type: str) -> bool:
    """A block counts as a satisfying visual iff it is a VISUAL_BLOCK_TYPES member AND it renders
    safe + carries a substantive payload (the single rule, via `blocks.normalize_block` — never the
    type-only test). chart/diagram renderability is folded into that predicate."""
    if block_type not in VISUAL_BLOCK_TYPES:
        return False
    return block_validation.normalize_block(block) is not None


def _metrics_substantive(metrics) -> bool:
    """Top-level `content.metrics` is itself a visual; validate it with the SAME metrics-grid item
    rule (>= 1 item with both value+label) so a hollow top-level metrics never clears a gate."""
    return block_validation.metrics_grid_substantive({"items": metrics})


def _numeric_dense(text: str) -> bool:
    """True iff `text` carries >= QUANT_PROSE_TOKENS DISTINCT numeric magnitudes, EXCLUDING 4-digit
    years and version tokens — D5's quant-prose trigger (numeric-density only, no comparison-word
    branch). Distinct so '42% 42% 42%' is one magnitude, not three."""
    if not isinstance(text, str) or not text:
        return False
    # strip full dates, version tokens, and years FIRST so their digits never count as magnitudes.
    scrubbed = _DATE_RE.sub(" ", text)
    scrubbed = _VERSION_RE.sub(" ", scrubbed)
    scrubbed = _YEAR_RE.sub(" ", scrubbed)
    magnitudes = {m.group(0).strip().lower() for m in _MAGNITUDE_RE.finditer(scrubbed)
                  if m.group(0).strip()}
    return len(magnitudes) >= QUANT_PROSE_TOKENS


def _nonvisual_text(block: dict) -> str:
    """The substantive prose text a NON-VISUAL block carries (the `_block_text` idiom — excludes the
    heading/label/header fields), for the numeric-density scan."""
    return _block_text(block)


def _check_visual_coverage(content: dict) -> list[str]:
    """Flag "visual-coverage" iff the content has quantitative/multi-value material
    but no SUBSTANTIVE visual palette element. Content with no quantitative material owes none.
    Traverses the FULL render tree (#7): top-level metrics is itself a visual (validated with the
    metrics-grid item rule); dense tables AND numeric-dense prose (D5) anywhere render touches —
    sections AND additional_sections — count as the quantitative trigger. A visual satisfies the
    owe only if it renders safe AND carries a substantive payload (D6) — a hollow/header-only block
    no longer clears it."""
    has_quantitative = False
    has_visual = _metrics_substantive(content.get("metrics"))  # top-level metrics grid is a visual
    for block in _iter_blocks(content):
        block_type = _type(block)  # canonicalize (graphviz->diagram, kpi-grid->metrics-grid)
        substantive_visual = _visual_substantive(block, block_type)
        if substantive_visual:
            has_visual = True
        if _is_dense_table(block, block_type):
            has_quantitative = True
        # D5: a NON-VISUAL block burying >= QUANT_PROSE_TOKENS magnitudes in its prose is the
        # quantitative trigger too (a real visual is excluded — already credited by substance,
        # so a metrics-grid of the numbers does not self-trip).
        elif not substantive_visual and _numeric_dense(_nonvisual_text(block)):
            has_quantitative = True
    if has_quantitative and not has_visual:
        return ["visual-coverage"]
    return []


def _is_dense_table(block: dict, block_type: str) -> bool:
    if block_type not in DATA_TABLE_TYPES:
        return False
    return len(block.get("rows", [])) >= QUANTITATIVE_ROW_THRESHOLD


def has_substantive_visual(content) -> bool:
    """True iff the content carries a SUBSTANTIVE visual (a top-level metrics grid or a substantive visual
    block) — the `satisfied` signal for adoption telemetry (R6/S10)."""
    content = content or {}
    if not isinstance(content, dict):
        return False
    if _metrics_substantive(content.get("metrics")):
        return True
    return any(isinstance(b, dict) and _visual_substantive(b, _type(b)) for b in _iter_blocks(content))


def content_owes_visual(content) -> bool:
    """True iff the content carries quantitative/multi-value material that OWES a visual — the SAME trigger
    as `_check_visual_coverage` (a dense table or numeric-dense prose anywhere). The content half of the
    R6/S10 `owed` signal (and the R1 owe-detector)."""
    content = content or {}
    if not isinstance(content, dict):
        return False
    # a PRESENT substantive visual (top-level metrics grid OR any substantive visual block) was owed — and
    # it also satisfies the owe; counting it keeps owed/satisfied CONSISTENT (satisfied ⟹ owed), so a
    # metrics-grid-only artefato is never reported satisfied-but-not-owed (Codex S10).
    if has_substantive_visual(content):
        return True
    for block in _iter_blocks(content):
        if not isinstance(block, dict):
            continue
        bt = _type(block)
        if _is_dense_table(block, bt):
            return True
        if not _visual_substantive(block, bt) and _numeric_dense(_nonvisual_text(block)):
            return True
    # top-level `executive_summary` is reader-visible prose too (render renders it; S2/S3 treat it as
    # prose) — a numeric-dense summary OWES a visual (Codex S10): include it so adoption isn't under-counted.
    summary = content.get("executive_summary")
    if isinstance(summary, list):
        for s in summary:
            if isinstance(s, str) and _numeric_dense(s):
                return True
    return False


# Non-substantive block fields EXCLUDED from marker scanning (Codex P2): a heading/label/header is
# not move-bearing prose, so a placeholder like {"type":"derivation","title":"Derivation"} or a
# gap-table headed "Unknown" must NOT clear a move via its label text. `type` is the block tag.
_NON_SUBSTANTIVE_BLOCK_FIELDS = frozenset({"type", "title", "label", "headers", "header"})


def _block_text(block: dict) -> str:
    """The SUBSTANTIVE human-readable text a block carries, for marker scanning — flattens the string
    values render reads (text/bullets/items/...) EXCEPT the non-substantive heading/label fields
    (title/label/headers — Codex P2) and the block's `type` tag. So a heading-only placeholder block
    carries no marker text and cannot self-clear a move via its label. Nested lists/dicts are walked
    one level (bullets, items)."""
    parts = []
    for k, v in block.items():
        if k in _NON_SUBSTANTIVE_BLOCK_FIELDS:
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
      - lineage           — a non-empty `distills` (the threads it builds on), a non-empty authored
                            `lineage` typed edge (a {type,slug} with a non-blank slug), or a marker.

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
        # WORD-BOUNDARY match, not substring (Codex P2): a bare `prior` must not be cleared by
        # `priority`/`prioritize`. Each marker (single word or phrase) matches only on word
        # boundaries; trailing-space markers (e.g. "because ") are stripped and matched the same way.
        return any(re.search(r"\b" + re.escape(m.strip()) + r"\b", text) for m in markers)

    def _field_nonblank(v):
        if isinstance(v, str):
            return bool(v.strip())
        if isinstance(v, list):
            return any(_field_nonblank(x) for x in v)
        if isinstance(v, dict):
            return any(_field_nonblank(x) for x in v.values())
        return False

    def has_filled_block(types):
        # a palette block satisfies a move ONLY if a SUBSTANTIVE field carries real payload (Codex
        # P2): a bare placeholder OR a heading-only block (a derivation with just a `title`, a
        # gap-table with just `headers`) must NOT clear the strike — only the move-bearing fields count.
        for b in blocks:
            bt = _BLOCK_TYPE_ALIASES.get(b.get("type", "paragraph"), b.get("type", "paragraph"))
            if bt not in types:
                continue
            fields = SUBSTANTIVE_BLOCK_FIELDS.get(bt, ())
            if any(_field_nonblank(b.get(f)) for f in fields):
                return True
        return False

    # external-frame requires an OUTSIDE benchmark (Codex P2): an `atividade` (internal provenance)
    # cite is the mentee's own work, not an external frame — only an external (`mundo`) cite or a
    # non-empty bibliography clears it. A cite with no/unknown kind is treated conservatively as
    # external (the reviewer's sourcing strike catches a hallucinated one).
    external_cite = any(
        isinstance(c, dict) and c.get("kind") != "atividade"
        # an internal-evidence / runstore ref is NEVER an external frame, even if mislabeled (Codex S3 #3).
        and not (isinstance(c.get("ref"), str) and c["ref"].startswith("runstore:"))
        and "internal_evidence" not in c
        for c in (artefato.get("cites") or [])
    )
    # a non-empty bibliography clears external-frame whether it is the top-level field OR a
    # rendered `bibliography` block in a section (Codex P2). Only `references` is checked — the ONLY
    # field render_bibliography renders — and only a NON-EMPTY reference counts (Codex P2): a truthy-
    # but-empty payload like [""] renders an empty bibliography and must NOT clear the move.
    def _nonblank(v):
        return isinstance(v, str) and v.strip()
    def _has_real_refs(refs):
        # a reference is real only if it carries NON-BLANK text/url/source (dict) or a non-blank
        # string (Codex P2): a whitespace-only field {"text":"   "} must NOT clear the move.
        return any(
            (_nonblank(r.get("text")) or _nonblank(r.get("url")) or _nonblank(r.get("source")))
            if isinstance(r, dict) else _nonblank(r)
            for r in (refs or [])
        )
    bibliography = _has_real_refs(content.get("bibliography")) or any(
        _BLOCK_TYPE_ALIASES.get(b.get("type", "paragraph"), b.get("type", "paragraph")) == "bibliography"
        and _has_real_refs(b.get("references"))
        for b in blocks
    )
    # a distill clears lineage only if at least one ref is a REAL non-empty thread (Codex P2): a
    # placeholder container like [''] or [{}] must NOT clear it (and would not resolve in projection).
    real_distill = any(
        (_nonblank(d) or (isinstance(d, dict) and any(_nonblank(v) for v in d.values())))
        for d in (artefato.get("distills") or [])
    )
    # Cortex-v1 (slice lineage-rich-rite): the AUTHORED typed lineage (the builds_on/supersedes/
    # contradicts edges the publisher materializes) ALSO clears the move — a developed synthesis
    # that names its prior thread as a typed edge owes no distill. SINGLE SOURCE OF TRUTH: it clears
    # the move iff `normalize_lineage` keeps at least one edge — exactly the set the proof binds, the
    # event persists, and the publisher projects (Codex). So a target-only edge counts (the publisher's
    # primary prior ref), while a malformed item — bad type, blank/non-string slug AND target — does not.
    real_lineage = bool(normalize_lineage(artefato.get("lineage")))

    has_derivation = has_filled_block(DERIVATION_BLOCK_TYPES) or marked(DERIVATION_MARKERS)
    has_boundary = has_filled_block(BOUNDARY_BLOCK_TYPES) or marked(BOUNDARY_MARKERS)
    has_frame = external_cite or bibliography
    has_lineage = real_distill or real_lineage or marked(LINEAGE_MARKERS)

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
# R0 (S2) — the storytelling floor: EXPLAIN, don't label (DOMINANT, content-relative, genus-relative).
# The DETERMINISTIC structural core (ADR-0013: the genus enforces STRUCTURE; the reviewer judges
# whether each explanation is ADEQUATE and whether the artefato's own source claims are PRESERVED — the
# irreducibly semantic R0-I-adequacy / R0-III, raised as furos by the advisory reviewer, ADR-0025). The robust
# deterministic floor is R0-II(d): a SECTION carrying a visual/labeled structure owes >=1 non-visual
# explanatory prose unit IN THAT SECTION — the visual is accompanied by prose, never substitutes it. This
# kills the operator's regression (a report that shows the phase siglas in a visual but never explains
# them). Pure-prose content owes nothing; a non-narrative form (map/plan) still owes prose for ITS visuals.
# ---------------------------------------------------------------------------

# the visual/labeled STRUCTURE types that owe accompanying prose (R0-II(d)): the visual palette + data
# tables + every other rendered NON-PROSE, reader-facing LABEL-bearing structure (list, card/numbered-card,
# risk-table, code-block, template-block — Codex S2 #1/#3). A bare card/list/table of phase siglas names
# without expanding. EXCLUDED are the prose/explanation-by-nature blocks (paragraph, callout, derivation,
# gap-*, glossary, bibliography, subsection heading) — they are the explanation, not labels owing one.
# Keyed by type so R0 is robust to renderer-shape drift; `_type` resolves aliases.
_R0_LABELED_BLOCK_TYPES = VISUAL_BLOCK_TYPES | DATA_TABLE_TYPES | {
    "list", "card", "numbered-card", "risk-table", "code-block", "template-block",
}


def _r0_any_visible_prose(content) -> bool:
    """True iff the artefato carries reader-visible explanatory prose ANYWHERE — a section paragraph/
    callout or an executive_summary item (the latter renders as prose with no author style)."""
    for section in _sections(content):
        for b in (section.get("blocks") or []):
            if isinstance(b, dict) and _type(b) in PROSE_BLOCK_TYPES and visible.is_visible(b):
                return True
    summary = content.get("executive_summary") if isinstance(content, dict) else None
    # an executive_summary item must render a VISIBLE GLYPH too (Codex S2 #3): a markup-only or zero-width
    # item is not reader-visible prose — share the SAME visible-glyph predicate as the blocks.
    return isinstance(summary, list) and any(visible.is_visible(s) for s in summary)


def _sections(content):
    """Yield every real SECTION slot render renders (sections + additional_sections)."""
    if not isinstance(content, dict):
        return
    for key in ("sections", "additional_sections"):
        for section in (content.get(key) or []):
            if isinstance(section, dict):
                yield section


def _check_storytelling_floor(content) -> list[str]:
    """R0-II(d): each section with a visual/labeled STRUCTURE but NO accompanying non-visual prose unit
    (paragraph/callout with real text) is flagged `r0:visual-without-prose` — a visual that names without
    expanding. Keyed on the structure's TYPE (VISUAL_BLOCK_TYPES + data tables), not the substance
    predicate, so it is robust to renderer-shape drift and fires on the operator's actual regression (a
    diagram/list of phase siglas with no prose). Content-relative (a section with no visual owes nothing)
    and genus-relative (any form that uses a visual owes prose for it, but a non-narrative map is never
    failed for lacking a prose ARC — only for a visual with no explanation at all)."""
    violations = []
    for section in _sections(content):
        blocks = [b for b in (section.get("blocks") or []) if isinstance(b, dict)]
        has_visual = any(_type(b) in _R0_LABELED_BLOCK_TYPES for b in blocks)
        # has_prose counts only READER-VISIBLE prose (Codex S2 #1/#2): a paragraph/callout styled invisible
        # does NOT satisfy the owe, but a benignly-styled visible one DOES.
        has_prose = any(_type(b) in PROSE_BLOCK_TYPES and visible.is_visible(b) for b in blocks)
        if has_visual and not has_prose:
            violations.append("r0:visual-without-prose")
    # top-level `content.metrics` is a visual the renderer emits OUTSIDE any section; if it is a
    # substantive metrics grid it still owes reader-visible explanatory prose SOMEWHERE in the artefato
    # (an executive_summary item or a section paragraph/callout), never a bare top-level dashboard.
    if _metrics_substantive(content.get("metrics")) and not _r0_any_visible_prose(content):
        violations.append("r0:visual-without-prose")
    return violations


# ---------------------------------------------------------------------------
# S7 — the review (ADR-0025, owner 2026-11-01: "quero que o revisor só avise dos furos, e o edge
# pode ou corrigir ou só mencionar a nota do revisor, à sua conveniencia"). ONE reviewer, ONE
# pass, NO veto: it points out furos (fato sem fonte, número errado, conclusão que não segue,
# trecho confuso, o que faltou). The producer decides each furo — fix it in `improve_fn`, or keep
# it; every kept furo is mentioned in a short "Notas do revisor" section (content["reviewer_notes"],
# rendered by render.spec_to_html) the close sets BEFORE the mint (so the digest binds it). The review never blocks publication. This replaced the two
# blind gates (feynman + regular, both had to pass), the improve loop, the bounce on strikes, the
# passability veto, the discharge ledger, the cosmetic meta-gate and publish-with-residuals.
# The reviewer stays BLIND (ADR-0013): it sees the final content + cites only.
# ---------------------------------------------------------------------------

import revisor  # noqa: E402 — the shared reviewer/author contract (also used by the rito)

REVIEWER_ID = "revisor"
REVIEW_CONTRACT_VERSION = "revisor@1"
REVIEW_CONTRACT_SHA = hashlib.sha256(
    revisor.REVIEWER_CONTRACT.encode("utf-8")).hexdigest()

_REVIEWER_PREAMBLE = (
    "You are the reviewer of a published Artefato. You see ONLY its final content and its cites "
    "(not the evidence the author read, not the session). A factual claim must be re-sourceable "
    "from its cite; a reasoning step is judged by its internal validity, never struck for lacking "
    "a cite. Respond with ONLY a JSON object: {\"furos\": [str]} — one string per furo, quoting "
    "the passage; [] when there is none."
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


def _build_prompt(artefato: dict) -> str:
    view = _published_view(artefato)
    rendered = yaml_rite.reader_facing_from_artefato(artefato)
    if rendered:
        cites = view.get("cites") or []
        body = rendered
        if cites:
            body = f"{rendered}\n\nCites:\n{json.dumps(cites, ensure_ascii=False)}"
    else:
        body = json.dumps(view, ensure_ascii=False)
    return (f"{_REVIEWER_PREAMBLE}\n\n{revisor.REVIEWER_CONTRACT}\n"
            f"Artefato (content + cites only):\n{body}")


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


def _parse_furos(raw) -> dict:
    """Parse the reviewer's answer into {furos: [str]}. NEVER raises and NEVER blocks: an
    unreadable answer is recorded as `degraded` with no furos — the review is advisory, so a
    broken reviewer costs a note, not the publication."""
    text = str(raw or "").strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        if text.endswith("```"):
            text = text[:-3].strip()
    try:
        result = json.loads(text)
    except (ValueError, TypeError) as e:
        return {"furos": [], "degraded": f"unparseable reviewer answer: {e}"}
    furos = result.get("furos") if isinstance(result, dict) else None
    if not isinstance(furos, list):
        return {"furos": [], "degraded": f"reviewer answer has no furos list: {result!r}"[:300]}
    return {"furos": [str(f).strip() for f in furos if str(f).strip()]}


def _log_infra_error(e):
    """Registra a falha de TRANSPORTE do completer (quota/auth/rede/CLI ausente) como evento
    `llm.infra_error` no log — de onde o dashboard a exibe — antes de o close subir o erro.
    O log lê eventlog.LOG na CHAMADA (testável); um log quebrado nunca mascara a infra em si."""
    try:
        import eventlog
        eventlog.append("llm.infra_error", "close",
                        {"status": e.status, "detail": e.detail}, log=eventlog.LOG)
    except Exception:  # noqa: BLE001 — o registro é best-effort; o raise da infra é o contrato
        pass


def review(artefato: dict, complete_fn) -> dict:
    """The single advisory reviewer (ADR-0025), blind. Returns {furos: [str]} (+ `degraded`)."""
    return _parse_furos(complete_fn(_build_prompt(artefato)))


review.identity = REVIEWER_ID


def _run_reviewer(reviewer, artefato, complete_fn) -> dict:
    """Run the reviewer once. Infra (quota/auth/network) propagates — it is not a review (#55); any
    other failure or malformed return degrades to a note with no furos, never a block."""
    try:
        v = reviewer(artefato, complete_fn)
    except _llm.LLMTransportError as e:
        _log_infra_error(e)
        raise
    except Exception as e:  # noqa: BLE001 — an advisory reviewer can never crash the close
        v = {"furos": [], "degraded": f"reviewer raised: {type(e).__name__}: {e}"}
    if not isinstance(v, dict):
        v = {"furos": [], "degraded": f"non-dict reviewer return: {type(v).__name__}"}
    furos = v.get("furos")
    if not isinstance(furos, list):
        v = {**v, "furos": [], "degraded": f"malformed furos: {furos!r}"[:300]}
    v = {**v, "furos": [str(f) for f in v["furos"]]}
    identity = getattr(reviewer, "identity", None)
    if identity is not None:
        v["reviewer"] = identity
    return v


def _note_text(note) -> str:
    """One kept furo as one line: the furo, and the producer's answer when it gave one."""
    if isinstance(note, dict):
        furo = str(note.get("furo") or "").strip()
        resposta = str(note.get("resposta") or "").strip()
        return f"{furo} — Resposta: {resposta}" if resposta else furo
    return str(note).strip()


# ---------------------------------------------------------------------------
# The proof contract — UNFORGEABLE and BOUND (Codex re-review #2).
#
# A passing review is no longer a shape-only dict the publisher trusts on sight (a forged or
# stale `{pass: True, verdicts: [...]}` published unreviewed/different content). The proof
# `run_close` mints is bound to a sha256 DIGEST of the EXACT publish payload (slug + spec +
# intent + cites + proposes + distills + skill — EVERY state/page-affecting publish arg, #3),
# carries the reviewer's verdict stamped with its CANONICAL reviewer identity (#3), and is
# stamped with a `run_close`-only secret token minted ONCE per process — a caller cannot
# fabricate one because the token never leaves this module. The mint itself is module-PRIVATE
# (`_mint_proof`, #3): only run_close (and the explicit test seam) can reach it. `verify_proof`
# (called at the publish seam) refuses unless the token is run_close's, the digest matches the
# payload actually being published (so distills/skill cannot be altered post-mint), the
# reviewer ran (ADR-0025: it is advisory — its furos never refuse), AND its canonical identity is present.
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


def proof_digest(*, slug, spec, intent, cites, proposes, distills=None, skill=None,
                 lineage=None, dispatch_id=None, bears_on=None, para=None, reports_on=None,
                 experiment_curation=None) -> str:
    """The sha256 digest BINDING a proof to the EXACT publish payload (incl. dispatch_id — E1b:
    persisted field = digested field). Canonical JSON
    (sorted keys) so the same payload always digests identically and the publisher can
    recompute it from the args it is about to publish — any difference (different slug, spec,
    intent, cites, proposes, distills, skill, or lineage) yields a different digest and is
    rejected.

    Codex re-review #3: `distills` and `skill` are page/state-affecting publish arguments
    (they ride the durable `artefato.published` event), so they MUST be bound — otherwise a
    proof-holder could alter them at publish time without invalidating the proof (poisoning
    provenance).

    Cortex-v1 (brick-1): `lineage` (the AUTHORED typed builds_on/supersedes/contradicts edges
    the publisher materializes as DIRECTED edges) is bound for the same reason — without the
    bind the authored lineage is forgeable at publish time.

    S2 (E1b): `dispatch_id` is bound the same way — it affects the yield-join fold (S7), so it
    is state-affecting; outside the digest a publish_fn could publish under ANOTHER dispatch_id
    with no mismatch, corrupting the join without violating the proof. Same class as slug:
    persisted field = digested field."""
    payload = {
        "slug": slug,
        "spec": spec,
        "intent": intent,
        "cites": cites or [],
        "proposes": proposes or [],
        "distills": distills or [],
        "skill": skill,
        # normalize so the digest binds ONLY well-formed authored edges — a malformed lineage item can
        # never be json.dumps(default=str)-coerced into the verification anchor (Cortex-v1 brick-1).
        "lineage": normalize_lineage(lineage),
        "dispatch_id": dispatch_id,
        # Ticket A (ontologia §2b/§6): bears_on/para are state-affecting publish args (they ride the
        # durable event and become valenced/PARA edges). reports_on makes a report Artefato the
        # navigable bridge to an Experiment. experiment_curation writes experiment.curated in the
        # same publish batch. Same threat class as lineage, same bind.
        "bears_on": normalize_bears_on(bears_on),
        "para": normalize_para(para),
        "reports_on": normalize_reports_on(reports_on),
        "experiment_curation": normalize_experiment_curation(
            reports_on, experiment_curation, report_slug=slug, by=skill),
    }
    blob = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _mint_proof(verdicts, *, slug, spec, intent, cites, proposes,
                distills=None, skill=None, lineage=None, dispatch_id=None,
                bears_on=None, para=None, reports_on=None, experiment_curation=None,
                reviewer_notes=None) -> dict:
    """Mint the bound, token-stamped proof for a close. Carries the reviewer's verdict (stamped by
    run_close with its canonical identity), the digest of the exact payload (incl. the appended
    "Notas do revisor" section, since `spec` is the final content) and the run_close-only token.
    Module-PRIVATE (Codex re-review #3): only `run_close` (and the explicit test seam) calls it.
    `reviewer_notes` is the first-class projection of the furos the producer kept."""
    return {
        "pass": True,
        "verdicts": list(verdicts),
        "digest": proof_digest(slug=slug, spec=spec, intent=intent,
                               cites=cites, proposes=proposes,
                               distills=distills, skill=skill, lineage=lineage,
                               dispatch_id=dispatch_id, bears_on=bears_on, para=para,
                               reports_on=reports_on, experiment_curation=experiment_curation),
        "token": _PROOF_TOKEN,
        "reviewer_notes": [_note_text(n) for n in (reviewer_notes or [])],
        # the contract that framed THIS review, pinned by content (GLO-13): the publisher persists
        # it, so an old review is never read against a new contract.
        "gate_rubric": REVIEW_CONTRACT_VERSION,
        "gate_rubric_sha": REVIEW_CONTRACT_SHA,
    }


def verify_proof(proof, *, slug, spec, intent, cites, proposes,
                 distills=None, skill=None, lineage=None, dispatch_id=None,
                 bears_on=None, para=None, reports_on=None, experiment_curation=None,
                 reviewer_count=1):
    """Verify a proof BINDS to the payload being published — raise ValueError otherwise, BEFORE
    any state/HTML is written. Refuses unless: the token is run_close's (not a fabricated one),
    the digest matches THIS payload (E1b: distills/skill/lineage/dispatch_id included, #3), the
    proof carries `reviewer_count` verdicts AND the canonical reviewer identity (the review
    actually RAN — a proof from a fake/injected reviewer is rejected, #3). The reviewer's furos
    never refuse (ADR-0025): they are already in the content, as notes or as fixes."""
    if not isinstance(proof, dict):
        raise ValueError(f"cannot publish artefato {slug!r}: no proof (#2)")
    if not secrets.compare_digest(str(proof.get("token", "")), _PROOF_TOKEN):
        raise ValueError(
            f"cannot publish artefato {slug!r}: forged/absent proof token — "
            "publish only through close.run_close (#2)")
    expected = proof_digest(slug=slug, spec=spec, intent=intent,
                            cites=cites, proposes=proposes,
                            distills=distills, skill=skill, lineage=lineage,
                            dispatch_id=dispatch_id, bears_on=bears_on, para=para,
                            reports_on=reports_on, experiment_curation=experiment_curation)
    if not secrets.compare_digest(str(proof.get("digest", "")), expected):
        raise ValueError(
            f"cannot publish artefato {slug!r}: proof digest does not bind to this "
            "payload (minted for a different artefato, or distills/skill/lineage altered) (#3)")
    verdicts = proof.get("verdicts") or []
    if len(verdicts) != reviewer_count:
        raise ValueError(
            f"cannot publish artefato {slug!r}: proof lacks {reviewer_count} reviewer "
            "verdict(s) (#2/#9)")
    identities = {v.get("reviewer") for v in verdicts if isinstance(v, dict)}
    if REVIEWER_ID not in identities:
        raise ValueError(
            f"cannot publish artefato {slug!r}: proof lacks the canonical reviewer "
            "identity — built from a fake/injected reviewer (#3)")


# ---------------------------------------------------------------------------
# S6 — the genus floor (enxerto A1)
# ---------------------------------------------------------------------------

def _floor(floor_fn) -> list[str]:
    """Evaluate the injected SESSION floor safely (design-close §6). The floor is a `() -> list[str]`
    the wiring injects at the call-site (close.py NEVER imports harvest — same idiom as
    complete_fn/publish_fn). A raising floor_fn is DARK → [] (the floor measures an out-of-band
    artefact; darkness is fail-OPEN, never a close crash, inverse of genus). A non-list return is
    treated as [] (fail-open). A returned list of violation strings is genus-class: it is summed
    into the gate's `violations` and inherits ALL the blocking-first mechanics (before the reviewer,
    bounces via the genus path, hard-fails on exhaustion)."""
    if floor_fn is None:
        return []
    try:
        v = floor_fn()
    except Exception:  # noqa: BLE001 — a floor that cannot run is dark, never a close crash (§6)
        return []
    return list(v) if isinstance(v, list) else []


def _log_close_event(type_, payload):
    """Best-effort event log from the close (mirrors `_log_infra_error`'s belt-and-suspenders): a
    broken log never masks the close decision itself."""
    try:
        import eventlog
        eventlog.append(type_, "close", payload, log=eventlog.LOG)
    except Exception:  # noqa: BLE001 — the record is best-effort; the decision is the contract
        pass


# The genus bound lives HERE, in the protocol constants — never in the producer's discretion
# (that bound separates a mechanical check from the retry-envelope ADR-0003 killed). Only the
# MECHANICAL genus contract bounces now; the reviewer never does (ADR-0025).
BOUNCE_MAX = _envconf.env_int("EDGE_BOUNCE_MAX", 1)              # genus violation → re-produce, at most this many times
LOOP2_MAX_REOPENS = _envconf.env_int("EDGE_LOOP2_MAX_REOPENS", 1)  # serendipity may reopen loop-1 at most this many times


def run_close(artefato, produce_fn, reviewer=review, complete_fn=None, publish_fn=None,
              improve_fn=None, floor_fn=None):
    """The ONE enforced close path (#2). `publisher.publish` refuses without the bound proof this
    mints, so a producer can never reach the publisher around the close.

    1. GENUS (mechanical, blocking-first): `check_genus` + the injected session floor. A
       violation bounces — `improve_fn(artefato, [genus feedback])` when wired, else
       `produce_fn()` — at most `BOUNCE_MAX` times, then hard-fails. Never unbounded.
    2. REVIEW (advisory, ADR-0025): the reviewer runs ONCE on the genus-clean artefato and points
       out furos. No score, no veto, no second round.
    3. THE PRODUCER DECIDES: with furos and an `improve_fn`, it is called ONCE as
       `improve_fn(artefato, verdict)` and returns the revised artefato. Each furo is either fixed
       in the text or KEPT; the revised dict may carry `reviewer_notes` — the furos it kept, as
       strings or `{furo, resposta}` — and when it omits that key every furo counts as kept (the
       safe default: nothing the reviewer said disappears silently). A revision that crashes,
       is not a dict, or breaks the genus is discarded: the pre-revision draft publishes with
       every furo as a note. Without an `improve_fn`, every furo is kept.
    4. Kept furos ride `content["reviewer_notes"]` — rendered as a "Notas do revisor" section —
       set BEFORE the mint (the digest binds it); then `publish_fn(artefato, proof)` publishes.

    Returns the proof on publish, else `{pass: False, artefato, verdicts: [], genus_violations}`
    when the MECHANICAL genus bound is exhausted (the review never produces a failure)."""
    bounces = 0
    while True:
        ground_visuals(artefato)   # S7 (R2): sign cite-grounded visuals before the genus check
        violations = check_genus(artefato) + _floor(floor_fn)
        if not violations:
            break
        if bounces >= BOUNCE_MAX:
            return {"pass": False, "artefato": artefato, "verdicts": [],
                    "genus_violations": violations}
        bounces += 1
        if improve_fn is not None:
            try:
                revised = improve_fn(artefato, [_genus_feedback(violations)])
            except Exception:  # noqa: BLE001 — crashing refiner → fail closed with the violations
                return {"pass": False, "artefato": artefato, "verdicts": [],
                        "genus_violations": violations, "non_convergence": True}
            if not isinstance(revised, dict):
                return {"pass": False, "artefato": artefato, "verdicts": [],
                        "genus_violations": violations, "non_convergence": True}
            artefato = revised
        else:
            artefato = produce_fn()

    verdict = _run_reviewer(reviewer, artefato, complete_fn)
    furos = verdict["furos"]
    notes = list(furos)
    if furos and improve_fn is not None:
        try:
            revised = improve_fn(artefato, verdict)
        except Exception:  # noqa: BLE001 — a crashing revision is discarded, never a block
            revised = None
        if isinstance(revised, dict):
            revised = dict(revised)
            kept = revised.pop("reviewer_notes", None)
            ground_visuals(revised)
            if not (check_genus(revised) + _floor(floor_fn)):
                artefato = revised
                notes = list(kept) if isinstance(kept, list) else list(furos)
            else:
                _log_close_event("close.revision_discarded",
                                 {"slug": artefato.get("slug"), "reason": "genus"})

    if notes:
        # the kept furos ride the content as `reviewer_notes` (rendered as a "Notas do revisor"
        # section) BEFORE the mint, so the digest binds them; a top-level key, not a block, so
        # the genus floors keep judging the author's content, never the reviewer's note.
        content = artefato.get("content")
        content = content if isinstance(content, dict) else {}
        artefato = {**artefato, "content": {
            **content, "reviewer_notes": [t for t in (_note_text(n) for n in notes) if t]}}

    proof = _mint_proof(
        [verdict],
        slug=artefato.get("slug"), spec=artefato.get("content"),
        intent=artefato.get("intent"), cites=artefato.get("cites"),
        proposes=artefato.get("proposes"),
        distills=artefato.get("distills"), skill=artefato.get("skill"),
        lineage=artefato.get("lineage"),
        dispatch_id=artefato.get("dispatch_id"),
        bears_on=artefato.get("bears_on"), para=artefato.get("para"),
        reports_on=artefato.get("reports_on"),
        experiment_curation=artefato.get("experiment_curation"),
        reviewer_notes=notes)
    if publish_fn is not None:
        publish_fn(artefato, proof)
    return proof


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
