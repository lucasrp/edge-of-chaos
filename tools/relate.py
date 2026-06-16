"""relate — the two-stage RELATES_TO nominator/typer (issue #39, brick-1 Cortex).

Research spec: cosine-nominates-the-author-disposes. Stage 1 NOMINATES candidate pairs
(mutual-kNN + a relative floor); Stage 2 DISPOSES (NLI-first, then a grounded typer) so a
RELATES_TO edge is never minted from bare similarity. This module ships Stage 1's floor first.

THE FLOOR IS RELATIVE, NOT ABSOLUTE. OpenAI's 1536-d embeddings are anisotropic and
corpus-specific: in high dimensions random vectors concentrate toward orthogonality, so the
absolute cosine is mostly a property of the model+corpus, and the signal is the DEVIATION
from that background — not the raw value (spec line 18). A borrowed 0.7/0.8 (HippoRAG's 0.8
was tuned on 100 labelled examples on 512-d NV-Embed) means a different thing per corpus and
does not transfer. So the floor is a PERCENTILE of the LIVE pairwise-cosine distribution,
which tracks the model's anisotropy automatically (spec lines 42-44).
"""
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import eventlog  # noqa: E402  (reuse the one cosine; the math lives there, ADR-0009)


def relative_floor(vectors, *, pct=87):
    """Return the `pct`-th percentile of the full pairwise-cosine distribution over `vectors`.

    `pct` is the RELATIVE FLOOR from the research spec — the spec names a P85-90 BAND (spec
    lines 921/934), not a single point; the default 87 is one point inside that band, NOT a
    derived midpoint. It is a METHOD PARAMETER, deliberately NOT a borrowed absolute cosine
    constant: the same percentile recomputed against THIS corpus tracks the model's anisotropy
    automatically. A tuned absolute tau is DEFERRED until ~100 labelled judgments exist (spec
    line 1018) — until then the relative floor is the instrument.

    The distribution is computed EXACTLY over all C(N,2) pairs via `eventlog.cosine`. At small
    N this is cheap (N=16 → 120 pairs). When the corpus grows large enough that all-pairs is
    too costly, the spec's documented next step is a ~10k-pair RANDOM SAMPLE of the same
    distribution — that sampling is NOT built here; v1 ships exact all-pairs.

    PRECONDITION: each entry is an equal-length numeric vector (sweep's embeddings). Degrade-safe:
    fewer than two usable vectors → there is no pairwise distribution, so no floor → None (no-op);
    a malformed (non-numeric) vector also degrades to None. It never raises.
    """
    if not vectors or len(vectors) < 2:
        return None
    try:
        cosines = [
            eventlog.cosine(vectors[i], vectors[j])
            for i in range(len(vectors))
            for j in range(i + 1, len(vectors))
        ]
    except (TypeError, ValueError):
        # PRECONDITION: vectors are equal-length numeric embeddings (sweep emits these; not
        # re-validated here). eventlog.cosine degrades a zero-norm vector to 0.0, but a
        # non-numeric / malformed element still raises — so to honour "never raises" a
        # malformed corpus degrades to no floor rather than propagating the error.
        return None
    return _percentile(cosines, pct)


def _percentile(values, pct):
    """The `pct`-th percentile of `values` by (n-1) linear interpolation between order
    statistics — numpy's default and statistics.quantiles' `inclusive` method (NOT the
    `exclusive` default, which differs at small N); pinned for N=2,3 in test_relate. Pure-Python
    so the floor has no runtime dependency. `pct` in 0..100; a single value is its own percentile."""
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    rank = (pct / 100) * (len(ordered) - 1)
    lo = math.floor(rank)
    hi = math.ceil(rank)
    return ordered[lo] + (ordered[hi] - ordered[lo]) * (rank - lo)
