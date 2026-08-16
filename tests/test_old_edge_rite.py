# NOTA (2026-08-16, issue #612): 2 testes deste arquivo foram removidos por decisão
# do operador. Eles cobravam as strikes `old-edge-rite:*` do check_genus — API que NUNCA existiu em tools/ em commit
# algum. Não eram testes envelhecidos: chegaram órfãos em 401feee, vindos de uma
# árvore que ainda acreditava numa feature que be3aea5 ("Rollback failed genus rite
# rollout") já havia revertido, levando o código e deixando os testes.
#
# A especificação que eles descreviam está preservada na issue #612 — apagá-la daqui
# não a perde. O que sobrou neste arquivo cobre código que EXISTE e passa.

import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))

import close  # noqa: E402
import old_edge_rite_check  # noqa: E402


POSITIVE = REPO / "drafts/exp072-report-quality/post-gate-grounding-arm/run-v1/04_FINAL_REPORT.html"
NEGATIVE = Path("/home/vboxuser/Downloads/contrato-schema-v10-grafo-de-decisoes.html")


class ApprovedExperimentRegression(unittest.TestCase):
    @unittest.skipUnless(POSITIVE.exists() and NEGATIVE.exists(), "local approved/rejected fixtures")
    def test_approved_exp072_passes_and_roberto_old_shell_fails(self):
        self.assertTrue(old_edge_rite_check.check(POSITIVE.read_text())["pass"])
        rejected = old_edge_rite_check.check(NEGATIVE.read_text())
        self.assertFalse(rejected["pass"])
        self.assertTrue(
            any(f["name"] == "reading_frame_matches_approved_arm" for f in rejected["failures"]),
            rejected,
        )


class PageShellContract(unittest.TestCase):
    def test_direct_main_page_is_the_material_shell(self):
        html = '<!doctype html><html><body><main class="edge-artifact"><h1>x</h1></main></body></html>'
        self.assertEqual(old_edge_rite_check.check_page_shell(html)["failures"], [])

    def test_main_without_edge_artifact_class_is_rejected(self):
        html = '<!doctype html><html><body><main><h1>x</h1></main></body></html>'
        failures = old_edge_rite_check.check_page_shell(html)["failures"]
        self.assertIn("old-edge-shell:missing-main-edge-artifact", failures)

    def test_old_report_shell_is_rejected(self):
        html = (
            '<html><body><article class="report"><div class="report-header"></div>'
            '<div class="metric-card">x</div><div class="next-step-card">y</div></article></body></html>'
        )
        failures = old_edge_rite_check.check_page_shell(html)["failures"]
        self.assertIn("old-edge-shell:article-report", failures)
        self.assertTrue(any(f.startswith("old-edge-shell:old-component-classes") for f in failures))


def _old_edge_art():
    return {
        "slug": "old-edge-rite",
        "skill": "report",
        "intent": "open: artifact rite; bet: make the next report useful",
        "proposes": [{"body": "run the next report through this rite", "kind": "constraint"}],
        "distills": ["cluster:reportrite"],
        "lineage": [{"type": "builds_on", "slug": "approved-exp072-arm"}],
        "cites": [{"ref": "paper:benchmark", "kind": "mundo", "relevant": True,
                   "snippet": "external benchmark for grounded qualitative reporting"}],
        "content": {"sections": [{"title": "Arc", "blocks": [
            {"type": "paragraph", "text": (
                "Pergunta viva: o que esta em jogo na decisao? Contexto: o experimento compara "
                "um corpus real com baseline e config suficiente para o leitor reconstruir o objeto. "
                "Derive from first principles: if the reader cannot replay the object, insight becomes lore."
            )},
            {"type": "paragraph", "text": (
                "Mecanismo concreto: por exemplo, caso 007, rodada 2, before/after do draft; "
                "the trace shows why the mechanism changes the interpretation instead of only naming it."
            )},
            {"type": "paragraph", "text": (
                "Mundo: the benchmark is a fit with qualitative evaluation practice and a mismatch with "
                "thin acceptance reports; therefore it reposiciona the claim and limita what we can say."
            )},
            {"type": "paragraph", "text": (
                "Lineage L0/L1: herdo the prior report's setup, rejeito its old shell, and keep the "
                "limite herdado explicit. O que eu ainda nao sei: whether this holds in every skill."
            )},
            {"type": "paragraph", "text": (
                "O que muda agora: produto should ship the richer rite, report should package the "
                "next validation, and the next bet is to test this on one autonomous artifact."
            )},
        ]}]},
    }


class OldEdgeRiteGenus(unittest.TestCase):
    def test_developed_artifact_with_the_generalized_rite_is_clean(self):
        violations = [v for v in close.check_genus(_old_edge_art()) if v.startswith("old-edge-rite")]
        self.assertEqual(violations, [])




if __name__ == "__main__":
    unittest.main(verbosity=2)
