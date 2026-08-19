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


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def data(self):
        return self._rows

    def single(self):
        return self._rows[0] if self._rows else None


class _FakeSession:
    """O mínimo do driver neo4j que `consolidate` toca: as duas leituras e a escrita."""

    def __init__(self, ents=(), rels=(), raise_on_read=None):
        self.ents, self.rels, self.raise_on_read = list(ents), list(rels), raise_on_read
        self.writes = []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def run(self, query, **params):
        if self.raise_on_read:
            raise self.raise_on_read
        if "MATCH (n:Entity" in query:
            return _FakeResult(self.ents)
        if "RELATES_TO" in query and "RETURN a.uuid" in query:
            return _FakeResult(self.rels)
        self.writes.append(query)
        return _FakeResult([])

    def execute_write(self, fn):
        return fn(self)


class _FakeDriver:
    def __init__(self, session):
        self._session = session

    def session(self):
        return self._session


class TestConsolidateNoneIsAFailure(unittest.TestCase):
    """O dente da #635.

    `consolidate()` devolvia None em três situações que são coisas DIFERENTES — sem grupo, sem
    driver, e erro no meio do grafo — e o chamador imprimia "0 clusters" para todas. Um órgão que
    não rodou lia-se exatamente como um grafo que ainda não tem o que agrupar; foi essa
    indistinção que fez o apagão de identidade (lida em tempo de import, corrigido no #603)
    passar por ESCASSEZ por meses. Ausência de resultado só é sucesso quando o órgão rodou."""

    def _patched_driver(self, driver):
        original = communities._driver
        communities._driver = lambda **kw: driver
        self.addCleanup(lambda: setattr(communities, "_driver", original))

    def test_no_group_is_a_failure_not_a_silent_none(self):
        """A FIXTURE do sintoma relatado: a chamada que devolvia None na hora, antes de tocar o
        grafo. Vermelha no comportamento antigo — lá isto era `assertIsNone`."""
        with self.assertRaises(communities.ConsolidationFailed) as caught:
            communities.consolidate(group=None)
        self.assertEqual(caught.exception.reason, "no-group")
        self.assertEqual(caught.exception.severity, "dark")   # não pude rodar

    def test_unreachable_graph_is_a_failure(self):
        self._patched_driver(None)
        with self.assertRaises(communities.ConsolidationFailed) as caught:
            communities.consolidate(group="g")
        self.assertEqual(caught.exception.reason, "graph-unreachable")
        self.assertEqual(caught.exception.severity, "dark")

    def test_error_mid_sweep_is_a_failure_and_keeps_the_cause(self):
        boom = RuntimeError("Neo4jError: transaction terminated")
        self._patched_driver(_FakeDriver(_FakeSession(raise_on_read=boom)))
        with self.assertRaises(communities.ConsolidationFailed) as caught:
            communities.consolidate(group="g")
        self.assertEqual(caught.exception.reason, "graph-error")
        self.assertEqual(caught.exception.severity, "fail")   # rodei e quebrei
        self.assertIs(caught.exception.__cause__, boom)

    def test_the_severities_are_group_healths_words(self):
        """#638 já separa `dark` (não pude medir) de `fail` (medi e está ruim) e diz, no
        próprio verdict de Community, que ZERO só é legítimo se o consolidate falhou ALTO.
        Este módulo fala a MESMA língua — um terceiro vocabulário reabriria a indistinção
        num outro lugar."""
        import group_health
        vocabulary = {sev for sev, _ in group_health.verdicts(
            {"group": "g", "nodes": 0, "genesis": 0, "objectives": 0, "directions_total": 0,
             "directions_with_handle": 0, "directions_with_lifecycle": 0, "communities": 0,
             "has_topic_edges": 0, "has_topic_degree": 0.0})} | {"dark", "warn"}
        self.assertTrue(set(communities.ConsolidationFailed.SEVERITIES.values()) <= vocabulary)

    def test_nothing_to_group_is_a_legitimate_empty_list(self):
        """O outro lado do dente: um grafo alcançável e vazio NÃO é falha — devolve []."""
        self._patched_driver(_FakeDriver(_FakeSession(ents=[], rels=[])))
        self.assertEqual(communities.consolidate(group="g"), [])

    def test_only_dust_is_also_an_empty_list(self):
        """Entidades existem mas nenhuma forma cluster >= min_size: rodou, não achou. []"""
        ents = [{"u": u, "name": u, "summ": ""} for u in ("a", "b")]
        self._patched_driver(_FakeDriver(_FakeSession(ents=ents, rels=[])))
        self.assertEqual(communities.consolidate(group="g", summarize_fn=lambda m: "NOME: x"), [])

    def test_a_real_cluster_still_writes_and_returns_it(self):
        ents = [{"u": u, "name": u, "summ": ""} for u in ("a", "b", "c")]
        rels = [{"a": x, "b": y} for x, y in TRI_A]
        session = _FakeSession(ents=ents, rels=rels)
        self._patched_driver(_FakeDriver(session))
        out = communities.consolidate(
            group="g", summarize_fn=lambda m: "NOME: Tema | SUMÁRIO: resumo")
        self.assertEqual(out, [{"name": "Tema", "size": 3}])
        self.assertTrue(any("CREATE (c:Community" in q for q in session.writes))


class TestSweepReportsConsolidationFailureLoud(unittest.TestCase):
    """"0 clusters" tem que significar UMA coisa só. O chamador é onde a indistinção era visível
    para o operador, então é onde o teste morde."""

    def _run_maybe_consolidate(self, fake):
        import contextlib
        import io
        import os
        import sweep
        original = communities.consolidate
        os.environ["EDGE_COMMUNITIES"] = "1"
        buf = io.StringIO()
        try:
            communities.consolidate = fake
            with contextlib.redirect_stdout(buf):
                sweep._maybe_consolidate()
        finally:
            communities.consolidate = original
            os.environ.pop("EDGE_COMMUNITIES", None)
        return buf.getvalue()

    def test_nothing_to_group_reads_as_zero_clusters(self):
        out = self._run_maybe_consolidate(lambda **kw: [])
        self.assertIn("0 clusters", out)

    def test_failure_does_not_read_as_zero_clusters(self):
        def fail(**kw):
            raise communities.ConsolidationFailed("no-group", "sem identidade de grupo")

        out = self._run_maybe_consolidate(fail)
        self.assertNotIn("0 clusters", out)      # a linha calma da escassez NÃO pode aparecer
        self.assertIn("FALHARAM", out)
        self.assertIn("no-group", out)
        self.assertIn("[dark]", out)             # a severidade de group_health, no terminal
        self.assertIn("PARADAS", out)            # paradas, não vazias

    def test_an_unexpected_error_is_also_loud_and_never_raises(self):
        def boom(**kw):
            raise RuntimeError("boom")

        out = self._run_maybe_consolidate(boom)   # não derruba o sweep
        self.assertNotIn("0 clusters", out)
        self.assertIn("FALHARAM", out)


if __name__ == "__main__":
    unittest.main()
