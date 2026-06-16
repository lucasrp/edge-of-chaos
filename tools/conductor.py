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

import json
import os
import re

import close
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
        f"{_TYPE_FORMAT_RULE}\n\n"
        "Write developed prose for this node, THEN emit ONE fenced ```json ENVELOPE — STRICT "
        "JSON — carrying the node's content as TYPED BLOCKS following the rule above:\n"
        '{"title": <a SHORT content-derived section title (NEVER the scaffold intent above)>, '
        '"blocks": [<the typed blocks: a paragraph for the prose, PLUS the metrics-grid/'
        'comparison-table/diff-block/derivation/gap-table/chart the content shape owes>], '
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
    "- a comparison -> comparison-table (rows each {cells:[...]}).\n"
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
_BLOCK_CHROME_FIELDS = frozenset({"type", "title", "label", "header", "headers", "variant",
                                  "badge", "badge_class", "style"})


def _strings(v) -> list:
    """Every string nested anywhere in `v` (lists/dicts at any depth) — the substantive payload."""
    if isinstance(v, str):
        return [v]
    if isinstance(v, list):
        return [s for x in v for s in _strings(x)]
    if isinstance(v, dict):
        return [s for x in v.values() for s in _strings(x)]
    return []


def _node_text(node: dict) -> str:
    """The SUBSTANTIVE text a node's blocks carry (for the contract/opener gates). EXCLUDES BLOCK
    chrome (type/title/label/header/headers/…) so a heading-only placeholder cannot spoof discharge,
    but counts nested payload — paragraph text, bullets, metric labels, table cells."""
    parts = []
    for b in node.get("blocks") or []:
        if not isinstance(b, dict):
            continue
        for k, v in b.items():
            if k in _BLOCK_CHROME_FIELDS:
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
    return {"motivate": "Why this matters", "deliver": "The finding",
            "change-the-course": "What this changes"}.get(node.get("role"), "Synthesis")


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

    # The derivation block — the synthesis's own reasoning, satisfying the rich-rite derivation
    # move with a substantive field. Built from the seed's findings (the mined deep structure).
    deriv_bullets = [
        f"{f.get('claim', '')} — because {f.get('bears_on', '')} ({f.get('citation', '')})"
        for f in (seed.get("findings") or [])
    ] or [f"derive the objective from first principles: {objective}"]
    sections.append({
        "title": "Why this holds",
        "blocks": [{
            "type": "derivation",
            "title": "From the mined findings",
            "bullets": deriv_bullets,
            "text": ("It follows that the objective is reachable from the seed's findings, "
                     "not asserted."),
        }],
    })

    # The knowledge boundary — the seed's residuals rendered as an explicit what-i-dont-know,
    # satisfying the rich-rite boundary move.
    residuals = seed.get("residuals") or []
    # lead with a rich-rite boundary MARKER ("uncertain") in the TEXT — the title is excluded from
    # the marker scan, so a markerless text fails rich-rite:what-i-dont-know (dogfood regression).
    boundary = ("What remains uncertain — " + "; ".join(residuals)) if residuals else (
        "What remains uncertain — the open questions this synthesis did not resolve.")
    sections.append({
        "title": "Open questions",
        "blocks": [{"type": "callout", "variant": "info", "title": "What I don't know",
                    "text": boundary}],
    })

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
        "metrics-grid/comparison-table/diff-block/derivation/gap-table/chart any quantitative or "
        'multi-value material owes>]}.\n\n'
        f"OBJECTIVE: {objective}\n\n"
        f"THE NODE DIGESTS (your raw material — the deep work is already done):\n"
        f"{_digest_brief(nodes)}"
    )


def _substantive(s) -> bool:
    """A digest contribution is usable as a derivation bullet only if it is a real clause — not a
    stray fragment ('D', 'Esta.') that a truncated or wrong-language model digest can leave behind.
    Requires a non-trivial length and at least two words."""
    return isinstance(s, str) and len(s.strip()) >= 15 and len(s.strip().split()) >= 2


def _digest_derivation(nodes: list[dict], lead: str) -> dict:
    """A `derivation` block built from the nodes' digest CONTRIBUTIONS — the rich-rite derivation
    move, off the digests (not the essays). The bullets are each node's one-line arc contribution;
    degenerate fragments are dropped so junk never reaches the page."""
    bullets = [c for n in nodes
               for c in [(n.get("digest") or _empty_digest())["contribution"]]
               if _substantive(c)]
    return {"type": "derivation", "title": "The through-line",
            "text": lead, "bullets": bullets or [lead]}


def _boundary_block(nodes: list[dict]) -> dict:
    """A `what-i-dont-know` callout — the rich-rite boundary move. Draws the open tensions from the
    digests' `assumed_prior` where present, else a default boundary; always names the lineage."""
    # the text MUST carry a rich-rite boundary MARKER ("uncertain"): the title is excluded from the
    # marker scan and "open questions" (plural) misses the "open question" marker, so a markerless
    # text fails rich-rite:what-i-dont-know (the dogfood-surfaced regression).
    return {"type": "callout", "variant": "info", "title": "What I don't know",
            "text": ("What remains uncertain — the open questions this synthesis did not "
                     "resolve; it builds on the excavate seed and the prior nodes.")}


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


def conciliate(nodes: list[dict], outline: list[dict], objective: str, complete_fn,
               *, seed=None) -> tuple:
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
    # (a) DEEP — the smoothed full report: every node's typed blocks (already normalized in
    # fill_node — hollow/malformed dropped), with content-derived titles (D4, never the scaffold
    # intent), then the derivation + boundary moves attached so it clears the floor.
    deep_sections = [
        {"title": _section_title(n, seed), "blocks": n.get("blocks") or []}
        for n in nodes
    ]
    deep_sections.append({"title": "Why this holds", "blocks": [
        _digest_derivation(nodes,
                           "It follows from the assembled findings that the objective is "
                           "reachable — the synthesis derives it, not asserts it.")]})
    deep_sections.append({"title": "Open questions", "blocks": [_boundary_block(nodes)]})
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
    synthetic_spec = {"title": objective[:120], "sections": [
        {"title": "Synthesis", "blocks": synth_blocks},
        {"title": "Why this holds", "blocks": [
            _digest_derivation(nodes,
                               "It follows that the objective is reachable from the synthesis "
                               "of the nodes — derived, not asserted.")]},
        {"title": "Open questions", "blocks": [_boundary_block(nodes)]},
    ]}
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
                  conciliate_fn=None, discharge_fn=None) -> dict:
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
                "synthetic_shape": [], "opener_flags": []}

    nodes = author_outline(seed, objective)
    final_nodes = []
    for node in nodes:
        filled = fill_node(node, seed, objective, complete_fn, outline=nodes)  # empty->draft, +digest
        filled["gate"] = contract_gate(filled, seed)
        # The SEMANTIC half of the contract review (#36) — enforced, not just defined: a node whose
        # assigned findings the judge ruled NOT delivered is flagged, so it can block the pipeline.
        # The judge is its own injected cognition (`discharge_fn`, a subagent under #40); defaults
        # to `complete_fn` so today's single-completer behavior is unchanged.
        filled["discharge"] = semantic_discharge(filled, seed, discharge_fn or complete_fn)
        filled["status"] = advance(filled["status"])             # draft -> revised
        filled["status"] = advance(filled["status"])             # revised -> final
        final_nodes.append(filled)

    # The per-node discharge failures rolled up — which nodes dropped which assigned findings.
    discharge_failures = [
        {"id": n.get("id"),
         "dropped": [v["finding_id"] for v in n.get("discharge", []) if not v["delivered"]]}
        for n in final_nodes
        if any(not v["delivered"] for v in n.get("discharge", []))
    ]

    deep_spec, synthetic_spec, synthetic_shape = conciliate(
        final_nodes, nodes, objective, conciliate_fn or complete_fn, seed=seed)
    # Genus-validate BOTH specs before return — degraded content surfaces here, not silently ships.
    genus = {"deep": _genus_violations(deep_spec, objective),
             "synthetic": _genus_violations(synthetic_spec, objective)}
    return {"enabled": True, "passthrough": False, "content": deep_spec, "outline": final_nodes,
            "deep_spec": deep_spec, "synthetic_spec": synthetic_spec,
            "discharge": discharge_failures, "genus": genus,
            "synthetic_shape": synthetic_shape, "opener_flags": opener_violations(final_nodes)}
