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

    def test_undirected_rows_do_not_double_count(self):
        """[codex high] MATCH -[:RELATES_TO]- devolve cada aresta 2x (uma por direção): UMA
        aresta real entre grupos não pode disparar min_cross=2 — canonicaliza antes de contar."""
        groups = [["a", "b", "c"], ["d", "e", "f"]]
        edges = TRI_A + TRI_B + [("c", "d"), ("d", "c")]  # 1 aresta real, 2 linhas
        merged = communities.merge_pass(groups, edges, min_cross=2)
        self.assertEqual(len(merged), 2)  # NÃO funde


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


class TestBriefingSection(unittest.TestCase):
    """§5 re-apontado: renderiza o shape das communities (nome·size·last_touched·summary),
    contrato None/[] preservado, e a regra TEMPO-DIVIDE-DONOS (cluster tocado dentro da janela
    do quente não expande — vira ponteiro)."""

    ROWS = [
        {"name": "Tema Velho", "summary": "resumo velho", "size": 5,
         "last_touched": "2026-06-10T00:00:00Z"},
        {"name": "Tema Quente", "summary": "resumo novo", "size": 3,
         "last_touched": "2026-07-05T01:00:00Z"},
    ]

    def test_renders_communities_shape(self):
        import briefing
        out = briefing._section_clusters(self.ROWS)
        self.assertIn("Tema Velho", out)
        self.assertIn("2026-06-10", out)  # a navegação pelo tempo aparece
        self.assertIn("resumo velho", out)

    def test_tempo_divide_donos(self):
        import briefing
        out = briefing._section_clusters(self.ROWS, hot_cutoff="2026-07-04T00:00:00Z")
        self.assertIn("coberto no quente", out)      # o quente é o dono do recente
        self.assertNotIn("resumo novo", out)          # não expande
        self.assertIn("resumo velho", out)            # o velho expande normal

    def test_dark_and_empty_contracts_hold(self):
        import briefing
        self.assertIn("DARK", briefing._section_clusters(None))
        self.assertIn("no clusters yet", briefing._section_clusters([]))


class TestSweepKnob(unittest.TestCase):
    """Consolidação no sweep atrás de EDGE_COMMUNITIES (dark por default, padrão EDGE_CONDUCTOR)."""

    def test_off_by_default(self):
        import os, sweep
        os.environ.pop("EDGE_COMMUNITIES", None)
        called = []
        original = communities.consolidate
        try:
            communities.consolidate = lambda **k: called.append(1)
            sweep._maybe_consolidate()
        finally:
            communities.consolidate = original
        self.assertEqual(called, [])

    def test_on_calls_and_never_raises(self):
        import os, sweep
        os.environ["EDGE_COMMUNITIES"] = "1"
        original = communities.consolidate
        try:
            communities.consolidate = lambda **k: (_ for _ in ()).throw(RuntimeError("boom"))
            sweep._maybe_consolidate()  # engole e loga — nunca derruba o sweep
            called = []
            communities.consolidate = lambda **k: called.append(1) or [{"name": "x", "size": 3}]
            sweep._maybe_consolidate()
            self.assertEqual(called, [1])
        finally:
            communities.consolidate = original
            os.environ.pop("EDGE_COMMUNITIES", None)

if __name__ == "__main__":
    unittest.main()
