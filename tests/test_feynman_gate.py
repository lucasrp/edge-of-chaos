"""Feynman content reviewer — judge ONLY the page. Content, not form.

The rite tooth is review() (old-edge LLM reviewer). Tests mock complete_fn
with canned JSON. Fixture A FAIL (unexplained rates). Fixture B PASS
(instruments taught). Heading-only glossary/biblio does not pass.
assume-known does not waive. Two evals + two lastros always run — a
"pass" under the old all-dims>=3 rule does not skip a round.
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


def _dim(score, feedback):
    return {"score": score, "feedback": feedback}


def _review_json(*, scores, critical, suggestions, feedback=None):
    feedback = feedback or {}
    dims = {
        name: _dim(scores.get(name, 4), feedback.get(name, f"{name} ok"))
        for name in feynman_gate.DIMENSIONS
    }
    return {
        "overall": 0,
        "dimensions": dims,
        "critical_issues": list(critical),
        "suggestions": list(suggestions),
    }


FIXTURE_A_REVIEW = _review_json(
    scores={
        "profundidade": 3,
        "historia": 2,
        "feynman": 2,
        "prosa": 3,
        "honestidade": 2,
        "consistencia": 1,
        "didatica": 1,
        "mundo": 3,
    },
    critical=[
        "0,2% lacks whose evaluation, of what, n — Harvey + invention is not the instrument",
        "17% lacks whose evaluation, of what, n — Stanford + misgrounded is not the instrument",
        "já está estabelecido carrying the rates; sibling / assume-known does not waive",
    ],
    suggestions=[
        "Fetch Dahl et al. 2024: whose eval, of what, n for the 0,2%.",
        "Fetch Magesh et al. 2024: whose eval, of what, n for the 17%.",
        "Open on the object, not the sibling scoreboard.",
    ],
    feedback={
        "didatica": "0,2% e 17% sem whose / of what / n; Glossário H2 não salvaria.",
        "consistencia": "já está estabelecido carrega a taxa; a página não carrega.",
        "historia": "abre no placar da peça anterior, não na porta.",
        "feynman": "resultado no colo, derivação invisível.",
        "honestidade": "incerteza dispensada em volta do número.",
        "mundo": "Harvey/Stanford são rótulos, não o instrumento.",
        "profundidade": "há corpo, mas o número não ensina.",
        "prosa": "prosa corre, o conteúdo não.",
    },
)

FIXTURE_B_REVIEW = _review_json(
    scores={name: 5 for name in feynman_gate.DIMENSIONS},
    critical=[],
    suggestions=[
        "Nomeie um caso de campo (Mata v. Avianca) se o lastro alcançar.",
        "Repita whose/of-what/n em cada callback da taxa.",
        "Deixe visível o passo da derivação que foi pulado.",
    ],
    feedback={
        name: "ensinado; derivação visível; instrumento no prosa."
        for name in feynman_gate.DIMENSIONS
    },
)

FIXTURE_LOCAL_REVIEW = _review_json(
    scores={"mundo": 1, "didatica": 2, "consistencia": 1, "historia": 2},
    critical=["page never leaves the local idiom — no named thing in the world in the prose"],
    suggestions=["Hang the residual on a named paper, product, or case in the prose."],
    feedback={
        "mundo": "só slug/ticket/exp; nenhum nome no mundo na prosa.",
        "didatica": "termos de carga (#foo-bar-baz, S5) sem ensino.",
        "consistencia": "operador já sabe / peça anterior.",
    },
)

FIXTURE_GLOSS_H2_REVIEW = _review_json(
    scores={"didatica": 1, "consistencia": 1, "historia": 2},
    critical=[
        "0,2% lacks whose evaluation, of what, n",
        "heading-only Glossário does not teach the rates in the prose",
    ],
    suggestions=["Teach 0,2% and 17% on first use in the prose, not under an H2."],
    feedback={"didatica": "Glossário H2 não passa; as taxas no corpo continuam sem n."},
)

FIXTURE_BIBLIO_H2_REVIEW = _review_json(
    scores={"mundo": 1, "didatica": 2},
    critical=["page never leaves the local idiom — Bibliography H2 does not count"],
    suggestions=["Put Magesh / Dahl in the prose, not only under Bibliografia."],
    feedback={"mundo": "H2 Bibliografia não passa; a prosa ficou no idioma local."},
)


def _mock(payload):
    blob = json.dumps(payload, ensure_ascii=False)

    def complete(route, prompt, max_tokens):
        assert route == "review", route
        assert feynman_gate.REVIEWER_MARKER in prompt
        return blob

    return complete


class ReviewerPromptContract(unittest.TestCase):
    def test_reviewer_prompt_is_page_only_no_tools(self):
        prompt = feynman_gate.reviewer_prompt(FIXTURE_A_FAIL)
        self.assertIn(feynman_gate.REVIEWER_MARKER, prompt)
        self.assertIn("0,2%", prompt)
        self.assertIn("no tools", prompt.lower())
        self.assertIn("Judge ONLY", prompt)
        for axis in feynman_gate.DIMENSIONS:
            self.assertIn(axis, prompt)

    def test_reviewer_prompt_forbids_heading_only_glossary(self):
        prompt = feynman_gate.reviewer_prompt(FIXTURE_GLOSSARY_H2_DOES_NOT_PASS)
        self.assertIn("Glossário", prompt)
        self.assertIn("does not pass", prompt)
        self.assertIn("Do NOT flag missing headings", prompt)

    def test_reviewer_prompt_forbids_heading_only_bibliography(self):
        prompt = feynman_gate.reviewer_prompt(FIXTURE_BIBLIO_H2_DOES_NOT_PASS)
        self.assertIn("Bibliografia", prompt)
        self.assertIn("does not pass", prompt)
        self.assertIn("local idiom", prompt)

    def test_reviewer_prompt_forbids_assume_known_waiver(self):
        prompt = feynman_gate.reviewer_prompt(FIXTURE_A_FAIL)
        self.assertIn("já está estabelecido", prompt)
        self.assertIn("assume-known", prompt)
        self.assertIn("does not waive", prompt)

    def test_critical_rule_is_the_quoted_fail_rule(self):
        self.assertIn("whose evaluation, of what, and n", feynman_gate.CRITICAL_RULE)
        self.assertIn("does not waive", feynman_gate.CRITICAL_RULE)
        self.assertIn("local idiom", feynman_gate.CRITICAL_RULE)


class ReviewParsesCannedJson(unittest.TestCase):
    def test_fixture_a_unexplained_rates_fail(self):
        v = feynman_gate.review(FIXTURE_A_FAIL, _mock(FIXTURE_A_REVIEW))
        self.assertEqual(v["verdict"], "FAIL", v)
        self.assertFalse(v["pass"], v)
        self.assertTrue(v["critical_issues"], v)
        self.assertFalse(v["dimensions"]["didatica"]["pass"], v)
        joined = " ".join(v["critical_issues"]).lower()
        self.assertTrue("whose" in joined or "n" in joined, v)
        self.assertLess(v["overall"], 3.5)

    def test_fixture_b_teaches_instruments_and_derives_pass(self):
        v = feynman_gate.review(FIXTURE_B_PASS, _mock(FIXTURE_B_REVIEW))
        self.assertEqual(v["verdict"], "PASS", v)
        self.assertTrue(v["pass"], v)
        self.assertEqual(v["critical_issues"], [])
        self.assertTrue(v["dimensions"]["didatica"]["pass"], v)
        self.assertTrue(v["dimensions"]["feynman"]["pass"], v)
        self.assertTrue(v["dimensions"]["mundo"]["pass"], v)
        self.assertGreaterEqual(v["overall"], 3.5)
        self.assertLess(len(FIXTURE_B_PASS.split()), 250)

    def test_local_idiom_without_world_fails_mundo(self):
        v = feynman_gate.review(FIXTURE_LOCAL_IDIOM_FAIL, _mock(FIXTURE_LOCAL_REVIEW))
        self.assertEqual(v["verdict"], "FAIL", v)
        self.assertFalse(v["dimensions"]["mundo"]["pass"], v)
        self.assertTrue(any("local idiom" in c for c in v["critical_issues"]), v)

    def test_glossary_heading_does_not_pass(self):
        v = feynman_gate.review(
            FIXTURE_GLOSSARY_H2_DOES_NOT_PASS, _mock(FIXTURE_GLOSS_H2_REVIEW)
        )
        self.assertEqual(v["verdict"], "FAIL", v)
        self.assertFalse(v["dimensions"]["didatica"]["pass"], v)

    def test_bibliography_heading_does_not_pass(self):
        v = feynman_gate.review(
            FIXTURE_BIBLIO_H2_DOES_NOT_PASS, _mock(FIXTURE_BIBLIO_H2_REVIEW)
        )
        self.assertEqual(v["verdict"], "FAIL", v)
        self.assertFalse(v["dimensions"]["mundo"]["pass"], v)

    def test_assume_known_does_not_waive(self):
        waived = FIXTURE_A_FAIL + "\n\nCalibração: o operador já sabe do 0818.\n"
        v = feynman_gate.review(waived, _mock(FIXTURE_A_REVIEW))
        self.assertEqual(v["verdict"], "FAIL", v)
        joined = " ".join(v["critical_issues"]).lower()
        self.assertTrue("estabelecido" in joined or "assume" in joined or "sibling" in joined, v)

    def test_pass_rule_recomputed_not_trusted_from_model(self):
        payload = _review_json(
            scores={"didatica": 2},
            critical=[],
            suggestions=["ensinar o termo"],
        )
        payload["pass"] = True
        payload["overall"] = 5.0
        v = feynman_gate.parse_review(json.dumps(payload))
        self.assertFalse(v["pass"])
        self.assertEqual(v["verdict"], "FAIL")
        self.assertEqual(v["dimensions"]["didatica"]["score"], 2)

    def test_pass_rule_needs_all_dims_critical_and_overall(self):
        almost = _review_json(
            scores={name: 3 for name in feynman_gate.DIMENSIONS},
            critical=["0,2% lacks whose evaluation, of what, n"],
            suggestions=[],
        )
        v = feynman_gate.parse_review(json.dumps(almost))
        self.assertFalse(v["pass"])
        self.assertEqual(v["verdict"], "FAIL")

    def test_briefing_uses_model_feedback_not_canned_thin_spots(self):
        v = feynman_gate.review(FIXTURE_A_FAIL, _mock(FIXTURE_A_REVIEW))
        brief = feynman_gate.briefing(v)
        self.assertIn("didatica", brief)
        self.assertIn("0,2%", brief)
        self.assertNotIn("thin spots", brief)
        self.assertNotIn("the round is not skipped because the gate passed lightly", brief)
        pass_v = feynman_gate.review(FIXTURE_B_PASS, _mock(FIXTURE_B_REVIEW))
        pass_b = feynman_gate.briefing(pass_v)
        self.assertTrue(len(pass_b) > 40)
        self.assertIn("Suggestions:", pass_b)
        self.assertIn("Mata v. Avianca", pass_b)
        self.assertNotIn("thin spots", pass_b)

    def test_cli_exits_one_on_fail(self):
        import subprocess
        proc = subprocess.run(
            [sys.executable, str(REPO / "tools" / "feynman_gate.py")],
            input=FIXTURE_A_FAIL, text=True, capture_output=True,
        )
        self.assertEqual(proc.returncode, 1)
        self.assertIn("FEYNMAN: FAIL", proc.stdout)


class RitoHonorsTheReviewer(unittest.TestCase):
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

    def test_loop_runs_two_evals_and_two_lastros_even_when_first_review_would_pass(self):
        canned = dict(tr.CANNED)
        canned["feynman_review"] = json.dumps(FIXTURE_B_REVIEW, ensure_ascii=False)
        with tempfile.TemporaryDirectory() as tmp:
            manifest, run_dir, log, blog = tr._green_run(tmp, canned=canned)
            self.assertEqual(manifest["status"], "completed")
            self.assertTrue((run_dir / "08a_FEYNMAN_GATE_1.json").is_file())
            self.assertTrue((run_dir / "08b_FEYNMAN_GROUNDING_A.md").is_file())
            self.assertTrue((run_dir / "08c_FEYNMAN_REWRITE_1.md").is_file())
            self.assertTrue((run_dir / "08d_FEYNMAN_GATE_2.json").is_file())
            self.assertTrue((run_dir / "08e_FEYNMAN_GROUNDING_B.md").is_file())
            self.assertTrue((run_dir / "08f_FEYNMAN_REWRITE_2.md").is_file())
            g1 = json.loads((run_dir / "08a_FEYNMAN_GATE_1.json").read_text())
            g2 = json.loads((run_dir / "08d_FEYNMAN_GATE_2.json").read_text())
            self.assertEqual(g1["verdict"], "PASS")
            self.assertEqual(g2["verdict"], "PASS")
            self.assertGreaterEqual(g1["overall"], 3.5)
            prompt_a = (run_dir / "prompts" / "09_feynman_grounding_a.md").read_text()
            prompt_b = (run_dir / "prompts" / "12_feynman_grounding_b.md").read_text()
            self.assertIn("feynman_briefing", prompt_a)
            self.assertIn("feynman_briefing", prompt_b)
            self.assertTrue((blog / f"{tr.SLUG}.html").is_file())

    def test_mid_loop_fail_does_not_abort_or_skip_round_two(self):
        canned = dict(tr.CANNED)
        canned["author_correction"] = FIXTURE_A_FAIL
        canned["feynman_rewrite_1"] = FIXTURE_A_FAIL
        canned["feynman_rewrite_2"] = FIXTURE_B_PASS
        canned["feynman_review"] = None  # content-aware mock: A→FAIL, B→PASS
        with tempfile.TemporaryDirectory() as tmp:
            manifest, run_dir, log, blog = tr._green_run(tmp, canned=canned)
            self.assertEqual(manifest["status"], "completed")
            g1 = json.loads((run_dir / "08a_FEYNMAN_GATE_1.json").read_text())
            g2 = json.loads((run_dir / "08d_FEYNMAN_GATE_2.json").read_text())
            self.assertEqual(g1["verdict"], "FAIL")
            self.assertTrue((run_dir / "08b_FEYNMAN_GROUNDING_A.md").is_file())
            self.assertTrue((run_dir / "08e_FEYNMAN_GROUNDING_B.md").is_file())
            self.assertTrue((run_dir / "08f_FEYNMAN_REWRITE_2.md").is_file())
            self.assertEqual(manifest["feynman_gate"]["verdict"], "PASS")
            self.assertTrue((blog / f"{tr.SLUG}.html").is_file())
            self.assertEqual(g2["verdict"], "FAIL")  # rewrite_1 still fixture A

    def test_fixture_b_survives_the_rite(self):
        canned = dict(tr.CANNED)
        canned["author_correction"] = FIXTURE_B_PASS
        canned["feynman_rewrite_1"] = FIXTURE_B_PASS
        canned["feynman_rewrite_2"] = FIXTURE_B_PASS
        canned["feynman_review"] = json.dumps(FIXTURE_B_REVIEW, ensure_ascii=False)
        with tempfile.TemporaryDirectory() as tmp:
            manifest, run_dir, log, blog = tr._green_run(tmp, canned=canned)
            self.assertEqual(manifest["status"], "completed")
            self.assertEqual(manifest["feynman_gate"]["verdict"], "PASS")
            self.assertTrue((blog / f"{tr.SLUG}.html").is_file())

    def test_reviewer_is_invoked_on_review_route(self):
        seen = []

        def wrap(route, prompt, max_tokens):
            seen.append((route, feynman_gate.REVIEWER_MARKER in prompt, max_tokens))
            return tr._complete_fn(tr.CANNED, tr.LLM_ORDER)(route, prompt, max_tokens)

        # use the stock complete via a spy around _green_run internals
        canned = dict(tr.CANNED)
        canned["feynman_review"] = json.dumps(FIXTURE_B_REVIEW, ensure_ascii=False)
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            log, blog, run_dir = tmp / "log.jsonl", tmp / "blog", tmp / "run"
            did = tr._stamp_wake(log)
            inner = tr._complete_fn(canned, tr.LLM_ORDER)

            def spy(route, prompt, max_tokens):
                seen.append(route if feynman_gate.REVIEWER_MARKER not in prompt
                            else f"reviewer:{route}")
                return inner(route, prompt, max_tokens)

            rito.run_rito(
                tr.SLUG, run_dir=run_dir,
                grounding1_fn=lambda: "# Dossier factual\n\nFatos: 29-8-3 em 40 rodadas.",
                prompts=tr._prompts(),
                complete_fn=spy,
                intent=tr.INTENT, skill="report", dispatch_id=did,
                log=log, blog_dir=blog,
            )
            reviewer_calls = [s for s in seen if s.startswith("reviewer:")]
            self.assertGreaterEqual(len(reviewer_calls), 3, seen)  # gate1, gate2, close
            self.assertTrue(all(s == "reviewer:review" for s in reviewer_calls), seen)


if __name__ == "__main__":
    unittest.main()
