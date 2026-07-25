"""A lente lectures-on-physics é parte FIXA do final_review (rito injeta
feynman_gate.LENS_BLOCK), e só dele. Contrapesos vinculantes no texto:
fato é do fact-audit; enchimento ≠ crescimento.
"""
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
import feynman_gate  # noqa: E402


class LensContract(unittest.TestCase):
    def test_lens_carries_ruler_and_both_counterweights(self):
        lens = feynman_gate.LENS_BLOCK
        self.assertIn("Feynman Lectures", lens)
        self.assertIn("STRIKE", lens)
        self.assertIn("fact-audit", lens)
        self.assertIn("ENCHIMENTO", lens)
        self.assertIn("Comprimento NÃO é defeito", lens)

    def test_rito_injects_lens_into_final_review_only(self):
        src = (REPO / "tools" / "rito.py").read_text()
        self.assertIn("LENS_BLOCK", src)
        i = src.index("# 10 — final review")
        stage10 = src[i:]
        self.assertIn("LENS_BLOCK", stage10.split("_llm_stage")[0])
        self.assertNotIn("LENS_BLOCK", src[:i])


if __name__ == "__main__":
    unittest.main()
