"""assembly — provenance helpers for a stamped `_assembly` block (S-WIRE).

The producer may stamp `artefato['_assembly']`; the close re-verifies and
SIGNS it (the signing primitive is close-PRIVATE — A8 — and lives in `close.py`, never here). This
module holds only the NON-secret, pure computations both sides share:

  - `content_digest(spec)` — a stable digest of assembled content that IGNORES
    close-owned `_grounding` signatures, so the same content digests identically before and after
    close's `ground_visuals` (the H2 ordering fix). Used by S-WIRE to stamp `content_digest` and by
    S-ATTEST's re-verify to detect content revised after the stamp (P1).
  - `assembly_facts(result, seed)` — the `_assembly` dict the producer stamps onto the artefato.

Deliberately holds NO secret and NO `sign`/`attest` — keeping it here would be the public sign-any API
A8 forbids.
"""
from __future__ import annotations

import hashlib
import json


# The spec keys whose `.blocks[]` `ground_visuals` signs — EXACTLY `close._iter_blocks`'s traversal
# (sections + additional_sections, no recursion into block internals). A block's OWN data — even a field
# literally named `blocks` — is CONTENT and is left verbatim, so a post-conductor edit to it moves the
# digest (codex review: scope the strip to real rendered section-block arrays, not arbitrary nesting).
_BLOCK_SECTION_KEYS = ("sections", "additional_sections")


def _strip_grounding(spec):
    """Return the spec with each SECTION BLOCK's own `_grounding` attestation removed, scoped to exactly
    where `ground_visuals` adds it — `sections[*].blocks[*]` and `additional_sections[*].blocks[*]`. Block
    internals (including any nested data) are kept verbatim, so only the close-owned attestation is
    invariant; real content changes still move the digest."""
    if not isinstance(spec, dict):
        return spec
    out = dict(spec)
    for key in _BLOCK_SECTION_KEYS:
        sections = spec.get(key)
        if isinstance(sections, list):
            out[key] = [_strip_section(s) for s in sections]
    return out


def _strip_section(section):
    if not isinstance(section, dict):
        return section
    blocks = section.get("blocks")
    if not isinstance(blocks, list):
        return section
    return {**section, "blocks": [_strip_block(b) for b in blocks]}


def _strip_block(block):
    """Drop a section block's OWN top-level `_grounding`; keep everything else verbatim (block data is
    content — never recursed for more `_grounding`)."""
    if not isinstance(block, dict):
        return block
    return {k: v for k, v in block.items() if k != "_grounding"}


def content_digest(spec) -> str:
    """sha256 over the canonical content with all `_grounding` signatures stripped. Stable and
    order-insensitive (sorted keys), so the same content digests identically before and after
    close's additive visual signing."""
    blob = json.dumps(_strip_grounding(spec), sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def assembly_facts(result: dict, seed: dict) -> dict:
    """Build the `_assembly` provenance dict from a production `result` + the seed it ran on.
    `content_digest` binds THIS run's content so a later revision in the close loop is detectable."""
    facts = {
        "assembled": "multi-agent" if result.get("enabled") else "single-context",
        "node_count": len(result.get("outline") or []),
        "seed_finding_count": len(seed.get("findings") or []),
        "conductor_ship": bool(result.get("ship")),
        "blocking": list(result.get("blocking") or []),
        "conductor_digest": content_digest(result.get("content")),
    }
    # Q6 (S-DEFAULT) defense-in-depth: if the producer recorded the RAW excavate finding count on the seed
    # and the seed it ran on carries fewer, log a soft `seed_collapse` warning — a multi-finding excavate
    # result collapsed to a smaller seed (the NG7 seed residual). Best-effort, NEVER blocking: the seed is
    # producer-built so a determined producer can omit `excavate_finding_count`; this catches the accident.
    efc = seed.get("excavate_finding_count")
    if isinstance(efc, int) and not isinstance(efc, bool) and efc > facts["seed_finding_count"]:
        facts["seed_collapse"] = {"excavate": efc, "seed": facts["seed_finding_count"]}
    return facts
