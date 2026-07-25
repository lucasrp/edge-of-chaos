"""relate — the two-stage RELATES_TO nominator (issue #39, cosine-nominates-the-author-disposes).

Stage-1 floor is a RELATIVE percentile of the LIVE pairwise-cosine distribution, NOT a
borrowed absolute constant. OpenAI embeddings are anisotropic and corpus-specific, so an
absolute 0.7/0.8 means a different thing per corpus; the signal is the DEVIATION from the
model's background, so the floor must track the live distribution (research spec lines 18,
42-44). These tests pin that the floor IS a percentile of the actual pairs handed in — move
the vectors and the floor moves — and that it degrades to no-floor on thin input.
"""
import math
import statistics
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
import relate  # noqa: E402


def _cos(a, b):
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


class RelativeFloorIsPercentileOfLivePairs(unittest.TestCase):
    """The floor is the pct-th percentile of THESE pairs' cosines, not a fixed number.
    Hand-build vectors with known pairwise cosines, assert relative_floor returns the
    87th percentile of THOSE pairs — then change the vectors and watch the floor move."""

    def test_relative_floor_is_percentile_of_live_pairs(self):
        # Five 2-D vectors at known angles → known pairwise cosines.
        def unit(deg):
            r = math.radians(deg)
            return [math.cos(r), math.sin(r)]

        vectors = [unit(d) for d in (0, 10, 20, 40, 80)]

        # Reference: every pair's cosine, then the 87th percentile of that distribution.
        pairs = [
            _cos(vectors[i], vectors[j])
            for i in range(len(vectors))
            for j in range(i + 1, len(vectors))
        ]
        ordered = sorted(pairs)
        # Linear-interpolation percentile over the sorted sample (pct in 0..100).
        rank = (87 / 100) * (len(ordered) - 1)
        lo = int(math.floor(rank))
        hi = int(math.ceil(rank))
        expected = ordered[lo] + (ordered[hi] - ordered[lo]) * (rank - lo)

        floor = relate.relative_floor(vectors, pct=87)
        self.assertIsNotNone(floor)
        self.assertAlmostEqual(floor, expected, places=9)

        # pct is a real METHOD PARAMETER, not a hardcoded 87 inside the function: a distinct
        # pct on the SAME corpus must route through _percentile and yield a different floor.
        rank60 = (60 / 100) * (len(ordered) - 1)
        lo60, hi60 = int(math.floor(rank60)), int(math.ceil(rank60))
        expected60 = ordered[lo60] + (ordered[hi60] - ordered[lo60]) * (rank60 - lo60)
        floor60 = relate.relative_floor(vectors, pct=60)
        self.assertAlmostEqual(floor60, expected60, places=9)
        self.assertNotAlmostEqual(floor60, floor, places=6)  # the pct knob actually moves it

        # It is RELATIVE: a different live distribution yields a different floor.
        tighter = [unit(d) for d in (0, 2, 4, 6, 8)]  # all near-parallel → higher cosines
        floor_tighter = relate.relative_floor(tighter, pct=87)
        self.assertIsNotNone(floor_tighter)
        self.assertNotAlmostEqual(floor, floor_tighter, places=6)
        self.assertGreater(floor_tighter, floor)

        # And it is genuinely a percentile of THAT corpus, not a constant.
        pairs_t = [
            _cos(tighter[i], tighter[j])
            for i in range(len(tighter))
            for j in range(i + 1, len(tighter))
        ]
        ot = sorted(pairs_t)
        rank_t = (87 / 100) * (len(ot) - 1)
        lo_t, hi_t = int(math.floor(rank_t)), int(math.ceil(rank_t))
        expected_t = ot[lo_t] + (ot[hi_t] - ot[lo_t]) * (rank_t - lo_t)
        self.assertAlmostEqual(floor_tighter, expected_t, places=9)


class FloorDegradesOnThinInput(unittest.TestCase):
    """Fewer than two vectors → there is no pairwise distribution, so there is no floor.
    Degrade-safe: return None (no-op), never raise (mirrors eventlog.cosine's degrade rule)."""

    def test_floor_degrades_on_thin_input(self):
        self.assertIsNone(relate.relative_floor([]))
        self.assertIsNone(relate.relative_floor([[1.0, 0.0]]))
        # None / garbage embeddings do not crash the floor either.
        self.assertIsNone(relate.relative_floor(None))


class FloorNeverRaisesOnBadVectors(unittest.TestCase):
    """The docstring promises "never raises". eventlog.cosine raises TypeError on
    non-numeric elements, so a corpus with a malformed vector must degrade to None
    (no floor), not propagate the exception (mirrors eventlog.cosine's degrade rule)."""

    def test_non_numeric_vectors_degrade_to_none(self):
        bad = [[1.0, 0.0], ["a", "b"]]  # second vector is non-numeric → cosine would raise
        self.assertIsNone(relate.relative_floor(bad))
        none_el = [[1.0, 0.0], [None, 1.0]]
        self.assertIsNone(relate.relative_floor(none_el))


class NominateMutualKnnAboveFloor(unittest.TestCase):
    """Stage 1 NOMINATE — mutual-kNN with k = round(log2 N), above the relative floor.
    The corpus of embeddings is INJECTED (fake vectors), so these pin the method, not OpenAI:
      - k follows round(log2 N) exactly (k=4 at N=16, k=3 at N=8);
      - a one-directional top-k membership (hub) produces NO candidate — only a mutual pair survives;
      - a mutual pair whose cosine sits BELOW the relative floor is not nominated;
      - no graph (no reader, no creds) degrades to [] and never raises.
    Candidates come back as a set of frozenset({slug_i, slug_j}) — undirected, deduped."""

    @staticmethod
    def _unit(deg):
        r = math.radians(deg)
        return [math.cos(r), math.sin(r)]

    def test_k_is_round_log2_n(self):
        # k = round(log2 N): N=16 -> 4, N=8 -> 3. Pin via the injected corpus size.
        self.assertEqual(relate._k_for(16), 4)
        self.assertEqual(relate._k_for(8), 3)

    def test_mutual_knn_drops_one_directional_edges(self):
        # Four near-parallel notes (a tight cluster) plus one OUTLIER far away. With k=round(log2 4)=2,
        # each cluster note's top-2 are its two nearest cluster peers; the outlier is in NOBODY's top-2
        # (it is everyone's farthest), and the outlier's OWN top-2 point back into the cluster — a
        # one-directional membership. Mutual-kNN must drop every outlier edge and keep cluster pairs.
        corpus = [
            ("a", self._unit(0)),
            ("b", self._unit(4)),
            ("c", self._unit(8)),
            ("d", self._unit(12)),
            ("z", self._unit(170)),  # outlier: far from the cluster
        ]
        # floor low enough that the cluster's own pairs clear it but the test is about mutuality.
        cands = relate.nominate(embeddings=corpus, floor=-1.0)
        # No candidate may include the outlier — its top-k membership is one-directional only.
        for pair in cands:
            self.assertNotIn("z", pair, f"one-directional hub edge survived: {sorted(pair)}")
        # A genuinely mutual cluster pair is kept (a<->b are each other's nearest).
        self.assertIn(frozenset({"a", "b"}), cands)

    def test_below_floor_excluded(self):
        # A mutual pair (each is the other's sole nearest neighbour) whose cosine is BELOW the floor
        # must NOT be nominated — mutuality is necessary but not sufficient; the floor still gates.
        a, b = self._unit(0), self._unit(40)  # cos(40deg) ~= 0.766
        corpus = [("a", a), ("b", b)]
        cos_ab = _cos(a, b)
        # Floor just ABOVE their cosine -> excluded even though they are mutual.
        self.assertEqual(relate.nominate(embeddings=corpus, floor=cos_ab + 0.05), set())
        # Floor just BELOW -> the same mutual pair IS nominated (proves the floor is the only gate).
        self.assertEqual(relate.nominate(embeddings=corpus, floor=cos_ab - 0.05),
                         {frozenset({"a", "b"})})

    def test_nominate_degrades_offline(self):
        # No graph reachable (no reader, no creds, no group) -> [] / empty set, never a raise.
        self.assertEqual(relate.nominate(group=None), set())
        # An injected reader that returns nothing (dark/empty graph) also degrades, not crashes.
        self.assertEqual(relate.nominate(read_fn=lambda **_: []), set())
        # A reader that itself raises (transient outage) is swallowed -> empty, never propagates.
        def boom(**_):
            raise RuntimeError("neo4j down")
        self.assertEqual(relate.nominate(read_fn=boom, group="g"), set())
        # A MALFORMED vector in the injected corpus (non-numeric element) also degrades to empty
        # and never raises — eventlog.cosine would TypeError, but "never raises" is the contract.
        self.assertEqual(
            relate.nominate(embeddings=[("a", [1.0, 0.0]), ("b", ["bad", 0.0])], floor=0.0),
            set())

    def test_nominate_resolves_floor_from_corpus_not_caller(self):
        # The C1 floor is the relative percentile of THIS corpus, NOT a caller-supplied constant.
        # Omit `floor` (floor=_AUTO) so nominate must resolve it via relative_floor(vectors, pct).
        # Five vectors at known angles → a known pairwise-cosine distribution; shifting `pct`
        # moves the floor and so changes which mutual pairs survive — proving the gate is the
        # computed corpus percentile, not a fixed number.
        corpus = [(s, self._unit(d)) for s, d in zip("abcde", (0, 10, 20, 40, 80))]
        vectors = [v for _, v in corpus]

        # A LOW percentile floor (pct=10) sits near the bottom of the distribution → permissive,
        # so the mutual cluster pairs clear it.
        loose = relate.nominate(embeddings=corpus, pct=10)
        # A HIGH percentile floor (pct=99) sits near the top → strict, so strictly fewer survive.
        strict = relate.nominate(embeddings=corpus, pct=99)
        self.assertNotEqual(loose, strict)
        self.assertTrue(strict.issubset(loose),
                        "a higher percentile floor must only ever REMOVE candidates")
        self.assertLess(len(strict), len(loose))

        # And the resolved gate is exactly relative_floor(vectors, pct), not a constant: replaying
        # nominate with that explicit floor must reproduce the _AUTO result for the SAME pct.
        for pct in (10, 99):
            resolved = relate.relative_floor(vectors, pct=pct)
            self.assertEqual(
                relate.nominate(embeddings=corpus, pct=pct),
                relate.nominate(embeddings=corpus, floor=resolved),
                f"_AUTO floor must equal relative_floor(corpus, pct={pct})")


class ReaderDegradesOnExplicitNoneGroup(unittest.TestCase):
    """The reader's docstring promises `group=None -> []` (degrade, no cross-tenant default).
    A DIRECT helper call with group=None must therefore degrade to [] — it must NOT self-resolve
    to this install's own group. Auto-resolution is gated behind the _AUTO sentinel (parity with
    nominate), so the explicit None is honoured as a degrade."""

    def test_reader_explicit_none_group_degrades_to_empty(self):
        self.assertEqual(relate._read_artefato_embeddings(group=None), [])


class NliRouterRunsBeforeRelateTyper(unittest.TestCase):
    """Stage 2 router (C2a) — NLI/entailment FIRST, BOTH directions, BEFORE any relate framing
    (research spec lines 42-44, 54). Cosine has ALREADY guaranteed topical closeness, so a
    relate-primed prompt is blind to refutation: the contradiction signal must be extracted by a
    DECOUPLED high-recall NLI path, not a post-filter. So the router calls nli_fn FIRST; only
    entailment/neutral pairs reach the relate typer (C2b); a calibrated contradiction short-circuits
    to a MACHINE-FOUND contradicts OFFER (C2c) and NEVER touches the typer. nli_fn and type_fn are
    both INJECTED here (spies), so these pin the ORDER and the ROUTING, not OpenAI."""

    def test_nli_runs_before_relate_typer(self):
        # Spies record the global call order. An injected contradiction must short-circuit: the
        # relate type_fn must NEVER be called for that pair, and NLI must have run before it.
        order = []

        def nli(a, b):
            order.append(("nli", a, b))
            return {"label": "contradiction", "score": 0.95}

        def type_fn(a, b):
            order.append(("type", a, b))
            return {"type": "relates_to", "context": "shared claim", "confidence": 0.9}

        pairs = [("A is true", "A is false")]
        relate.route(pairs, nli_fn=nli, type_fn=type_fn)

        # NLI ran; the relate typer NEVER ran on a contradiction pair.
        self.assertTrue(any(c[0] == "nli" for c in order), "NLI must run")
        self.assertFalse(any(c[0] == "type" for c in order),
                         "relate typer must NOT run when NLI calibrates a contradiction")
        # And NLI ran FIRST (it is the first recorded call).
        self.assertEqual(order[0][0], "nli")

    def test_nli_both_directions_run_before_typer_on_surviving_pair(self):
        # The ordering proof on a SURVIVING (neutral/entailment) pair — the case where the typer
        # is NOT trivially skipped. A spy records every call in global order; the contract is that
        # BOTH NLI directions (forward then reverse) run BEFORE type_fn is ever invoked. A
        # contradiction pair (where the typer is skipped) cannot prove "NLI-before-typer" because
        # the typer never runs at all; this pins the order for a pair that DOES reach the typer.
        order = []

        def nli(a, b):
            order.append(("nli", a, b))
            return {"label": "neutral", "score": 0.1}

        def type_fn(a, b):
            order.append(("type", a, b))
            return {"type": "relates_to", "context": "shared topic", "confidence": 0.8}

        relate.route([("alpha", "beta")], nli_fn=nli, type_fn=type_fn)

        # Exact, ordered: forward NLI, reverse NLI, THEN the relate typer — no interleaving.
        self.assertEqual(order, [
            ("nli", "alpha", "beta"),
            ("nli", "beta", "alpha"),
            ("type", "alpha", "beta"),
        ])

    def test_nli_runs_both_directions(self):
        # NLI is asymmetric (entailment(A,B) != entailment(B,A)); the spec says BOTH directions.
        # A contradiction surfacing only in the B->A direction must still route to an offer.
        seen = []

        def nli(a, b):
            seen.append((a, b))
            # contradiction only when called as (B, A)
            return {"label": "contradiction" if a == "B" else "neutral", "score": 0.9}

        def type_fn(a, b):
            raise AssertionError("typer must not run when a direction calibrates contradiction")

        offers, passed = relate.route([("A", "B")], nli_fn=nli, type_fn=type_fn)
        self.assertIn(("A", "B"), seen)
        self.assertIn(("B", "A"), seen)
        self.assertEqual(len(offers), 1)
        self.assertEqual(passed, [])

    def test_contradiction_pair_is_routed_to_offer_not_relate(self):
        # A calibrated contradiction becomes a MACHINE-FOUND contradicts OFFER record — RETURNED,
        # not persisted (C2c: offer for the author to confirm, do not auto-write a directed claim).
        def nli(a, b):
            return {"label": "contradiction", "score": 0.91}

        def type_fn(a, b):
            raise AssertionError("contradiction must not reach the relate typer")

        offers, passed = relate.route([("note-x", "note-y")], nli_fn=nli, type_fn=type_fn)
        self.assertEqual(passed, [], "a contradiction pair is NOT passed to the typer")
        self.assertEqual(len(offers), 1)
        offer = offers[0]
        # machine-found, contradicts, an OFFER (not persisted), carrying its NLI provenance.
        self.assertEqual(offer["type"], "contradicts")
        self.assertEqual(offer["origin"], "machine-found")
        self.assertEqual(offer["pair"], ("note-x", "note-y"))
        self.assertEqual(offer["nli"]["label"], "contradiction")

    def test_neutral_passes_to_typer(self):
        # entailment / neutral -> the pair is passed THROUGH to the relate typer (C2b). Pin both.
        for label in ("neutral", "entailment"):
            with self.subTest(label=label):
                typed = []

                def nli(a, b):
                    return {"label": label, "score": 0.8}

                def type_fn(a, b):
                    typed.append((a, b))
                    return {"type": "relates_to", "context": "c", "confidence": 0.8}

                offers, passed = relate.route([("p", "q")], nli_fn=nli, type_fn=type_fn)
                self.assertEqual(offers, [], f"{label} must NOT become a contradiction offer")
                self.assertEqual(passed, [("p", "q")], f"{label} must pass to the typer")
                self.assertEqual(typed, [("p", "q")], f"{label} must reach type_fn")

    def test_nli_degrades_without_key(self):
        # Degrade-safe: with NO injected nli_fn and no key/client reachable, the default NLI must
        # resolve to neutral (pass-through) and NEVER raise — a darkened router is high-recall,
        # not a crash. Every pair passes to the typer; no contradiction offers are invented.
        typed = []

        def type_fn(a, b):
            typed.append((a, b))
            return None

        # No nli_fn supplied -> default runs; no client is reachable in the test env -> neutral.
        offers, passed = relate.route([("a", "b"), ("c", "d")], type_fn=type_fn)
        self.assertEqual(offers, [], "a dark NLI must not fabricate contradiction offers")
        self.assertEqual(passed, [("a", "b"), ("c", "d")], "dark NLI passes everything through")
        self.assertEqual(typed, [("a", "b"), ("c", "d")])

    def test_nli_swallows_a_raising_nli_fn(self):
        # "never raises": an nli_fn that throws (transient outage / bad parse) degrades that pair to
        # neutral pass-through, not a crash that drops the whole batch.
        def boom(a, b):
            raise RuntimeError("nli endpoint down")

        offers, passed = relate.route([("a", "b")], nli_fn=boom, type_fn=lambda a, b: None)
        self.assertEqual(offers, [])
        self.assertEqual(passed, [("a", "b")])


class PercentileMatchesStatisticsQuantiles(unittest.TestCase):
    """The docstring claims parity with statistics.quantiles. Pin it for the small-N
    cases the reviewer flagged (N=2,3): inclusive method == our (n-1) linear interpolation
    for integer percentiles."""

    def test_parity_with_statistics_quantiles_small_n(self):
        for values in ([0.1, 0.5], [0.1, 0.5, 0.9], [0.2, 0.4, 0.6, 0.8]):
            for pct in (50, 60, 87):
                q = statistics.quantiles(values, n=100, method="inclusive")
                ref = q[pct - 1]  # n=100 → q[i] is the (i+1)-th percentile
                got = relate._percentile(values, pct)
                self.assertAlmostEqual(got, ref, places=12, msg=f"{values} @ {pct}")


if __name__ == "__main__":
    unittest.main()
