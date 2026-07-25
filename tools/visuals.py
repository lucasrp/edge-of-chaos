"""Slice 4 — the grounded 2-spot visual post-pass (D-E). The ONLY place a chart/diagram enters a
conductor report: Slices 1-3 hold the GLOBAL VISUAL INVARIANT (no node emits a drawn visual), so the
whole assembled `content` reaches here visual-free, and `add_visuals` adds AT MOST 2 genuinely good,
GROUNDED visuals — read from the full report + evidence, never fabricated.

Design (ed-research, sharpened against the real APIs):
  - the role-mark / "data drives the marks" check is NOT SVG-primitive-counting (verified wrong for
    vl-convert: bars are <path>, a line is one path, the dag has no per-datum aria role). It reduces
    to the EXISTING `render.chart_renderable`/`diagram_renderable` (recipe valid + actually renders —
    and the recipe builders fail closed on empty data, so a renderable chart HAS data-driven marks by
    construction) PLUS non-empty data + landscape (chart) / node-cap + density (graph, anti-hairball).
  - GROUND-BY-ATTRIBUTION: every datum/edge must trace to a span that exists in the EVIDENCE (not the
    report prose — the laundering guard). A datum whose value/label isn't in an evidence-resident span
    is rejected; no partial visuals; no iterate-to-fabricate.
  - dispatch_fn is the injected #40 subagent seam (role-tagged: selector | builder). None => SAFE
    NO-OP (zero spend). <=3 dispatches total (1 selector + <=2 builders).

`add_visuals(content, *, evidence, dispatch_fn=None, max_visuals=2) -> (content, flags)` ALWAYS returns
a dict for `content` (the caller assigns it to artefato["content"] and then close.run_close re-runs
check_genus on the spliced spec — a bad visual still bounces there). NEVER raises."""
from __future__ import annotations

import copy
import re

import close
import conductor
import render
import visual_grounding  # S7/R2: sign each grounded splice with its unforgeable attestation
import visual_recipes

_GRAPH_NODE_CAP = 12            # operator's ~<=12; a denser graph is a hairball (Ghoniem/Fekete)


def _norm(s) -> str:
    """Normalize text for attribution matching — reuse the conductor's gap normalizer (casefold,
    punctuation→space, whitespace-collapse) so the corpus and the cited spans agree."""
    return conductor._norm_gap(s if isinstance(s, str) else "")


# ---------------------------------------------------------------------------
# The invariant guard (Slice 3 guarantees content is visual-free on entry)
# ---------------------------------------------------------------------------

def _all_sections(content: dict) -> list:
    """Every section the render stack draws — BOTH `sections` and `additional_sections` (spec_to_html
    renders both), so the invariant guard and the report-text reader can't miss a visual hiding in the
    additional list."""
    return list(content.get("sections") or []) + list(content.get("additional_sections") or [])


def _existing_drawn_visuals(content: dict) -> set:
    """The drawn-visual block types already present in `content` (should be EMPTY — Slice 3)."""
    found = set()
    for s in _all_sections(content):
        for b in (s.get("blocks") or []):
            t = render.canonical_block(b)[0]
            if t in conductor._DRAWN_VISUALS:
                found.add(t)
    return found


def _assert_no_drawn_visuals(content: dict) -> None:
    """Belt-and-braces (test mode): raise iff content already carries a drawn visual — that would be a
    Slice-3 regression, not a Slice-4 failure. Production `add_visuals` skips+flags instead of raising."""
    pre = _existing_drawn_visuals(content)
    assert not pre, f"content already carries drawn visuals (Slice-3 invariant broken): {sorted(pre)}"


# ---------------------------------------------------------------------------
# Grounding — every datum/edge must trace to a span that EXISTS in the evidence
# ---------------------------------------------------------------------------

# A number token: a digit run that may carry internal grouping/decimal separators ('.' or ',') —
# `_parse_number` then classifies thousands-grouping vs decimal for BOTH locales (EN 0.91 / 3,000 and
# PT 0,91 / 3.000). The leading '-' counts only at a token boundary (so a range '30-40' is two
# positives, not -40; and 'v1.2' is not matched mid-word).
_NUM_TOKEN_RE = re.compile(r"(?<![\w.,])-?\d(?:[\d.,]*\d)?")
# Sentence/clause delimiters: punctuation AND coordinating conjunctions (en+pt). A '.' or ',' splits
# ONLY when NOT followed by a digit, so a decimal/grouped number (EN 0.91 / 3,000, PT 0,91 / 3.000)
# stays one token while a sentence-ending '10.' or a clause comma 'a, b' still splits.
_UNIT_SPLIT_RE = re.compile(r"[.,](?!\d)|[;:\n]+|\s+(?:and|or|e|ou)\s+", re.IGNORECASE)
_GROUPED_INT_RE = re.compile(r"\d{1,3}(?:[.,]\d{3})+")   # 3,000 / 1.000.000 / 1,234,567
_DECIMAL_RE = re.compile(r"\d+[.,]\d+")                  # 0.91 / 0,91 (single separator)


def _evidence_parts(evidence: dict) -> list[str]:
    parts = [str((evidence or {}).get("text") or "")]
    for f in ((evidence or {}).get("findings") or []):
        if isinstance(f, dict):
            parts += [str(f.get("claim", "")), str(f.get("bears_on", "")), str(f.get("citation", ""))]
    return parts


def _corpus(evidence: dict) -> str:
    """The normalized evidence corpus: the raw evidence text + every seed finding's claim/bears_on/
    citation. The laundering guard checks a builder's cited source EXISTS here (the evidence), never
    just in the report prose."""
    return _norm(" ".join(_evidence_parts(evidence)))


def _parse_number(tok: str):
    """Parse a number token to a float, classifying its separators (locale-agnostic): groups of 3 →
    thousands separator (3,000 / 1.000.000 → 3000); a single '.' or ',' → decimal (0.91 / 0,91 → 0.91).
    Returns None if unparseable. This is what makes a PT comma-decimal evidence ground correctly."""
    neg = tok.startswith("-")
    t = tok.lstrip("+-")
    try:
        if "." in t and "," in t:
            # mixed separators (1,234.56 / 1.234,56): the LAST separator is the decimal point, the
            # earlier ones are thousands grouping.
            last = max(t.rfind("."), t.rfind(","))
            val = float(re.sub(r"[.,]", "", t[:last]) + "." + t[last + 1:])
        elif _GROUPED_INT_RE.fullmatch(t):
            val = float(t.replace(",", "").replace(".", ""))
        elif _DECIMAL_RE.fullmatch(t):
            val = float(t.replace(",", "."))
        else:
            val = float(re.sub(r"[.,]", "", t) or "0")  # bare integer or stray separators
    except ValueError:
        return None
    return -val if neg else val


def _raw_number_seq(raw: str) -> list:
    """The EXACT numeric values in a raw (pre-normalization) chunk, IN ORDER of appearance — parsed
    BEFORE `_norm` strips the separators, so 0.91 / 0,91 stay 0.91 (not 0 and 91). Order lets a
    multi-number datum (slopegraph before/after, scatter x/y) be verified as a SUBSEQUENCE, rejecting
    a swapped pair (Codex P2); exact (signed) values reject `10` riding on `100`."""
    out = []
    for m in _NUM_TOKEN_RE.findall(raw):
        v = _parse_number(m)
        if v is not None:
            out.append(v)
    return out


def _evidence_units(evidence: dict) -> list[dict]:
    """The evidence split into sentence/CLAUSE units on `. ; , : \\n` + conjunctions — clause-level, so
    a fabricated label↔value pairing assembled from two facts in ONE sentence fails (a cross-pair
    within 'slice one closed 3, slice three closed 7' is split apart — Codex P1). Each unit carries its
    normalized `text` (for token matching) AND its ordered `num_seq` (parsed from the RAW chunk, so
    decimals survive and order is preserved). Association binds to a single unit (the evidence's OWN
    granularity, not a builder-controlled span), so a coarse 'cite the whole document' span can't
    defeat the binding."""
    units = []
    for part in _evidence_parts(evidence):
        for chunk in _UNIT_SPLIT_RE.split(part or ""):
            text = _norm(chunk or "")
            if text:
                units.append({"text": text, "num_seq": _raw_number_seq(chunk or "")})
    return units


def _is_subsequence(needle: list, hay: list) -> bool:
    """True iff `needle` appears in `hay` in order (a subsequence) — so an ordered multi-number datum
    must match the evidence's number ORDER, not just its set (rejecting a swapped before/after)."""
    it = iter(hay)
    return all(n in it for n in needle)   # `n in it` advances the shared iterator past the match


def _token_pos(needle: str, text: str) -> int:
    """The index of the whole-token run `needle` in `text` (-1 if absent), for directional ordering."""
    return f" {text} ".find(f" {needle} ")


# The CLOSED set of visible chart-level / diagram-level author chrome (post-canonicalization). These
# render as the chart/diagram title and axis/stage labels — text in the reader's eye-line that NAMES
# the data, so a fabricated axis title ("revenue" on attendance data) misleads even when every datum
# is grounded. They have no structural regularity to walk generically, so they are named here; the
# guard tests (test_visuals) tie these tuples to BLOCK_SCHEMAS so a new visible field fails closed.
_CHART_TEXT_FIELDS = ("title", "x_label", "y_label", "before_label", "after_label")
_DIAGRAM_TEXT_FIELDS = ("title",)


def _token_match(needle: str, text: str) -> bool:
    """Whole-TOKEN containment: `needle` (a normalized, possibly multi-word string) must appear as a
    contiguous token run in `text`, not an arbitrary substring — so a fabricated label 'a' does NOT
    match 'alpha' (Codex P2). Space-padding makes the match respect word boundaries."""
    return f" {needle} " in f" {text} "


def _str_grounded(value, units) -> bool:
    """A node/edge label (a verbatim ENTITY) is grounded iff its normalized form is a whole-token run in
    some evidence unit's text. Blank / non-str → vacuously grounded (nothing visible)."""
    t = _norm(value) if isinstance(value, str) else ""
    return True if not t else any(_token_match(t, u["text"]) for u in units)


def _chrome_grounded(value, units) -> bool:
    """Chart/diagram CHROME (title, axis/stage labels) is COMPOSED descriptive text, rarely a verbatim
    span — so ground it PER-TOKEN: every word must appear as a whole token in some evidence unit. Still
    catches a fabricated key word (a 'revenue' axis on attendance data fails) while allowing honest
    composed phrasing ('Defects closed per slice') that isn't a contiguous evidence substring."""
    t = _norm(value) if isinstance(value, str) else ""
    if not t:
        return True
    return all(any(_token_match(tok, u["text"]) for u in units) for tok in t.split())


# The SEMANTIC numeric-field order per recipe — the order the values are read in for the subsequence
# check. JSON key order is NOT reliable (a builder may emit {"y":20,"x":10}), so order by FIELD
# meaning (x before y, before before after), not by dict insertion (Codex P2).
_CHART_NUM_ORDER = {"bar": ["value"], "line": ["x", "y"], "scatter": ["x", "y"],
                    "slopegraph": ["before", "after"]}


def _ordered_datum_nums(d: dict, recipe: str) -> list:
    order = _CHART_NUM_ORDER.get(recipe, [])
    nums = [float(d[f]) for f in order
            if isinstance(d.get(f), (int, float)) and not isinstance(d.get(f), bool)]
    nums += [float(v) for k, v in d.items()          # any extra numeric field, after the known ones
             if k not in order and isinstance(v, (int, float)) and not isinstance(v, bool)]
    return nums


def _datum_grounded(d: dict, units, recipe: str, sibling_labels=()) -> bool:
    """A chart datum is grounded iff SOME single evidence unit contains ALL its visible fields — every
    string field as a whole-TOKEN run of the unit text AND its numeric values (in RECIPE-SEMANTIC field
    order, not JSON key order) as an ordered SUBSEQUENCE of the unit's MEASURE numbers. Guards:
      - single-unit binding blocks a cross-unit label↔value association (Codex P1);
      - a unit that ALSO contains a SIBLING datum's label is AMBIGUOUS (two facts packed with no
        delimiter, e.g. 'alpha 10 beta 20') — it is SKIPPED, so a mispaired {alpha,20} can't ground
        (the chart drops rather than ships a wrong pairing — Codex P1);
      - ordered-subsequence + exact signed values block a swapped before/after, a `10` riding on `100`,
        a wrong sign (Codex P2); token matching blocks 'a' riding on 'alpha';
      - numbers EMBEDDED in the datum's OWN labels (the '1' in a '1k' category) are removed from the
        candidate measures, so a fabricated value can't ride on a numeric label (Codex P2)."""
    nums = _ordered_datum_nums(d, recipe)
    strs = [_norm(v) for v in d.values() if isinstance(v, str) and _norm(v)]
    if not nums and not strs:
        return False
    own = set(strs)
    others = [s for s in sibling_labels if s and s not in own]
    label_nums = [n for v in d.values() if isinstance(v, str) for n in _raw_number_seq(v)]
    for u in units:
        if not all(_token_match(t, u["text"]) for t in strs):
            continue
        if any(_token_match(o, u["text"]) for o in others):
            continue                   # unit mixes a sibling fact → ambiguous binding, skip
        measure = list(u["num_seq"])
        for ln in label_nums:          # a label's own number is not an available measure value
            if ln in measure:
                measure.remove(ln)
        if _is_subsequence(nums, measure):
            return True
    return False


def attributable(block: dict, provenance: list, evidence: dict) -> tuple[bool, str]:
    """True iff EVERY reader-visible, model-authored surface of the rendered chart/diagram traces to the
    EVIDENCE. The builder must first ATTEST (>=1 provenance source that exists in the evidence corpus —
    the laundering guard); the actual binding then resolves against the evidence's OWN sentence/clause
    UNITS, not the builder's spans, so association can't be gamed by a coarse citation. Recipe-agnostic
    over the CLOSED recipe set: grounds every datum field (single-unit + EXACT numbers), every chart/
    diagram title + axis/stage label (per-token), every node's visible text (label, ELSE id — covers
    ISOLATED nodes), and every edge label. Strict: a partial or laundered visual is rejected whole."""
    corpus = _corpus(evidence)
    units = _evidence_units(evidence)
    cited = [_norm(p.get("source", "")) for p in provenance
             if isinstance(p, dict) and isinstance(p.get("source"), str)]
    if not any(c and c in corpus for c in cited):  # attestation + laundering: cite a real evidence span
        return False, "no cited source resolves to the evidence"
    btype, canon = render.canonical_block(block)

    if btype == "chart":
        for fld in _CHART_TEXT_FIELDS:  # (R3) chart-level chrome that names the data (per-token)
            if not _chrome_grounded(canon.get(fld), units):
                return False, f"chart {fld} not attributable to the evidence: {canon.get(fld)!r}"
        # A slopegraph renders a HARDCODED English default ('before'/'after') when these are absent —
        # so the builder MUST supply them (the chrome loop above then grounds them). This keeps the
        # axis in-language and every rendered surface grounded (Codex P2).
        if canon.get("chart") == "slopegraph":
            for fld in ("before_label", "after_label"):
                if not (isinstance(canon.get(fld), str) and canon[fld].strip()):
                    return False, f"slopegraph must supply a grounded {fld} (an English default would ship)"
        data = canon.get("data") or []
        if not isinstance(data, list) or not data:
            return False, "chart carries no data"
        # every string label across the data — a datum may not bind in a unit that ALSO holds another
        # datum's label (an undelimited multi-fact unit is too ambiguous to pair safely).
        all_labels = {_norm(v) for dd in data if isinstance(dd, dict)
                      for v in dd.values() if isinstance(v, str) and _norm(v)}
        for d in data:
            if isinstance(d, dict):
                if not (any(isinstance(v, (int, float)) and not isinstance(v, bool) for v in d.values())
                        or any(isinstance(v, str) and _norm(v) for v in d.values())):
                    return False, f"chart datum has no attributable fields: {d}"
                if not _datum_grounded(d, units, canon.get("chart"), sibling_labels=all_labels):
                    return False, f"chart datum not attributable to a single evidence unit: {d}"
            elif isinstance(d, (int, float)) and not isinstance(d, bool):
                if not any(float(d) in u["num_seq"] for u in units):  # sparkline scalar (exact)
                    return False, f"sparkline value not attributable to the evidence: {d}"
            else:
                return False, f"chart datum is not a dict or number: {d!r}"
        return True, ""

    if btype == "diagram":
        for fld in _DIAGRAM_TEXT_FIELDS:  # (R6) diagram-level chrome (per-token)
            if not _chrome_grounded(canon.get(fld), units):
                return False, f"diagram {fld} not attributable to the evidence: {canon.get(fld)!r}"
        nodes = canon.get("nodes") or []
        if not isinstance(nodes, list) or not nodes:
            return False, "graph carries no nodes"
        # (R4) the VISIBLE text per node = label if present, ELSE the id (which renders as the node
        # text when no label). Iterating NODES (not edges) grounds ISOLATED nodes too.
        vis = {}
        for n in nodes:
            if not isinstance(n, dict) or "id" not in n:
                return False, f"graph node missing id: {n!r}"
            label = n.get("label")
            visible = label if (isinstance(label, str) and label.strip()) else str(n["id"])
            if not _str_grounded(visible, units):
                return False, f"node label not attributable to the evidence: {visible!r}"
            vis[n["id"]] = _norm(visible)
        edges = canon.get("edges") or []
        if not isinstance(edges, list):
            return False, "graph edges is not a list"
        for e in edges:
            if not isinstance(e, dict):
                return False, "graph edge is not a dict"
            s_lbl, t_lbl = vis.get(e.get("source"), ""), vis.get(e.get("target"), "")
            if not s_lbl or not t_lbl:
                return False, f"edge endpoint has no groundable label: {e}"
            # (R5) the RELATION must be asserted together — both endpoint texts AND the edge's own label
            # (if any) in ONE evidence unit. Grounding the label separately would let an A→B edge wear a
            # 'blocks' label from an unrelated 'C blocks D' sentence (Codex P2). For a DIRECTED layout
            # (dag), the source must also appear textually BEFORE the target, so a reversed B→A edge of
            # an 'A feeds B' relation is rejected (Codex P2); force is undirected, so order is ignored.
            elbl = _norm(e.get("label")) if isinstance(e.get("label"), str) else ""
            directed = canon.get("layout") == "dag"

            def _unit_supports_edge(u):
                txt = u["text"]
                if not (_token_match(s_lbl, txt) and _token_match(t_lbl, txt)):
                    return False
                if elbl and not _token_match(elbl, txt):
                    return False
                if directed and _token_pos(s_lbl, txt) >= _token_pos(t_lbl, txt):
                    return False
                return True

            if not any(_unit_supports_edge(u) for u in units):
                return False, f"edge (direction/label) not attributable to a single evidence unit: {e}"
        return True, ""
    # `ascii-diagram` is intentionally NOT groundable (operator decision, S7): a free-form ascii relation
    # can't be soundly grounded (its endpoints+direction+label aren't structurally parseable the way a
    # `diagram` edge is), and with the renderable `diagram`/`chart` recipes present it carries no advantage.
    # An authored ascii-diagram is therefore rejected by close. raw-html/svg are likewise unsupported.
    return False, f"unsupported visual type {btype!r}"


# ---------------------------------------------------------------------------
# Quality gates — reuse the renderable predicates (NOT SVG-counting); add data/landscape/cap
# ---------------------------------------------------------------------------

def _is_landscape(spec: dict) -> bool:
    """A chart spec is landscape iff width >= height — handling the faceted shape where the top level
    drops width/height and the inner `spec` carries them."""
    for d in (spec, spec.get("spec") or {}):
        w, h = d.get("width"), d.get("height")
        if isinstance(w, (int, float)) and isinstance(h, (int, float)):
            return w >= h
    return True  # unknown sizing → don't block on it


def chart_block_ok(block: dict) -> tuple[bool, str]:
    """A chart block ships iff it has non-empty data, ACTUALLY renders (render.chart_renderable), and
    is landscape. Reads the CANONICAL data (so `values`/`rows` synonyms are accepted, matching what
    build_chart/render consume). The renderable check already proves the data drives the marks (the
    recipe builders fail closed on empty data) — so no SVG-primitive-counting is needed."""
    _t, canon = render.canonical_block(block)
    data = canon.get("data")
    if not isinstance(data, list) or not data:
        return False, "chart has no data"
    spec, err = visual_recipes.build_chart(block)
    if err:
        return False, f"chart build error: {err}"
    if not render.chart_renderable(block):
        return False, "chart does not render"
    if not _is_landscape(spec):
        return False, "chart is not landscape"
    return True, ""


def _has_cycle(nodes: list, edges: list) -> bool:
    """True iff the directed edge set has a cycle (DFS 3-color). A cyclic dag would lose a back-edge
    in the Sugiyama layout, so it must not pass as a dag."""
    adj: dict = {}
    for e in edges:
        if isinstance(e, dict) and e.get("source") is not None:
            adj.setdefault(e["source"], []).append(e.get("target"))
    ids = [n.get("id") for n in nodes if isinstance(n, dict)]
    color: dict = {}

    def visit(u) -> bool:
        color[u] = 1  # gray (on the stack)
        for v in adj.get(u, []):
            if color.get(v, 0) == 1:
                return True
            if color.get(v, 0) == 0 and visit(v):
                return True
        color[u] = 2  # black (done)
        return False

    return any(color.get(u, 0) == 0 and visit(u) for u in ids)


def graph_block_ok(block: dict) -> tuple[bool, str]:
    """A graph ships iff it has 2..CAP nodes, >=1 edge, is NOT too dense (anti-hairball:
    edges <= 2*nodes), and ACTUALLY renders (render.diagram_renderable, which validates topology).
    Reads CANONICAL nodes/edges so the `links` synonym is accepted (matching build_diagram/render)."""
    _t, canon = render.canonical_block(block)
    nodes = canon.get("nodes")
    edges = canon.get("edges") or []
    if not isinstance(nodes, list) or len(nodes) < 2:
        return False, "graph needs >= 2 nodes"
    if len(nodes) > _GRAPH_NODE_CAP:
        return False, f"graph too large ({len(nodes)} > {_GRAPH_NODE_CAP} nodes)"
    if not isinstance(edges, list) or len(edges) < 1:
        return False, "graph needs >= 1 edge"
    if len(edges) > 2 * len(nodes):
        return False, f"relation too dense for a readable graph ({len(edges)} edges / {len(nodes)} nodes)"
    if canon.get("layout") == "dag" and _has_cycle(nodes, edges):
        # the dag layout drops back-edges to terminate — a cycle would render with a relationship
        # silently missing. Reject (a true cycle should use force, or drop the back-edge) — Codex P2.
        return False, "directed graph has a cycle (would render with a dropped edge)"
    if not render.diagram_renderable(block):
        return False, "graph does not render"
    return True, ""


# ---------------------------------------------------------------------------
# The selector + builders (one dispatch each, role-tagged)
# ---------------------------------------------------------------------------

def _report_text(content: dict) -> str:
    out = []
    for i, s in enumerate(_all_sections(content)):
        out.append(f"[section {i}] {s.get('title', '')}")
        for b in (s.get("blocks") or []):
            out.append(close._block_text(b))
    return "\n".join(out)


def _evidence_text(evidence: dict) -> str:
    """The readable evidence shown to the selector/builder — the raw text AND every finding's
    claim/bears_on/citation (the SAME parts attribution resolves against). A finding-only evidence
    (the seed shape: findings, no top-level `text`) must NOT yield an empty prompt, else the post-pass
    silently no-ops (Codex P2)."""
    return "\n".join(p for p in _evidence_parts(evidence) if p and p.strip())


def _selector_prompt(content: dict, evidence: dict, max_visuals: int) -> str:
    return (
        f"You select AT MOST {max_visuals} spots in a finished report that would each be made CLEARER "
        "by ONE visual — and nothing where the prose already says it in a sentence. Propose a visual "
        "ONLY if it shows something the reader cannot see at a glance from the prose: a magnitude "
        "comparison across >=3 items or a trend over an ordered sequence (a CHART), or a small, sparse "
        "causal/dependency structure (a GRAPH). If the data is <=2 points or already plain in prose, "
        "do NOT propose it. Every spot must name data/relations that exist in the evidence.\n\n"
        f"THE REPORT:\n{_report_text(content)}\n\n"
        f"THE EVIDENCE:\n{_evidence_text(evidence)}\n\n"
        'Return STRICT JSON only: {"spots": [{"section_index": <int>, "visual_kind": "chart"|"graph", '
        '"intent": "the question this visual answers", "rationale": "why it out-informs the prose"}]}')


def _builder_prompt(spot: dict, evidence: dict) -> str:
    kind = spot.get("visual_kind")
    if kind == "chart":
        shape = ('{"block": {"type":"chart","chart":"<recipe>","data":[...],"title":...}, '
                 '"provenance": [{"datum":{...}, "source":"<verbatim evidence span the datum came from>"}]}. '
                 "Pick ONE recipe and use ITS data shape: bar → data:[{label, value}] (+x_label/y_label); "
                 "line/scatter → data:[{x, y}] (+x_label/y_label); slopegraph → data:[{item, before, after}] "
                 "AND before_label + after_label. Every datum field must come from the evidence.")
    else:
        shape = ('{"block": {"type":"diagram","layout":"dag|force",'
                 '"nodes":[{"id":...,"label":...}],"edges":[{"source":...,"target":...,"label":...}]}, '
                 '"provenance": [{"edge":{"source":...,"target":...}, "source":"<evidence span asserting '
                 'that relation>"}]}')
    return (
        f"Build ONE {kind} that answers: {spot.get('intent', '')}.\n"
        "EVERY datum/edge must come from the evidence below and cite the exact span it came from in "
        "`provenance`. Do NOT invent values or relations. Keep a graph small (<=12 nodes) and sparse.\n\n"
        f"THE EVIDENCE:\n{_evidence_text(evidence)}\n\n"
        f"Return STRICT JSON only: {shape}")


def _resolve_section(content: dict, spot: dict):
    """Resolve a spot to an index into the COMBINED `_all_sections` list — the SAME enumeration the
    selector prompt showed (sections + additional_sections), so an index the selector returns maps to
    the section it actually saw (splice_visuals maps the combined index back to the right sublist)."""
    secs = _all_sections(content)
    si = spot.get("section_index")
    if isinstance(si, int) and 0 <= si < len(secs):
        return si
    anchor = spot.get("anchor")
    if isinstance(anchor, str) and anchor.strip():
        a = anchor.strip().lower()
        for i, s in enumerate(secs):
            if a in (s.get("title") or "").lower():
                return i
    return None  # unresolved → splice as a trailing section


def select_spots(content: dict, evidence: dict, dispatch_fn, max_visuals: int) -> list[dict]:
    """One selector dispatch → <= max_visuals well-formed spot dicts (each carrying a resolved
    `_section_index`). A garbled response yields [] (ship with no visual), never a crash."""
    if max_visuals <= 0:
        return []
    raw = dispatch_fn(role="selector", prompt=_selector_prompt(content, evidence, max_visuals))
    data = conductor._parse_envelope(raw) or {}
    spots = data.get("spots")
    if not isinstance(spots, list):
        return []
    out = []
    for s in spots:
        if len(out) >= max_visuals:   # check BEFORE appending so a 0/N cap is exact
            break
        if isinstance(s, dict) and s.get("visual_kind") in ("chart", "graph"):
            s = dict(s)
            s["_section_index"] = _resolve_section(content, s)
            out.append(s)
    return out


# OPTIONAL chrome that is decoration, not data: if it doesn't ground it is STRIPPED (so a fabricated
# title/axis can't mislead) rather than killing an otherwise data-grounded visual. NOTE: slopegraph
# before_label/after_label are deliberately NOT here — their absence ships a hardcoded English default,
# so they stay REQUIRED+grounded in `attributable`.
_STRIPPABLE_CHROME = {"chart": ("title", "x_label", "y_label"), "diagram": ("title",)}


def sanitize_chrome(block: dict, evidence: dict) -> dict:
    """Return a copy of `block` with ungrounded optional chrome (chart title/axis labels, diagram
    title) removed — decoration the reader can lose, unlike the data. Keeps a data-grounded visual
    alive while still preventing a fabricated label from shipping (it is dropped, not displayed)."""
    btype, _ = render.canonical_block(block)
    fields = _STRIPPABLE_CHROME.get(btype, ())
    if not fields:
        return block
    units = _evidence_units(evidence)
    out = dict(block)
    for f in fields:
        if f in out and not _chrome_grounded(out.get(f), units):
            out.pop(f, None)
    return out


def build_spot(spot: dict, evidence: dict, dispatch_fn) -> tuple[dict | None, str]:
    """One builder dispatch → a verified visual block, or (None, reason). Strips ungrounded decoration,
    grounds by attribution against the evidence, then verifies it renders + passes the chart/graph
    quality gate. Fail closed."""
    raw = dispatch_fn(role="builder", prompt=_builder_prompt(spot, evidence))
    data = conductor._parse_envelope(raw)
    if not data:
        return None, "builder returned no parseable payload"
    block, provenance = data.get("block"), data.get("provenance")
    if not isinstance(block, dict) or not isinstance(provenance, list):
        return None, "builder payload missing block/provenance"
    block = sanitize_chrome(block, evidence)   # drop ungrounded decoration, keep the data-grounded visual
    ok, why = attributable(block, provenance, evidence)
    if not ok:
        return None, f"ungrounded: {why}"
    ok, why = (chart_block_ok(block) if spot.get("visual_kind") == "chart" else graph_block_ok(block))
    return (block, "") if ok else (None, why)


def splice_visuals(content: dict, picks: list[dict]) -> dict:
    """Pure: deep-copy `content`, append each pick's block to the END of its target section (where the
    prose it augments lives — sections are FREE, ADR-0012/0013), or a new trailing section when the
    anchor didn't resolve. The pick's `section_index` is a COMBINED `_all_sections` index (same space
    as the selector + `_resolve_section`); it's mapped back to the right sublist here. Returns a NEW
    spec; the caller's dict is never mutated."""
    out = copy.deepcopy(content)
    combined = _all_sections(out)  # references into out["sections"] + out["additional_sections"]
    for p in picks:
        si, block = p.get("section_index"), p["block"]
        if isinstance(si, int) and 0 <= si < len(combined):
            combined[si].setdefault("blocks", []).append(block)
        else:
            out.setdefault("sections", []).append({"title": "", "blocks": [block]})
    return out


def add_visuals(content: dict, *, evidence: dict, dispatch_fn=None,
                max_visuals: int = 2) -> tuple[dict, list[str]]:
    """The grounded visual post-pass. dispatch_fn None => SAFE NO-OP. Else: select <=max_visuals
    grounded spots, build+verify each, splice the survivors. Returns (content_spec, flags) — content
    is ALWAYS a dict (close.run_close re-genus-checks it next); flags log every shortfall/drop (no
    silent caps). NEVER raises; on any internal failure it ships the report WITHOUT a forced visual."""
    if dispatch_fn is None:
        return content, []
    pre = _existing_drawn_visuals(content)
    if pre:  # Slice-3 invariant broken upstream — ship the report, don't crash; flag it loudly.
        return content, [f"skipped visual post-pass: content already carries {sorted(pre)}"]
    flags: list[str] = []
    try:
        spots = select_spots(content, evidence, dispatch_fn, max_visuals)
    except Exception as exc:  # noqa: BLE001 — a selector failure must never sink the report
        return content, [f"selector failed ({exc!r}); shipped without visuals"]
    picks = []
    for i, spot in enumerate(spots):
        try:
            block, reason = build_spot(spot, evidence, dispatch_fn)
        except Exception as exc:  # noqa: BLE001
            block, reason = None, f"builder crashed: {exc!r}"
        if block is None:
            flags.append(f"dropped spot {i} ({spot.get('visual_kind')}): {reason}")
        else:
            picks.append({"block": block, "section_index": spot.get("_section_index")})
    # Shortfall is measured against the SELECTED spots, not the cap (the API promises "at most"
    # max_visuals): a selector that intentionally found 1 worthwhile spot which grounds is NOT a
    # shortfall — only spots that were selected but failed to ground are (Codex P3).
    if len(picks) < len(spots):
        flags.insert(0, f"shortfall: {len(spots)} spot(s) selected, {len(picks)} grounded")
    if not picks:
        return content, flags  # no grounded visual → ship as-is, NEVER fabricate
    # S7 (R2): each pick is `attributable` (build_spot verified it) → mint its unforgeable grounding
    # attestation so it survives close._check_visual_grounding at the publish path.
    for p in picks:
        p["block"] = visual_grounding.sign(p["block"])
    return splice_visuals(content, picks), flags
