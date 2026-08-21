"""Feynman content reviewer — judge ONLY the page. Content, not form.

The rite tooth is review() (old-edge LLM reviewer). Tests mock complete_fn
with canned JSON. Fixture A is thin (unexplained rates + written holes).
Fixture B teaches instruments and still names a concrete improvement per
axis (no 5s). Heading-only glossary/biblio does not satisfy the duty.
assume-known does not waive. Two evals + two lastros always run. Scores
contextualize the next lastro; they are not a pass/fail ticket. Close
must not StageFailure on a low score.
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
    scores={name: 4 for name in feynman_gate.DIMENSIONS},
    critical=[],
    suggestions=[
        "Nomeie um caso de campo (Mata v. Avianca) se o lastro alcançar.",
        "Repita whose/of-what/n em cada callback da taxa.",
        "Deixe visível o passo da derivação que foi pulado.",
    ],
    feedback={
        "profundidade": "n=205 já está; ainda falta um caso concreto (Mata v. Avianca) no parágrafo do Harvey.",
        "historia": "o arco abre no objeto; o fim ainda pode voltar à porta ('os jeitos não comutam').",
        "feynman": "a derivação está visível; nomeie o passo que pulou entre 'se o documento existe' e o placar.",
        "prosa": "prosa corre; a transição entre os dois instrumentos ainda pode ser uma frase, não um corte.",
        "honestidade": "o 'aí o raciocínio trava' é buraco real; deixe explícito o que o n=216 ainda não decide.",
        "consistencia": "a página carrega; não cite a peça anterior nem de relance no callback da taxa.",
        "didatica": "instrumentos ensinados; repita whose/of-what/n quando 0,2% voltar.",
        "mundo": "Dahl/Magesh estão na prosa; pendure também o produto (CoCounsel / Harvey) pelo que faz.",
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

    def test_reviewer_scale_is_zero_to_four_never_five(self):
        prompt = feynman_gate.reviewer_prompt(FIXTURE_A_FAIL)
        self.assertIn("0-4", prompt)
        self.assertIn("There is no 5", prompt)
        self.assertNotIn("Excellent — no issues found", prompt)
        self.assertIn('Never write "no issues found"', prompt)
        self.assertIn("NO minimum score to pass", prompt)
        self.assertEqual(feynman_gate.SCORE_MAX, 4)


class ReviewParsesCannedJson(unittest.TestCase):
    def test_fixture_a_unexplained_rates_are_low_with_written_holes(self):
        v = feynman_gate.review(FIXTURE_A_FAIL, _mock(FIXTURE_A_REVIEW))
        self.assertTrue(v["critical_issues"], v)
        self.assertLess(v["dimensions"]["didatica"]["score"], 3, v)
        self.assertLess(v["overall"], 3.0)
        joined = " ".join(v["critical_issues"]).lower()
        self.assertTrue("whose" in joined or "n" in joined, v)
        brief = feynman_gate.briefing(v)
        self.assertIn("0,2%", brief)
        self.assertIn("didatica", brief)
        self.assertNotEqual(v.get("verdict"), "PASS")
        self.assertNotEqual(v.get("verdict"), "FAIL")
        self.assertNotIn("pass", v)

    def test_fixture_b_teaches_instruments_and_still_names_improvements(self):
        v = feynman_gate.review(FIXTURE_B_PASS, _mock(FIXTURE_B_REVIEW))
        self.assertEqual(v["critical_issues"], [])
        self.assertGreaterEqual(v["dimensions"]["didatica"]["score"], 3)
        self.assertGreaterEqual(v["dimensions"]["feynman"]["score"], 3)
        self.assertGreaterEqual(v["dimensions"]["mundo"]["score"], 3)
        for name in feynman_gate.DIMENSIONS:
            score = v["dimensions"][name]["score"]
            fb = v["dimensions"][name]["feedback"]
            self.assertLessEqual(score, 4, name)
            self.assertNotEqual(score, 5, name)
            self.assertTrue(fb.strip(), name)
            self.assertNotIn("no issues", fb.lower())
            self.assertNotIn("sem issues", fb.lower())
        brief = feynman_gate.briefing(v)
        for name in feynman_gate.DIMENSIONS:
            self.assertIn(name, brief)
        self.assertIn("Mata v. Avianca", brief)
        self.assertIn("Suggestions:", brief)
        self.assertLess(len(FIXTURE_B_PASS.split()), 250)
        self.assertNotEqual(v.get("verdict"), "PASS")
        self.assertNotEqual(v.get("verdict"), "FAIL")
        self.assertNotIn("pass", v)

    def test_local_idiom_without_world_is_a_mundo_hole(self):
        v = feynman_gate.review(FIXTURE_LOCAL_IDIOM_FAIL, _mock(FIXTURE_LOCAL_REVIEW))
        self.assertLess(v["dimensions"]["mundo"]["score"], 3, v)
        self.assertTrue(any("local idiom" in c for c in v["critical_issues"]), v)
        self.assertTrue(v["dimensions"]["mundo"]["feedback"].strip())

    def test_glossary_heading_does_not_satisfy_didatica(self):
        v = feynman_gate.review(
            FIXTURE_GLOSSARY_H2_DOES_NOT_PASS, _mock(FIXTURE_GLOSS_H2_REVIEW)
        )
        self.assertLess(v["dimensions"]["didatica"]["score"], 3, v)
        self.assertTrue(v["critical_issues"], v)

    def test_bibliography_heading_does_not_satisfy_mundo(self):
        v = feynman_gate.review(
            FIXTURE_BIBLIO_H2_DOES_NOT_PASS, _mock(FIXTURE_BIBLIO_H2_REVIEW)
        )
        self.assertLess(v["dimensions"]["mundo"]["score"], 3, v)
        self.assertTrue(any("local idiom" in c for c in v["critical_issues"]), v)

    def test_assume_known_does_not_waive(self):
        waived = FIXTURE_A_FAIL + "\n\nCalibração: o operador já sabe do 0818.\n"
        v = feynman_gate.review(waived, _mock(FIXTURE_A_REVIEW))
        joined = " ".join(v["critical_issues"]).lower()
        self.assertTrue("estabelecido" in joined or "assume" in joined or "sibling" in joined, v)
        self.assertLess(v["overall"], 3.0)

    def test_scores_recomputed_and_clamped_not_trusted_from_model(self):
        payload = _review_json(
            scores={"didatica": 5},
            critical=[],
            suggestions=["ensinar o termo", "nome no mundo", "derivar o número"],
        )
        payload["pass"] = True
        payload["overall"] = 5.0
        payload["verdict"] = "PASS"
        v = feynman_gate.parse_review(json.dumps(payload))
        self.assertEqual(v["dimensions"]["didatica"]["score"], 4)
        self.assertLessEqual(v["overall"], 4.0)
        self.assertEqual(v["verdict"], "NOTES")
        self.assertNotIn("pass", v)
        for name in feynman_gate.DIMENSIONS:
            self.assertLessEqual(v["dimensions"][name]["score"], 4)

    def test_critical_issues_are_briefing_flags_not_a_ticket(self):
        almost = _review_json(
            scores={name: 4 for name in feynman_gate.DIMENSIONS},
            critical=["0,2% lacks whose evaluation, of what, n"],
            suggestions=["fetch n", "teach the rate", "name the instrument"],
        )
        v = feynman_gate.parse_review(json.dumps(almost))
        self.assertEqual(
            v["critical_issues"],
            ["0,2% lacks whose evaluation, of what, n"],
        )
        self.assertEqual(v["verdict"], "NOTES")
        self.assertNotIn("pass", v)

    def test_empty_feedback_becomes_axis_duty_hole(self):
        payload = _review_json(
            scores={name: 4 for name in feynman_gate.DIMENSIONS},
            critical=[],
            suggestions=[],
            feedback={name: "" for name in feynman_gate.DIMENSIONS},
        )
        payload["dimensions"]["didatica"]["feedback"] = "no issues found"
        v = feynman_gate.parse_review(json.dumps(payload))
        for name in feynman_gate.DIMENSIONS:
            fb = v["dimensions"][name]["feedback"]
            self.assertTrue(fb.strip(), name)
            self.assertNotIn("no issues", fb.lower())
            self.assertIn("eixo", fb)
        brief = feynman_gate.briefing(v)
        for name in feynman_gate.DIMENSIONS:
            self.assertIn(name, brief)
        self.assertNotIn("no issues", brief.lower())
        self.assertTrue(v["suggestions"])

    def test_briefing_uses_model_feedback_not_canned_thin_spots(self):
        v = feynman_gate.review(FIXTURE_A_FAIL, _mock(FIXTURE_A_REVIEW))
        brief = feynman_gate.briefing(v)
        self.assertIn("didatica", brief)
        self.assertIn("0,2%", brief)
        self.assertNotIn("thin spots", brief)
        self.assertNotIn("the round is not skipped because the gate passed lightly", brief)
        for name in feynman_gate.DIMENSIONS:
            self.assertIn(f"{name} (", brief)
        strong = feynman_gate.review(FIXTURE_B_PASS, _mock(FIXTURE_B_REVIEW))
        strong_b = feynman_gate.briefing(strong)
        self.assertTrue(len(strong_b) > 40)
        self.assertIn("Suggestions:", strong_b)
        self.assertIn("Mata v. Avianca", strong_b)
        self.assertNotIn("thin spots", strong_b)
        self.assertNotIn("/5)", strong_b)

    def test_cli_does_not_exit_one_on_low_score(self):
        import subprocess
        proc = subprocess.run(
            [sys.executable, str(REPO / "tools" / "feynman_gate.py")],
            input=FIXTURE_A_FAIL, text=True, capture_output=True,
        )
        self.assertEqual(proc.returncode, 0)
        self.assertNotIn("FEYNMAN: FAIL", proc.stdout)
        self.assertNotIn("FEYNMAN: PASS", proc.stdout)
        self.assertIn("not a ticket", proc.stdout)


class RitoHonorsTheReviewer(unittest.TestCase):
    def test_unexplained_rates_are_briefing_not_a_publish_block(self):
        canned = dict(tr.CANNED)
        canned["author_correction"] = FIXTURE_A_FAIL
        canned["feynman_rewrite_1"] = FIXTURE_A_FAIL
        canned["feynman_rewrite_2"] = FIXTURE_A_FAIL
        with tempfile.TemporaryDirectory() as tmp:
            manifest, run_dir, log, blog = tr._green_run(tmp, canned=canned)
            self.assertEqual(manifest["status"], "completed")
            self.assertTrue((blog / f"{tr.SLUG}.html").exists())
            notes = manifest["feynman_gate"]
            self.assertTrue(notes["critical_issues"], notes)
            self.assertLess(notes["overall"], 3.0)
            self.assertNotEqual(notes.get("verdict"), "FAIL")
            self.assertNotEqual(notes.get("verdict"), "PASS")
            g1 = json.loads((run_dir / "08a_FEYNMAN_GATE_1.json").read_text())
            joined = " ".join(g1["critical_issues"])
            self.assertIn("0,2%", joined)
            evs = [e for e in __import__("eventlog").read(log=Path(tmp) / "log.jsonl")
                   if e["type"] == "artefato.published"]
            self.assertEqual(len(evs), 1)

    def test_loop_runs_two_evals_and_two_lastros_even_when_first_review_is_strong(self):
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
            for gate in (g1, g2):
                self.assertEqual(gate["verdict"], "NOTES")
                self.assertNotIn("pass", gate)
                for name in feynman_gate.DIMENSIONS:
                    self.assertLessEqual(gate["dimensions"][name]["score"], 4)
                    self.assertTrue(gate["dimensions"][name]["feedback"].strip())
            prompt_a = (run_dir / "prompts" / "09_feynman_grounding_a.md").read_text()
            prompt_b = (run_dir / "prompts" / "12_feynman_grounding_b.md").read_text()
            self.assertIn("feynman_briefing", prompt_a)
            self.assertIn("feynman_briefing", prompt_b)
            self.assertTrue((blog / f"{tr.SLUG}.html").is_file())

    def test_mid_loop_low_score_does_not_abort_or_skip_round_two(self):
        canned = dict(tr.CANNED)
        canned["author_correction"] = FIXTURE_A_FAIL
        canned["feynman_rewrite_1"] = FIXTURE_A_FAIL
        canned["feynman_rewrite_2"] = FIXTURE_B_PASS
        canned["feynman_review"] = None  # content-aware mock: A thin, B taught
        with tempfile.TemporaryDirectory() as tmp:
            manifest, run_dir, log, blog = tr._green_run(tmp, canned=canned)
            self.assertEqual(manifest["status"], "completed")
            g1 = json.loads((run_dir / "08a_FEYNMAN_GATE_1.json").read_text())
            g2 = json.loads((run_dir / "08d_FEYNMAN_GATE_2.json").read_text())
            self.assertLess(g1["overall"], 3.0)
            self.assertTrue(g1["critical_issues"])
            self.assertTrue((run_dir / "08b_FEYNMAN_GROUNDING_A.md").is_file())
            self.assertTrue((run_dir / "08e_FEYNMAN_GROUNDING_B.md").is_file())
            self.assertTrue((run_dir / "08f_FEYNMAN_REWRITE_2.md").is_file())
            close = manifest["feynman_gate"]
            self.assertGreaterEqual(close["overall"], 3.0)
            self.assertNotEqual(close.get("verdict"), "FAIL")
            self.assertNotEqual(close.get("verdict"), "PASS")
            self.assertTrue((blog / f"{tr.SLUG}.html").is_file())
            self.assertLess(g2["overall"], 3.0)  # rewrite_1 still fixture A

    def test_fixture_b_survives_the_rite(self):
        canned = dict(tr.CANNED)
        canned["author_correction"] = FIXTURE_B_PASS
        canned["feynman_rewrite_1"] = FIXTURE_B_PASS
        canned["feynman_rewrite_2"] = FIXTURE_B_PASS
        canned["feynman_review"] = json.dumps(FIXTURE_B_REVIEW, ensure_ascii=False)
        with tempfile.TemporaryDirectory() as tmp:
            manifest, run_dir, log, blog = tr._green_run(tmp, canned=canned)
            self.assertEqual(manifest["status"], "completed")
            close = manifest["feynman_gate"]
            self.assertEqual(close["verdict"], "NOTES")
            for name in feynman_gate.DIMENSIONS:
                self.assertLessEqual(close["dimensions"][name]["score"], 4)
                self.assertNotEqual(close["dimensions"][name]["score"], 5)
                self.assertTrue(close["dimensions"][name]["feedback"].strip())
                self.assertNotIn("no issues", close["dimensions"][name]["feedback"].lower())
            self.assertTrue((blog / f"{tr.SLUG}.html").is_file())

    def test_reviewer_is_invoked_on_review_route(self):
        seen = []

        def wrap(route, prompt, max_tokens):
            seen.append((route, feynman_gate.REVIEWER_MARKER in prompt, max_tokens))
            return tr._complete_fn(tr.CANNED, tr.LLM_ORDER)(route, prompt, max_tokens)

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
            reviewer_calls = [s for s in seen if isinstance(s, str) and s.startswith("reviewer:")]
            self.assertGreaterEqual(len(reviewer_calls), 3, seen)  # gate1, gate2, close
            self.assertTrue(all(s == "reviewer:review" for s in reviewer_calls), seen)


if __name__ == "__main__":
    unittest.main()
