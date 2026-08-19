"""O critério de saúde de frota (#636) — medido contra um grafo FALSO, de propósito.

Este módulo é hermético: nada aqui abre o Neo4j. O instrumento existe para dizer se um grafo é
navegável, e um teste que precisasse de um grafo vivo mediria o host de quem roda a suíte — a
doença que os PRs #610/#611/#615/#623/#630 passaram o dia extirpando.

O dublê responde às consultas por assinatura. Se `group_health` mudar de query, o dublê deixa de
reconhecê-la e devolve zero — o teste fica vermelho em vez de mentir. Foi assim que
`test_project_doc` escondeu uma projeção quebrada por meses (PR #621).
"""
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
import group_health  # noqa: E402


class _Record(dict):
    def single(self):
        return self

    def data(self):
        return self.get("_rows", [])


class FakeSession:
    """Um grafo declarado como números, não como nós — o instrumento só conta."""

    def __init__(self, spec, group_counts=None):
        self.spec = spec
        self.group_counts = group_counts or [(g, s["nodes"]) for g, s in spec.items()]
        self.queries = []

    def run(self, cypher, **kw):
        self.queries.append(cypher)
        g = kw.get("g")
        s = self.spec.get(g, {})
        if "RETURN n.group_id AS g" in cypher:
            rec = _Record()
            rec["_rows"] = [{"g": name, "c": c} for name, c in self.group_counts]
            return rec
        if ":Genesis" in cypher:
            return _Record(n=s.get("genesis", 0))
        if ":Objective" in cypher:
            return _Record(n=s.get("objectives", 0))
        if ":Direction" in cypher:
            return _Record(total=s.get("directions", 0),
                           with_handle=s.get("handles", 0),
                           with_lifecycle=s.get("lifecycles", 0))
        if ":Community" in cypher:
            return _Record(n=s.get("communities", 0))
        if "HAS_TOPIC" in cypher:
            return _Record(n=s.get("has_topic", 0))
        if "MATCH (n {group_id:$g})" in cypher:
            return _Record(n=s.get("nodes", 0))
        raise AssertionError(f"consulta não reconhecida pelo dublê: {cypher[:70]}")


HEALTHY = {"nodes": 200, "genesis": 1, "objectives": 1, "directions": 3,
           "handles": 3, "lifecycles": 3, "communities": 2, "has_topic": 40}


class TheCriterionAnswersWithoutReadingBody(unittest.TestCase):
    def test_a_navigable_group_has_no_verdicts(self):
        s = FakeSession({"ok": HEALTHY})
        self.assertEqual(group_health.verdicts(group_health.health(s, "ok")), [])

    def test_no_query_reads_a_body(self):
        """A restrição É o teste: se para saber no que o agente trabalha for preciso abrir o
        body, o grafo é diário e não memória. O instrumento não pode contornar isso lendo."""
        s = FakeSession({"ok": HEALTHY})
        group_health.health(s, "ok")
        self.assertTrue(s.queries, "o dublê não recebeu consulta nenhuma")
        for q in s.queries:
            self.assertNotIn(".body", q, f"o critério leu body: {q[:80]}")
            self.assertNotIn("n.content", q, f"o critério leu conteúdo: {q[:80]}")


class TheFourFailuresAreDetected(unittest.TestCase):
    def _msgs(self, **over):
        spec = dict(HEALTHY, **over)
        card = group_health.health(FakeSession({"g": spec}), "g")
        return [m for _sev, m in group_health.verdicts(card)]

    def test_direction_without_handle_is_named(self):
        """#632: o caso roberto — 788 Directions e nenhuma listável."""
        msgs = self._msgs(directions=788, handles=0, lifecycles=0)
        self.assertTrue(any("788 Directions sem handle" in m for m in msgs), msgs)
        self.assertTrue(any("acima do teto" in m for m in msgs), msgs)

    def test_objective_is_not_a_singleton(self):
        """#633: o caso petertosh — 6 cópias do mesmo norte."""
        self.assertTrue(any("6 Objectives vivos" in m for m in self._msgs(objectives=6)))

    def test_zero_community_on_a_big_graph_is_a_failure_not_scarcity(self):
        """#635: zero Community só é legítimo se o consolidate falhou ALTO. Num grafo grande,
        silêncio é falha — foi essa indistinção que fez o apagão da frota durar meses."""
        self.assertTrue(any("grafo write-only" in m for m in self._msgs(communities=0)))

    def test_a_small_graph_with_no_community_is_not_accused(self):
        """O contrapeso: 20 nós sem cluster é escassez de verdade, não apagão. Um critério que
        acusa os dois igual treina o operador a ignorar o critério."""
        self.assertEqual([], self._msgs(nodes=20, communities=0, directions=1,
                                        handles=1, lifecycles=1, has_topic=2))

    def test_has_topic_saturation_is_named(self):
        """#635: 21357 arestas para ~15400 nós — tudo liga em tudo, o grafo deixa de apontar."""
        self.assertTrue(any("HAS_TOPIC" in m for m in self._msgs(nodes=15400, has_topic=21357)))


class LeftoversAreTheFenceHidingTheDead(unittest.TestCase):
    def test_a_group_that_is_not_an_install_is_flagged(self):
        """#634: `peter tosh` 269 + `petertosh` 2490 são o mesmo agente em dois tenants."""
        s = FakeSession({}, group_counts=[("petertosh", 2490), ("peter tosh", 269)])
        msgs = [m for _s, m in group_health.leftovers(s, {"petertosh"})]
        self.assertEqual(len(msgs), 1)
        self.assertIn("peter tosh", msgs[0])

    def test_nodes_without_a_group_are_a_failure(self):
        """Nó sem group_id é invisível a qualquer filtro por tenant — e uma query sem `$g` o
        vê como fantasma."""
        s = FakeSession({}, group_counts=[("ed", 21), (None, 9)])
        sev = [sv for sv, _m in group_health.leftovers(s, {"ed"})]
        self.assertIn("fail", sev)


if __name__ == "__main__":
    unittest.main()
