"""Gate visual-rico do ato-3 (follow-up 05, docs/agencia/implementacao/05 §"Gate visual-rico").

Salva o gate ENDURECIDO da linha parkada feat/conductor (c0eb810 type→format + quant-prose
trigger; ccfc73b banca-cega) — SÓ o critério do gate, nunca o multi-writer rejeitado — como
dimensão/critério do reviewer cego do close. SEMÂNTICO (o LLM julga; no-keyword-classifiers):
o critério viaja no PROMPT do reviewer, nunca vira regex no harness.

O critério salvo:
  * forma onde a informação PEDE forma — o mapa type→format (3+ valores → metrics-grid;
    comparação → tabela; antes/depois → diff; cadeia de raciocínio → derivation;
    fronteira aberta → gap-table; dado quantitativo → chart; relação/fluxo → diagrama);
  * a banca-cega: o visual SUBSTITUI o parágrafo, nunca decora;
  * o VETO: 3+ magnitudes numéricas distintas narradas em prosa sem bloco visual = STRIKE
    (anos/versões/datas não contam — o quant-prose trigger do conductor, agora semântico).
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

import close  # noqa: E402


class VisualizationDimensionIsHardened(unittest.TestCase):
    """A dimensão `visualization` carrega o critério type→format do conductor: forma onde a
    informação PEDE forma, com o mapa content-shape → bloco — não só o soft 'earns a chart'."""

    def test_dimension_carries_the_type_format_rule(self):
        dim = close.DIMENSIONS["visualization"]
        # o princípio: a forma responde ao que o conteúdo É
        self.assertIn("content shape", dim.lower())
        # o mapa salvo do conductor — cada shape com seu bloco
        for owed in ("metrics-grid", "comparison", "diff", "derivation",
                     "gap-table", "chart", "diagram"):
            self.assertIn(owed, dim.lower())

    def test_dimension_carries_the_banca_cega(self):
        # a banca-cega (ccfc73b): o bloco CARREGA os dados que a prosa narraria, nunca decora —
        # reconciliada com o R0 do narrative_depth (o visual ACOMPANHA a prosa que explica,
        # nunca a substitui): "carries", nunca "substitutes" (codex adversarial #1, gate=SINAL)
        dim = close.DIMENSIONS["visualization"].lower()
        self.assertIn("carries", dim)
        self.assertIn("decorat", dim)
        self.assertNotIn("substitutes the paragraph", dim)

    def test_dimension_stays_content_relative(self):
        # o guard anti-falso-fail continua: prosa genuinamente não-visual não deve nada
        dim = close.DIMENSIONS["visualization"]
        self.assertIn("never failed", dim)


class QuantProseVetoIsSemantic(unittest.TestCase):
    """O veto (3+ números viraram prosa) é instrução de STRIKE ao reviewer — o canal de veto
    que já existe (strike força revisão) — julgado pelo LLM, nunca regex no harness."""

    def test_regular_focus_instructs_the_strike(self):
        focus = close._REGULAR_FOCUS
        self.assertIn("STRIKE", focus)
        self.assertIn("3+", focus)
        # a exclusão do conductor: anos/versões/datas nunca contam como magnitude
        for excl in ("year", "version", "date"):
            self.assertIn(excl, focus.lower())

    def test_the_criterion_reaches_the_blind_reviewer_prompt(self):
        # o critério viaja no prompt — é o LLM que julga (no-keyword-classifiers)
        prompt = close._build_prompt(close._REGULAR_FOCUS,
                                     {"slug": "x", "content": {}, "cites": []})
        self.assertIn("metrics-grid", prompt)
        self.assertIn("3+", prompt)

    def test_veto_is_in_the_reviewer_channel_not_a_new_deterministic_gate(self):
        # o VETO novo é semântico — vive no focus do reviewer (strike), não em mais um
        # classificador determinístico. O floor estrutural pré-existente (_check_visual_coverage,
        # ADR-0013: o genus guarda ESTRUTURA) fica como estava — o reviewer julga adequação.
        self.assertIn("STRIKE quantitative material buried in prose", close._REGULAR_FOCUS)
        self.assertNotIn("quant", str(close.PASSABILITY_VETO_DIMS))


class RubricVersionBumped(unittest.TestCase):
    """Editar a rubrica = sha novo = versão nova no label (B.1/GLO-13). A rubrica atual
    inclui o genus rite v6: old-edge grounded trace, reader growth, lineage ledger, mecanismo,
    canonical form e grounding/fact-audit."""

    def test_version_label_is_7(self):
        self.assertEqual(close.GATE_RUBRIC_VERSION, "gate_rubric@7")


if __name__ == "__main__":
    unittest.main()
