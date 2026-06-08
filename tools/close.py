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
import json

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
    violations += _check_visual_coverage(artefato.get("content", {}))
    return violations


def _check_cites(cites: list) -> list[str]:
    violations = []
    for cite in cites:
        if not isinstance(cite, dict):
            continue
        ref = cite.get("ref")
        label = ref or "(cite with no ref)"
        if not ref:
            violations.append(f"cite missing ref: {label}")
        if not cite.get("snippet"):
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


def _check_visual_coverage(content: dict) -> list[str]:
    """Flag "visual-coverage" iff the content has quantitative/multi-value material
    but no visual palette element. Content with no quantitative material owes none."""
    has_quantitative = False
    has_visual = False
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


def _iter_blocks(content: dict):
    """Yield every block across the render-spec's sections (sections are FREE — order
    and names are irrelevant; the genus reads the blocks, not the layout)."""
    for section in content.get("sections", []):
        for block in section.get("blocks", []):
            yield block


# ---------------------------------------------------------------------------
# S7 — the two blind review gates (ADR-0013: blind by evidence-and-session,
# property-not-section, cross-provider). Kept cleanly separate from the genus
# above and from the S8 bounce that will follow.
# ---------------------------------------------------------------------------

# The KEPT dimensions — the legacy 9-dim DIMENSIONS (review-gate.py) minus the two
# report-welded dims (structural_completeness = section-order mandate, storytelling =
# narrative arc). Each def is reworded PROPERTY-NOT-SECTION: the gate checks whether the
# property is present ANYWHERE, genuine and specific — never whether a named section exists.
DIMENSIONS = {
    "content_depth": (
        "Substance, not placeholders: concrete details, data, numbers, real examples. "
        "No empty or stub content; tables carry real data."
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
# dim set changed). The legacy kept-weights summed to 0.73 after dropping structural (.15)
# + storytelling (.12); each is rescaled proportionally by /0.73 so the seven sum to 1.0.
_LEGACY_KEPT_WEIGHTS = {
    "content_depth": 0.15,
    "feynman_method": 0.12,
    "intellectual_honesty": 0.10,
    "didactic_clarity": 0.12,
    "internal_consistency": 0.08,
    "visualization": 0.08,
    "writing_quality": 0.08,
}
_KEPT_SUM = sum(_LEGACY_KEPT_WEIGHTS.values())  # 0.73
DIMENSION_WEIGHTS = {dim: w / _KEPT_SUM for dim, w in _LEGACY_KEPT_WEIGHTS.items()}

# The shared blind-reviewer instruction. Each reviewer prepends its own focus. The reviewer
# sees the FINAL Artefato text + its cites ONLY — evidence, session, and briefing are denied.
_BLIND_PREAMBLE = (
    "You are a blind quality reviewer for a published Artefato. You see ONLY the artefato's "
    "final content and its cites — you have NO access to the evidence the author read, the "
    "session/transcript, or the briefing. Judge only what is in front of you. Score each "
    "dimension 0-5. Respond with ONLY a JSON object: "
    '{"pass": bool, "scores": {dim: int}, "strikes": [str], "overall": float}.'
)

_FEYNMAN_FOCUS = (
    "FOCUS: rigor and intellectual honesty. The BLINDFOLD test — every claim must be "
    "re-sourceable from its cite; a claim that cannot be traced to a cite is struck "
    "(add it to `strikes` and fail). Check the derived/repeated/unknown knowledge-boundary "
    "is explicit, specific, and present anywhere — not boilerplate."
)

_REGULAR_FOCUS = (
    "FOCUS: clarity and craft. Substance, didactic clarity (every term comprehensible "
    "somewhere), flowing prose, internal consistency, and content-relative visualization."
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


def _parse_verdict(raw: str) -> dict:
    """Parse the reviewer's JSON verdict into {pass, scores, strikes, overall}, computing the
    weighted overall from the dim scores when the model omits/garbles it."""
    text = raw.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        if text.endswith("```"):
            text = text[:-3].strip()
    result = json.loads(text)
    scores = result.get("scores", {})
    strikes = result.get("strikes", [])
    overall = sum(scores.get(dim, 0) * w for dim, w in DIMENSION_WEIGHTS.items())
    return {
        "pass": bool(result.get("pass", False)),
        "scores": scores,
        "strikes": strikes,
        "overall": round(float(overall), 2),
    }


def _review(focus: str, artefato: dict, complete_fn) -> dict:
    """Run one blind reviewer: build the blind prompt, hand it to the injected completer,
    parse the verdict. `complete_fn(prompt) -> str` is injectable so tests run offline;
    real runs pass a make_client-backed completer on the review router (Grok)."""
    raw = complete_fn(_build_prompt(focus, artefato))
    return _parse_verdict(raw)


def feynman_review(artefato: dict, complete_fn) -> dict:
    """The feynman gate (rigor + honesty), blind. Returns {pass, scores, strikes, overall}."""
    return _review(_FEYNMAN_FOCUS, artefato, complete_fn)


def regular_review(artefato: dict, complete_fn) -> dict:
    """The regular gate (clarity + craft), blind. Returns {pass, scores, strikes, overall}."""
    return _review(_REGULAR_FOCUS, artefato, complete_fn)


# ---------------------------------------------------------------------------
# S8 — the bounce loop + the loop-2 brake. The bound lives HERE, in the
# protocol constants — never in the producer's discretion. That bound is what
# separates a gate from the retry-envelope ADR-0003 killed (which let a producer
# retry at will). BOUNCE_MAX caps reviewer→producer re-produces; LOOP2_MAX_REOPENS
# caps serendipity's advisory loop-1 reopens. Neither loop can ever run unbounded.
# ---------------------------------------------------------------------------

BOUNCE_MAX = 1            # reviewer strike → re-produce, at most this many times
LOOP2_MAX_REOPENS = 1     # serendipity may reopen loop-1 at most this many times


def run_close(artefato, produce_fn, reviewers=(feynman_review, regular_review),
              complete_fn=None):
    """Run the blind review gate, bounded. BOTH reviewers must pass; any strike/fail
    BOUNCES — `produce_fn()` re-produces the artefato and the gate re-runs — up to
    `BOUNCE_MAX` times. After `BOUNCE_MAX` consecutive failed gates it HARD-FAILS;
    it never loops unbounded (that would resurrect ADR-0003's retry envelope).

    `produce_fn`, `reviewers`, and the reviewers' `complete_fn` are injectable so the
    gate runs offline in tests; real runs pass the make_client-backed completer.

    Returns {pass: True, artefato, verdicts} when both reviewers pass, else
    {pass: False, artefato, verdicts} after the bound is exhausted."""
    bounces = 0
    while True:
        verdicts = [r(artefato, complete_fn) for r in reviewers]
        if all(v["pass"] for v in verdicts):
            return {"pass": True, "artefato": artefato, "verdicts": verdicts}
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
