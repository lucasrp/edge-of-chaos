"""Pauta R2 — o funil do meio: catálogo por objeto, shortlist A (~6 + slot ser) com os
checks (delta_voz · filtro direction/wayfind-aberto · substrato) e o hook de grounding
(2–3 pontos de dispatch de explorer). Spec §3 passos 2–5.

As ~12 sugestões ENTRAM como argumento (função do wake, trabalho agêntico do chamador) —
NUNCA pool fixo no repo. Todo check é semântico via completer injetado; offline.
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
import pauta  # noqa: E402
from test_pauta_gates import scripted  # noqa: E402


def sug(i, tema=None):
    return {"tema": tema or f"tema-{i}", "forma": "report", "semente": f"do wake {i}"}


class CatalogoAimsTheWake(unittest.TestCase):
    def test_every_objeto_has_a_catalog_aim_and_ser_is_unbound(self):
        for o in pauta.OBJETOS:
            cat = pauta.catalogo({"objeto": o, "abordagem": "fog"})
            self.assertEqual(cat["objeto"], o)
            self.assertTrue(cat["catalogo"].strip())
        livre = pauta.catalogo({"objeto": "ser", "abordagem": "fog"})
        # §2: objeto=ser → catálogo SEM limite; a exigência fora-do-circuito é do GATE
        self.assertIn("desamarra", livre["catalogo"])
        self.assertNotIn("fora do circuito", livre["catalogo"])

    def test_catalogo_carries_the_funnel_numbers_not_a_theme_pool(self):
        cat = pauta.catalogo({"objeto": "mundo", "abordagem": "fog"})
        self.assertEqual(cat["n_sugestoes"], 12)
        self.assertNotIn("temas", cat)  # onde olhar, nunca o quê dizer


class ShortlistJudgesSemantically(unittest.TestCase):
    CELL = {"objeto": "mundo", "abordagem": "fog", "locked": []}

    def _merit(self, rank, ser=None):
        return json.dumps({"rank": rank, "ser": ser})

    def test_merit_ranking_plus_structural_ser_slot(self):
        sugestoes = [sug(i) for i in range(12)]
        comp = scripted([
            self._merit(list(range(12)), ser=11),          # mérito + pick ser
            json.dumps({"reprova": []}),                    # forma_fit: todos ok
            json.dumps({"reprova": []}),                    # substrato: todos ok
        ])
        out = pauta.shortlist(self.CELL, sugestoes, completer=comp)
        temas = [c["tema"] for c in out["A"]]
        self.assertEqual(len(temas), 6)                     # ~6: 5 mérito + 1 ser
        self.assertIn("tema-11", temas)                     # o slot estrutural
        ser_slot = [c for c in out["A"] if c.get("slot") == "ser"]
        self.assertEqual(len(ser_slot), 1)
        self.assertEqual(ser_slot[0]["tema"], "tema-11")

    def test_ser_slot_null_with_a_non_empty_pool_raises_juiz_fora_do_protocolo(self):
        # adv r2 #6 / §3.4 "+ 1 slot estrutural", §7bis-2 "sempre presente no A":
        # ser=null com pool não-vazio é juiz fora do protocolo — nunca A sem o slot.
        comp = scripted([self._merit([0, 1, 2], ser=None)])
        with self.assertRaises(ValueError):
            pauta.shortlist(self.CELL, [sug(i) for i in range(3)], completer=comp)

    def test_substrato_is_advisory_never_cuts(self):
        sugestoes = [sug(i) for i in range(3)]
        comp = scripted([
            self._merit([0, 1, 2], ser=2),
            json.dumps({"reprova": []}),                    # forma_fit
            json.dumps({"reprova": [{"idx": 0, "evidencia": "vem de log de agente delegado"}]}),
        ])
        out = pauta.shortlist(self.CELL, sugestoes, completer=comp)
        # operador 2026-07-25: wake é insumo, não coleira — substrato NUNCA corta;
        # a ressalva sobrevive no trace, o candidato fica no A.
        self.assertIn("tema-0", [c["tema"] for c in out["A"]])
        self.assertIn("advisory", out["trace"]["substrato"])

    def test_wayfind_filter_runs_only_with_direction_text_and_cuts(self):
        sugestoes = [sug(i) for i in range(3)]
        comp = scripted([
            self._merit([0, 1, 2], ser=2),
            json.dumps({"reprova": []}),                    # forma_fit
            json.dumps({"reprova": []}),                    # substrato
            json.dumps({"reprova": [{"idx": 1, "evidencia": "só re-declara o fio aberto"}]}),
        ])
        out = pauta.shortlist(self.CELL, sugestoes, completer=comp,
                              direction_text="wayfind aberto: fio X")
        self.assertNotIn("tema-1", [c["tema"] for c in out["A"]])
        # sem direction_text o filtro é declarado-não-rodado, nunca fingido
        comp2 = scripted([self._merit([0], ser=0), json.dumps({"reprova": []}),
                          json.dumps({"reprova": []})])
        out2 = pauta.shortlist(self.CELL, [sug(0)], completer=comp2)
        self.assertIn("nao-rodado", out2["trace"]["wayfind"])

    def test_delta_voz_runs_only_on_shortlist_A_and_noop_cuts(self):
        # §7: o órgão delta_voz roda SÓ na shortlist A (custo); noop = pousar sem delta novo
        sugestoes = [sug(i) for i in range(3)]
        comp = scripted([
            self._merit([0, 1, 2], ser=2),
            json.dumps({"reprova": []}),                    # forma_fit
            json.dumps({"reprova": []}),                    # substrato
            json.dumps({"outcome": "noop", "cita": "já disse isso", "dominio": False}),
            json.dumps({"outcome": "delta", "cita": "nunca tocou", "dominio": False}),
            json.dumps({"outcome": "delta", "cita": "nunca tocou 2", "dominio": False}),
        ])
        out = pauta.shortlist(self.CELL, sugestoes, completer=comp,
                              voz_recall_fn=lambda t: f"recall de {t}")
        temas = [c["tema"] for c in out["A"]]
        self.assertNotIn("tema-0", temas)
        for c in out["A"]:
            self.assertEqual(c["delta_voz"]["outcome"], "delta")

    def test_dark_recall_rail_keeps_the_candidate_and_declares(self):
        # adv r2 #8: órgão devolve None (rail escuro) — declara, nunca corta nem finge
        comp = scripted([self._merit([0], ser=0), json.dumps({"reprova": []}),
                         json.dumps({"reprova": []})])
        out = pauta.shortlist(self.CELL, [sug(0)], completer=comp,
                              voz_recall_fn=lambda t: None)
        self.assertEqual(len(out["A"]), 1)
        self.assertEqual(out["A"][0]["delta_voz"]["recall_status"], "unavailable")

    def test_grounding_hook_names_two_to_three_explorer_dispatch_points(self):
        sugestoes = [sug(i) for i in range(6)]
        comp = scripted([
            self._merit(list(range(6)), ser=5),
            json.dumps({"reprova": []}),                    # forma_fit
            json.dumps({"reprova": []}),                    # substrato
        ])
        out = pauta.shortlist(self.CELL, sugestoes, completer=comp)
        self.assertIn(len(out["aterrar"]), (2, 3))
        for pt in out["aterrar"]:
            self.assertIn("explorer", pt)
            self.assertIn(pt["tema"], [c["tema"] for c in out["A"]])
            # mirado no pólo: o aim cita o catálogo da célula
            self.assertIn("mundo", pt["explorer"])

    def test_malformed_merit_rank_raises_fail_closed(self):
        # protocolo do juiz é um só (_ask): rank fora do range = infra quebrada
        comp = scripted([json.dumps({"rank": [0, 99], "ser": None})])
        with self.assertRaises(ValueError):
            pauta.shortlist(self.CELL, [sug(0)], completer=comp)

    def test_degenerate_rank_raises_juiz_fora_do_protocolo(self):
        # adv r3 #2 (REPRODUZIDO lá): rank=[] com pool não-vazio passava e colapsava
        # o pool silenciosamente — todo outro desvio de protocolo levanta. O protocolo
        # é PERMUTAÇÃO plena: todos os idx, sem repetição nem omissão.
        for rank in ([], [0, 0, 1], [0, 1]):  # vazio · duplicado · parcial (3 sugs)
            comp = scripted([self._merit(rank, ser=0)])
            with self.assertRaises(ValueError, msg=f"rank degenerado passou: {rank!r}"):
                pauta.shortlist(self.CELL, [sug(i) for i in range(3)], completer=comp)

    def test_merit_prompt_demands_the_full_permutation(self):
        comp = scripted([self._merit([0], ser=0), json.dumps({"reprova": []}),
                         json.dumps({"reprova": []})])
        pauta.shortlist(self.CELL, [sug(0)], completer=comp)
        self.assertIn("TODOS os idx", comp.prompts[0])

    def test_floor_cutting_the_ser_slot_is_declared_in_the_trace(self):
        # adv r3 #3 (REPRODUZIDO lá): um piso cortava o candidato do slot ser e o A
        # final saía SEM slot e sem flag — §7bis-2 audita presença OU corte declarado,
        # nunca silêncio. O cortado mantém a tag slot:"ser" nos cortados.
        sugestoes = [sug(i) for i in range(3)]
        comp = scripted([
            self._merit([0, 1, 2], ser=2),
            json.dumps({"reprova": []}),                    # forma_fit
            json.dumps({"reprova": [{"idx": 2, "evidencia": "rastro de agente delegado"}]}),
        ])
        out = pauta.shortlist(self.CELL, sugestoes, completer=comp)
        # operador 2026-07-25: substrato é advisory — o slot ser SOBREVIVE com a
        # ressalva no trace (o corte-declarado agora só ocorre por pisos reais).
        self.assertTrue([c for c in out["A"] if c.get("slot") == "ser"])
        self.assertIn("advisory", out["trace"]["substrato"])

    def test_forma_fit_check_cuts_the_absurd_forma_with_evidence(self):
        # adv r3 #6 / §2 Forma: o critério assinado ("que desenvolvimento o candidato
        # precisa + que momento de leitura serve; a coluna formas-default poda o
        # absurdo") nasce na shortlist como poda semântica — nunca no pen (piso lá
        # segue roster-membership, declarado no docstring do propose).
        sugestoes = [sug(i) for i in range(3)]
        comp = scripted([
            self._merit([0, 1, 2], ser=2),
            json.dumps({"reprova": [{"idx": 0, "evidencia":
                        "prototype não serve o momento de leitura de um espelho de horas"}]}),
            json.dumps({"reprova": []}),                    # substrato
        ])
        out = pauta.shortlist(self.CELL, sugestoes, completer=comp)
        self.assertNotIn("tema-0", [c["tema"] for c in out["A"]])
        cortado = next(c for c in out["cortados"] if c["tema"] == "tema-0")
        self.assertIn("momento de leitura", cortado["checks"]["forma_fit"]["evidencia"])
        self.assertEqual(out["trace"]["forma_fit"], "rodado")

    def test_empty_sugestoes_returns_empty_A_never_invents(self):
        # pool vazio = a ÚNICA ausência legítima do slot ser (declarada no trace)
        def boom(prompt):
            raise AssertionError("sem sugestões não há o que julgar")
        out = pauta.shortlist(self.CELL, [], completer=boom)
        self.assertEqual(out["A"], [])
        self.assertEqual(out["aterrar"], [])


class CliDirectionDefaultsToTheSignedFile(unittest.TestCase):
    """adv r2 #11: --direction omitido lia NUNCA o filtro assinado §3.4 mesmo com
    state/direction.md no disco. Default = o arquivo do install quando existe;
    '' opta fora alto; caminho explícito vence."""

    def test_default_reads_state_direction_md_when_present(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            (base / "state").mkdir()
            (base / "state" / "direction.md").write_text("fio X aberto")
            self.assertEqual(pauta._cli_direction_text(None, base=base), "fio X aberto")

    def test_absent_default_file_is_empty_declared_by_the_trace(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(pauta._cli_direction_text(None, base=Path(tmp)), "")

    def test_explicit_empty_opts_out_even_when_the_file_exists(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            (base / "state").mkdir()
            (base / "state" / "direction.md").write_text("fio X")
            self.assertEqual(pauta._cli_direction_text("", base=base), "")

    def test_explicit_path_wins(self):
        with tempfile.TemporaryDirectory() as tmp:
            f = Path(tmp) / "outros-fios.md"
            f.write_text("fio Y")
            self.assertEqual(pauta._cli_direction_text(str(f), base=Path(tmp)), "fio Y")


if __name__ == "__main__":
    unittest.main()
