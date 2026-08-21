"""Pauta — objetivo da escolha (operador 2026-08-21).

Ato-1 escolhe briefing de conhecimento útil face aos desafios ATUAIS.
Offline: presença no skill E nos prompts mecânicos (shortlist, aterrar,
propose/gate); explorer não é visor-do-pólo; fossil/chore no juiz;
propose escolhe o mais útil entre passers, não o primeiro da ordem.
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
import eventlog  # noqa: E402
import pauta  # noqa: E402
from test_pauta_gates import scripted  # noqa: E402


LOCK = "O que parece mais útil agora"
BRIEFING = "briefing de conhecimento útil"
FOSSIL = "fóssil"
CHORE = "chore de uma vez"


def _sug(i, tema=None):
    return {"tema": tema or f"tema-{i}", "forma": "report", "semente": f"do wake {i}"}


def _merit(rank, ser=None):
    return json.dumps({"rank": rank, "ser": ser})


class ObjectiveLivesInSkillAndModule(unittest.TestCase):
    def test_objetivo_constant_states_useful_knowledge_no_week_window(self):
        self.assertIn(LOCK, pauta.OBJETIVO)
        self.assertIn(BRIEFING, pauta.OBJETIVO)
        self.assertIn("desafios ATUAIS", pauta.OBJETIVO)
        self.assertIn("Sem janela", pauta.OBJETIVO)
        self.assertIn(FOSSIL, pauta.OBJETIVO_REPROVA)
        self.assertIn(CHORE, pauta.OBJETIVO_REPROVA)
        self.assertIn("WABA", pauta.OBJETIVO_REPROVA)
        self.assertIn("emprego de outro install", pauta.OBJETIVO_REPROVA)

    def test_skill_states_the_objective_and_kills_the_gradient(self):
        skill = (REPO / "skills" / "beat" / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn(LOCK, skill)
        self.assertIn(BRIEFING, skill)
        self.assertIn("desafios ATUAIS", skill)
        self.assertNotIn("the gradient the proposta follows", skill)
        self.assertNotIn("mirado no pólo", skill)
        self.assertIn("explorer no", skill)
        self.assertIn("panorama", skill)
        self.assertIn("não o visor", skill)
        # panoramic look FIRST stays
        self.assertIn("Olhar holístico PRIMEIRO", skill)
        self.assertIn("direção na escolha do assunto; contextualização ampla", skill)

    def test_tabela_and_adr_carry_the_dated_amendment(self):
        tabela = (REPO / "docs" / "agencia" / "pauta-tabela-normativa.md").read_text(
            encoding="utf-8")
        adr = (REPO / "docs" / "adr" / "0024-pauta-a-escolha-e-etapa-do-dispatch.md"
               ).read_text(encoding="utf-8")
        self.assertIn("O QUE PARECE MAIS ÚTIL AGORA", tabela)
        self.assertIn(BRIEFING, tabela)
        self.assertIn("Chore de uma vez só REPROVA", tabela)
        self.assertNotIn("mirados no pólo", tabela)
        self.assertIn(LOCK, adr)
        self.assertIn("2026-08-21", adr)


class MechanicalPromptsCarryTheObjective(unittest.TestCase):
    CELL = {"objeto": "mundo", "abordagem": "fog", "locked": []}

    def test_shortlist_merit_ranks_useful_knowledge_on_live_challenges(self):
        comp = scripted([_merit([0], ser=0),
                         json.dumps({"reprova": []}),
                         json.dumps({"reprova": []})])
        pauta.shortlist(self.CELL, [_sug(0)], completer=comp)
        merit = comp.prompts[0]
        self.assertIn(LOCK, merit)
        self.assertIn(BRIEFING, merit)
        self.assertIn("desafios", merit)
        self.assertIn(FOSSIL, merit)
        self.assertIn("chore", merit)
        self.assertIn("NÃO ranqueie por encaixe", merit)
        self.assertIn("TODOS os idx", merit)  # permutation protocol stays

    def test_aterrar_explorer_is_panoramic_not_visor_only(self):
        comp = scripted([_merit([0], ser=0),
                         json.dumps({"reprova": []}),
                         json.dumps({"reprova": []})])
        out = pauta.shortlist(self.CELL, [_sug(0)], completer=comp)
        self.assertEqual(len(out["aterrar"]), 1)
        hook = out["aterrar"][0]["explorer"]
        self.assertNotIn("mirado no pólo", hook)
        self.assertIn("panorama", hook)
        self.assertIn("não o visor", hook)
        self.assertIn("mundo", hook)
        self.assertIn("mentorado", hook)
        self.assertIn("nome de fora", hook)
        self.assertIn(LOCK, hook)

    def test_run_gate_prompt_carries_objective_and_fossil_chore(self):
        cell = {"objeto": "mentorado", "abordagem": "curiosidade"}
        cand = {"tema": "T", "forma": "report", "lastro": "lido: X",
                "nome_de_fora": "Little", "ponte": "fila HITL"}
        comp = scripted([
            json.dumps({"veredito": "passa", "evidencia": "a"}),
            json.dumps({"veredito": "passa", "evidencia": "b"}),
        ])
        pauta.run_gate(cell, cand, completer=comp)
        joined = "\n".join(comp.prompts)
        self.assertIn(LOCK, joined)
        self.assertIn(FOSSIL, joined)
        self.assertIn(CHORE, joined)
        self.assertIn("não reprove por falta de passo executável", joined)
        self.assertIn("nome_de_fora", joined)  # judge sees faro fields
        self.assertIn("Little", joined)

    def test_propose_prompt_carries_objective_via_gate(self):
        cand = {"tema": "surrogação", "forma": "report",
                "lastro": "lido: assemble-brief QR 3/4",
                "nome_de_fora": "Harris & Tayler"}
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            comp = scripted([
                json.dumps({"reprova": []}),
                json.dumps({"veredito": "passa", "evidencia": "a"}),
                json.dumps({"veredito": "passa", "evidencia": "b"}),
            ])
            ev = pauta.propose({"objeto": "mentorado", "abordagem": "fog", "locked": []},
                               [cand], dispatch_id="d1", completer=comp, log=log)
            self.assertEqual(ev["type"], "pauta.proposta")
            self.assertIn(LOCK, ev["payload"]["gate_trace"]["objetivo"])
            self.assertIn("panorâmico", ev["payload"]["gate_trace"]["ato2"])
            gate_prompts = [p for p in comp.prompts if "gate da Pauta" in p]
            self.assertTrue(gate_prompts)
            self.assertIn(LOCK, gate_prompts[0])
            self.assertIn(FOSSIL, gate_prompts[0])


class GatesNoLongerDemandNextStepPage(unittest.TestCase):
    def test_kept_floors_and_chore_reprova_stay(self):
        # operacional (a) still kills one-shot chore; forma_fit / lastro / âncoras
        # are other files — here we lock the kept REPROVA in the gate data.
        a = pauta.GATES["operacional"][0]["exigencia"]
        self.assertIn("chore de uma vez", a.lower())
        self.assertIn("reprova", a.lower())

    def test_fog_b_does_not_demand_executable_step(self):
        b = pauta.GATES["fog"][1]["exigencia"]
        self.assertNotIn("primeiro passo executável", b)
        self.assertIn("briefing", b)

    def test_operacional_c_allows_diagnosis_as_deliverable(self):
        c = pauta.GATES["operacional"][2]["exigencia"]
        self.assertIn("PODE ser o entregável", c)
        self.assertNotIn("nunca entregável", c)

    def test_estrategico_c_does_not_require_abrir_obra(self):
        c = pauta.GATES["estrategico"][2]["exigencia"]
        self.assertNotIn("abre obra", c)
        self.assertIn("NÃO exige abrir obra", c)

    def test_meta_dica_c_has_no_week_window(self):
        c = pauta.GATES["meta_dica"][2]["exigencia"]
        self.assertIn("SEM janela", c)
        self.assertNotIn("testável na próxima semana", c)

    def test_tempo_gasto_c_does_not_require_reallocation_ticket(self):
        c = pauta.GATES["tempo_gasto"][2]["exigencia"]
        self.assertIn("NÃO exige realocação-ticket", c)


class ProposePicksMostUsefulAmongPassers(unittest.TestCase):
    def test_single_passer_needs_no_extra_judge(self):
        # existing one-candidate road: no propose/escolha call
        cand = {"tema": "T", "forma": "report",
                "lastro": "lido: X"}
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            comp = scripted([
                json.dumps({"reprova": []}),
                json.dumps({"veredito": "passa", "evidencia": "a"}),
                json.dumps({"veredito": "passa", "evidencia": "b"}),
            ])
            ev = pauta.propose({"objeto": "mentorado", "abordagem": "fog", "locked": []},
                               [cand], dispatch_id="d1", completer=comp, log=log)
            self.assertEqual(ev["type"], "pauta.proposta")
            self.assertNotIn("escolha", ev["payload"]["gate_trace"])
            self.assertFalse(any("NÃO escolha o primeiro por ordem" in p for p in comp.prompts))

    def test_two_passers_usefulness_beats_first_in_order(self):
        chore = {"tema": "assign WABA", "forma": "report",
                 "lastro": "lido: console PENDING_REVIEW"}
        faro = {"tema": "surrogação Harris", "forma": "report",
                "lastro": "lido: QR 3/4 + estoque L1",
                "nome_de_fora": "Harris & Tayler",
                "ponte": "QR-como-pronto",
                "desafio_vivo": "shadow tratado como N/4"}
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            # per cand: substrato + fog a + fog b; then escolha picks idx=1
            passa = json.dumps({"veredito": "passa", "evidencia": "ok"})
            substrato = json.dumps({"reprova": []})
            comp = scripted([
                substrato, passa, passa,   # chore — also passes AND
                substrato, passa, passa,   # faro
                json.dumps({"idx": 1, "evidencia": "nome de fora + desafio vivo"}),
            ])
            ev = pauta.propose({"objeto": "mentorado", "abordagem": "fog", "locked": []},
                               [chore, faro], dispatch_id="d1", completer=comp, log=log)
            self.assertEqual(ev["type"], "pauta.proposta")
            self.assertEqual(ev["payload"]["tema"], faro["tema"])
            self.assertEqual(ev["payload"]["gate_trace"]["escolha"]["idx"], 1)
            escolha_prompt = [p for p in comp.prompts if "NÃO escolha o primeiro por ordem" in p]
            self.assertEqual(len(escolha_prompt), 1)
            self.assertIn(LOCK, escolha_prompt[0])
            self.assertIn(FOSSIL, escolha_prompt[0])
            self.assertIn(CHORE, escolha_prompt[0])


class DeltaVozSeesTheCandidateNotOnlyTema(unittest.TestCase):
    def test_prompt_includes_nome_de_fora_when_present(self):
        cand = {"tema": "omit%", "lastro": "lido: laudo",
                "nome_de_fora": "ExtractBench", "ponte": "cite-or-drop"}
        comp = scripted([json.dumps(
            {"outcome": "delta", "cita": "já falou omit%", "dominio": False})])
        out = pauta.delta_voz_check(
            "omit%", voz_recall_fn=lambda t: "já falou omit%",
            completer=comp, cand=cand)
        self.assertEqual(out["outcome"], "delta")
        self.assertIn("ExtractBench", comp.prompts[0])
        self.assertIn("candidato INTEIRO", comp.prompts[0])


if __name__ == "__main__":
    unittest.main()
