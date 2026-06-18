"""S7 (R2) — the per-visual UNFORGEABLE grounding attestation. A claim-bearing visual only reaches the
published Artefato if it carries a valid `_grounding` token: an HMAC over the block's canonical data,
keyed by a PROCESS-PRIVATE secret the producer cannot reproduce. The token is minted ONLY by the grounding
step (`sign`, called by close/visuals AFTER `visuals.attributable` passes), so a visual DRAWN DIRECTLY in
the spec (never grounded) has no valid token and is rejected by the same `close.check_genus` that the
publisher runs (ADR-0013 blind: `verify` needs only the secret + the block, NO evidence). This is
PROVENANCE, not integrity — a self-consistent digest the producer computes does not pass (gate reframe-4).
"""
import hashlib
import hmac
import json
import secrets

# process-private signing key — re-randomized each run; the producer's spec is just data and never sees it.
_SECRET = secrets.token_bytes(32)
ATTEST_FIELD = "_grounding"


def _canonical(block: dict) -> bytes:
    """The canonical bytes the attestation covers: the block MINUS its own `_grounding` field, sorted and
    NaN-free so a re-serialization (JSON round-trip through the log/proof) recomputes the same bytes."""
    body = {k: v for k, v in block.items() if k != ATTEST_FIELD}
    return json.dumps(body, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, default=str, allow_nan=False).encode()


def attest(block: dict) -> str:
    """The HMAC-SHA256 attestation over the block's canonical data (keyed by the private secret)."""
    return hmac.new(_SECRET, _canonical(block), hashlib.sha256).hexdigest()


def sign(block: dict) -> dict:
    """Return a COPY of `block` carrying a valid attestation. Called ONLY by the grounding step after the
    visual's data has been verified attributable to the evidence — never a public 'sign anything' a
    producer invokes (a producer emits a spec dict; it does not execute this at the close seam)."""
    body = {k: v for k, v in block.items() if k != ATTEST_FIELD}
    body[ATTEST_FIELD] = attest(body)
    return body


def verify(block: dict) -> bool:
    """True iff the block carries a valid attestation for its current data — fail-closed on a missing /
    non-string / mismatched token. Recomputes the HMAC, so any edit to the block's data after signing
    (a swapped datum, a fabricated edge) invalidates it. Needs only the secret + the block (blind-safe)."""
    if not isinstance(block, dict):
        return False
    sig = block.get(ATTEST_FIELD)
    if not isinstance(sig, str) or not sig:
        return False
    try:
        return hmac.compare_digest(sig, attest(block))
    except (TypeError, ValueError):
        return False
