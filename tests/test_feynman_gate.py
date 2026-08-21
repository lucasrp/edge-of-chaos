"""Feynman content gate — judge ONLY the page. Content, not form.

Fixture A must FAIL (Harvey 0.2% / Stanford 17% without instruments).
Fixture B must PASS (same claim, instruments taught, derivation visible).
A page that never leaves the local idiom must FAIL (mundo).
A Glossário / Bibliografia H2 does not pass those duties.
The rite hard-fails on a FAIL page even when ACCEPTANCE: PASS.
The loop always runs two lastros; a light PASS does not skip a round.
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
sys.path.insert(0, str(REPO / "tests"))
import feynman_gate  # noqa: E402
import rito  # noqa: E402
import test_rito_runtime as tr  # noqa: E402


# Opening like the 2026-08-21 published report: names invention vs misgrounded,
# does not say whose eval / of what / n for 0.2% and 17%.
FIXTURE_A_FAIL = """\
# O endereço de prova

Vamos direto ao ponto em que a peça anterior nos deixou, porque não vale a
pena reabrir o que já ficou resolvido lá: existência do link e suporte da
passagem são coisas diferentes. Os 0,2% do Harvey são a taxa de pura
invenção — casos, decisões, precedentes que simplesmente não existem em
lugar nenhum. Os mais de 17% do Stanford medem algo mais largo: o que o
estudo chama de *misgrounded* — passagens em que o documento citado existe,
só que o texto gerado não está apoiado nele. Já está estabelecido — o
operador já sabe. Invention versus misgrounded: dois instrumentos, dois
defeitos.
"""

# Same claim, teaches the instruments, derives first. No word floor.
FIXTURE_B_PASS = """\
# O endereço de prova

Uma citação jurídica gerada por IA pode falhar de dois jeitos, e os jeitos
não comutam. Antes de buscar o placar, deriva: se o teste é "o documento
existe?", um caso inventado cai; um caso real com a frase inventada passa.
Aí o raciocínio trava — sem medir, não sei qual dos dois defeitos domina.

Harvey Citation Hallucination Benchmark (Dahl et al., 2024) avaliou n=205
citações geradas por ferramentas de IA jurídica e achou 0,2% de invenção —
autoridade que não existe em lugar nenhum. A ferramenta faz o seguinte:
gera uma citação e confere se o precedente existe em qualquer reporter.

Magesh et al. (Stanford HAI / RegLab, 2024) avaliaram n=216 citações no
mesmo tipo de tarefa e acharam >17% *misgrounded*: o documento citado
existe, mas a passagem não sustenta a proposição. Os instrumentos medem
defeitos diferentes; o segundo é o que o laudo precisa registrar.
"""

FIXTURE_LOCAL_IDIOM_FAIL = """\
# Residual depois da Pauta

A peça anterior (0818) já resolveu o #ser-mundo--harvey-casetext. O
operador já sabe. O residual é #foo-bar-baz, não o anti-X. Ticket
01KYBTM espera o S5. Exp072 ainda manda. Não reabrir. Q1 não Q4.
"""

FIXTURE_GLOSSARY_H2_DOES_NOT_PASS = FIXTURE_A_FAIL + """

## Glossário

- Harvey: Citation Hallucination Benchmark, Dahl et al. 2024, n=205 citações geradas.
- Stanford: Magesh et al. 2024, n=216, misgrounded.
"""

FIXTURE_BIBLIO_H2_DOES_NOT_PASS = FIXTURE_LOCAL_IDIOM_FAIL + """

## Bibliografia

- Magesh et al., Stanford HAI / RegLab, 2024.
- Dahl et al., Harvey Citation Hallucination Benchmark, 2024.
"""


class ContentGateFixtures(unittest.TestCase):
    def test_fixture_a_unexplained_rates_fail(self):
        v = feynman_gate.judge(FIXTURE_A_FAIL)
        self.assertEqual(v["verdict"], "FAIL", v)
        self.assertTrue(v["critical_issues"], v)
        self.assertFalse(v["dimensions"]["didatica"]["pass"], v)
        joined = " ".join(v["critical_issues"]).lower()
        self.assertTrue("whose" in joined or "n" in joined, v)

    def test_fixture_b_teaches_instruments_and_derives_pass(self):
        v = feynman_gate.judge(FIXTURE_B_PASS)
        self.assertEqual(v["verdict"], "PASS", v)
        self.assertEqual(v["critical_issues"], [])
        self.assertTrue(v["dimensions"]["didatica"]["pass"], v)
        self.assertTrue(v["dimensions"]["feynman"]["pass"], v)
        self.assertTrue(v["dimensions"]["mundo"]["pass"], v)
        self.assertLess(len(FIXTURE_B_PASS.split()), 250)

    def test_local_idiom_without_world_fails_mundo(self):
        v = feynman_gate.judge(FIXTURE_LOCAL_IDIOM_FAIL)
        self.assertEqual(v["verdict"], "FAIL", v)
        self.assertFalse(v["dimensions"]["mundo"]["pass"], v)
        self.assertTrue(any("local idiom" in c for c in v["critical_issues"]), v)

    def test_glossary_heading_does_not_pass(self):
        v = feynman_gate.judge(FIXTURE_GLOSSARY_H2_DOES_NOT_PASS)
        self.assertEqual(v["verdict"], "FAIL", v)
        self.assertFalse(v["dimensions"]["didatica"]["pass"], v)

    def test_bibliography_heading_does_not_pass(self):
        v = feynman_gate.judge(FIXTURE_BIBLIO_H2_DOES_NOT_PASS)
        self.assertEqual(v["verdict"], "FAIL", v)
        self.assertFalse(v["dimensions"]["mundo"]["pass"], v)

    def test_assume_known_does_not_waive(self):
        waived = FIXTURE_A_FAIL + "\n\nCalibração: o operador já sabe do 0818.\n"
        v = feynman_gate.judge(waived)
        self.assertEqual(v["verdict"], "FAIL", v)

    def test_critical_rule_is_the_quoted_fail_rule(self):
        self.assertIn("whose evaluation, of what, and n", feynman_gate.CRITICAL_RULE)
        self.assertIn("does not waive", feynman_gate.CRITICAL_RULE)
        self.assertIn("local idiom", feynman_gate.CRITICAL_RULE)

    def test_briefing_nonempty_on_pass_and_fail(self):
        fail_b = feynman_gate.briefing(feynman_gate.judge(FIXTURE_A_FAIL))
        pass_b = feynman_gate.briefing(feynman_gate.judge(FIXTURE_B_PASS))
        self.assertIn("FAIL", fail_b)
        self.assertTrue(len(fail_b) > 40)
        self.assertIn("PASS", pass_b)
        self.assertIn("thin spots", pass_b)

    def test_cli_exits_one_on_fail(self):
        import subprocess
        proc = subprocess.run(
            [sys.executable, str(REPO / "tools" / "feynman_gate.py")],
            input=FIXTURE_A_FAIL, text=True, capture_output=True,
        )
        self.assertEqual(proc.returncode, 1)
        self.assertIn("FEYNMAN: FAIL", proc.stdout)


class RitoHonorsTheGate(unittest.TestCase):
    def test_acceptance_pass_still_fails_unexplained_rates(self):
        canned = dict(tr.CANNED)
        canned["author_correction"] = FIXTURE_A_FAIL
        canned["feynman_rewrite_1"] = FIXTURE_A_FAIL
        canned["feynman_rewrite_2"] = FIXTURE_A_FAIL
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(rito.StageFailure) as ctx:
                tr._green_run(tmp, canned=canned)
            self.assertIn("feynman", str(ctx.exception).lower())
            blog = Path(tmp) / "blog"
            self.assertFalse((blog / f"{tr.SLUG}.html").exists())
            evs = [e for e in __import__("eventlog").read(log=Path(tmp) / "log.jsonl")
                   if e["type"] == "artefato.published"]
            self.assertEqual(evs, [])

    def test_loop_runs_two_lastros_even_when_gate_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            manifest, run_dir, log, blog = tr._green_run(tmp)
            self.assertEqual(manifest["status"], "completed")
            self.assertTrue((run_dir / "08a_FEYNMAN_GATE_1.json").is_file())
            self.assertTrue((run_dir / "08b_FEYNMAN_GROUNDING_A.md").is_file())
            self.assertTrue((run_dir / "08c_FEYNMAN_REWRITE_1.md").is_file())
            self.assertTrue((run_dir / "08d_FEYNMAN_GATE_2.json").is_file())
            self.assertTrue((run_dir / "08e_FEYNMAN_GROUNDING_B.md").is_file())
            self.assertTrue((run_dir / "08f_FEYNMAN_REWRITE_2.md").is_file())
            g1 = json.loads((run_dir / "08a_FEYNMAN_GATE_1.json").read_text())
            self.assertEqual(g1["verdict"], "PASS")
            self.assertTrue(g1.get("thin_spots"))
            self.assertTrue((blog / f"{tr.SLUG}.html").is_file())

    def test_fixture_b_survives_the_rite(self):
        canned = dict(tr.CANNED)
        canned["author_correction"] = FIXTURE_B_PASS
        canned["feynman_rewrite_1"] = FIXTURE_B_PASS
        canned["feynman_rewrite_2"] = FIXTURE_B_PASS
        with tempfile.TemporaryDirectory() as tmp:
            manifest, run_dir, log, blog = tr._green_run(tmp, canned=canned)
            self.assertEqual(manifest["status"], "completed")
            self.assertEqual(manifest["feynman_gate"]["verdict"], "PASS")
            self.assertTrue((blog / f"{tr.SLUG}.html").is_file())


if __name__ == "__main__":
    unittest.main()
