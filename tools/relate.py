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
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _identity  # noqa: E402
import eventlog  # noqa: E402  (reuse the one cosine; the math lives there, ADR-0009)

# Sentinel so `nominate` can tell "caller passed None / 0.0" (a real value) from "use the default":
# group=None must mean a degraded read (no group), and floor=0.0 is a legitimate gate, so neither
# can double as the unset marker.
_AUTO = object()


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


def _k_for(n):
    """k = round(log2 N) — the mutual-kNN fan-out (research spec line 916). NOT a borrowed
    constant (A-MEM's k=5): it GROWS ~log with the corpus, so it is k=4 at N=16, k=3 at N=8, and
    stays sparse as N climbs. Below N=2 there are no neighbours, so k=0 (no candidate possible)."""
    if n < 2:
        return 0
    return round(math.log2(n))


def _read_artefato_embeddings(group=None, uri=None, user=None, password=None):
    """Read every fully-projected Artefato in THIS group that has an embedding, as
    ``[(slug, embedding), ...]``. The corpus the nominator runs over: `project_artefato` stores
    `a.embedding` (text-embedding-3-small) and flips `a.projection_complete=true` as its LAST step,
    so this reads ONLY complete nodes with a non-null vector. Degrade-safe (CONTRACT C1, ADR-0011):
    no group / no driver / unreachable graph → ``[]``, never raises — the default reader behind
    `nominate`'s seam (tests inject their own corpus instead)."""
    try:
        group = group or _identity.group()
        if not group:
            return []
        uri = uri or os.environ.get("EDGE_NEO4J_URI", "bolt://localhost:7687")
        user = user or os.environ.get("EDGE_NEO4J_USER", "neo4j")
        password = password or os.environ.get("EDGE_NEO4J_PASSWORD") or _identity.neo4j_password()
    except Exception:
        return []
    try:
        from neo4j import GraphDatabase
    except Exception:
        return []
    try:
        drv = GraphDatabase.driver(uri, auth=(user, password))
    except Exception:
        return []
    try:
        with drv.session() as s:
            rows = s.run(
                "MATCH (a:Artefato {group_id:$g}) "
                "WHERE a.projection_complete = true AND a.embedding IS NOT NULL "
                "RETURN a.slug AS slug, a.embedding AS embedding",
                g=group).data()
            return [(r["slug"], r["embedding"]) for r in rows]
    except Exception:
        return []
    finally:
        try:
            drv.close()
        except Exception:
            pass


def nominate(embeddings=None, *, group=_AUTO, floor=_AUTO, pct=87,
             read_fn=_read_artefato_embeddings, uri=None, user=None, password=None):
    """Stage 1 — NOMINATE candidate RELATES_TO pairs by mutual-kNN above the relative floor
    (research spec C1, line 916). Returns a ``set`` of ``frozenset({slug_i, slug_j})`` — undirected,
    deduped candidate pairs — for Stage 2 (the NLI router + grounded typer) to dispose of. NEVER a
    bare-similarity EDGE: this only nominates; nothing is minted here.

    The method, exactly as the spec forces it:
      1. read the live corpus of ``(slug, embedding)`` — every fully-projected Artefato with a vector;
      2. ``k = round(log2 N)`` — the fan-out grows ~log with N, never a borrowed constant;
      3. each node's top-k cosine neighbours;
      4. emit ``(i, j)`` ONLY if MUTUAL (i in j's top-k AND j in i's top-k) AND ``cosine >= floor``.
    Mutual-kNN kills the one-directional hub edges (plain top-k wires ~1/3 of all pairs at N=16 — a
    hub artifact, not signal, spec line 913); the resulting graph is SPARSE, the honest outcome at
    small N. The floor is the RELATIVE percentile from C1a (`relative_floor`), recomputed over THIS
    corpus — not a fixed 0.7/0.8 — so mutuality is necessary but the floor still gates.

    Seams: ``embeddings`` injects the corpus directly (tests / a precomputed sweep); otherwise
    ``read_fn`` reads the graph (default `_read_artefato_embeddings`). ``group`` left as `_AUTO`
    auto-resolves THIS install's own corpus (`_identity.group`); an EXPLICIT ``group=None`` is a
    degrade (no cross-tenant default — mirrors `_identity.group` returning None) → empty set, never
    the install's graph. ``floor`` overrides the computed relative floor (tests pin the gate); left
    as `_AUTO` it is `relative_floor(vectors, pct=pct)`. Degrade-safe (CONTRACT C1): no corpus / no
    graph / a reader that raises → empty set, never raises."""
    try:
        if embeddings is not None:
            corpus = embeddings
        else:
            # Resolve the group HERE so an explicit group=None degrades (no self-resolve); only an
            # UNSET group (_AUTO) reaches for the install's own corpus. Resolution is guarded — a
            # misconfigured install must darken this leg, not propagate (CONTRACT C1).
            g = _identity.group() if group is _AUTO else group
            if not g:
                return set()
            corpus = read_fn(group=g, uri=uri, user=user, password=password)
    except Exception:
        return set()
    if not corpus or len(corpus) < 2:
        return set()
    slugs = [slug for slug, _ in corpus]
    vectors = [vec for _, vec in corpus]
    n = len(corpus)
    k = _k_for(n)
    if k < 1:
        return set()

    if floor is _AUTO:
        floor = relative_floor(vectors, pct=pct)
    if floor is None:
        return set()

    # Pairwise cosines once (i<j), reused for both the top-k neighbours and the floor gate.
    try:
        sim = {}
        for i in range(n):
            for j in range(i + 1, n):
                sim[(i, j)] = eventlog.cosine(vectors[i], vectors[j])
    except (TypeError, ValueError):
        # Malformed (non-numeric) embedding: honour "never raises" — degrade to no candidates.
        return set()

    def _cos(i, j):
        return sim[(i, j)] if i < j else sim[(j, i)]

    # Each node's top-k neighbour indices, by descending cosine (slug tiebreak for determinism).
    topk = []
    for i in range(n):
        others = [j for j in range(n) if j != i]
        others.sort(key=lambda j: (-_cos(i, j), slugs[j]))
        topk.append(set(others[:k]))

    cands = set()
    for i in range(n):
        for j in range(i + 1, n):
            if j in topk[i] and i in topk[j] and _cos(i, j) >= floor:
                cands.add(frozenset({slugs[i], slugs[j]}))
    return cands
