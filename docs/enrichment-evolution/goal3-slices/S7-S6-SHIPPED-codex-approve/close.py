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
import re
import secrets
import unicodedata
from html.parser import HTMLParser as _HTMLParser

import _envconf  # loads the repo-root .env and provides typed EDGE_* reads
import runstore  # internal-evidence (R8) verification: runstore.attest_value
import visual_grounding  # S7/R2: per-visual unforgeable grounding attestation (verify is blind-safe)

from render import BLOCK_SCHEMAS, _BLOCK_TYPE_ALIASES
import render
import producer_descriptor
import blocks as block_validation

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


def _attrs_mark_hidden(attrs) -> bool:
    """A start tag's subtree is DROPPED from the reader-visible claim corpus if ANY hide-or-untrusted
    mechanism is present (Codex S3 #5/#6/#7). Centralized so every mechanism lives in one place:
      • the boolean HTML `hidden` attribute (browser-default `display:none`) — any presence, any value;
      • `aria-hidden="true"`;
      • ANY non-empty inline `style`. We cannot prove an author-controlled style keeps text VISIBLE —
        `safe_style` permits `opacity:0` / `font-size:0` / `position:absolute;left:-9999px` /
        `display:none` / `visibility:hidden` / `color:#fff` and unbounded other tricks — so a styled
        element is treated as possibly-hidden and its text does NOT ground a claim (fail-closed). This
        kills the OPEN-ENDED CSS class instead of blocklisting individual declarations. Trusted renderers
        emit `style` only from an author-controlled field, so a grounding claim must live in UNSTYLED
        trusted prose (raw-html is already stripped from the corpus upstream)."""
    a = dict(attrs)
    return ("hidden" in a
            or a.get("aria-hidden") == "true"
            or bool(isinstance(a.get("style"), str) and a["style"].strip()))


def _attrs_render_hidden(attrs) -> bool:
    """Hidden-predicate for the R0-for-values corpus: a subtree is hidden by the boolean `hidden` attr,
    `aria-hidden="true"`, or a style that hides under `_style_hides_text` — the SAME allowlist detector the R0
    storytelling floor uses, so the corpus is provably NO WEAKER than the R0 prose floor (Codex re-gate #10).
    Unlike `_attrs_mark_hidden` (any style → hidden) it credits the renderer's benign text styling
    (font-size/margin/background/border/line-height in _R0_SAFE_PROSE_PROPS), but it STILL fail-closes on any
    non-benign property — so a producer-slipped overflow:hidden / position:absolute;left:-9999px /
    content-visibility:hidden / zoom:0 / novel trick is dropped, exactly as R0 would drop it."""
    a = dict(attrs)
    if "hidden" in a or a.get("aria-hidden") == "true":
        return True
    style = a.get("style")
    return bool(isinstance(style, str) and style.strip() and _style_hides_text(render.safe_style(style)))


# tags that create a VISUAL break — text on either side is NOT visually contiguous, so it must not fuse
# into one token (Codex S3 #7: `1000<br>0` reads as two numbers, not `10000`). `<br>` is the line-break in
# render_text's inline safelist; the rest are block-level. Inline formatting (strong/em/code/…) flows and
# is deliberately NOT here, so `8<strong>5</strong>` stays the contiguous `85` the reader sees.
_BREAK_TAGS = frozenset({
    "br", "p", "div", "li", "tr", "td", "th", "ul", "ol", "table", "thead", "tbody",
    "section", "blockquote", "hr", "h1", "h2", "h3", "h4", "h5", "h6",
})


class _VisibleTextParser(_HTMLParser):
    """Collect only the DISPLAYED text of rendered HTML — text inside a subtree marked hidden
    (the boolean `hidden` attribute, style display:none / visibility:hidden, or aria-hidden=true) is
    dropped (Codex S3 #5). A visual-break tag (`<br>` / block-level) emits a space separator so visible
    text never fuses across a line/block boundary (Codex S3 #7). Tolerant of unbalanced tags.
    convert_charrefs unescapes entities into the collected text."""
    def __init__(self, hidden_fn=_attrs_mark_hidden):
        super().__init__(convert_charrefs=True)
        self._hidden_fn = hidden_fn   # which start tags hide their subtree (conservative vs render-truth)
        self._stack = []   # (tag, contributes_hidden)
        self._hidden = 0
        self._out = []

    def _maybe_break(self, tag):
        if self._hidden == 0 and tag.lower() in _BREAK_TAGS:
            self._out.append(" ")

    def handle_starttag(self, tag, attrs):
        is_hidden = self._hidden_fn(attrs)
        self._stack.append((tag, is_hidden))
        if is_hidden:
            self._hidden += 1
        self._maybe_break(tag)

    def handle_startendtag(self, tag, attrs):  # e.g. `<br/>` — void, no matching end tag
        if not self._hidden_fn(attrs):
            self._maybe_break(tag)

    def handle_endtag(self, tag):
        for i in range(len(self._stack) - 1, -1, -1):
            if self._stack[i][0] == tag:
                self._hidden -= sum(1 for _, h in self._stack[i:] if h)
                del self._stack[i:]
                break
        self._maybe_break(tag)

    def handle_data(self, data):
        if self._hidden == 0:
            self._out.append(data)

    def text(self):
        return "".join(self._out)


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
                corpus.update(_magnitudes(_render_visible(render.render_text(s), _attrs_render_hidden)))
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


def _render_visible(html_str, hidden_fn=_attrs_mark_hidden) -> str:
    """Visible text of one rendered HTML fragment. `hidden_fn` decides which subtrees are hidden: the default
    `_attrs_mark_hidden` is CONSERVATIVE (any inline `style` → dropped) for the untrusted-prose grounding
    corpus; pass `_attrs_render_hidden` for TRUSTED renderer output, which credits benign renderer styling and
    drops only EXPLICIT hiding (display:none / visibility:hidden / opacity:0 / offscreen / …). '' on error."""
    parser = _VisibleTextParser(hidden_fn)
    try:
        parser.feed(html_str)
        parser.close()
    except Exception:  # noqa: BLE001 — malformed HTML → fail closed
        return ""
    return parser.text()


def _block_corpus_magnitudes(block) -> set:
    """Magnitudes in the ACTUAL reader-visible text the renderer emits for `block` (RENDER-TRUTH): render it,
    then keep only the text a reader sees (`_attrs_render_hidden` credits benign renderer styling, drops real
    hiding). This is what makes the corpus exhaustive WITHOUT a field skip-list — unrendered metadata never
    appears in the renderer's output, so it cannot launder a value (Codex S7 re-gate #6). Fail-closed to
    empty on any render error (the block then contributes nothing — the safe, over-strict direction)."""
    try:
        return _magnitudes(_render_visible(render.render_block(block), _attrs_render_hidden))
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
            units.append(_render_visible(render.render_block(blk)))
        summary = content.get("executive_summary")
        if isinstance(summary, list):
            for item in summary:
                if isinstance(item, str) and item.strip():
                    units.append(_render_visible(render.render_text(item)))
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
    # that names its prior thread as a typed edge owes no distill. Mirrors real_distill/_nonblank:
    # an item clears it only if its `slug` is a NON-BLANK string (a placeholder {} or {"slug":"  "}
    # would not resolve in projection, so it must not clear the move either).
    real_lineage = any(
        isinstance(item, dict) and _nonblank(item.get("slug"))
        for item in (artefato.get("lineage") or [])
    )

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
# The DETERMINISTIC structural core (ADR-0013: the genus enforces STRUCTURE; the blind reviewers judge
# whether each explanation is ADEQUATE and whether the artefato's own source claims are PRESERVED — the
# irreducibly semantic R0-I-adequacy / R0-III, carried by the narrative_depth dimension). The robust
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

# R0 prose visibility is judged against the SANITIZED style render_paragraph emits, PARSED
# declaration-by-declaration with EXACT property names (Codex S2 #3) — never a flat substring regex (which
# false-matched `color` inside `background-color` and missed colored zero-alpha hex). `safe_style` already
# DROPS any paren-bearing declaration, so function hiders (transform:scale(0)/clip:rect(…)) never reach the
# reader and are not our concern. R0 must COUNT benignly-styled visible prose and only disqualify GENUINE
# hiders. The enumerated KNOWN single-declaration text-hiders below are deterministic; the narrative_depth
# blind reviewer is the documented ADR-0013 backstop for adequacy AND any novel/multi-declaration collapse
# (contrast/white-on-white, width:0+overflow) — a miss degrades to a reviewer catch, never a security hole.
# a CSS <number>[unit] value, parsed for its NUMERIC magnitude — handles sign, decimals AND exponent
# notation (0e0 / 1e3) uniformly (Codex S2 #3), so the zero/off-screen tests judge the real value rather
# than chasing literal forms. (render.safe_style strips `+`-signed declarations, but `[+-]?` is harmless.)
_NUM_UNIT = re.compile(r"([+-]?(?:\d+\.?\d*|\.\d+)(?:e[+-]?\d+)?)\s*([a-z%]*)", re.I)
_ZERO_ALPHA_HEX = re.compile(r"#[0-9a-f]{3}0|#[0-9a-f]{6}00", re.I)         # #RGBA / #RRGGBBAA, alpha 0


def _num_unit(val: str):
    """Parse a single CSS numeric value into (float magnitude, unit) or None — exponent/sign/decimal aware."""
    m = _NUM_UNIT.fullmatch(val.strip())
    if not m:
        return None
    try:
        return float(m.group(1)), m.group(2).lower()
    except ValueError:
        return None


def _is_css_zero(val: str) -> bool:
    """True iff `val` is a CSS numeric value equal to zero (any form: 0 / .0 / 0px / 0% / 0e0 / -0) — the
    magnitude is parsed as a float, so exponent and signed forms are covered; 0.5 / 1e3 are NOT zero."""
    nu = _num_unit(val)
    return nu is not None and nu[0] == 0.0


def _is_transparent_color(val: str) -> bool:
    v = val.strip().lower()
    return v == "transparent" or bool(_ZERO_ALPHA_HEX.fullmatch(v))


# approximate px-per-unit so a negative text-indent is judged by its REAL off-screen distance, not a raw
# integer (Codex S2 #3: -50em ≈ 800px hides, -20px is a legit hanging-indent nudge). Unknown unit → em-scale
# (conservative). Relative units (%/vw/…) are handled separately (a large negative % moves text off its box).
_LEN_PX = {"px": 1.0, "pt": 96 / 72, "pc": 16.0, "in": 96.0, "cm": 96 / 2.54, "mm": 96 / 25.4,
           "em": 16.0, "rem": 16.0, "ex": 8.0, "ch": 8.0, "q": 96 / 25.4 / 4}
_OFFSCREEN_PX = 100.0


def _text_indent_hides(val: str) -> bool:
    """True iff a NEGATIVE text-indent moves the text far enough to be off-screen — the text-replacement
    hide idiom. A small negative px (hanging-indent nudge) stays visible; a large or relative-unit negative
    hides. Magnitude is parsed as a float (sign/decimal/exponent aware) and unit-scaled to real px."""
    nu = _num_unit(val)
    if nu is None or nu[0] >= 0:        # only a negative indent pushes text off-screen
        return False
    mag, unit = -nu[0], nu[1]
    if unit in ("%", "vw", "vh", "vmin", "vmax"):
        return mag >= 50            # a large negative relative indent pushes text off its box
    return mag * _LEN_PX.get(unit or "px", 16.0) >= _OFFSCREEN_PX


# R0 prose visibility is ALLOWLIST-based, the DECISIVE end to the single-declaration-hider arms race
# (Codex S2 #3, operator decision): prose counts as visible only if EVERY sanitized declaration uses a
# known-SAFE text-styling property with a non-hiding value. The hide-capable properties below carry value
# checks; every OTHER property must be in `_R0_SAFE_PROSE_PROPS` or the declaration is treated as
# possibly-hiding (fail-closed) — so an UNKNOWN or future property (content-visibility / zoom / …) can
# never produce a false PASS of the floor. (safe_style already strips paren-bearing declarations like
# transform:scale(0) / clip:rect(…), so those never reach here.) The narrative_depth blind reviewer remains
# the adequacy backstop. Fail-closed is the right direction for R0: a benign-but-exotic style that doesn't
# count just means the author states the explanation in plainer prose — hidden prose never passes.
_R0_SAFE_PROSE_PROPS = frozenset({
    # purely-benign visible text styling (no value can hide the text)
    "background", "background-color", "background-image", "background-position", "background-size",
    "background-repeat", "background-clip",
    "margin", "margin-top", "margin-bottom", "margin-left", "margin-right",
    "padding", "padding-top", "padding-bottom", "padding-left", "padding-right",
    "border", "border-top", "border-bottom", "border-left", "border-right",
    "border-color", "border-width", "border-style", "border-radius",
    "font-weight", "font-style", "font-family", "font-variant", "font-stretch", "font-feature-settings",
    "text-align", "text-transform", "text-decoration", "text-decoration-color", "text-decoration-line",
    "text-shadow", "line-height", "letter-spacing", "word-spacing", "word-break", "overflow-wrap",
    "white-space", "vertical-align", "direction", "writing-mode", "text-orientation", "tab-size",
    "list-style", "list-style-type", "cursor",
    # hide-CAPABLE but kept-visible-with-a-good-value (their hiding value is checked below)
    "color", "-webkit-text-fill-color", "display", "visibility", "opacity", "font-size", "font", "scale",
    "text-indent",
    # layout offsets that DON'T hide on their own (need position to go off-screen → reviewer backstop)
    "left", "top", "right", "bottom", "width", "min-width", "max-width", "height", "min-height", "max-height",
})
# `display` VALUES that paint their text content (positive allowlist — Codex S2 #3). Any other value
# (none, table-column, table-column-group, …) does not render the text and is treated as hiding.
_VISIBLE_DISPLAY = frozenset({
    "block", "inline", "inline-block", "flow-root", "list-item", "flex", "inline-flex",
    "grid", "inline-grid", "table", "inline-table", "table-cell", "table-caption", "table-row",
    "table-row-group", "table-header-group", "table-footer-group", "contents", "run-in",
})


# painting-CATEGORY characters that nonetheless render NOTHING on their own: default-ignorable letters
# (Hangul fillers + combining grapheme joiner) and the blank-rendering Braille Pattern Blank (a `So`
# symbol). (Variation selectors / zero-width / format chars are category M*/C* and already excluded by
# requiring a base L/N/P/S category; Unicode spaces are Z* and excluded too.)
_DEFAULT_IGNORABLE = frozenset({0x034F, 0x115F, 0x1160, 0x3164, 0xFFA0, 0x2800})


def _has_visible_glyph(s: str) -> bool:
    """True iff `s` contains a glyph that PAINTS — a base letter/number/punctuation/symbol (L/N/P/S).
    Excludes whitespace (Unicode Z*), zero-width/format/control characters (C*) like ​ / ﻿, bare
    combining marks (M*) and default-ignorable variation selectors (Mn), and the default-ignorable
    Hangul-filler letters — so a paragraph made of only those renders no visible explanation (Codex S2 #3)."""
    return any(unicodedata.category(c)[0] in "LNPS" and ord(c) not in _DEFAULT_IGNORABLE for c in s)


def _style_explicitly_hides(safe: str) -> bool:
    """True iff the SANITIZED inline style contains a KNOWN hiding declaration (display:none / table-column;
    visibility:hidden|collapse; opacity/font-size signed-zero; scale zero-axis; `font:` shorthand zero size;
    transparent/zero-alpha color; large-negative text-indent; negative letter/word spacing). The
    value-checked half of `_style_hides_text` — kept separate so the value checks can be reasoned about on
    their own; the unknown-property fail-closed half (which catches overflow / position / content-visibility /
    zoom / any exotic prop) lives in `_style_hides_text`."""
    for decl in safe.split(";"):
        prop, sep, val = decl.partition(":")
        if not sep:
            continue
        prop, val = prop.strip().lower(), val.strip().lower()
        if not prop:
            continue
        if prop == "display" and val not in _VISIBLE_DISPLAY:
            return True   # none / table-column / any non-painting display value
        if prop == "visibility" and val in ("hidden", "collapse"):
            return True
        if prop in ("opacity", "font-size") and _is_css_zero(val):
            return True
        if prop == "scale" and any(_is_css_zero(t) for t in val.split()):
            return True
        if prop == "font":
            # `font` shorthand: drop the `/line-height` component, then a ZERO size token (bare `0` is a
            # valid length, or `0px`/`0%`) hides — family/keyword tokens are never css-zero (Codex S2 #3).
            size_region = re.sub(r"/\s*\S+", " ", val)
            if any(_is_css_zero(t) for t in size_region.split()):
                return True
        if prop in ("color", "-webkit-text-fill-color") and _is_transparent_color(val):
            return True
        if prop == "text-indent" and _text_indent_hides(val):
            return True
        if prop in ("letter-spacing", "word-spacing"):
            # NEGATIVE tracking collapses glyphs onto each other into an unreadable smear (Codex re-gate #9).
            # The renderers never emit these, and legitimate explanation never uses negative tracking, so any
            # negative value is treated as hiding (positive/normal spacing stays visible).
            nu = _num_unit(val)
            if nu is not None and nu[0] < 0:
                return True
    return False


def _style_hides_text(safe: str) -> bool:
    """True iff the SANITIZED inline style hides/collapses the text (ALLOWLIST model): a known hiding
    declaration (`_style_explicitly_hides`), OR a property NOT in `_R0_SAFE_PROSE_PROPS` (unknown/exotic →
    fail-closed — e.g. position offscreen / content-visibility:hidden / zoom:0 / overflow clipping). Returns
    False only when EVERY declaration is a known-safe, non-hiding one. Shared by the R0 storytelling floor and
    the R0-for-values corpus, so neither can be tricked by a style the other would catch."""
    if _style_explicitly_hides(safe):
        return True
    for decl in safe.split(";"):
        prop, sep, _ = decl.partition(":")
        prop = prop.strip().lower()
        if sep and prop and prop not in _R0_SAFE_PROSE_PROPS:
            return True   # unknown/exotic property kept by safe_style → fail-closed as possibly-hiding
    return False


def _r0_prose_visible(block) -> bool:
    """True iff a prose block (paragraph/callout) is reader-VISIBLE explanation: it carries real RENDERED
    body text AND is not hidden by its own inline style. Reads the canonical `text` field the renderer
    actually displays (Codex S2 #3) — NOT `_block_text`, which flattens metadata like `style`, so an empty
    styled block cannot pose as prose. The `style` field is the only hiding vector for a prose block
    (render_text escapes raw HTML, so no nested style/hidden enters via the text)."""
    _bt, cblock = render.canonical_block(block)        # normalize synonyms to the field render reads
    text = cblock.get("text") if isinstance(cblock, dict) else None
    if not (isinstance(text, str) and text.strip()):
        return False
    # the RENDERED body must show a VISIBLE GLYPH: markup-only formatting (text "<br>") or zero-width/
    # format characters (​/﻿) render no readable explanation (Codex S2 #3). render_text emits no
    # style attrs, so `_render_visible` here strips only inline tags / break-separators (block style below).
    if not _has_visible_glyph(_render_visible(render.render_text(text))):
        return False
    # Only a PARAGRAPH applies `style` as a CSS attribute (render_paragraph → safe_style); a callout uses
    # `style` as a VARIANT name (a class), never a hiding CSS attr. Run the hider check against the SAME
    # sanitized style render_paragraph emits, so the predicate exactly matches renderer output (Codex S2 #3).
    if _bt == "paragraph":
        style = block.get("style")
        if isinstance(style, str) and _style_hides_text(render.safe_style(style)):
            return False
    return True


def _r0_any_visible_prose(content) -> bool:
    """True iff the artefato carries reader-visible explanatory prose ANYWHERE — a section paragraph/
    callout or an executive_summary item (the latter renders as prose with no author style)."""
    for section in _sections(content):
        for b in (section.get("blocks") or []):
            if isinstance(b, dict) and _type(b) in PROSE_BLOCK_TYPES and _r0_prose_visible(b):
                return True
    summary = content.get("executive_summary") if isinstance(content, dict) else None
    # an executive_summary item must render a VISIBLE GLYPH too (Codex S2 #3): a markup-only or zero-width
    # item is not reader-visible prose — share the SAME visible-glyph predicate as the blocks.
    return isinstance(summary, list) and any(
        isinstance(s, str) and _has_visible_glyph(_render_visible(render.render_text(s))) for s in summary)


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
        has_prose = any(_type(b) in PROSE_BLOCK_TYPES and _r0_prose_visible(b) for b in blocks)
        if has_visual and not has_prose:
            violations.append("r0:visual-without-prose")
    # top-level `content.metrics` is a visual the renderer emits OUTSIDE any section; if it is a
    # substantive metrics grid it still owes reader-visible explanatory prose SOMEWHERE in the artefato
    # (an executive_summary item or a section paragraph/callout), never a bare top-level dashboard.
    if _metrics_substantive(content.get("metrics")) and not _r0_any_visible_prose(content):
        violations.append("r0:visual-without-prose")
    return violations


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
        "findings, or a bite that states a conclusion without earning it, fails. "
        "EXPLAIN, NEVER MERELY LABEL (R0, DOMINANT): every term, acronym, phase-id, or label a visual "
        "or heading introduces is EXPANDED in prose at first use — what it is, what it does, why it "
        "matters — in proximity, never left as a bare sigla. A phase diagram that names the phases but "
        "never says which is which, or a grid/card/table whose labels are never expanded in accompanying "
        "prose, FAILS: the visual ACCOMPANIES the prose that explains it, it never substitutes it. And "
        "enriching must not LOSE content: every claim the artefato's OWN declared source/baseline carried "
        "is still SUPPORTED in non-visual prose (paraphrase / split / merge are fine) — a surface mention "
        "that drops the claim, or a retained CONTRADICTORY claim, fails. Property-not-section, "
        "source-relative (the artefato is judged against its OWN material, never a fixed external set)."
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
        # R5/S1 (Codex S1 review [high]): PRESERVE the reviewer's `residual` through the parser so the
        # default-deny sanitizer in run_close can see it — else a blocking finding mischanneled into
        # residual would be silently dropped on the production path. Non-list residual is kept as-is;
        # _sanitize_verdict_residual promotes it (and any blocking-looking entry) to a strike.
        "residual": result.get("residual", []),
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

BOUNCE_MAX = _envconf.env_int("EDGE_BOUNCE_MAX", 1)              # reviewer strike → re-produce, at most this many times
LOOP2_MAX_REOPENS = _envconf.env_int("EDGE_LOOP2_MAX_REOPENS", 1)  # serendipity may reopen loop-1 at most this many times
IMPROVE_BACKSTOP = _envconf.env_int("EDGE_IMPROVE_BACKSTOP", 15)   # R7 ABSOLUTE bound (operator-set, EDGE_IMPROVE_BACKSTOP): improve loop runs while the refiner keeps
#                          CHANGING the draft toward resolution and stops the moment it CONVERGES (issues
#                          resolved) or PLATEAUS (draft unchanged); this bound caps a non-converging
#                          refiner (churn / receding-target) and a repair deeper than it. No count-based
#                          early stop — count-flat is indistinguishable between one-at-a-time progress and
#                          churn without stable per-issue ids (deferred reviewer contract), so a still-
#                          changing loop is NEVER cut off mid-progress within the bound; a non-converged
#                          bound hit FAILS CLOSED, never a false pass.


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


def proof_digest(*, slug, spec, intent, cites, proposes, distills=None, skill=None,
                 lineage=None) -> str:
    """The sha256 digest BINDING a proof to the EXACT publish payload. Canonical JSON
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
    bind the authored lineage is forgeable at publish time."""
    payload = {
        "slug": slug,
        "spec": spec,
        "intent": intent,
        "cites": cites or [],
        "proposes": proposes or [],
        "distills": distills or [],
        "skill": skill,
        "lineage": lineage or [],
    }
    blob = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _mint_proof(verdicts, *, slug, spec, intent, cites, proposes,
                distills=None, skill=None, lineage=None) -> dict:
    """Mint the bound, token-stamped proof for a passing close. Carries BOTH reviewer
    verdicts (each stamped by run_close with its canonical reviewer identity), the digest of
    the exact payload (now including distills + skill + lineage), and the run_close-only token.

    Codex re-review #3: this is module-PRIVATE — ONLY `run_close` (and the explicit test-only
    seam standing in for it) calls it. It is no longer a public function a producer could call
    to stamp the valid token onto a verdict list of its own choosing."""
    return {
        "pass": True,
        "verdicts": list(verdicts),
        "digest": proof_digest(slug=slug, spec=spec, intent=intent,
                               cites=cites, proposes=proposes,
                               distills=distills, skill=skill, lineage=lineage),
        "token": _PROOF_TOKEN,
        # R5/S1 severity: NON-BLOCKING residual notes the reviewers chose to log rather than strike.
        # A residual can only ride a CLEAN verdict (no strikes); a BLOCKING finding is a strike or a
        # genus violation, which never mints (fail-closed) — so a blocking finding can never become a
        # residual by construction. This just surfaces the acknowledged nits on the shipped proof.
        "residual": [r for v in verdicts for r in (v.get("residual") or [])],
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


def _normalize_verdict(v) -> dict:
    """Coerce a reviewer return into a well-shaped dict so SCHEMA DRIFT fails CLOSED, never crashes
    (Codex S1 #15/#19) — used at BOTH reviewer-collection points (improve loop + gating close). A
    non-dict becomes a bounded failing verdict; a dict whose `strikes` isn't a list gets a failing
    strike. Identity stamping / issue counting / sanitizing then only ever see a dict with list strikes."""
    if not isinstance(v, dict):
        return {"pass": False, "scores": {},
                "strikes": [f"non-dict verdict: {type(v).__name__}"], "overall": 0.0}
    strikes = v.get("strikes", [])
    if not isinstance(strikes, list):
        return {**v, "pass": False, "strikes": [f"malformed strikes: {strikes!r}"]}
    # enforce the SAME shape contract as _parse_verdict on direct reviewer returns (Codex S1 #23): a
    # non-dict `scores`, or a bool/non-numeric dimension score, fails CLOSED — so a direct reviewer can
    # never mint with a malformed-but-pass:true verdict.
    scores = v.get("scores", {})
    if not isinstance(scores, dict):
        return {**v, "pass": False, "strikes": list(strikes) + [f"malformed scores: {scores!r}"]}
    bad = [d for d, s in scores.items() if isinstance(s, bool) or not isinstance(s, (int, float))]
    if bad:
        # sort by repr (Codex S1 #24): score keys can be heterogeneous (int + str) and sorting them
        # directly would raise — the bad-score report must never crash the fail-closed path.
        return {**v, "pass": False,
                "strikes": list(strikes) + [f"malformed score(s): {sorted(map(repr, bad))}"]}
    return v


# R5/S1 severity — a REVIEWER-authored `residual` is NEVER trusted as non-blocking. An LLM reviewer's
# self-classification (severity/category) is not proof of cosmetic status — a blocking correctness/R0
# finding can be filed under any tag (Codex S1 review #7). So EVERY reviewer-authored residual entry is
# PROMOTED to a strike, failing the close CLOSED. The non-blocking residual channel (proof['residual'])
# is reserved for a DETERMINISTIC cosmetic-only classifier (e.g. a typo/whitespace linter) — a future
# slice — never the reviewer. This makes "a blocking finding can never ship as residual" true in CODE
# without trusting the reviewer's say-so.
def _sanitize_verdict_residual(verdict):
    """Promote EVERY reviewer-authored residual entry to a strike (its non-blocking status is not
    mechanically derived, so it is not trusted). Returns the verdict unchanged when it has no residual;
    otherwise a copy with the residual moved into strikes and `residual` cleared."""
    if not isinstance(verdict, dict):
        return verdict
    residual = verdict.get("residual")
    if not residual:
        return verdict
    entries = residual if isinstance(residual, list) else [residual]
    # coerce a malformed (non-list) `strikes` safely — a truthy non-list (e.g. `1`) would crash
    # `list(...)` (Codex S1 #16); it becomes a real strike so the verdict fails closed, never raises.
    base = verdict.get("strikes")
    if not isinstance(base, list):
        base = [] if not base else [f"malformed strikes: {base!r}"]
    strikes = base + [
        f"reviewer-authored residual (untrusted, promoted to strike): {e!r}" for e in entries]
    return {**verdict, "strikes": strikes, "residual": []}


# R9 (S4) — DISCHARGE PERSISTENCE. A stochastic reviewer that re-raises a finding it had already cleared
# (raised in round k, absent in k+1 once the draft changed, re-raised in k+2) is the receding-target trap
# that made roberto's loop run to the cap and "sair na marra" (non-convergence). The discharge LEDGER
# stamps a finding resolved the round it goes absent, and suppresses its later re-emergence IN THE SAME
# TERMS. Discharge applies ONLY to stochastic REVIEWER strikes — genus violations are deterministic and
# NEVER discharged, so all structural correctness stays gated. A genuinely persistent strike (raised every
# round, never absent) is never discharged and still fails closed.
def _norm_strike(s) -> str:
    """Normalize a strike for same-terms matching: collapse whitespace, casefold. Differently-worded
    findings don't match (treated as new — `fundamento novo`), so only verbatim re-emergence is suppressed."""
    return " ".join(str(s).split()).casefold()


def _round_strikes(verdicts) -> set:
    """The set of normalized strikes raised across a round's reviewer verdicts."""
    return {_norm_strike(s) for v in verdicts if isinstance(v, dict)
            for s in (v.get("strikes") or [])}


def _discharge_verdict(verdict, discharged: set):
    """Return the verdict with every DISCHARGED (already-resolved, re-emergent) strike removed. If the
    verdict failed ONLY on discharged strikes (it had strikes, none survive), its block is resolved → it
    becomes a passing verdict. A verdict with any surviving (non-discharged) strike, or a strike-less
    opaque `pass:false`, is returned unchanged — discharge can never clear a NEW or unnamed failure."""
    if not isinstance(verdict, dict) or not discharged:
        return verdict
    strikes = verdict.get("strikes")
    if not isinstance(strikes, list) or not strikes:
        return verdict
    survivors = [s for s in strikes if _norm_strike(s) not in discharged]
    if len(survivors) == len(strikes):
        return verdict                       # nothing discharged
    nv = {**verdict, "strikes": survivors}
    if not survivors:
        nv["pass"] = True                    # every strike was a resolved finding re-emerging → clean
    return nv


def verify_proof(proof, *, slug, spec, intent, cites, proposes,
                 distills=None, skill=None, lineage=None, reviewer_count=2):
    """Verify a proof BINDS to the payload being published — raise ValueError otherwise,
    BEFORE any state/HTML is written. Refuses unless: the token is run_close's (not a
    fabricated one), the digest matches THIS payload — now including distills + skill +
    lineage, so a proof-holder cannot alter the persisted distills/skill/lineage (#3) — all
    `reviewer_count` reviewers passed (a single-reviewer proof is rejected), AND the verdicts
    carry BOTH canonical reviewer identities (a proof built from fake/injected reviewers is
    rejected on identity grounds, #3)."""
    if not isinstance(proof, dict):
        raise ValueError(f"cannot publish artefato {slug!r}: no proof (#2)")
    if not secrets.compare_digest(str(proof.get("token", "")), _PROOF_TOKEN):
        raise ValueError(
            f"cannot publish artefato {slug!r}: forged/absent proof token — "
            "publish only through close.run_close (#2)")
    expected = proof_digest(slug=slug, spec=spec, intent=intent,
                            cites=cites, proposes=proposes,
                            distills=distills, skill=skill, lineage=lineage)
    if not secrets.compare_digest(str(proof.get("digest", "")), expected):
        raise ValueError(
            f"cannot publish artefato {slug!r}: proof digest does not bind to this "
            "payload (minted for a different artefato, or distills/skill/lineage altered) (#3)")
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

    IMPROVE STAGE (R7 marginal-gain loop): when `improve_fn` is given, BEFORE the gating close
    run review→improve passes WHILE EACH ROUND GAINS — it stops on a plateau (a round whose
    revision is unchanged = marginal gain 0), bounded by `improve_rounds` (default IMPROVE_BACKSTOP)
    as a generous backstop against divergence, NOT a fixed count. Each pass runs BOTH reviewers
    purely to PRODUCE FEEDBACK — the
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
    improve_attempted = False   # at least one improve round actually ran (not a skip)
    improve_converged = False   # the improve loop reached zero outstanding issues
    improve_plateaued = False   # the refiner returned the draft UNCHANGED with issues outstanding
    discharged = set()          # R9: normalized strikes RESOLVED in a prior round (never re-litigated)
    prev_round_strikes = None   # R9: the raw strikes the reviewers raised LAST round (resolved-detection)
    if improve_fn is not None:
        # R7 (run-while-changing, bounded). Iterate while the refiner keeps CHANGING the draft toward
        # resolution; stop on CONVERGENCE (issue_count==0) or PLATEAU (draft returned unchanged). No
        # count-based early stop (count-flat is indistinguishable between one-at-a-time progress and the
        # receding-target trap without stable per-issue ids — Codex S1 #5/#7/#13/#20), so a still-changing
        # loop is NEVER cut off mid-progress within the bound. IMPROVE_BACKSTOP is the absolute bound on a
        # non-converging refiner (operator-set). Exits: CONVERGED → minting gate; PLATEAU (draft UNCHANGED
        # with issues) → HARD FAIL-CLOSED, never re-reviewed (a stateful reviewer could only flip it to a
        # spurious pass); BOUND hit while still CHANGING → exactly ONE verification review, no bounce (the
        # final improve may have converged → mint, else fail-closed, never milked). Codex S1 #8–#20.
        backstop = IMPROVE_BACKSTOP if improve_rounds is None else improve_rounds
        for _ in range(backstop):
            improve_attempted = True
            ground_visuals(artefato)   # S7 (R2): sign visuals grounded to the cites before the genus check
            gv = check_genus(artefato)
            verdicts_fb = []
            for r in reviewers:
                try:
                    v = r(artefato, complete_fn)
                except Exception as e:  # noqa: BLE001 — feedback only; never crash the refine
                    v = {"pass": False, "scores": {}, "rationales": {},
                         "strikes": [f"reviewer raised: {type(e).__name__}: {e}"], "overall": 0.0}
                # normalize a malformed RETURN (not just a raise) to a bounded failing verdict, so the
                # schema-drift fail-closed contract holds in the improve stage too (Codex S1 #15).
                verdicts_fb.append(_normalize_verdict(v))
            # sanitize FIRST (Codex S1 review #7): a reviewer-authored residual is promoted to a strike
            # before it can count as "resolved" or escape as non-blocking.
            verdicts_fb = [_sanitize_verdict_residual(v) for v in verdicts_fb]
            # R9 discharge: a strike RAISED last round but ABSENT this round was resolved by the revision →
            # stamp it discharged; then SUPPRESS any discharged strike that re-emerges this round, so the
            # receding-target trap can't keep the loop alive. (Genus `gv` is deterministic, never discharged.)
            this_round_strikes = _round_strikes(verdicts_fb)
            if prev_round_strikes is not None:
                discharged |= (prev_round_strikes - this_round_strikes)
            prev_round_strikes = this_round_strikes
            verdicts_fb = [_discharge_verdict(v, discharged) for v in verdicts_fb]
            # the genus violations (incl. the rich-rite floor strikes) are FED to improve_fn too
            # (Codex P2, #30): the floor forces depth only if the named gap reaches the reviser.
            feedback = ([_genus_feedback(gv)] if gv else []) + verdicts_fb
            # outstanding issues — genus + non-clean reviewer verdicts; a pass:false with empty strikes
            # still counts ≥1 (Codex S1 #7) so convergence is never declared on a failing verdict.
            issue_count = len(gv) + sum(
                (len(v.get("strikes") or []) or (0 if _verdict_clean(v) else 1))
                for v in verdicts_fb)
            if issue_count == 0:
                improve_converged = True
                break                      # converged — don't churn a clean draft (Codex S1 #6)
            # snapshot BEFORE the call (Codex S1 #14): an improve_fn that MUTATES the draft in place and
            # returns the same object would make `revised == artefato` vacuously true; comparing the
            # returned draft to the pre-call snapshot detects a real in-place change as progress.
            before = json.dumps(artefato, sort_keys=True, default=str)
            try:
                revised = improve_fn(artefato, feedback)
            except Exception:  # noqa: BLE001 — a CRASHING refiner is a non-convergence; fail closed
                improve_plateaued = True   # (Codex S1 #22) preserve the last feedback via the plateau return
                break
            if not isinstance(revised, dict):
                # malformed improver output (non-dict) cannot be genus-checked — fail closed, never
                # pass it to check_genus (Codex S1 #17). Treated as a non-convergence.
                improve_plateaued = True
                break
            if json.dumps(revised, sort_keys=True, default=str) == before:
                improve_plateaued = True
                break                      # plateau with outstanding issues → non-convergence
            artefato = revised

    # A PLATEAU (refiner returned the draft UNCHANGED with issues outstanding) HARD FAILS-CLOSED before
    # the gate: the draft was already reviewed as failing and did NOT change, so re-reviewing it could
    # only let a stateful/flaky reviewer flip to a spurious pass (Codex S1 #12) — never re-review it.
    if improve_plateaued:
        # preserve the LAST blocking feedback (reviewer verdicts + genus violations) so the operator
        # gets actionable strikes, not an opaque closed failure — no second reviewer pass (Codex S1 #21).
        return {"pass": False, "artefato": artefato, "verdicts": verdicts_fb,
                "genus_violations": gv, "non_convergence": True}

    # An EXHAUSTED improve stage (ran the full backstop while still CHANGING the draft) gets exactly ONE
    # verification review at the gate with NO re-produce bounce: a draft the FINAL improve happened to fix
    # can still converge and mint (Codex S1 #13), while a still-broken draft fails closed and cannot be
    # milked via a bounce (Codex S1 #9). A converged or skipped stage keeps the normal bound (BOUNCE_MAX).
    bounce_budget = 0 if (improve_attempted and not improve_converged) else BOUNCE_MAX

    bounces = 0
    while True:
        ground_visuals(artefato)   # S7 (R2): sign cite-grounded visuals before the gating genus check
        violations = check_genus(artefato)
        if violations:
            if bounces >= bounce_budget:
                return {"pass": False, "artefato": artefato, "verdicts": [],
                        "genus_violations": violations}
            bounces += 1
            # re-produce from the NAMED gap: when improve_fn is wired, hand it the genus
            # violations so the draft is enriched (the floor forces depth); else the unchanged
            # static produce_fn bounce (Codex P2, #30).
            if improve_fn is not None:
                try:
                    revised = improve_fn(artefato, [_genus_feedback(violations)])
                except Exception:  # noqa: BLE001 — crashing refiner → fail closed with the violations (#22)
                    return {"pass": False, "artefato": artefato, "verdicts": [],
                            "genus_violations": violations, "non_convergence": True}
                if not isinstance(revised, dict):
                    # malformed improver output cannot be genus-checked → fail closed, never pass a
                    # non-dict to the next check_genus (Codex S1 #18).
                    return {"pass": False, "artefato": artefato, "verdicts": [],
                            "genus_violations": violations, "non_convergence": True}
                artefato = revised
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
            # normalize a malformed RETURN before identity stamping — an identity-stamped reviewer that
            # returns a non-dict would crash the `{**v, ...}` spread otherwise (Codex S1 #19).
            v = _normalize_verdict(v)
            # stamp the canonical reviewer identity (#3) — only the canonical reviewers carry
            # an `.identity`; an injected fake reviewer leaves the verdict unstamped, so the
            # minted proof will fail verify_proof's identity check.
            identity = getattr(r, "identity", None)
            if identity is not None:
                v = {**v, "reviewer": identity}
            verdicts.append(v)
        # R5/S1 default-deny: a residual that isn't a proven non-blocking note becomes a strike,
        # so a blocking finding mischanneled into `residual` fails the close CLOSED (not on trust).
        verdicts = [_sanitize_verdict_residual(v) for v in verdicts]
        # R9 discharge is DELIBERATELY NOT applied here (Codex S4 #1): the gating close is the AUTHORITATIVE
        # final review and must require the CURRENT reviewers to be clean on every non-genus blocking
        # finding. Discharge is a single-absence heuristic — applying it at the mint would let ONE reviewer
        # false-negative permanently suppress a still-unresolved strike and mint a proof for it. Discharge
        # lives ONLY in the improve loop (anti-churn); this gate is the backstop that catches a finding the
        # loop discharged prematurely, so a genuinely-unresolved blocker can never mint.
        if all(_verdict_clean(v) for v in verdicts):
            proof = _mint_proof(
                verdicts,
                slug=artefato.get("slug"), spec=artefato.get("content"),
                intent=artefato.get("intent"), cites=artefato.get("cites"),
                proposes=artefato.get("proposes"),
                distills=artefato.get("distills"), skill=artefato.get("skill"),
                lineage=artefato.get("lineage"))
            if publish_fn is not None:
                publish_fn(artefato, proof)
            return proof
        if bounces >= bounce_budget:
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
