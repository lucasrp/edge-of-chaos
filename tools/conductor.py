"""conductor — multi-agent artefato production, SLICE 1 (EDGE_CONDUCTOR, dark by default).

A synthesis whose complexity exceeds one context can't be produced well in one pass — the
brevity prior drops the worthwhile tail (the excavate experiment, branch
`feat/excavate-synthetic-grill`). The fix (issue #36) is divide-and-conquer over a shared,
state-tracked outline: the conductor authors an outline of nodes FROM the excavate seed (the
already-mined deep structure — not raw context, which would re-commit the brevity prior at the
structural level), holds each node's lifecycle state, fills each node via the existing producer
cognition, gates it mechanically, and assembles the filled nodes into one artefato `content`.

Slice 1 is exactly that and no more. NOT in slice 1 (slices 2-3, #36): the scoped LLM review
stack (feynman-per-node / whole-doc adversarial / coherence / enrichment-relocation) and the
living-outline split/merge adjudication. The assembled whole still funnels through the existing
whole-artefato `close.run_close` unchanged.

The three-part arc — motivate (why this, why now) → deliver (the new content) → change-the-course
(how it entangles going forward) — is the ACCEPTANCE TEST made structural (the worthwhile-test:
no motivation = no reason to care; no consequence = it didn't change the course). The outline is
authored against it, but it lives at the production layer and is NEVER rendered as labeled
sections (ADR-0012/0013: sections are FREE).

The seed is ASSIGNMENT, not content reduction (#36): every writer gets the FULL seed; the
node's `finding_ids` are its responsibility + anti-drop checklist, so two writers don't develop
the same finding. The model call is INJECTED (`complete_fn`) so the logic tests offline, exactly
like close.py's reviewers and excavate.py.

The writer cognition DEFAULTS to the host agent's OWN subagents, not the gpt-5.4 OpenAI API (#40):
the writer call is a synchronous in-process Python call, but a subagent dispatch is a harness tool
call the Python cannot make — so the SKILL fans one subagent per node and feeds the collected prose
back through the orchestration-layer bridge (`node_briefs` → fan subagents → `subagent_completer`).
The gpt-5.4 route (`_llm.make_client` on the chat router) is then an explicit FALLBACK passed as
`complete_fn`, never the default. The semantic judge (`discharge_fn`) and conciliator
(`conciliate_fn`) are their own injected cognitions (their own subagents under #40).

Gated by EDGE_CONDUCTOR (off => passthrough, today's single-producer pipeline byte-for-byte AND
zero model spend).
"""
from __future__ import annotations

import difflib
import json
import os
import re
from collections import Counter

import close
import render
import blocks as block_validation

# The three-part arc — the structural acceptance test (#36). NEVER rendered as labeled sections;
# it is the production-layer contract the outline is authored against.
ARC_ROLES = ("motivate", "deliver", "change-the-course")

# The per-node lifecycle. The state IS the enabler of divide-and-conquer: it remembers what's
# done, provisional, or safe to build on. A pure, total, forward-only transition.
STATUSES = ("empty", "draft", "revised", "final")
_NEXT = {"empty": "draft", "draft": "revised", "revised": "final", "final": "final"}

_TRUTHY = {"1", "true", "yes", "on"}


def enabled(env=None) -> bool:
    """Read EDGE_CONDUCTOR. Dark by default — only an explicit truthy value turns it on."""
    env = os.environ if env is None else env
    return env.get("EDGE_CONDUCTOR", "").strip().lower() in _TRUTHY


def advance(status: str) -> str:
    """The pure per-node lifecycle transition empty→draft→revised→final. `final` is terminal
    (idempotent); an unknown status is a programming error and raises, never silently coerces."""
    if status not in _NEXT:
        raise ValueError(f"unknown node status {status!r}; expected one of {STATUSES}")
    return _NEXT[status]


def finding_id(i: int) -> str:
    """The stable id of the i-th seed finding — the assignment token a node carries."""
    return f"f{i}"


def _finding_by_id(seed: dict, fid: str) -> dict | None:
    findings = seed.get("findings") or []
    for i, f in enumerate(findings):
        if finding_id(i) == fid:
            return f
    return None


# ---------------------------------------------------------------------------
# Author the outline from the seed — a brand-new, objective-specific index built from the
# already-mined deep structure (#36), authored to cover the three-part arc.
# ---------------------------------------------------------------------------

def author_outline(seed: dict, objective: str) -> list[dict]:
    """Author the outline tree FROM the excavate seed: one `motivate` node, one `deliver` node
    per finding (the deliver part fans so each finding is developed in its own node — multi-node
    by construction, and the anti-drop assignment is exact), and one `change-the-course` node.
    Every node starts `empty` and carries a per-node `contract` (its intent + the seed-finding
    ids it owns). Findings are assigned to the deliver nodes exactly once; motivate and
    change-the-course own no findings (they frame and entangle, not develop).

    Each node also carries its PLACE in the arc — its `position` ("k of N") and the
    `established_upstream` summary (what the prior nodes already set). The place is what fixes the
    '23 different intros' bug (#36): every writer is told the frame is ALREADY set upstream and to
    write as a CONTINUATION, so only the opening node establishes context. The place is authored
    here (the only point that sees the whole arc order); the writer prompt reads it.

    With zero findings the arc is still authored (a single deliver node) — the structural
    contract holds even on an empty seed."""
    findings = seed.get("findings") or []
    nodes: list[dict] = []

    nodes.append(_node("n-motivate", "motivate", [],
                       "Motivate: why this synthesis, why now — the tension the objective opens, "
                       f"aimed at: {objective}"))

    if findings:
        for i, f in enumerate(findings):
            fid = finding_id(i)
            nodes.append(_node(
                f"n-deliver-{i}", "deliver", [fid],
                f"Deliver: develop the finding to plenitude — {f.get('claim', '')} "
                f"(bears on: {f.get('bears_on', '')})"))
    else:
        nodes.append(_node("n-deliver-0", "deliver", [],
                           "Deliver: the new content the objective asks for"))

    nodes.append(_node("n-change", "change-the-course", [],
                       "Change-the-course: how this entangles the mentee's live work going "
                       f"forward — the next bet for: {objective}"))

    _assign_places(nodes)
    _assign_target_forms(nodes, seed)   # Slice 3: per-finding form contract + sibling de-collision
    return nodes


def _node(node_id: str, role: str, finding_ids: list[str], intent: str) -> dict:
    return {
        "id": node_id,
        "role": role,
        "status": "empty",
        "contract": {"intent": intent, "finding_ids": list(finding_ids)},
        # `place` is filled by _assign_places once the whole arc order is known.
        "place": {"position": "", "established_upstream": ""},
    }


def _assign_places(nodes: list[dict]) -> None:
    """Stamp each node's PLACE in the arc, in place: its `position` ("k of N") and an
    `established_upstream` summary of every prior node's role + intent. The opening node has an
    empty upstream (it sets the frame); each downstream node's upstream names the roles/intents
    that precede it — the continuation context the writer opens mid-stream from."""
    total = len(nodes)
    for k, node in enumerate(nodes):
        prior = nodes[:k]
        if prior:
            upstream = "; ".join(
                f"{p['role']}: {p['contract']['intent']}" for p in prior)
        else:
            upstream = ""
        node["place"] = {"position": f"{k + 1} of {total}", "established_upstream": upstream}


# ---------------------------------------------------------------------------
# Slice 3 — plan-then-write: kill structural monotony (D-A) at the SOURCE. Each block-bearing node
# gets a per-finding FORM CONTRACT (`target_form`) so different findings own different shapes; a
# post-fill form gate ENFORCES it; a deterministic reconcile dedups gaps (D-B); a structural
# diversity report measures the result. The diversity-collapse root cause (ed-research, G5): one
# uniform type→format instruction makes the format the attractor — so we vary the instruction.
# ---------------------------------------------------------------------------

# The content forms a node may own. PROSE is always allowed. NONE of these is a DRAWN visual.
_PROSE = ("paragraph", "callout", "list")
_FORM_VOCAB = ("metrics-grid", "comparison-table", "diff-block", "derivation", "gap-table", "table")
# The GLOBAL VISUAL INVARIANT (ed-research, sharpened): a node may NOT emit a chart/diagram or an
# arbitrary-HTML/SVG escape hatch — those can fabricate an UNGROUNDED visual and are Slice-4-only
# (the grounded post-pass). This is a PRECISE subset of close.VISUAL_BLOCK_TYPES — it deliberately
# EXCLUDES metrics-grid/comparison-table/etc., which are grounded structured-data blocks and ARE
# legitimate node forms (they merely also satisfy the visual-coverage gate).
_DRAWN_VISUALS = frozenset({"chart", "diagram", "ascii-diagram", "raw-html", "svg", "html", "custom-html"})
# The gap family is ALWAYS allowed through the form gate (reconcile consolidates it afterward), so a
# writer's open tensions survive enforce_form to be deduped — not stripped before reconcile sees them.
_GAP_TYPES = ("gap-table", "gap-marker", "gap-resolution")

_COMPARE_RE = re.compile(r"\b(vs\.?|versus|compared|than|whereas|unlike|instead of|rather than)\b",
                         re.IGNORECASE)
_BEFORE_AFTER_RE = re.compile(r"\bbefore\b.*\bafter\b|\bwas\b.*\bnow\b", re.IGNORECASE)


def _numeric_magnitudes(text: str) -> int:
    """Count DISTINCT numeric magnitudes in `text`, reusing close's magnitude machinery (DRY with
    D5: the router and the prose gate agree on 'what is a number') — years/versions/dates excluded."""
    t = close._DATE_RE.sub(" ", text or "")
    t = close._VERSION_RE.sub(" ", t)
    t = close._YEAR_RE.sub(" ", t)
    return len({m.group(0).strip().lower() for m in close._MAGNITUDE_RE.finditer(t) if m.group(0).strip()})


def _route_form(finding: dict) -> str:
    """The PRIMARY non-prose form a single finding owes, from its {claim, probe}. Deterministic and
    total — "" means prose-only. The probe (excavate's closed enum: relevance/contradiction/surprise/
    lineage) is the strongest signal; the claim text is the fallback. NEVER routes to a drawn visual."""
    claim = finding.get("claim") or ""
    probe = (finding.get("probe") or "").strip().lower()
    if probe in ("contradiction", "surprise"):
        return "comparison-table"      # two states held against each other
    if probe == "lineage":
        return "derivation"            # a reasoning / where-it-came-from chain
    # relevance (or any unknown probe) → route on the claim text. Check before/after FIRST: a claim
    # like "latency was 200ms before and 80ms after" is numeric-dense too, but its SHAPE is a
    # before/after comparison (diff-block), not a flat metrics grid.
    if _BEFORE_AFTER_RE.search(claim):
        return "diff-block"            # explicit before/after → the finer comparison shape
    if _numeric_magnitudes(claim) >= 2:
        return "metrics-grid"          # numeric-dense claim (NOT chart — visual invariant)
    if _COMPARE_RE.search(claim):
        return "comparison-table"
    return ""                          # prose-only


# Each primary form's RANKED candidates — the de-collision pass walks this so a forced demotion still
# lands on a structurally-compatible shape (a comparison never becomes a derivation by accident),
# ending in "" (prose). No entry is ever a drawn visual.
_FORM_ALTERNATES = {
    "comparison-table": ["comparison-table", "diff-block", "table", "derivation", ""],
    "diff-block":       ["diff-block", "comparison-table", "table", ""],
    "metrics-grid":     ["metrics-grid", "table", "derivation", ""],
    "derivation":       ["derivation", ""],
    "gap-table":        ["gap-table", ""],
    "table":            ["table", "comparison-table", ""],
    "":                 [""],
}


def _assign_target_forms(nodes: list[dict], seed: dict) -> None:
    """Stamp each node's `target_form`, in place (call AFTER _assign_places — de-collision needs the
    full ordered list). Deliver nodes route from their finding WITH sibling de-collision: when a
    node's primary form is already taken by an earlier sibling this round, it demotes along its ranked
    candidates — so siblings get DISTINCT shapes (the D-A crux). motivate / change-the-course are
    prose-only. GUARANTEE: no two deliver siblings share a non-prose form until the vocabulary is
    exhausted (then it falls to prose, never a repeat)."""
    taken: Counter = Counter()
    for n in nodes:
        if n["role"] != "deliver":
            n["target_form"] = list(_PROSE)
            continue
        fids = n["contract"]["finding_ids"]
        finding = _finding_by_id(seed, fids[0]) if fids else None
        ranked = _FORM_ALTERNATES[_route_form(finding or {})]
        chosen = ""
        for cand in ranked:
            if cand == "" or taken[cand] == 0:   # a free non-prose form, or fall to prose
                chosen = cand
                break
        if chosen:
            taken[chosen] += 1
        n["target_form"] = list(_PROSE) + ([chosen] if chosen else [])


# The REQUIRED field contract per form (mirrors _TYPE_FORMAT_RULE) — the writer must see it, else a
# correctly-TYPED block missing a required field is silently dropped by normalize_blocks (Codex P2).
_FORM_SHAPE = {
    "metrics-grid": "items each {value, label} — value carries a number/magnitude (42%, 3x, 30ms)",
    "comparison-table": "REQUIRED headers:[col,...] AND rows each {cells:[...]}",
    "diff-block": "lines each {type: insert|delete, text}",
    "derivation": "text + bullets (the reasoning steps)",
    "table": "REQUIRED headers:[col,...] AND rows each [cell, cell, ...]",
    "gap-table": "gaps each {description, need, status}",
}


def _form_guidance(target_form) -> str:
    """The per-node form directive injected into the writer prompt — NOT the uniform full-palette
    rule (the diversity-collapse attractor, G5). It names ONLY this node's one owed structured form
    AND its required field shape (so the writer's block survives normalization), or asks for prose.
    It never mentions chart/diagram (the visual invariant)."""
    non_prose = [f for f in (target_form or []) if f not in _PROSE]
    if not non_prose:
        return ("Write this node as developed PROSE. Do NOT force a table/grid/diagram — the content "
                "here is narrative; a forced structure would be hollow.")
    forms = ", ".join(f"a {f} ({_FORM_SHAPE[f]})" if f in _FORM_SHAPE else f"a {f}"
                      for f in non_prose)
    return (f"Beyond the prose, THIS finding's shape owes ONE structured block: {forms}. Lead with "
            f"the prose, then emit that block with EVERY field shown above — and NO other block type "
            f"(no chart, no diagram, no unrelated grid).")


def enforce_form(node: dict) -> dict:
    """Post-fill form gate: drop every block whose CANONICAL type is a DRAWN visual (always — the
    visual invariant), or is non-prose/non-gap AND outside this node's `target_form`. Prose and the
    gap family are always kept (reconcile consolidates gaps afterward). Pure — returns a new node.
    If dropping empties the node, leave it empty so contract_gate flags it HONESTLY (a writer that
    emitted only disallowed structure has failed — we never mint filler to launder that)."""
    allowed = set(node.get("target_form") or _PROSE) | set(_PROSE) | set(_GAP_TYPES)
    kept = []
    for b in node.get("blocks") or []:
        ctype, _canon = render.canonical_block(b)
        if ctype is None or ctype in _DRAWN_VISUALS:
            continue
        if ctype in allowed:
            kept.append(b)
    out = dict(node)
    out["blocks"] = kept
    return out


def _form_block_substantive(b: dict, ctype: str, canon: dict) -> bool:
    """A block of an owed form delivers REAL payload, not hollow chrome: the substance predicate
    (metrics-grid/comparison-table/diff-block) + required-field gate via blocks.normalize_block, PLUS
    explicit payload checks for the predicate-less forms — a derivation needs bullets/text, a table
    needs rows — so a `{type: derivation, title: ...}` shell can't satisfy the contract (Codex P2)."""
    if block_validation.normalize_block(b) is None:
        return False  # hollow per the substance predicate / missing a required field

    def _has_cell(rows):
        return any(isinstance(r, (list, tuple)) and any(str(c).strip() for c in r) for r in (rows or []))

    if ctype == "derivation":  # at least one NON-BLANK bullet or non-blank text (not bullets:[""])
        return (any(isinstance(x, str) and x.strip() for x in (canon.get("bullets") or []))
                or bool((canon.get("text") or "").strip()))
    if ctype == "table":  # at least one row with a non-blank cell (not rows:[[]])
        return _has_cell(canon.get("rows"))
    if ctype == "gap-table":
        gaps = canon.get("gaps") or []
        return (any(isinstance(g, dict) and any(str(v).strip() for v in g.values()) for g in gaps)
                or _has_cell(canon.get("rows")))
    return True


def form_violations(node: dict) -> list[str]:
    """Flag a node that OWED a structured form (its target_form names a non-prose form) but delivered
    no SUBSTANTIVE block of that form — the writer ignored the per-node form contract OR emitted a
    hollow shell, which would let a structurally monotone report ship (the form gate drops wrong
    blocks but cannot conjure a real one). Surfaced like opener_flags; prose-only nodes never flag.
    The gap family doesn't count as the owed form (it's a boundary, not content)."""
    owed = set(f for f in (node.get("target_form") or []) if f not in _PROSE)
    if not owed:
        return []
    for b in (node.get("blocks") or []):
        ctype, canon = render.canonical_block(b)
        if ctype in owed and _form_block_substantive(b, ctype, canon):
            return []
    return [f"node {node.get('id')!r} owed a structured form {sorted(owed)} but delivered no "
            f"substantive one (form contract unmet)"]


# --- Deterministic reconcile (D-B): one consolidated gap-table, no LLM ---
_GAP_SIM_THRESHOLD = 0.82  # [UNCALIBRATED] on token-sorted normal forms; fails safe (under-merges)


def _norm_gap(s: str) -> str:
    s = (s or "").casefold()
    s = re.sub(r"[^\w\s]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def _gap_key(s: str) -> str:
    """Token-SORTED normal form: collapses paraphrase-by-reorder ('nothing forgets by default' vs
    'by default nothing forgets') so the char-ratio similarity actually merges them."""
    return " ".join(sorted(_norm_gap(s).split()))


def _gap_similar(a: str, b: str) -> bool:
    return difflib.SequenceMatcher(None, _gap_key(a), _gap_key(b)).ratio() >= _GAP_SIM_THRESHOLD


def _consumable_gaps(canon: dict):
    """The gaps list reconcile may fold in — ONLY the dict-list gap-table shape the renderer actually
    uses. A `headers+rows` gap-table renders its ROWS and IGNORES `gaps` (render's no-hybrid stance),
    so it is NOT consumable even when it also carries a `gaps` list. None = leave the block in place."""
    if canon.get("headers") and canon.get("rows"):
        return None
    gaps = canon.get("gaps")
    return gaps if isinstance(gaps, list) else None


def _gap_table_fully_consumable(canon: dict) -> bool:
    """True iff a dict-list gap-table EVERY row of which carries a non-blank string `description` —
    only then can reconcile strip the whole block and rebuild it losslessly. A headers+rows table, an
    empty gaps list, OR a MIXED table (some rows only need/status/id) is NOT consumable: it is left in
    place so its description-less rows — which the renderer draws — are never stripped into the void."""
    gaps = _consumable_gaps(canon)
    if not gaps:
        return False
    return all(isinstance(g, dict) and isinstance(g.get("description"), str) and g["description"].strip()
               for g in gaps)


def _gap_objects(nodes: list[dict], seed: dict) -> list[dict]:
    """Every CONSUMABLE gap across the nodes as FULL dicts (description + any need/status/id the writer
    supplied — preserving the dict keeps the remediation/status metadata the renderer supports), plus
    the seed residuals as bare {description}. Only FULLY-consumable gap-tables contribute (so consume
    ⇔ every row extracted — no partial loss); marker/residual gaps always do."""
    objs: list[dict] = []
    for n in nodes:
        for b in n.get("blocks") or []:
            ctype, canon = render.canonical_block(b)
            if ctype == "gap-table" and _gap_table_fully_consumable(canon):
                objs += [dict(g) for g in _consumable_gaps(canon)]
            elif ctype == "gap-marker" and isinstance(canon.get("text"), str) and canon["text"].strip():
                obj = {"description": canon["text"]}
                if canon.get("id") is not None:   # keep the id a gap-resolution.gap_id may reference
                    obj["id"] = canon["id"]
                objs.append(obj)
    objs += [{"description": r} for r in (seed.get("residuals") or [])
             if isinstance(r, str) and r.strip()]
    return objs


def _dedup_gap_objects(objs: list[dict]) -> list[dict]:
    """Greedy single-pass dedup of gap DICTS by description similarity. The representative keeps the
    first-seen description, but MERGES metadata (need/status/id) from later duplicates — so a bare
    gap-marker/residual seen first does not drop the richer remediation info a later gap-table row
    carries, regardless of node order (Codex P2). Greedy, not union-find: gap counts are tiny and
    greedy avoids transitive over-merge (A~B~C, A≁C)."""
    reps: list[dict] = []
    for o in objs:
        match = next((r for r in reps if _gap_similar(o["description"], r["description"])), None)
        if match is None:
            reps.append(dict(o))
        else:
            for k, v in o.items():
                if k != "description" and k not in match and v not in (None, ""):
                    match[k] = v
    return reps


def _is_consumed_gap(b: dict) -> bool:
    """A gap block whose content `_gap_objects` actually folded into the consolidated table — the
    dict-list gap-table and gap-marker (see `_consumable_gaps`). A `headers+rows` gap-table is NOT
    consumed, so reconcile leaves it in place rather than strip its only-boundary content into the void."""
    ctype, canon = render.canonical_block(b)
    if ctype == "gap-marker":
        return isinstance(canon.get("text"), str) and bool(canon["text"].strip())
    return ctype == "gap-table" and _gap_table_fully_consumable(canon)


def reconcile(nodes: list[dict], seed: dict):
    """Deterministic post-fill reconciliation (no LLM). Returns (stripped_nodes, consolidated_gap):
    every node with its CONSUMED gap blocks REMOVED, and ONE consolidated gap-table merging all node
    gaps + seed residuals (deduped) — None iff no consumable gap exists. This is what kills D-B: the
    per-node duplicates are stripped and the boundary becomes a single block (see conciliate wiring).
    A `headers+rows` gap-table (un-consumable) is left in its node so its content is never lost."""
    reps = _dedup_gap_objects(_gap_objects(nodes, seed))
    stripped = []
    for n in nodes:
        out = dict(n)
        out["blocks"] = [b for b in (n.get("blocks") or []) if not _is_consumed_gap(b)]
        stripped.append(out)
    consolidated = {"type": "gap-table", "gaps": reps} if reps else None
    return stripped, consolidated


# --- Structural diversity report (D-A measurement): ordered block-type signatures ---

def _section_signature(section: dict) -> tuple:
    """A section's ORDERED canonical block-type sequence — the rhythm whose repetition IS the D-A
    symptom (order preserved; a set would lose it)."""
    return tuple(render.canonical_block(b)[0] or "?" for b in (section.get("blocks") or []))


def _distinct_signatures(signatures: list[tuple]) -> float:
    """distinct section SIGNATURES / total sections. 1.0 = every section a different template; low =
    the same template repeats (the D-A symptom). The unit is the WHOLE ordered signature — pooling
    individual block types instead would be dominated by the ubiquitous `paragraph` and miss the
    section-level monotony. The PRINCIPLED gate (interpretable endpoints, no smoothing)."""
    return len(set(signatures)) / len(signatures) if signatures else 1.0


def _ngram_counts(seq: tuple, n: int) -> Counter:
    return Counter(seq[i:i + n] for i in range(len(seq) - n + 1)) if len(seq) >= n else Counter()


def _self_bleu(sequences: list[tuple], n: int = 1) -> float:
    """Mean unigram self-BLEU with add-1 smoothing (signatures are 3–5 long, so unsmoothed precision
    degenerates). HIGH = sections look alike. REPORTED, not hard-gated (no calibrated cut-point)."""
    if len(sequences) < 2:
        return 0.0
    scores = []
    for i, s in enumerate(sequences):
        refs = sequences[:i] + sequences[i + 1:]
        hyp_c = _ngram_counts(s, n)
        if not hyp_c:
            scores.append(0.0)
            continue
        max_ref: Counter = Counter()
        for r in refs:
            for g, c in _ngram_counts(r, n).items():
                max_ref[g] = max(max_ref[g], c)
        overlap = sum(min(c, max_ref[g]) for g, c in hyp_c.items())
        scores.append((overlap + 1) / (sum(hyp_c.values()) + 1))
    return sum(scores) / len(scores)


def diversity_report(spec: dict, *, min_distinct: float = 0.50) -> dict:
    """Measure structural diversity over a spec's section signatures. The distinct-SIGNATURE ratio is
    the HARD gate (principled, interpretable endpoints); unigram self-bleu is REPORTED only
    (uncalibrated). Sections with no blocks are ignored; < 2 comparable sections → no violation.
    Thresholds [UNCALIBRATED] — flagged for hand-judging against 2–3 real reports."""
    sigs = [_section_signature(s) for s in (spec.get("sections") or []) if s.get("blocks")]
    dsig = _distinct_signatures(sigs) if len(sigs) >= 2 else 1.0
    sb1 = _self_bleu(sigs, 1) if len(sigs) >= 2 else 0.0
    violations = []
    if len(sigs) >= 2 and dsig < min_distinct:
        violations.append(
            f"diversity: distinct-signatures {dsig:.2f} < {min_distinct} (sections over-templated)")
    return {"distinct_signatures": round(dsig, 3), "self_bleu_1": round(sb1, 3),
            "violations": violations}


# ---------------------------------------------------------------------------
# Fill a node — the existing producer cognition per node. The writer gets the FULL seed
# (assignment, not reduction) + its node's assigned findings as the anti-drop checklist. The
# model call is INJECTED so the logic tests offline.
# ---------------------------------------------------------------------------

def _outline_map(outline: list[dict]) -> str:
    """The WHOLE-outline map the writer sees — every node's position + role + intent, in order.
    This is the #28 map-then-recall posture for production: the writer holds the map of the whole
    arc so it knows exactly where its node sits and what the other nodes carry (so it does not
    duplicate or re-introduce them)."""
    return "\n".join(
        f"  [{n['place']['position']}] {n['role']}: {n['contract']['intent']}"
        for n in outline
    )


def _writer_prompt(node: dict, outline: list[dict], seed: dict, objective: str) -> str:
    """The per-node writer prompt — a CONTINUATION directive over the WHOLE-outline map (#36, the
    '23 different intros' fix). The writer sees: the whole outline (the map of the entire arc),
    what upstream nodes ALREADY established (so the frame is set — it must not re-establish it),
    and its own node's assignment. It is told to OPEN MID-STREAM as a continuation, never to
    re-introduce context the upstream already owns. Only the opening node (empty upstream)
    legitimately establishes the frame.

    The full seed is still the context (assignment, not reduction); the assigned finding CLAIMS
    are the explicit anti-drop checklist, one per line, for the writer and the mechanical gate.

    `outline` may be empty/None (the back-compat 4-arg `fill_node` path) — then the map is empty
    and the node falls back to its own place; `place` may be absent — then it opens as the frame."""
    assigned = [_finding_by_id(seed, fid) for fid in node["contract"]["finding_ids"]]
    assigned = [f for f in assigned if f]
    claim_lines = "\n".join(f.get("claim", "") for f in assigned)
    residuals = "; ".join(seed.get("residuals") or [])
    place = node.get("place") or {"position": "", "established_upstream": ""}
    upstream = place.get("established_upstream", "")
    is_opening = not upstream.strip()
    if is_opening:
        continuation = (
            "You are the OPENING node — you establish the frame for everything downstream. "
            "Set it once, here, cleanly."
        )
    else:
        continuation = (
            "WRITE AS A CONTINUATION: the frame is ALREADY set by the upstream nodes below — "
            "open MID-STREAM, do NOT re-establish context, do NOT re-introduce the subject, "
            "do NOT write a fresh intro. Pick up exactly where the upstream left off. "
            "Open with the SUBSTANCE of your own finding in your own words — do NOT open with a "
            "formulaic back-pointer ('That X matters more than it appears', 'This means…', "
            "'Building on the above'); vary your opening so it does not echo the other nodes."
        )
    return (
        f"You are writing ONE node of a larger, single synthesis. Objective: {objective}\n\n"
        "THE WHOLE OUTLINE (the map — your node is one part of THIS single arc; do not "
        "duplicate or re-introduce what the other nodes carry):\n"
        f"{_outline_map(outline or [])}\n\n"
        f"YOUR NODE: position {place.get('position', '')}, role {node['role']}.\n"
        f"Its contract: {node['contract']['intent']}\n\n"
        f"ALREADY ESTABLISHED UPSTREAM (the frame is set — do not repeat it):\n{upstream}\n\n"
        f"{continuation}\n\n"
        "Develop EVERY one of your assigned findings to plenitude — each must be present and "
        "earned in your prose (do not drop the tail):\n"
        f"{claim_lines}\n\n"
        f"Open tensions you may surface: {residuals}\n\n"
        f"{_form_guidance(node.get('target_form'))}\n\n"
        "Write developed prose for this node, THEN emit ONE fenced ```json ENVELOPE — STRICT "
        "JSON — carrying the node's content as TYPED BLOCKS following the rule above:\n"
        '{"title": <a SHORT content-derived section title (NEVER the scaffold intent above)>, '
        '"blocks": [<the typed blocks: a paragraph for the prose, PLUS the ONE structured block '
        'named above if the shape owes it>], '
        '"digest": {"bullets": ["the node\'s key points"], "assumed_prior": "what you took as '
        'already-established upstream", "contribution": "one line: this node\'s contribution to '
        'the arc", "cross_refs": ["other nodes/findings you lean on"]}}. The conciliator works '
        "off the digest, not your full prose."
    )


# ---------------------------------------------------------------------------
# The subagent-default bridge (#40) — the orchestration-layer fan-out seam. The writer cognition
# defaults to the host agent's OWN subagents (one per node), not the gpt-5.4 OpenAI API. A subagent
# dispatch is a harness tool call (Agent/Task), NOT callable from inside this Python — so the SKILL
# fans the subagents and feeds their collected outputs back in through this seam:
#   node_briefs(seed, objective)      -> [{id, role, prompt}], one per outline node (what to dispatch)
#   subagent_completer(briefs, outputs) -> the complete_fn(prompt)->text the pipeline already consumes
# The Python keeps the structure (outline → fill → gate → assemble); the WRITING is the subagents'.
# The gpt-5.4 route is no longer the default — it is an explicit fallback the skill builds only when
# subagents are unavailable, and passes as `complete_fn` exactly as before.
# ---------------------------------------------------------------------------

def node_briefs(seed: dict, objective: str) -> list[dict]:
    """The per-node writer briefs the orchestration layer fans to subagents — one per outline
    node, in arc order, each carrying its `id`, `role`, and the exact `prompt` `fill_node` would
    otherwise hand the injected completer. The skill dispatches one subagent per brief, collects
    `{node_id -> prose}`, and hands both back to `subagent_completer`. This is the only point a
    subagent dispatch is reachable (the skill layer); the Python cannot dispatch one itself."""
    nodes = author_outline(seed, objective)
    return [
        {"id": n["id"], "role": n["role"],
         "prompt": _writer_prompt(n, nodes, seed, objective)}
        for n in nodes
    ]


def subagent_completer(briefs: list[dict], outputs: dict):
    """Build the `complete_fn(prompt) -> text` the existing pipeline consumes, backed by the
    subagent prose the skill already collected. Each brief maps a node's writer `prompt` to its
    `id`; `outputs` maps `id -> prose`. The returned completer resolves an incoming writer prompt
    by EXACT match to its brief, then returns that node's subagent prose — so `run_conductor`'s
    writer cognition is the host agent's own subagents, the gpt-5.4 API never touched.

    A prompt with no matching brief, or a node with no collected prose, is a wiring bug (the skill
    dispatched fewer subagents than nodes) — it FAILS LOUD (KeyError), never fabricates or returns
    empty. The completer only ever sees WRITER prompts: the semantic judge and the conciliator are
    their own injected cognitions (`run_conductor`'s `discharge_fn` / `conciliate_fn`)."""
    prompt_to_id = {b["prompt"]: b["id"] for b in briefs}

    def complete_fn(prompt: str) -> str:
        node_id = prompt_to_id.get(prompt)
        if node_id is None:
            raise KeyError("subagent_completer: no brief matches this writer prompt "
                           "(the orchestration layer dispatched fewer subagents than nodes)")
        if node_id not in outputs:
            raise KeyError(f"subagent_completer: no subagent prose collected for node {node_id!r}")
        return outputs[node_id]

    return complete_fn


# The type->format rule (compact inline of skills/_shared/scaffold.md:114-135) — which block fits
# which content shape (property-not-section, ADR-0012/0013). The conductor's writers were taught
# NONE of it (D1), so they answered every shape with a paragraph; injecting it is the producer fix.
_TYPE_FORMAT_RULE = (
    "THE TYPE->FORMAT RULE — match the content shape, reach for the block (never a mandatory "
    "section, only what the content IS):\n"
    "- 3+ values / metrics -> metrics-grid (items each {value, label}).\n"
    "- a comparison -> comparison-table (REQUIRED headers:[col,...] AND rows each {cells:[...]}).\n"
    "- before / after -> diff-block (lines each {type:insert|delete, text}).\n"
    "- a reasoning chain -> derivation (text + bullets).\n"
    "- an open boundary (a gap, an unknown) -> gap-table (gaps each {id, description, need, "
    "status}).\n"
    "- quantitative data to visualize -> chart (line|sparkline|bar|scatter|slopegraph, with "
    "data).\n"
    "- a relation / dependency / flow -> diagram (dag|force); ascii-diagram is the zero-dep "
    "fallback.\n"
    "Default is prose; left alone you answer every shape with a paragraph and the rich palette "
    "goes unused. Lead with the block the content owes."
)


# The writer digest — the structured handle the CONCILIATOR works off (not the full essay).
# Every parse returns exactly these four keys so the conciliator never KeyErrors on a
# refused/garbled digest (a fresh dict each call — never a shared mutable default).
def _empty_digest() -> dict:
    return {"bullets": [], "assumed_prior": "", "contribution": "", "cross_refs": []}


def _parse_digest(raw: str) -> dict:
    """Tolerant parse of the writer's structured digest (mirrors excavate._parse_seed): strip a
    ```json fence, tolerate leading/trailing prose (the digest follows the body), coerce each
    field to its expected shape, and NEVER crash — garbage yields the empty digest, not an
    exception. `bullets`/`cross_refs` coerce to lists of non-empty strings; `assumed_prior`/
    `contribution` to a stripped string ("" if absent/non-string)."""
    if not isinstance(raw, str):  # a non-string raw (e.g. a list) has no .strip() — fail soft
        return _empty_digest()
    if not raw or not raw.strip():
        return _empty_digest()
    text = raw.strip()
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL | re.IGNORECASE)
    if fence:
        text = fence.group(1).strip()
    candidates = [text]
    brace = re.search(r"\{.*\}", text, re.DOTALL)
    if brace and brace.group(0) != text:
        candidates.append(brace.group(0))
    data = None
    for cand in candidates:
        try:
            data = json.loads(cand)
            break
        except (json.JSONDecodeError, ValueError):
            continue
    if not isinstance(data, dict):
        return _empty_digest()
    return _coerce_digest(data)


def _coerce_digest(data: dict) -> dict:
    """Coerce a parsed dict into the four-key digest shape — the field coercion shared by the flat
    `_parse_digest` and the nested `_parse_writer_output` (so the conciliator's digest parse is
    never orphaned by the new envelope, finding 1). `bullets`/`cross_refs` coerce to lists of
    non-empty strings; `assumed_prior`/`contribution` to a stripped string."""
    if not isinstance(data, dict):
        return _empty_digest()
    def _str_list(v):
        return [s.strip() for s in v if isinstance(s, str) and s.strip()] if isinstance(v, list) else []
    def _str(v):
        return v.strip() if isinstance(v, str) else ""
    return {
        "bullets": _str_list(data.get("bullets")),
        "assumed_prior": _str(data.get("assumed_prior")),
        "contribution": _str(data.get("contribution")),
        "cross_refs": _str_list(data.get("cross_refs")),
    }


def _parse_writer_output(raw: str) -> dict:
    """Parse the writer's fenced ```json ENVELOPE {"title","blocks","digest"} into a dict carrying
    `title` (the content-derived section title, or None), `blocks` (normalized + substance-validated
    via blocks.normalize_blocks — hollow/malformed blocks dropped), and `digest` (coerced). The
    digest is read from the NESTED `digest` key, falling back to the top-level dict (`or data`) so a
    writer that emits a flat top-level digest is still parsed (back-compat, finding 1). NEVER crashes
    — a garbled envelope yields {title:None, blocks:[], digest: empty}."""
    data = _parse_envelope(raw)
    if not isinstance(data, dict):
        return {"title": None, "blocks": [], "digest": _empty_digest()}
    title = data.get("title")
    title = title.strip() if isinstance(title, str) and title.strip() else None
    return {
        "title": title,
        "blocks": block_validation.normalize_blocks(data.get("blocks")),
        "digest": _coerce_digest(data.get("digest") or data),
    }


def _parse_envelope(raw: str):
    """Tolerant fence->dict parse shared by the digest/envelope parsers (mirrors _parse_digest's
    fence handling): strip a ```json fence, tolerate surrounding prose, return the dict or None."""
    if not isinstance(raw, str) or not raw.strip():
        return None
    text = raw.strip()
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL | re.IGNORECASE)
    if fence:
        text = fence.group(1).strip()
    candidates = [text]
    brace = re.search(r"\{.*\}", text, re.DOTALL)
    if brace and brace.group(0) != text:
        candidates.append(brace.group(0))
    for cand in candidates:
        try:
            data = json.loads(cand)
        except (json.JSONDecodeError, ValueError):
            continue
        if isinstance(data, dict):
            return data
    return None


def _strip_digest_block(text: str) -> str:
    """Return the body prose with a trailing ```json digest fence removed (the writer emits the
    digest AFTER the prose). If there is no fence, the whole text is the body."""
    return re.sub(r"\s*```(?:json)?\s*\{.*?\}\s*```\s*$", "", text.strip(),
                  flags=re.DOTALL | re.IGNORECASE).strip() or text.strip()


def _prose_outside_fences(raw) -> str:
    """The writer/conciliator's real prose OUTSIDE any fenced code block. `_strip_digest_block`
    returns the raw fence when stripping leaves no body, so a JSON-ONLY envelope would render as raw
    JSON; this returns only genuine prose ('' when the output is fence-only) — Codex P2."""
    return re.sub(r"```.*?```", "", raw, flags=re.DOTALL).strip() if isinstance(raw, str) else ""


def fill_node(node: dict, seed: dict, objective: str, complete_fn, *, outline=None) -> dict:
    """Fill one node via the injected `complete_fn(prompt) -> text` and advance it to `draft`.
    Returns a new node dict carrying `blocks` (a paragraph of the produced prose) AND a structured
    `digest` (the conciliator's handle — bullets/assumed_prior/contribution/cross_refs). The model
    emits the digest as a fenced JSON block after the prose; it is parsed TOLERANTLY (garbage =>
    empty digest, never a crash). Pure w.r.t. the input node — never mutates it.

    `outline` is the WHOLE arc the writer sees as the map (#36); it is KEYWORD-ONLY with a default
    so the old 4-arg call `fill_node(node, seed, objective, complete_fn)` is NOT broken (back-compat)
    — without it the writer simply gets no map and falls back to its own place. `complete_fn` is the
    producer cognition, injected exactly like close.py's reviewers; real runs pass a make_client-backed
    completer on the chat router (provision its max_tokens generously — a reasoning model truncates
    a tight budget, and the digest follows the prose so a tight budget truncates the digest first)."""
    raw = complete_fn(_writer_prompt(node, outline, seed, objective))
    parsed = _parse_writer_output(raw)
    filled = dict(node)
    filled["status"] = advance("empty")  # empty -> draft
    # the writer's typed blocks (normalized: hollow/malformed dropped). When the writer wrote
    # developed prose BEFORE the fenced envelope but the envelope carried only a visual block, the
    # prose (the finding claim) would vanish from contract_gate/opener/discharge — so preserve it as
    # a leading paragraph whenever no prose-bearing block is present (Codex P2). Use prose OUTSIDE the
    # fence so a JSON-only envelope never renders raw JSON; if there is no real prose AND no block,
    # the node is empty and contract_gate flags it (the writer produced nothing).
    body = _prose_outside_fences(raw)
    blocks = parsed["blocks"]
    if body and not any(
            isinstance(b, dict) and b.get("type") in ("paragraph", "callout")
            and isinstance(b.get("text"), str) and b.get("text", "").strip()
            for b in blocks):
        blocks = [{"type": "paragraph", "text": body}] + blocks
    filled["blocks"] = blocks or ([{"type": "paragraph", "text": body}] if body else [])
    filled["title"] = parsed["title"]
    filled["digest"] = parsed["digest"]
    return filled


# ---------------------------------------------------------------------------
# The mechanical contract gate — deterministic code (check_genus-style), never an LLM.
# ---------------------------------------------------------------------------

# Block chrome — heading/label/type fields that are NOT delivered prose; excluded (at the BLOCK
# level) from the contract gate's text so a claim placed only in a `title`/`header` cannot spoof
# discharge (Codex P2). Nested payload (a metric item's label, a table cell, a bullet) still counts.
# Styling fields that are NEVER visible content — excluded at EVERY nesting level so a claim hidden
# in a CSS class/variant cannot spoof contract discharge (Codex P2, review r7). NOTE: `id` and
# `badge` are NOT here — they render as visible content (gap-marker/gap-table ids, diagram node-label
# fallback, badge labels), so excluding them would falsely fail valid discharge (review r8).
_NONCONTENT_FIELDS = frozenset({"type", "classes", "class", "style", "badge_class",
                                "badge_variant", "variant"})
# Block-level heading fields — excluded only at the BLOCK top level (a metric item's `label` and a
# table cell ARE data, so these are NOT excluded at deeper levels).
_BLOCK_HEADING_FIELDS = frozenset({"title", "label", "header", "headers"})


def _strings(v) -> list:
    """Every VISIBLE string nested anywhere in `v` — skips styling/structural fields
    (`classes`/`style`/`variant`/…) at every depth so non-content metadata never counts as payload."""
    if isinstance(v, str):
        return [v]
    if isinstance(v, list):
        return [s for x in v for s in _strings(x)]
    if isinstance(v, dict):
        return [s for k, x in v.items() if k not in _NONCONTENT_FIELDS for s in _strings(x)]
    return []


def _node_text(node: dict) -> str:
    """The SUBSTANTIVE text a node's blocks carry (for the contract/opener gates). EXCLUDES block
    heading chrome (title/label/header/headers) at the block level AND styling metadata
    (classes/style/variant/…) at every level — so neither a heading-only placeholder nor a claim
    hidden in a CSS class can spoof discharge; nested payload (paragraph text, bullets, metric
    labels, table cells) still counts."""
    parts = []
    for b in node.get("blocks") or []:
        if not isinstance(b, dict):
            continue
        for k, v in b.items():
            if k in _NONCONTENT_FIELDS or k in _BLOCK_HEADING_FIELDS:
                continue
            parts.extend(_strings(v))
    return " ".join(parts)


def contract_gate(node: dict, seed: dict) -> list[str]:
    """Return the node's contract violations ([] iff it discharges its contract). Deterministic,
    free, exact — mirrors `close.check_genus`, NEVER an LLM:
      - the node is NON-EMPTY (it carries content blocks with real text);
      - every assigned finding is DISCHARGED — its claim is developed in the node's text.
    A node that drops one of its assigned findings (the brevity prior leaking back at the node
    level) is flagged by id; the semantic 'did it deliver the contract's intent' check is a
    slice-2 LLM review, not this gate."""
    violations = []
    text = _node_text(node).lower()
    if not text.strip():
        violations.append(f"node {node.get('id')!r} is empty (a node must carry non-empty content)")
        return violations
    for fid in node["contract"]["finding_ids"]:
        finding = _finding_by_id(seed, fid)
        claim = (finding or {}).get("claim", "")
        if not claim or claim.lower() not in text:
            violations.append(
                f"node {node.get('id')!r} did not discharge assigned finding {fid!r}: "
                f"{claim!r}")
    return violations


# ---------------------------------------------------------------------------
# The SEMANTIC discharge gate — the LLM half of the contract review (#36, slice 2). The
# mechanical `contract_gate` above demands a VERBATIM claim echo, so it flags legitimate
# paraphrase as a drop (the verbatim-echo bug the conductor report flagged). This gate judges,
# per assigned finding, whether the node DELIVERED THE MEANING — paraphrase passes, a genuine
# drop fails. Kept CLEANLY SEPARATE from the deterministic gate: the structural gate stays
# mechanical/free/exact; this one spends a model call (INJECTED) and is the part code can't see.
# ---------------------------------------------------------------------------

def _semantic_prompt(node: dict, findings: list[dict]) -> str:
    finding_lines = "\n".join(
        f'  - {fid}: {f.get("claim", "")}' for fid, f in findings)
    return (
        "You are the SEMANTIC discharge reviewer for one node of a synthesis. Judge, per "
        "assigned finding, whether the node's prose DELIVERED ITS MEANING — a faithful "
        "PARAPHRASE counts as delivered (do NOT require a verbatim echo); only a genuine DROP "
        "(the meaning is absent) is not delivered.\n\n"
        f"THE NODE'S PROSE:\n{_node_text(node)}\n\n"
        "ASSIGNED FINDINGS (judge each):\n"
        f"{finding_lines}\n\n"
        "Return STRICT JSON only: "
        '{"verdicts": [{"finding_id": "f0", "delivered": true}]}'
    )


def _parse_discharge(raw: str, expected_ids: list[str]) -> dict:
    """Tolerant parse of the semantic judge's verdicts into {finding_id: delivered_bool}. Mirrors
    excavate._parse_seed: strip a fence, drop malformed verdicts, NEVER crash. A finding the judge
    failed to rule on (or a garbled response) defaults to NOT delivered (fail-closed) — a node
    cannot mint a discharge from a refusal."""
    by_id = {fid: False for fid in expected_ids}
    if not raw or not raw.strip():
        return by_id
    text = raw.strip()
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL | re.IGNORECASE)
    if fence:
        text = fence.group(1).strip()
    candidates = [text]
    brace = re.search(r"\{.*\}", text, re.DOTALL)
    if brace and brace.group(0) != text:
        candidates.append(brace.group(0))
    data = None
    for cand in candidates:
        try:
            data = json.loads(cand)
            break
        except (json.JSONDecodeError, ValueError):
            continue
    if not isinstance(data, dict):
        return by_id
    for v in data.get("verdicts") or []:
        if not isinstance(v, dict):
            continue
        fid = v.get("finding_id")
        if fid in by_id:
            by_id[fid] = v.get("delivered") is True  # exact identity, no coercion
    return by_id


def semantic_discharge(node: dict, seed: dict, complete_fn) -> list[dict]:
    """Judge, per assigned finding, whether the node DELIVERED ITS MEANING — the semantic half of
    the contract review (#36). Returns a list of `{finding_id, delivered: bool}`, one per assigned
    finding (a node with no findings owes nothing — returns [] and NEVER calls the model). The
    model call is INJECTED (`complete_fn`, like close.py's reviewers); the verdict is parsed
    TOLERANTLY and FAILS CLOSED (a garbled/refused judge => every finding `delivered: False`)."""
    findings = [(fid, _finding_by_id(seed, fid)) for fid in node["contract"]["finding_ids"]]
    findings = [(fid, f) for fid, f in findings if f]
    if not findings:
        return []
    raw = complete_fn(_semantic_prompt(node, findings))
    by_id = _parse_discharge(raw, [fid for fid, _ in findings])
    return [{"finding_id": fid, "delivered": by_id[fid]} for fid, _ in findings]


# ---------------------------------------------------------------------------
# Assemble — the filled nodes into one `content` block-spec that passes close.check_genus.
# ---------------------------------------------------------------------------

def _section_title(node: dict, seed: dict) -> str:
    """A content-derived section title (D4) — NEVER the arc scaffold `intent` (which renders as a
    raw '<h2>Deliver: develop the finding to plenitude — …' heading). Prefers the writer's own
    `title`; else a deterministic clean title from the deliver node's assigned finding `claim`;
    else a generic, scaffold-free fallback. Capped at 80 chars."""
    title = node.get("title")
    if isinstance(title, str) and title.strip():
        return title.strip()[:80]
    for fid in node.get("contract", {}).get("finding_ids", []):
        claim = (_finding_by_id(seed, fid) or {}).get("claim", "")
        if claim.strip():
            return claim.strip()[:80]
    # No content title → NO label (sections are FREE, ADR-0012/0013; render emits no <h2>). We never
    # fall back to a hardcoded-language label — "structure not strings" (Slice 1): the language lives in
    # the cognition's own text, never in a code constant.
    return ""


# --- The closing rich-rite moves as BLOCKS (language-agnostic — the gate satisfies derivation by a
# `derivation` block and what-i-dont-know by a `gap-table` block, by TYPE, never an English marker;
# Slice 1 / ed-research "structure not strings"). No hardcoded-language section titles or block labels. ---

def _findings_derivation(seed: dict, objective: str) -> dict:
    """The derivation move as a `derivation` BLOCK built from the seed findings (in the content's
    language). Connector is a neutral arrow, not an English word; no hardcoded title."""
    bullets = [f"{f.get('claim', '')} → {f.get('bears_on', '')}".strip(" →")
               for f in (seed.get("findings") or []) if (f.get("claim") or "").strip()]
    return {"type": "derivation", "bullets": bullets or [objective]}


def _residual_gaps(seed: dict):
    """The knowledge-boundary move as a `gap-table` BLOCK (satisfies what-i-dont-know by TYPE — no
    English marker text). Gaps are the seed residuals (in-language) — what genuinely remains unknown.
    It does NOT fall back to a digest's `assumed_prior`: that field is what a node took as already
    ESTABLISHED upstream, the OPPOSITE of an open gap — rendering it as a limitation would clear the
    move with inverted meaning (Codex P2). Node-level gaps the writers emitted already live inside
    their own sections, so re-appending them here would only duplicate (D-B). NEVER fabricates: with
    no real residual it returns **None** (the caller omits the boundary, and the gate honestly flags a
    developed synthesis that stated no limitation — a real signal, not gamed with invented content)."""
    descs = [r.strip() for r in (seed.get("residuals") or []) if isinstance(r, str) and r.strip()]
    if not descs:
        return None
    return {"type": "gap-table", "gaps": [{"description": d} for d in descs]}


def assemble(nodes: list[dict], seed: dict, objective: str) -> dict:
    """Assemble the filled nodes into one artefato `content` spec (the shape
    `close.run_close`/`publisher.publish` consume). Each node becomes a free section (sections
    are FREE — the arc is NEVER rendered as labeled headings; the node `intent` is an internal
    title only). The content carries the rich-rite moves it can own on its own — a `derivation`
    block (the synthesis's reasoning) and the seed's residuals as an explicit knowledge boundary
    — so `close.check_genus` passes on the content side; external-frame (a cite) and lineage
    (distills) are supplied by the producer wrapping this content into the full artefato."""
    sections = []
    for node in nodes:
        sections.append({
            "title": _section_title(node, seed),
            "blocks": node.get("blocks") or [],
        })

    # Closing moves as BLOCKS (language-agnostic, title-free — sections FREE): derivation block
    # satisfies the derivation move BY TYPE; gap-table block satisfies what-i-dont-know BY TYPE.
    sections.append({"title": "", "blocks": [_findings_derivation(seed, objective)]})
    _gaps = _residual_gaps(seed)
    if _gaps:
        sections.append({"title": "", "blocks": [_gaps]})

    return {"title": objective[:120], "sections": sections}


# ---------------------------------------------------------------------------
# Conciliation — the TWO-ALTITUDE output (#36). The conciliator works off the DIGESTS (the
# structured per-node handles), NOT the full essays:
#   (a) the DEEP spec — the nodes assembled with transitions, the redundant per-node intros
#       removed (the place-aware writers already opened mid-stream, so the seams are smooth);
#   (b) the SYNTHETIC spec — a 2-page executive through-line the conciliator WRITES over the
#       digests (a flowing synthesis, not a bullet dump), materially shorter than the deep.
# Both specs pass close.check_genus (the content side); a model call is INJECTED for (b).
# ---------------------------------------------------------------------------

def _digest_brief(nodes: list[dict]) -> str:
    """The conciliator's input: every node's place + contribution + bullets, from the DIGESTS
    (never the full prose). This is the map-then-recall posture applied to conciliation — the
    conciliator writes the through-line off the compressed handles, not the essays."""
    lines = []
    for n in nodes:
        d = n.get("digest") or _empty_digest()
        lines.append(
            f"[{n.get('place', {}).get('position', '')}] {n.get('role', '')} — "
            f"{d['contribution'] or n['contract']['intent']}")
        for b in d["bullets"]:
            lines.append(f"    - {b}")
    return "\n".join(lines)


def _synthetic_prompt(nodes: list[dict], objective: str) -> str:
    return (
        "You are the CONCILIATOR. Write a 2-PAGE EXECUTIVE SYNTHESIS over the digests below — "
        "find the single argument that runs through them and tell it for a busy operator who "
        "reads top to bottom. Reason from the evidence (derive, do not assert), name what you do "
        "not yet know, and tie it to prior work.\n\n"
        f"{_TYPE_FORMAT_RULE}\n\n"
        "Emit ONE fenced ```json spec — STRICT JSON — carrying the synthesis as TYPED BLOCKS "
        'following the rule above: {"blocks": [<a paragraph for the through-line prose, PLUS the '
        "metrics-grid/comparison-table/diff-block/derivation/gap-table any quantitative or "
        'multi-value material owes (NO chart/diagram — those are added later, grounded)>]}.\n\n'
        f"OBJECTIVE: {objective}\n\n"
        f"THE NODE DIGESTS (your raw material — the deep work is already done):\n"
        f"{_digest_brief(nodes)}"
    )


def _substantive(s) -> bool:
    """A digest contribution is usable as a derivation bullet only if it is a real clause — not a stray
    fragment ('D', 'Esta.') a truncated/garbled digest leaves behind. LANGUAGE-AGNOSTIC: a non-trivial
    length floor PLUS either >=2 whitespace tokens (space-delimited scripts) OR any CJK/non-Latin
    character — so a CJK sentence (no inter-word spaces, one `split()` token) is NOT wrongly rejected."""
    if not isinstance(s, str):
        return False
    t = s.strip()
    return len(t) >= 15 and (len(t.split()) >= 2 or any(ord(c) > 0x2E80 for c in t))


def _digest_derivation(nodes: list[dict]):
    """The derivation move as a `derivation` BLOCK off the nodes' digest CONTRIBUTIONS (in the
    content's language). Satisfies the move BY TYPE — no hardcoded-language title/lead (Slice 1).
    Returns None when NO contribution is substantive (every digest truncated/garbled): emitting a
    block of one-letter fragments or blanks would reintroduce the junk the filter suppresses, so we
    omit the move and let the close gate flag it honestly (→ the improve loop re-produces)."""
    bullets = [c for n in nodes
               for c in [(n.get("digest") or _empty_digest())["contribution"]]
               if _substantive(c)]
    return {"type": "derivation", "bullets": bullets} if bullets else None


# The synthetic shape floor — a sane char floor + a content-relative visual-density check
# (deterministic, free). The 2-page synthetic is whatever the model returns; an empty string or a
# one-liner is degraded output and must be FLAGGED, not silently shipped. The OLD "bare bullet dump"
# penalty is REMOVED (D3): it pushed AWAY from visual density — structure is now what we WANT. In its
# place, a content-relative density check: a synthetic whose quantitative/multi-value material owes a
# visual it does not carry FLAGS via the strengthened close gate (the same gate that bites the deep).
def _blocks_text(blocks) -> str:
    """The substantive prose text a list of blocks carries (the _block_text idiom, excluding
    heading/label fields), for the synthetic char floor."""
    return " ".join(close._block_text(b) for b in (blocks or []) if isinstance(b, dict))


_SYNTHETIC_MIN_CHARS = 120


def _synthetic_shape_violations(synth_blocks, full_spec, objective: str) -> list[str]:
    """Flag a degraded 2-page synthetic ([] iff it is a sane, content-appropriately-visual
    synthesis). Deterministic and free (never an LLM): rejects an empty conciliator body and a body
    below a sane char floor (measured over the CONCILIATOR's own blocks, not the appended
    derivation/boundary scaffold), then adds the strengthened content-relative visual-coverage
    check (via `_genus_violations` on the full spec) so a synthetic that owes a visual and does not
    carry one is flagged — the flip from the old anti-bullet penalty (D3)."""
    text = _blocks_text(synth_blocks).strip()
    if not text:
        return ["synthetic is empty"]
    if len(text) < _SYNTHETIC_MIN_CHARS:
        return [f"synthetic is too short ({len(text)} chars < {_SYNTHETIC_MIN_CHARS})"]
    return _genus_violations(full_spec, objective)


_UNSET = object()  # distinguishes "caller passed no consolidated gap (legacy)" from "reconcile found none"


def conciliate(nodes: list[dict], outline: list[dict], objective: str, complete_fn,
               *, seed=None, consolidated_gap=_UNSET) -> tuple:
    """Conciliate the filled, digested nodes into the TWO altitudes (#36), working off the
    DIGESTS (not the full essays). Returns `(deep_spec, synthetic_spec, synthetic_shape)`:
      - `deep_spec`  — the node bodies assembled with the redundant per-node intros removed (the
                       place-aware writers already opened mid-stream, so the seams are smooth),
                       plus the rich-rite derivation + boundary moves (built from the digests).
      - `synthetic_spec` — a 2-page synthetic through-line the conciliator WRITES over the
                       digests, emitted as TYPED BLOCKS (D3), materially shorter than the deep.
      - `synthetic_shape` — the shape-gate violations of the synthetic spec ([] iff sane): empty,
                       too short, or owing-a-visual-it-lacks is flagged here, not silently shipped.

    Both pass close.check_genus on the content side; the producer wraps each with the cite +
    distills for the external-frame/lineage moves. `complete_fn` is the INJECTED conciliator
    cognition (prompt -> the synthetic spec). `outline` is accepted for the arc map; the digests
    already carry each node's place. `seed` is keyword-only (default None) for the content-derived
    section titles (D4); the deep titles also fall back to the writer's own node `title`."""
    seed = seed or {}
    # The knowledge-boundary block (D-B): when run_conductor ran `reconcile`, it passes the ONE
    # consolidated gap-table (per-node duplicates already stripped, seed residuals folded in) — used
    # for BOTH altitudes, so each carries exactly one gap-table. Legacy callers (no reconcile) keep
    # the old per-spec `_residual_gaps(seed)` behavior via the _UNSET sentinel.
    boundary = _residual_gaps(seed) if consolidated_gap is _UNSET else consolidated_gap
    # (a) DEEP — the smoothed full report: every node's typed blocks (already normalized in
    # fill_node — hollow/malformed dropped), with content-derived titles (D4, never the scaffold
    # intent), then the derivation + boundary moves attached so it clears the floor.
    deep_sections = [
        {"title": _section_title(n, seed), "blocks": n.get("blocks") or []}
        for n in nodes
    ]
    _deep_deriv = _digest_derivation(nodes)
    if _deep_deriv:
        deep_sections.append({"title": "", "blocks": [_deep_deriv]})
    if boundary:
        deep_sections.append({"title": "", "blocks": [boundary]})
    deep_spec = {"title": objective[:120], "sections": deep_sections}

    # (b) SYNTHETIC — the conciliator's 2-page through-line over the digests, now emitted as TYPED
    # BLOCKS (D3) and normalized (hollow/malformed dropped). Falls back to one paragraph if empty.
    raw = complete_fn(_synthetic_prompt(nodes, objective))
    parsed = _parse_writer_output(raw)
    # fallback to the conciliator's loose prose ONLY if it wrote real prose OUTSIDE the fence —
    # `_strip_digest_block` returns the raw fenced JSON when stripping leaves no body, so use a
    # fence-stripped body; if that is empty, leave synth_blocks empty so the shape gate flags
    # "synthetic is empty" instead of rendering raw JSON as prose (Codex P2).
    prose_body = _prose_outside_fences(raw)
    synth_blocks = parsed["blocks"] or (
        [{"type": "paragraph", "text": prose_body}] if prose_body else [])
    # Visual invariant: the synthetic owns NO drawn visual either (chart/diagram come only from the
    # grounded Slice-4 post-pass) — strip any the conciliator slipped in.
    synth_blocks = [b for b in synth_blocks if render.canonical_block(b)[0] not in _DRAWN_VISUALS]
    # If stripping the visual emptied the parsed envelope but the conciliator wrote loose prose
    # outside the fence, keep that prose (Codex P2 — don't treat a real synthesis as empty).
    if not synth_blocks and prose_body:
        synth_blocks = [{"type": "paragraph", "text": prose_body}]
    synthetic_sections = [
        {"title": "", "blocks": synth_blocks},
    ]
    _syn_deriv = _digest_derivation(nodes)
    if _syn_deriv:
        synthetic_sections.append({"title": "", "blocks": [_syn_deriv]})
    if boundary:
        synthetic_sections.append({"title": "", "blocks": [boundary]})
    synthetic_spec = {"title": objective[:120], "sections": synthetic_sections}
    synthetic_shape = _synthetic_shape_violations(synth_blocks, synthetic_spec, objective)
    return deep_spec, synthetic_spec, synthetic_shape


# ---------------------------------------------------------------------------
# The orchestrator — off => passthrough, ZERO spend; on => author, fill, gate, assemble.
# ---------------------------------------------------------------------------

# The minimal artefato envelope the PRODUCER always wraps the content in (an external cite + a
# distill thread + the objective as intent + a thread). The conductor owns only `content`; to
# genus-validate it WITHOUT falsely flagging the producer's external-frame/lineage moves, the spec
# is wrapped in this envelope before close.check_genus, so a violation traces to the model-produced
# CONTENT (a malformed block, missing derivation/boundary, an empty body), not the wrapping.
def _genus_violations(spec: dict, objective: str) -> list[str]:
    """Genus-validate a content spec via close.check_genus, wrapping it in the producer's minimal
    envelope so only CONTENT-side violations (the conductor's responsibility) surface."""
    artefato = {
        "content": spec,
        "intent": objective,
        "cites": [{"ref": "(conductor probe)", "kind": "mundo",
                   "snippet": "the external frame the producer supplies"}],
        "proposes": [{"body": objective, "kind": "thread"}],
        "distills": ["cluster:conductor"],
    }
    return close.check_genus(artefato)


# The opener gate (#1, the formulaic-opener fix's ENFORCEMENT) — deterministic, free. The
# place-aware continuation directive ASKS writers to open with substance; this DETECTS when they
# don't: a deliver node opening with a back-pointer demonstrative, or sharing its opening word with
# a sibling (the "23 identical That-X intros" signal the prompt alone cannot guarantee against).
# Back-pointer opener skeletons: a demonstrative + (optional noun) + a pointer/linking verb
# ("that wording changes", "that choice matters", "this means", "it follows") — NOT a bare
# demonstrative, so "This framework avoids…" is left alone; plus the literal lead-in phrases.
_BANNED_OPENER_RE = re.compile(
    r"^(this|that|these|those)\s+(\w+\s+){0,2}"
    r"(is|are|was|were|means|matter|matters|change|changes|show|shows|highlight|highlights|"
    r"explain|explains|appear|appears|impl(?:y|ies)|underscore|underscores|reinforce|reinforces)\b"
    r"|^it\s+(follows|means|implies|shows|underscores)\b"
    r"|^(building on|as noted|as established|as we saw|having established|as above)\b",
    re.IGNORECASE,
)
# Articles/demonstratives excluded from the repeated-opener check — two nodes both opening "The"
# is not repetition; the FIRST SIGNIFICANT (content) word is the signal.
_OPENER_STOPWORDS = frozenset({"the", "a", "an", "this", "that", "these", "those", "it", "its",
                               "in", "on", "of", "to", "and", "but", "so", "as", "for", "with"})


def _first_significant(opener: str) -> str:
    for w in opener.split():
        if w not in _OPENER_STOPWORDS:
            return w
    return ""


def _opener(node: dict) -> str:
    """The first sentence of a node's prose — its opening move. Reads only the block text/body,
    never the block `type` tag (which _node_text flattens in)."""
    parts = [b[k] for b in (node.get("blocks") or [])
             for k in ("text", "body") if isinstance(b.get(k), str)]
    t = " ".join(parts).strip()
    if not t:
        return ""
    return re.split(r"(?<=[.!?])\s", t, 1)[0].strip()


def opener_violations(nodes: list[dict]) -> list[dict]:
    """Flag deliver nodes whose opening is formulaic: a back-pointer demonstrative, or an opening
    word shared with a sibling deliver node. [] iff every deliver node opens with varied substance."""
    delivers = [n for n in nodes if n.get("role") == "deliver"]
    openers = {id(n): _opener(n).lower() for n in delivers}
    sig_count = {}
    for op in openers.values():
        s = _first_significant(op)
        if s:
            sig_count[s] = sig_count.get(s, 0) + 1
    flags = []
    for n in delivers:
        op = openers[id(n)]
        if not op:
            continue
        if _BANNED_OPENER_RE.match(op):
            flags.append({"id": n.get("id"), "issue": "formulaic back-pointer opener",
                          "opener": op[:80]})
        elif sig_count.get(_first_significant(op), 0) >= 2:
            flags.append({"id": n.get("id"),
                          "issue": "opener's first content word repeats a sibling's",
                          "opener": op[:80]})
    return flags


def run_conductor(seed: dict, objective: str, complete_fn, *, is_enabled=None,
                  conciliate_fn=None, discharge_fn=None, visual_dispatch_fn=None) -> dict:
    """Run the conductor pipeline. OFF (default) => passthrough, ZERO model spend (today's
    single-producer pipeline is unchanged). ON => author the place-aware outline from the seed,
    fill each node (the writer sees the whole-outline map and writes as a continuation), gate it
    mechanically, drive to `final`, then CONCILIATE the digests into the TWO altitudes.

    `is_enabled` overrides the env flag (for tests / explicit callers); otherwise EDGE_CONDUCTOR
    decides. `complete_fn` is the injected WRITER cognition (prompt -> text). The subagent-default
    path (#40) passes `subagent_completer(briefs, outputs)` here — the writers are the host agent's
    own subagents, no gpt-5.4 API; the gpt-5.4 route is an explicit fallback the skill builds only
    when subagents are unavailable. `conciliate_fn` is the injected conciliator cognition and
    `discharge_fn` the injected semantic-judge cognition; BOTH default to `complete_fn` (today's
    behavior, byte-for-byte). Under the subagent-default path each is its OWN subagent, so the
    writer bridge only ever sees writer prompts.

    Each filled node carries BOTH gates: the mechanical `gate` (the deterministic contract_gate)
    AND a semantic `discharge` (the injected per-finding semantic_discharge verdicts) — a node
    whose findings the judge ruled NOT delivered surfaces as a flagged node, so a semantic failure
    can block the pipeline. The result also genus-validates BOTH specs (`genus`) and gates the
    synthetic's SHAPE (`synthetic_shape`), so degraded model output surfaces instead of shipping.

    Returns {"enabled", "passthrough", "content", "outline", "deep_spec", "synthetic_spec",
    "discharge", "genus", "synthetic_shape"}. `content` and `deep_spec` are the same smoothed full
    report (kept under both keys: `content` is the slice-1 field callers already read; `deep_spec`
    is the named altitude). OFF returns every spec None and an empty outline, having called
    `complete_fn` ZERO times."""
    on = enabled() if is_enabled is None else bool(is_enabled)
    if not on:
        return {"enabled": False, "passthrough": True, "content": None, "outline": [],
                "deep_spec": None, "synthetic_spec": None,
                "discharge": [], "genus": {"deep": [], "synthetic": []},
                "synthetic_shape": [], "opener_flags": [], "form_flags": [], "visual_flags": [],
                "diversity": diversity_report({"sections": []})}  # stable shape: neutral when off

    nodes = author_outline(seed, objective)
    filled_nodes = []
    for node in nodes:
        filled = fill_node(node, seed, objective, complete_fn, outline=nodes)  # empty->draft, +digest
        filled = enforce_form(filled)   # Slice 3: drop out-of-form + drawn-visual blocks BEFORE gating
        filled_nodes.append(filled)

    # Slice 3: a node that owed a structured form but shipped only prose is flagged here (the writer
    # ignored the form contract) — computed on the FORM-GATED nodes (gap-strip doesn't touch forms).
    form_flags = [v for n in filled_nodes for v in form_violations(n)]

    # Slice 3: deterministic reconcile — strip per-node CONSUMED gap blocks and build ONE consolidated
    # gap-table (D-B), which conciliate then attaches once per altitude. Run BEFORE the gates so the
    # contract/semantic gates judge the FINAL stripped content — a finding that survived only inside a
    # consumed gap block must register as a DROP, not a clean gate computed before the strip (Codex P2).
    final_nodes, consolidated_gap = reconcile(filled_nodes, seed)

    for filled in final_nodes:
        filled["gate"] = contract_gate(filled, seed)
        # The SEMANTIC half of the contract review (#36) — enforced, not just defined: a node whose
        # assigned findings the judge ruled NOT delivered is flagged, so it can block the pipeline.
        # The judge is its own injected cognition (`discharge_fn`, a subagent under #40); defaults
        # to `complete_fn` so today's single-completer behavior is unchanged.
        filled["discharge"] = semantic_discharge(filled, seed, discharge_fn or complete_fn)
        filled["status"] = advance(advance(filled["status"]))    # draft -> revised -> final

    # The per-node discharge failures rolled up — which nodes dropped which assigned findings.
    discharge_failures = [
        {"id": n.get("id"),
         "dropped": [v["finding_id"] for v in n.get("discharge", []) if not v["delivered"]]}
        for n in final_nodes
        if any(not v["delivered"] for v in n.get("discharge", []))
    ]

    deep_spec, synthetic_spec, synthetic_shape = conciliate(
        final_nodes, nodes, objective, conciliate_fn or complete_fn,
        seed=seed, consolidated_gap=consolidated_gap)

    # Slice 4: the grounded visual post-pass, wired at the producer→close seam — it reads the whole
    # deep report + the seed evidence and splices AT MOST 2 grounded visuals. The subagent dispatch is
    # the injected #40 seam (the Python can't dispatch a subagent); `visual_dispatch_fn=None` (the
    # default, and every offline test) is a SAFE NO-OP, so today's behavior is byte-for-byte unchanged.
    # Lazy import breaks the visuals→conductor cycle. Runs BEFORE genus so a spliced visual is gated.
    import visuals as _visuals
    # Ground visuals ONLY on the established FINDINGS, never on `residuals` — residuals are OPEN
    # QUESTIONS, not facts; grounding a chart on "is latency 50ms?" would launder an unknown into a
    # visual that looks evidenced (Codex P2).
    _evidence = {"text": "", "findings": seed.get("findings") or []}
    deep_spec, visual_flags = _visuals.add_visuals(deep_spec, evidence=_evidence,
                                                   dispatch_fn=visual_dispatch_fn)
    # Genus-validate BOTH specs before return — degraded content surfaces here, not silently ships.
    genus = {"deep": _genus_violations(deep_spec, objective),
             "synthetic": _genus_violations(synthetic_spec, objective)}
    return {"enabled": True, "passthrough": False, "content": deep_spec, "outline": final_nodes,
            "deep_spec": deep_spec, "synthetic_spec": synthetic_spec,
            "discharge": discharge_failures, "genus": genus,
            "synthetic_shape": synthetic_shape, "opener_flags": opener_violations(final_nodes),
            "form_flags": form_flags, "visual_flags": visual_flags,
            # Diversity scores ONLY the AUTHORED NODE sections — never the appended derivation/gap
            # closing scaffold, whose two unique signatures would otherwise mask monotone node bodies
            # (Codex P2). This is exactly the D-A symptom: identical authored-section templates.
            "diversity": diversity_report(
                {"sections": [{"blocks": n.get("blocks") or []} for n in final_nodes]})}
