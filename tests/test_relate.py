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
