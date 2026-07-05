"""communities — Módulo 2 (Cortex): consolidação automática + navegação dos knowledge clusters.

Pins the PURE CORE (label propagation, twin-merge, recency fold — bare python, no neo4j) and the
cortex door surface (late-binding, same contract as the C4 wrappers). The neo4j/LLM adapters are
thin and injected; the graph leg degrades dark (None), mirroring briefing.graph_clusters.
"""
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
import communities  # noqa: E402
import cortex  # noqa: E402


TRI_A = [("a", "b"), ("b", "c"), ("a", "c")]
TRI_B = [("d", "e"), ("e", "f"), ("d", "f")]


class TestLabelPropagation(unittest.TestCase):
    def test_two_triangles_two_groups(self):
        groups = communities.cluster(list("abcdef"), TRI_A + TRI_B, min_size=3)
        self.assertEqual(sorted(sorted(g) for g in groups),
                         [["a", "b", "c"], ["d", "e", "f"]])

    def test_deterministic(self):
        nodes = list("abcdefgh")
        edges = TRI_A + TRI_B + [("g", "a"), ("h", "d")]
        self.assertEqual(communities.cluster(nodes, edges, min_size=2),
                         communities.cluster(nodes, edges, min_size=2))

    def test_min_size_drops_dust(self):
        groups = communities.cluster(list("abcx"), TRI_A, min_size=3)
        self.assertEqual([sorted(g) for g in groups], [["a", "b", "c"]])  # x = poeira, fora


class TestMergePass(unittest.TestCase):
    def test_twins_with_cross_edges_merge(self):
        """Dois grupos com ≥2 arestas cruzadas são o mesmo tema partido — fundem."""
        groups = [["a", "b", "c"], ["d", "e", "f"]]
        cross = TRI_A + TRI_B + [("c", "d"), ("b", "e")]
        merged = communities.merge_pass(groups, cross, min_cross=2)
        self.assertEqual([sorted(g) for g in merged], [["a", "b", "c", "d", "e", "f"]])

    def test_unrelated_groups_stay_apart(self):
        groups = [["a", "b", "c"], ["d", "e", "f"]]
        merged = communities.merge_pass(groups, TRI_A + TRI_B, min_cross=2)
        self.assertEqual(len(merged), 2)


class TestRecencyFold(unittest.TestCase):
    def test_last_touched_is_max_member_date(self):
        dates = {"a": "2026-06-01T00:00:00Z", "b": "2026-07-04T12:00:00Z", "c": None}
        self.assertEqual(communities.last_touched(dates), "2026-07-04T12:00:00Z")

    def test_all_none_is_none(self):
        self.assertIsNone(communities.last_touched({"a": None}))


class TestCortexDoor(unittest.TestCase):
    def test_surface(self):
        """A porta Módulo-2 expõe a navegação: communities · community · locate."""
        for name in ("communities", "community", "locate"):
            self.assertTrue(callable(getattr(cortex, name)), name)

    def test_late_binding(self):
        """Monkeypatch no órgão atravessa a porta (o contrato C4)."""
        original = communities.communities
        try:
            communities.communities = lambda *a, **k: [{"name": "patched"}]
            self.assertEqual(cortex.communities()[0]["name"], "patched")
        finally:
            communities.communities = original


if __name__ == "__main__":
    unittest.main()
