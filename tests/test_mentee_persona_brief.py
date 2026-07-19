"""P1.5 — Persona do mentee surface (not edge Personality identity)."""
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
import recall  # noqa: E402


class MenteePersonaBrief(unittest.TestCase):
    def test_empty_root_declares_empty_perfil(self):
        with tempfile.TemporaryDirectory() as tmp:
            text = recall.compose_mentee_persona_brief(root=tmp)
            self.assertIn("Persona do mentee", text)
            self.assertIn("perfil vazio", text.lower())

    def test_reads_perfil_and_mapa_frontier(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "perfil.md").write_text("# Perfil\n\n- gosta de papel\n")
            (root / "mapa.md").write_text("# Mapa\n\n| área | nível |\n| UU | primeiro |\n")
            text = recall.compose_mentee_persona_brief(root=root)
            self.assertIn("gosta de papel", text)
            self.assertIn("Persona do mentee", text)
            self.assertIn("UU", text)

    def test_compose_recall_brief_includes_persona_block(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "perfil.md").write_text("sou o mentee\n")
            # dark subgraph path still appends persona when root injected
            text = recall.compose_recall_brief(subgraph=None, mentee_leveling_root=root)
            self.assertIn("Persona do mentee", text)
            self.assertIn("sou o mentee", text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
