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

Gated by EDGE_CONDUCTOR (off => passthrough, today's single-producer pipeline byte-for-byte AND
zero model spend).
"""
from __future__ import annotations

import os

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
    return nodes


def _node(node_id: str, role: str, finding_ids: list[str], intent: str) -> dict:
    return {
        "id": node_id,
        "role": role,
        "status": "empty",
        "contract": {"intent": intent, "finding_ids": list(finding_ids)},
    }


# ---------------------------------------------------------------------------
# Fill a node — the existing producer cognition per node. The writer gets the FULL seed
# (assignment, not reduction) + its node's assigned findings as the anti-drop checklist. The
# model call is INJECTED so the logic tests offline.
# ---------------------------------------------------------------------------

def _writer_prompt(node: dict, seed: dict, objective: str) -> str:
    """The per-node writer prompt. Carries the full seed as context and the node's assigned
    finding CLAIMS as the explicit anti-drop checklist — every assigned claim appears on its own
    line so the writer (and the mechanical gate) can hold it to account."""
    assigned = [_finding_by_id(seed, fid) for fid in node["contract"]["finding_ids"]]
    assigned = [f for f in assigned if f]
    claim_lines = "\n".join(f.get("claim", "") for f in assigned)
    residuals = "; ".join(seed.get("residuals") or [])
    return (
        f"You are writing ONE node of a larger synthesis. Objective: {objective}\n"
        f"This node's role in the arc: {node['role']}.\n"
        f"Its contract: {node['contract']['intent']}\n\n"
        "Develop EVERY one of your assigned findings to plenitude — each must be present and "
        "earned in your prose (do not drop the tail):\n"
        f"{claim_lines}\n\n"
        f"Open tensions you may surface: {residuals}\n\n"
        "Write developed prose for this node only."
    )


def fill_node(node: dict, seed: dict, objective: str, complete_fn) -> dict:
    """Fill one node via the injected `complete_fn(prompt) -> text` and advance it to `draft`.
    Returns a new node dict carrying `blocks` (a paragraph of the produced prose). Pure w.r.t.
    the input node — never mutates it. `complete_fn` is the producer cognition, injected exactly
    like close.py's reviewers; real runs pass a make_client-backed completer on the chat router
    (provision its max_tokens generously — a reasoning model truncates a tight budget)."""
    prose = complete_fn(_writer_prompt(node, seed, objective))
    filled = dict(node)
    filled["status"] = advance("empty")  # empty -> draft
    filled["blocks"] = [{"type": "paragraph", "text": prose}]
    return filled


# ---------------------------------------------------------------------------
# The mechanical contract gate — deterministic code (check_genus-style), never an LLM.
# ---------------------------------------------------------------------------

def _node_text(node: dict) -> str:
    parts = []
    for b in node.get("blocks") or []:
        for v in b.values():
            if isinstance(v, str):
                parts.append(v)
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
# Assemble — the filled nodes into one `content` block-spec that passes close.check_genus.
# ---------------------------------------------------------------------------

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
            "title": node["contract"]["intent"][:80],
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
    boundary = ("What I don't know: " + "; ".join(residuals)) if residuals else (
        "What I don't know: the open questions this synthesis did not resolve.")
    sections.append({
        "title": "Open questions",
        "blocks": [{"type": "callout", "variant": "info", "title": "What I don't know",
                    "text": boundary}],
    })

    return {"title": objective[:120], "sections": sections}


# ---------------------------------------------------------------------------
# The orchestrator — off => passthrough, ZERO spend; on => author, fill, gate, assemble.
# ---------------------------------------------------------------------------

def run_conductor(seed: dict, objective: str, complete_fn, *, is_enabled=None) -> dict:
    """Run the conductor pipeline. OFF (default) => passthrough, ZERO model spend (today's
    single-producer pipeline is unchanged). ON => author the outline from the seed, fill each
    node via `complete_fn`, drive each through the mechanical gate to `final`, assemble.

    `is_enabled` overrides the env flag (for tests / explicit callers); otherwise EDGE_CONDUCTOR
    decides. `complete_fn` is the injected producer cognition (prompt -> text).

    Returns {"enabled", "passthrough", "content", "outline"}; OFF returns content=None and an
    empty outline, having called `complete_fn` zero times."""
    on = enabled() if is_enabled is None else bool(is_enabled)
    if not on:
        return {"enabled": False, "passthrough": True, "content": None, "outline": []}

    nodes = author_outline(seed, objective)
    final_nodes = []
    for node in nodes:
        filled = fill_node(node, seed, objective, complete_fn)   # empty -> draft
        filled["gate"] = contract_gate(filled, seed)
        filled["status"] = advance(filled["status"])             # draft -> revised
        filled["status"] = advance(filled["status"])             # revised -> final
        final_nodes.append(filled)

    content = assemble(final_nodes, seed, objective)
    return {"enabled": True, "passthrough": False, "content": content, "outline": final_nodes}
