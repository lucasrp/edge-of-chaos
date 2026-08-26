"""Produce reader contract — leitura isolada is THE fail of Ato-2.

The Tetris pipe (#655) stays: generate_report + yaml_to_html + grok CLI
review-gate, two rounds, RR produce skills. The March *reader* contract
that #655 did not restore is here: isolated reading, no required H2
skeleton, object before name, this page carries.
"""
from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def _load_review_gate():
    path = REPO / "tools" / "review-gate.py"
    spec = importlib.util.spec_from_file_location("review_gate", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


FORBIDDEN_REQUIRED_H2 = (
    "required sections present: linhagem",
    "seção obrigatória ausente (linhagem",
    "seções obrigatórias: linhagem",
    "glossario (last)",
    "glossário (last)",
    "glossary (last)",
    "'o que nao sei' (penultimate)",
    '"o que nao sei" (penultimate)',
    "linhagem (first section)",
    "linhagem (primeira)",
)


class ReviewGateNamesLeituraIsolada(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rg = _load_review_gate()
        cls.src = (REPO / "tools" / "review-gate.py").read_text(encoding="utf-8")
        cls.low = cls.src.lower()
        cls.prompt = cls.rg._build_review_prompt("title: x\n", "<html></html>").lower()
        cls.refine = cls.rg._build_refine_prompt("title: x\n", {"pass": False, "overall": 2}).lower()

    def test_nine_dims_and_threshold_kept(self):
        self.assertEqual(len(self.rg.DIM_ORDER), 9)
        self.assertAlmostEqual(sum(self.rg.DIMENSION_WEIGHTS.values()), 1.0, places=9)
        self.assertEqual(self.rg.THRESHOLD, 3.5)
        self.assertIn("structural_completeness", self.rg.DIMENSIONS)
        self.assertIn("didactic_clarity", self.rg.DIMENSIONS)

    def test_gate_still_grok_cli_two_rounds(self):
        self.assertIn("grok CLI", self.src)
        self.assertIn("--rounds", self.src)
        self.assertIn("generate_report.py", self.src)
        self.assertIn("NOT OpenAI/xAI API", self.src)

    def test_required_h2_skeleton_is_gone(self):
        for phrase in FORBIDDEN_REQUIRED_H2:
            self.assertNotIn(phrase, self.low, f"gate still requires {phrase!r}")
            self.assertNotIn(phrase, self.prompt, f"review prompt still requires {phrase!r}")
            self.assertNotIn(phrase, self.refine, f"refine prompt still requires {phrase!r}")

    def test_leitura_isolada_is_the_binding_fail(self):
        for blob in (self.low, self.prompt):
            self.assertIn("leitura isolada", blob)
            self.assertIn("isolated reading", blob)
            self.assertIn("colega do operador", blob)
        dim = self.rg.DIMENSIONS["didactic_clarity"].lower()
        self.assertIn("leitura isolada", dim)
        self.assertIn("colleague of the operator", dim)
        self.assertIn("missed this session", dim)

    def test_canonical_encrypted_opener_is_named_as_fail(self):
        joined = self.low + "\n" + self.prompt
        self.assertIn("galison", joined)
        self.assertIn("occupy-hedge", joined)
        self.assertIn("25/08", joined)
        self.assertIn("objeto", self.prompt)

    def test_sequel_and_linhagem_first_are_fails(self):
        struct = self.rg.DIMENSIONS["structural_completeness"].lower()
        consist = self.rg.DIMENSIONS["internal_consistency"].lower()
        feyn = self.rg.DIMENSIONS["feynman_method"].lower()
        self.assertIn("linhagem-first is a fail", struct)
        self.assertIn("sequel", consist)
        self.assertIn("this page carries", consist)
        self.assertIn("before any outside name", feyn)
        self.assertIn("linhagem-first", self.prompt)
        self.assertIn("sequel", self.prompt)

    def test_missing_costume_h2_is_not_a_defect(self):
        self.assertIn("não são obrigatórios", self.prompt)
        self.assertIn("não restaure h2 obrigatório", self.prompt)
        self.assertIn("seções livres", self.refine)
        self.assertIn("não invente nem exija h2", self.refine)

    def test_teach_on_first_use_in_the_prose(self):
        did = self.rg.DIMENSIONS["didactic_clarity"].lower()
        self.assertIn("first use", did)
        self.assertIn("in the prose", did)
        self.assertIn("heading named glossário does not pass", did)

    def test_honesty_does_not_require_o_que_nao_sei_h2(self):
        hon = self.rg.DIMENSIONS["intellectual_honesty"].lower()
        self.assertIn("not a required h2", hon)
        self.assertIn("missing that heading does not fail", hon)


class ProduceSkillsNameLeituraIsolada(unittest.TestCase):
    def _text(self, *parts):
        return (REPO.joinpath(*parts)).read_text(encoding="utf-8")

    def test_beat_ato2_drops_required_h2_skeleton(self):
        text = self._text("skills", "beat", "SKILL.md")
        low = text.lower()
        self.assertIn("leitura isolada", low)
        self.assertIn("isolated reading", low)
        self.assertIn("sections are free", low)
        self.assertNotIn("linhagem** first", low)
        self.assertNotIn("glossario** last", low)
        self.assertNotIn('"o que nao sei"** penultimate', low)
        self.assertNotIn("penultimate", low)
        self.assertIn("galison", low)
        self.assertIn("occupy-hedge", low)
        self.assertIn("generate_report.py", low)
        self.assertIn("review-gate.py", low)
        self.assertIn("yaml_to_html", low)

    def test_report_research_discovery_lazer_name_the_fail(self):
        for skill in ("report", "research", "discovery", "lazer"):
            low = self._text("skills", skill, "SKILL.md").lower()
            self.assertIn("leitura isolada", low, skill)
            self.assertIn("colleague of the operator", low, skill)
            self.assertIn("linhagem-first is a fail", low, skill)
            self.assertNotIn("glossário (last)", low, skill)
            self.assertNotIn("glossary (last)", low, skill)
            self.assertNotIn("penultimate", low, skill)


class PipeAssetsUntouched(unittest.TestCase):
    def test_tetris_css_and_generate_report_still_there(self):
        self.assertTrue((REPO / "tools" / "assets" / "tetris.css").is_file())
        gen = (REPO / "tools" / "generate_report.py").read_text(encoding="utf-8")
        self.assertIn("tetris.css", gen)
        yaml_html = (REPO / "tools" / "yaml_to_html.py").read_text(encoding="utf-8")
        self.assertIn("def yaml_to_html", yaml_html)


if __name__ == "__main__":
    unittest.main(verbosity=2)
