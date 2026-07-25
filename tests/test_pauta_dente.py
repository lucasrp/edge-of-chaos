"""O DENTE no seam do dispatch (ADR-0024, spec §1): sem `pauta.proposta` viva não abre
Ato-2 — o producer do plano É a forma da PROPOSTA. A rotação (cursor.json / next_producer)
morreu com esta fiação; a estrada theme_suggest idem (commit-to-remove).
"""
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
import _beat  # noqa: E402
import eventlog  # noqa: E402
import pauta  # noqa: E402

CELL = {"objeto": "mentorado", "abordagem": "fog", "locked": []}
CMD = ["/opt/claude", "-p", "-", "--dangerously-skip-permissions"]


def _passa_tudo(prompt):
    # Fake permissivo (o dente não testa juízo): satisfaz check batch E critério.
    return '{"reprova": [], "veredito": "passa", "evidencia": "ok"}'


def _propose(log, dispatch_id="d1", forma="report"):
    # Caminho AUTÔNOMO (r3): a via Voz agora exige dispatch.open comandado no log
    # (adv r2 #1) — o dente é agnóstico da via; o fixture usa a estrada sem pedigree.
    cand = {"tema": "T", "forma": forma, "lastro": "lido: x"}
    return pauta.propose(CELL, [cand], dispatch_id=dispatch_id,
                         completer=_passa_tudo, log=log)


class _LogCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.log = Path(self._tmp.name) / "log.jsonl"
        self.addCleanup(self._tmp.cleanup)


class DispatchPlanIsTheDente(_LogCase):
    def test_no_proposta_no_plan(self):
        with self.assertRaises(RuntimeError):
            _beat.dispatch_plan("lead", "d1", runtime_command=CMD, log=self.log)

    def test_producer_is_the_proposta_forma(self):
        _propose(self.log, forma="map")
        plan = _beat.dispatch_plan("lead", "d1", runtime_command=CMD, log=self.log)
        self.assertEqual(plan["decision"]["producer"], "map")
        self.assertEqual(plan["decision"]["dispatch_id"], "d1")
        self.assertEqual(set(plan), {"decision", "tools", "permissions"})

    def test_veto_closes_the_door_again(self):
        _propose(self.log)
        pauta.veto("d1", "não é a hora", log=self.log)
        with self.assertRaises(RuntimeError):
            _beat.dispatch_plan("lead", "d1", runtime_command=CMD, log=self.log)

    def test_prelaunch_plan_is_explicitly_pending_never_a_producer(self):
        # o heartbeat computa o plano ANTES do agente existir — sem proposta o plano
        # declara pendência; nunca inventa producer (a rotação morreu).
        plan = _beat.dispatch_plan("lead", "d1", runtime_command=CMD, log=self.log,
                                   require_pauta=False)
        self.assertIsNone(plan["decision"]["producer"])
        self.assertIn("pendente", plan["decision"]["pauta"])

    def test_rotation_road_is_dead(self):
        for name in ("next_producer", "_producer_for_dispatch", "_dispatch_fingerprint",
                     "DEFAULT_PRODUCER_ROSTER"):
            self.assertFalse(hasattr(_beat, name), f"estrada velha viva: _beat.{name}")


class PostGateBitesWithoutProposta(_LogCase):
    def test_artefato_without_live_proposta_is_a_gap(self):
        eventlog.publish_artefato_atomic("furtivo", "why", skill="report",
                                         _rite_authorized=True, log=self.log)
        gaps = _beat.assert_beat_produced(self.log, 0, dispatch_id="d1")
        self.assertTrue(any("pauta.proposta" in g for g in gaps))

    def test_wrong_forma_is_a_gap(self):
        _propose(self.log, forma="map")
        eventlog.publish_artefato_atomic("desviado", "why", skill="report",
                                         _rite_authorized=True, log=self.log)
        gaps = _beat.assert_beat_produced(self.log, 0, dispatch_id="d1")
        self.assertTrue(any("map" in g for g in gaps))

    def test_matching_forma_and_cell_prefixed_slug_pass(self):
        _propose(self.log, forma="report")
        eventlog.publish_artefato_atomic("fog-mentorado--certo", "why", skill="report",
                                         _rite_authorized=True, log=self.log)
        self.assertEqual(_beat.assert_beat_produced(self.log, 0, dispatch_id="d1"), [])

    def test_slug_without_the_cell_prefix_is_a_gap(self):
        # §3 "o nome carrega o setup" agora é MECÂNICO no post-gate (adv r1 #10,
        # dig r2 #4: contrato de metadata verificado pelo gate, nunca asserido no JSON)
        _propose(self.log, forma="report")
        eventlog.publish_artefato_atomic("sem-prefixo", "why", skill="report",
                                         _rite_authorized=True, log=self.log)
        gaps = _beat.assert_beat_produced(self.log, 0, dispatch_id="d1")
        self.assertTrue(any("fog-mentorado--" in g for g in gaps), gaps)

    def test_logged_silencio_is_an_honest_beat_not_a_gap(self):
        # lei do risco: modo de falha honesto = silêncio logado; o heartbeat não pune
        pauta.propose(CELL, [], dispatch_id="d1", log=self.log)  # → pauta.silencio
        gaps = _beat.assert_beat_produced(self.log, 0, dispatch_id="d1")
        self.assertEqual(gaps, [])

    def test_a_historical_silencio_does_not_exempt_forever(self):
        # adv r1 #9 / dig r2 #2: o silêncio exime SÓ se for o ÚLTIMO evento pauta.*
        # do dispatch — silêncio → depois proposta → sem produção = GAP.
        pauta.propose(CELL, [], dispatch_id="d1", log=self.log)  # silêncio
        _propose(self.log, forma="report")                       # depois: proposta viva
        gaps = _beat.assert_beat_produced(self.log, 0, dispatch_id="d1")
        self.assertTrue(gaps)

    def test_proposta_then_silencio_without_production_is_still_a_gap(self):
        # adv r2 #2 (REPRODUZIDO lá — a inversão espelho): proposta viva → silêncio
        # posterior → nada produzido. O silêncio não mata a proposta (by design);
        # a isenção exige latest==silencio E nenhuma proposta viva.
        _propose(self.log, forma="report")                       # proposta viva
        pauta.propose(CELL, [], dispatch_id="d1", log=self.log)  # depois: silêncio
        gaps = _beat.assert_beat_produced(self.log, 0, dispatch_id="d1")
        self.assertTrue(gaps, "proposta viva + silêncio posterior + zero produção "
                              "passou sem gap (inversão da isenção)")

    def test_no_growth_and_no_silencio_is_still_a_gap(self):
        gaps = _beat.assert_beat_produced(self.log, 0, dispatch_id="d1")
        self.assertTrue(gaps)

    def test_forged_voz_proposta_in_the_log_is_a_gap_at_the_dente(self):
        # design r3 graft (cinto na caneta, suspensório no dente): um append direto
        # forja origem="voz" SEM dispatch.open comandado — propose nunca viu; o
        # pós-gate deriva do log e marca gap.
        eventlog.append("pauta.proposta", "pauta", {
            "abordagem": "fog", "objeto": "mentorado", "forma": "report", "tema": "T",
            "origem": "voz", "dispatch_id": "d1", "slug_prefix": "fog-mentorado--"},
            log=self.log)
        eventlog.publish_artefato_atomic("fog-mentorado--forjado", "why", skill="report",
                                         _rite_authorized=True, log=self.log)
        gaps = _beat.assert_beat_produced(self.log, 0, dispatch_id="d1")
        self.assertTrue(any("forjada" in g for g in gaps), gaps)

    def test_legit_voz_proposta_with_commanded_open_passes_the_dente(self):
        eventlog.dispatch_open({"dispatch_id": "d1", "origin": "user_requested"},
                               log=self.log)
        pauta.propose(CELL, [], dispatch_id="d1",
                      constraints={"origem": "voz", "tema": "T", "forma": "report"},
                      log=self.log)
        eventlog.publish_artefato_atomic("fog-mentorado--comandado", "why", skill="report",
                                         _rite_authorized=True, log=self.log)
        self.assertEqual(_beat.assert_beat_produced(self.log, 0, dispatch_id="d1"), [])

    def test_dispatch_plan_refuses_a_forged_voz_proposta(self):
        # adv r3 #1 (REPRODUZIDO lá): a fivela do meio estava aberta — o pré-gate
        # aceitava voz forjada e abria Ato-2. Round 4 (Variant A): a verificação mora
        # no fold reader; dispatch_plan herda o raise SEM guarda própria.
        eventlog.append("pauta.proposta", "pauta", {
            "abordagem": "fog", "objeto": "mentorado", "forma": "report", "tema": "T",
            "origem": "voz", "dispatch_id": "d1", "slug_prefix": "fog-mentorado--"},
            log=self.log)
        with self.assertRaises(ValueError):
            _beat.dispatch_plan("lead", "d1", runtime_command=CMD, log=self.log)

    def test_roster_forgery_at_the_post_gate_is_a_gap_never_a_crash(self):
        # o pós-gate REPORTA (o heartbeat precisa do relatório, nunca de um crash):
        # ValueError do fold vira gap nomeado + a lógica do dente segue com proposta=None
        eventlog.append("pauta.proposta", "pauta", {
            "abordagem": "fog", "objeto": "mentorado", "forma": "dig", "tema": "T",
            "origem": "autonomo", "dispatch_id": "d1", "slug_prefix": "fog-mentorado--"},
            log=self.log)
        gaps = _beat.assert_beat_produced(self.log, 0, dispatch_id="d1")
        self.assertTrue(any("forjad" in g for g in gaps), gaps)

    def test_dispatch_plan_refuses_an_out_of_roster_forma_from_a_forged_event(self):
        # adv r2 #3 graft: forma fora do roster só chega ao log por append forjado —
        # o plano nunca nomeia producer que o install não roda; falha alto.
        eventlog.append("pauta.proposta", "pauta", {
            "abordagem": "fog", "objeto": "mentorado", "forma": "dig", "tema": "T",
            "origem": "autonomo", "dispatch_id": "d1", "slug_prefix": "fog-mentorado--"},
            log=self.log)
        with self.assertRaises(ValueError):
            _beat.dispatch_plan("lead", "d1", runtime_command=CMD, log=self.log)


class OldRoadIsClosed(unittest.TestCase):
    def test_theme_suggest_is_gone(self):
        self.assertFalse((REPO / "tools" / "theme_suggest.py").exists(),
                         "commit-to-remove: theme_suggest.py devia ter morrido na fiação")
        for f in ("tools/predispatch.py", "skills/beat/SKILL.md"):
            self.assertNotIn("theme_suggest", (REPO / f).read_text(), f)

    def test_beat_skill_teaches_the_pauta_road(self):
        skill = (REPO / "skills" / "beat" / "SKILL.md").read_text()
        self.assertIn("tools/pauta.py", skill)
        self.assertIn("sortear", skill)
        self.assertIn("pauta.proposta", skill)


if __name__ == "__main__":
    unittest.main()
