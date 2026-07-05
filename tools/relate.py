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
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _identity  # noqa: E402
import cortex  # noqa: E402  (reuse the one cosine via the Cortex door — ADR-0009/0019)
import cortex_provenance  # noqa: E402  (the ONE provenance derivation — never fork the plane)

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

    The distribution is computed EXACTLY over all C(N,2) pairs via `cortex.cosine`. At small
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
            cortex.cosine(vectors[i], vectors[j])
            for i in range(len(vectors))
            for j in range(i + 1, len(vectors))
        ]
    except (TypeError, ValueError):
        # PRECONDITION: vectors are equal-length numeric embeddings (sweep emits these; not
        # re-validated here). cortex.cosine degrades a zero-norm vector to 0.0, but a
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


def _read_artefato_embeddings(group=_AUTO, uri=None, user=None, password=None):
    """Read every fully-projected Artefato in THIS group that has an embedding, as
    ``[(slug, embedding), ...]``. The corpus the nominator runs over: `project_artefato` stores
    `a.embedding` (text-embedding-3-small) and flips `a.projection_complete=true` as its LAST step,
    so this reads ONLY complete nodes with a non-null vector. Degrade-safe (CONTRACT C1, ADR-0011):
    no group / no driver / unreachable graph → ``[]``, never raises — the default reader behind
    `nominate`'s seam (tests inject their own corpus instead).

    Group resolution mirrors `nominate`: ``group`` left as `_AUTO` (the unset default) resolves THIS
    install's own corpus via `_identity.group`; an EXPLICIT ``group=None`` is a degrade (no
    cross-tenant default) → ``[]``, never the install's graph. `nominate` always passes an explicit
    `group=g`, so this auto-resolution is only the standalone-call convenience."""
    try:
        group = _identity.group() if group is _AUTO else group
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
                sim[(i, j)] = cortex.cosine(vectors[i], vectors[j])
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


# ---------------------------------------------------------------------------
# Stage 2a — the NLI ROUTER (research spec C2, lines 42-44, 54).
#
# NLI/entailment runs FIRST, BEFORE any relate framing, and in BOTH directions. By the time a
# relate-typer runs, cosine (Stage 1) has ALREADY guaranteed the pair is topically close — so a
# single 'related?' prompt is primed to say yes and will never surface the negation. The
# contradiction signal must be extracted by a DECOUPLED, high-recall NLI path, not a post-filter
# (spec line 54). So the router calls `nli_fn` first and only THEN hands survivors to the typer:
#   contradiction (calibrated) -> a MACHINE-FOUND `contradicts` OFFER (returned, NOT persisted;
#                                 C2c: the author confirms a directed claim, the machine never
#                                 auto-writes one) — and the pair NEVER reaches the relate typer;
#   entailment / neutral       -> pass the pair THROUGH to the relate typer (C2b).
#
# OPEN (spec U1 — NLI on long notes): NLI models are sentence-pair-trained but Artefato notes are
# paragraphs; a relate-router over whole notes can miss a contradiction buried in one. Claim-
# sentence decomposition + pairwise NLI is the documented fix and is NOT built here — deferred.
# OPEN (spec U4 — two-pass cost): NLI-on-every-pair THEN a typer is a latency/cost multiplier; the
# cheap-judge-then-escalate cascade that bounds it is deferred together WITH the heartbeat
# scheduling (issue item 4 / report item 5, both OUT of v1). v1 ships the router, not the cascade.
#
# OPEN (L1 — authored lineage bound into the close proof digest): the research spec REVISES the
# plan so AUTHORED, intent-bearing edges (builds_on/supersedes/contradicts) are author-asserted at
# PUBLISH and MUST be bound into the close proof digest — the `lineage-proof-bind` slice (L1) that
# adds a `lineage` field to `proof_digest`/`verify_proof` in close.py, on the L1->L3->L4 critical
# path. That is a SEPARATE slice on the close/publish seam and is NOT in this Stage-2a router: the
# router only DISCOVERS a *machine-found* `contradicts` OFFER for the author to confirm (C2c) and
# NEVER mints or proof-binds a directed edge itself. L1 is deferred to its own slice; the offer
# record below is deliberately the discovery hand-off, not the authored, digest-bound lineage edge.
# ---------------------------------------------------------------------------

# Calibration threshold for "this is a contradiction, not just topical proximity". A bare
# `label == "contradiction"` is not enough — the NLI score must clear this floor before the pair is
# pulled out of the typer path into an offer (spec line 43: "contradiction (calibrated)"). Like
# `pct`, this is a METHOD PARAMETER to be tuned on the Cortex, not a trusted constant.
NLI_CONTRADICTION_TAU = 0.5


def _neutral(_a, _b):
    """The degraded NLI verdict: neutral, pass-through. No key / no client / a raising completer
    all resolve HERE — a darkened router is high-recall (everything reaches the typer), never a
    crash and never an invented contradiction (CONTRACT C1: degrade-safe, never raises)."""
    return {"label": "neutral", "score": 0.0}


def _default_nli_fn(a_text, b_text):
    """The production default behind the `nli_fn` seam (tests inject a fake). v1 ships the SEAM,
    not the live entailment call: the real NLI completer is a make_client-backed prompt scheduled
    INTO the heartbeat, and that scheduling is deferred together with the U4 cheap-judge cascade
    (issue item 4 / report item 5, OUT of v1). Until then the default degrades to neutral pass-
    through — a darkened router is high-recall (every pair reaches the typer), never a crash and
    never an invented contradiction (CONTRACT C1: degrade-safe, never raises). This is the
    no-key/no-client branch that `route`'s degrade tests pin; wiring the live call only changes
    what happens WHEN a key is present, not this fallback."""
    return _neutral(a_text, b_text)


def _calibrated_contradiction(verdict):
    """A verdict is a calibrated contradiction iff label==contradiction AND score>=tau. A malformed
    or missing verdict (a degraded / raising nli_fn) is NOT a contradiction — it passes through."""
    try:
        return (verdict.get("label") == "contradiction"
                and float(verdict.get("score", 0.0)) >= NLI_CONTRADICTION_TAU)
    except Exception:
        return False


def route(pairs, *, nli_fn=None, type_fn=None):
    """Stage 2a router: partition C1's candidate pairs by an NLI-FIRST verdict (spec C2).

    `pairs` is an iterable of ``(a_text, b_text)`` — the full text of both notes (NOT the cosine
    score: that would anchor the typer, spec line 45). For each pair, `nli_fn` runs in BOTH
    directions BEFORE any relate framing:
      - a CALIBRATED contradiction in EITHER direction -> a machine-found `contradicts` OFFER
        (returned, not persisted; C2c) and the pair does NOT reach the relate typer;
      - otherwise (entailment / neutral, both directions) -> the pair passes to the relate typer.

    Returns ``(offers, passed)``: `offers` is a list of offer records
    ``{type:"contradicts", origin:"machine-found", pair:(a,b), nli:<verdict>}`` (the author confirms
    these — the machine never auto-writes a directed claim); `passed` is the list of pairs handed
    on to C2b. When `type_fn` is supplied, each passed pair is also forwarded to it here (the C2b
    typer is a later slice; this slice only proves the routing + ordering into that seam).

    Seams: `nli_fn(a_text, b_text) -> {label, score}` defaults to the real entailment completer,
    which degrades to neutral pass-through with no key (never raises). `type_fn(a_text, b_text)` is
    the C2b grounded typer, injected. Degrade-safe (CONTRACT C1): an nli_fn that raises degrades
    THAT pair to neutral pass-through, never dropping the batch and never propagating."""
    nli_fn = nli_fn or _default_nli_fn
    offers = []
    passed = []
    for a_text, b_text in pairs:
        # BOTH directions, FIRST — NLI is asymmetric, and the spec wants the refutation surfaced
        # before any similarity framing biases the call. A raising nli_fn degrades to neutral.
        try:
            fwd = nli_fn(a_text, b_text)
            rev = nli_fn(b_text, a_text)
        except Exception:
            fwd = rev = _neutral(a_text, b_text)
        if _calibrated_contradiction(fwd) or _calibrated_contradiction(rev):
            verdict = fwd if _calibrated_contradiction(fwd) else rev
            # L1 OPEN: this is a DISCOVERY offer, not an authored, proof-bound lineage edge. The
            # author confirms it at publish; binding `lineage` into the close proof digest is the
            # separate `lineage-proof-bind` slice (close.py), deferred — see the Stage-2a notes above.
            offers.append({
                "type": "contradicts",
                "origin": "machine-found",
                "pair": (a_text, b_text),
                "nli": verdict,
            })
            continue  # NEVER pass a contradiction to the relate typer (spec line 54)
        passed.append((a_text, b_text))
        if type_fn is not None:
            type_fn(a_text, b_text)
    return offers, passed


# ---------------------------------------------------------------------------
# Ticket D (docs/agencia/implementacao/02-D) — the caller relate never had, + the MENTIONS leg.
#
# `sync` wakes the semantic via: nominate → route → the missing MERGE RELATES_TO, edges stamped
# provenance_class='extracted' (a navigable HYPOTHESIS on the semantic plane — CX-1 keeps it out
# of every verdict rollup by construction). `extract_mentions`/`project_mentions` are the
# thematic via: the artefato's OWN published text names entities → MENTIONS ('asserted': o
# artefato DE FATO menciona) → Entity → HAS_MEMBER → Community → sibling artefatos. Curadoria é
# SÓ inline no publish (operador cortou o curador offline): what publish didn't curate stays raw
# until the next artefato touches the theme — forward-only honesto.
# ---------------------------------------------------------------------------

# The corpus reader behind `sync` — `_read_artefato_embeddings` widened with the kernel (route
# needs the TEXTS, spec line 45: never the cosine score). Same degrade contract: [] on any dark leg.
_CORPUS_QUERY = ("MATCH (a:Artefato {group_id:$g}) "
                 "WHERE a.projection_complete = true AND a.embedding IS NOT NULL "
                 "RETURN a.slug AS slug, coalesce(a.kernel,'') AS kernel, a.embedding AS embedding")

# The wipe is scoped to OUR edges only: cosine-nominated, Artefato↔Artefato. Graphiti's
# Entity↔Entity RELATES_TO and any author-confirmed edge carry no such origin — untouched.
_WIPE_QUERY = ("MATCH (a:Artefato {group_id:$g})-[r:RELATES_TO {origin:'cosine-nominated'}]-"
               "(b:Artefato {group_id:$g}) DELETE r")

_MINT_QUERY = ("MATCH (x:Artefato {group_id:$g, slug:$a}),(y:Artefato {group_id:$g, slug:$b}) "
               "MERGE (x)-[r:RELATES_TO {origin:'cosine-nominated'}]->(y) "
               "SET r.provenance_class=$pc")


def sync(group=_AUTO, *, corpus=None, session=None, nli_fn=None,
         uri=None, user=None, password=None):
    """Wake the semantic via (ticket D): nominate → route → WIPE-REBUILD the cosine-nominated
    RELATES_TO edges between Artefatos. The recompute is GLOBAL and periodic by design — the
    relative floor and the mutual-kNN shift with every new node, so a per-publish incremental
    mint would freeze yesterday's floor; the sweep calls this on every canonical run.

    Method: read the corpus of ``(slug, kernel, embedding)`` → Stage-1 `nominate` (mutual-kNN
    above the relative floor) → per pair, Stage-2a `route` over the KERNEL TEXTS (NLI-first; a
    calibrated contradiction becomes an OFFER in the return — C2c: the machine NEVER persists a
    directed claim) → survivors are minted ``(min_slug)-[:RELATES_TO {origin:'cosine-nominated',
    provenance_class:'extracted'}]->(max_slug)`` — direction deterministic, reads stay
    direction-agnostic; the plane comes from `cortex_provenance.provenance_class_for` (never a
    forked literal) so the edge is a navigable hypothesis CX-1 structurally excludes from rollups.

    The wipe runs FIRST and is scoped to `origin='cosine-nominated'` between :Artefato ends only:
    graphiti's Entity↔Entity RELATES_TO and author-confirmed edges are never touched; a corpus
    that shrank still clears its stale nominations honestly.

    Seams: ``corpus`` injects ``[(slug, kernel, embedding)]``; ``session`` injects the write
    session (tests: fakes; production resolves both). Degrade-safe (CONTRACT C1): no group / dark
    graph / a raising session → **None**, never a raise. Returns
    ``{"minted": [(a, b), ...], "offers": [...]}`` on success."""
    drv = None
    try:
        g = _identity.group() if group is _AUTO else group
        if not g:
            return None
        if session is None:
            try:
                from neo4j import GraphDatabase
                uri = uri or os.environ.get("EDGE_NEO4J_URI", "bolt://localhost:7687")
                user = user or os.environ.get("EDGE_NEO4J_USER", "neo4j")
                password = (password or os.environ.get("EDGE_NEO4J_PASSWORD")
                            or _identity.neo4j_password())
                drv = GraphDatabase.driver(uri, auth=(user, password))
                session = drv.session()   # closed with the driver in `finally`
            except Exception:
                return None
        if corpus is None:
            corpus = [(r["slug"], r["kernel"], r["embedding"])
                      for r in session.run(_CORPUS_QUERY, g=g).data()]
        kernels = {slug: kernel or "" for slug, kernel, _ in corpus}
        pairs = nominate(embeddings=[(slug, emb) for slug, _, emb in corpus])
        # ROUTE FIRST, WRITE LAST (codex adversarial #1): the NLI leg is the slow/flaky one, so
        # every route call completes BEFORE the wipe opens the write window — a raising route
        # leaves the graph untouched, and the wipe→mint window holds no LLM call. A partial
        # write failure still self-heals: sync re-derives the whole layer next canonical sweep.
        survivors, offers = [], []
        for pair in sorted(pairs, key=sorted):
            a, b = sorted(pair)
            off, passed = route([(kernels[a], kernels[b])], nli_fn=nli_fn)
            if off:
                offers.append({"type": "contradicts", "origin": "machine-found",
                               "pair": (a, b), "nli": off[0]["nli"]})
                continue  # an offer is returned for the author — NEVER minted (C2c)
            survivors.append((a, b))
        # wipe unconditionally: a shrunken/empty nomination set still clears stale edges.
        session.run(_WIPE_QUERY, g=g)
        pc = cortex_provenance.provenance_class_for("relates_to")
        minted = []
        for a, b in survivors:
            session.run(_MINT_QUERY, g=g, a=a, b=b, pc=pc)
            minted.append((a, b))
        return {"minted": minted, "offers": offers}
    except Exception:
        return None
    finally:
        if drv is not None:
            try:
                drv.close()
            except Exception:
                pass


# ponytail: 3-char floor — 1-2 char entity names ("ed", "AI") false-positive all over prose;
# lower it only if a real short-named Entity ever matters enough to pay the noise.
_MIN_MENTION_LEN = 3


def extract_mentions(text, names):
    """The entities `text` DE FATO names, matched CONSERVATIVELY against the graph's existing
    entity `names` (spec 02-D guard-rail: nome exato, word-boundary, case-insensitive; sem
    fuzzy-inventivo — a mention is never fabricated, so no stemming, no plural, no substring).
    Lookaround boundaries (not ``\\b``) so names ending in non-word chars ("node.js") still
    anchor. Returns graph-cased names, deduped case-insensitively, in input order. Pure."""
    if not text or not names:
        return []
    out, seen = [], set()
    for name in names:
        if not isinstance(name, str):
            continue
        n = name.strip()
        if len(n) < _MIN_MENTION_LEN or n.lower() in seen:
            continue
        if re.search(r"(?<!\w)" + re.escape(n) + r"(?!\w)", text, re.IGNORECASE):
            seen.add(n.lower())
            out.append(n)
    return out


def project_mentions(session, group, slug, text):
    """The thematic via, written INLINE at publish (the operator cut the offline curator — the
    producer, hot with the theme's context, is the only curator): wipe THIS artefato's outgoing
    MENTIONS (a republish whose text dropped a mention strands no stale edge; Episodic MENTIONS
    are graphiti's, untouched) → MERGE (a)-[:MENTIONS {provenance_class:'asserted'}]->(e) for
    every existing :Entity the published `text` exactly names. 'asserted' because o artefato DE
    FATO menciona (spec 02-D); the plane is derived, never a literal fork.

    Runs inside the publisher's ALREADY-OPEN session (no second driver). NEVER raises into the
    publish (prints) — but a swallowed failure returns **None**, not a count (codex adversarial
    #3): the wipe may have landed before the failure, so the caller must leave the projection
    INCOMPLETE and let the next sweep replay the slug (the embed-retry precedent — self-heal,
    never a silent strand). Success returns the mention count (0 is a success)."""
    try:
        rows = session.run("MATCH (e:Entity {group_id:$g}) WHERE e.name IS NOT NULL "
                           "RETURN DISTINCT e.name AS name", g=group).data()
        found = extract_mentions(text, [r["name"] for r in rows])
        session.run("MATCH (a:Artefato {group_id:$g, slug:$slug})-[r:MENTIONS]->() DELETE r",
                    g=group, slug=slug)
        pc = cortex_provenance.provenance_class_for("mentions")
        for name in found:
            session.run("MATCH (a:Artefato {group_id:$g, slug:$slug}),"
                        "(e:Entity {group_id:$g, name:$n}) "
                        "MERGE (a)-[r:MENTIONS]->(e) SET r.provenance_class=$pc",
                        g=group, slug=slug, n=name, pc=pc)
        return len(found)
    except Exception as ex:  # noqa: BLE001 — best-effort; the publish must never feel this
        print("mentions skipped (best-effort, will retry on recovery):", ex)
        return None
