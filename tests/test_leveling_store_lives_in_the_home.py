"""O leveling-store (persona do mentorado) mora na casa do install, não no genótipo.

`_identity` define o contrato: num install com genótipo e home separados, identidade vive no
HOME e "o repo é genótipo puro, sem identidade". A persona do mentorado é o arquivo mais
identitário que existe — e escritor e leitor a resolviam por literal do repositório.

Escritor e leitor CONCORDAVAM entre si, então um install isolado funcionava e nada acusava. O
dano aparece quando dois installs partilham um clone do genótipo: a persona de um mentorado
sobrescreve a do outro. É a família do #154 (colonização), e por isso o teste cobre as duas
pontas juntas — verificar só uma delas reproduz exatamente a cegueira original.
"""
import os
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
import grill_writeback  # noqa: E402
import recall  # noqa: E402


class LevelingStoreResolvesAtTheSeam(unittest.TestCase):
    def test_writer_lands_in_the_home_and_reader_finds_it_there(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            (home / "memory").mkdir()
            log = home / "log.jsonl"
            old = os.environ.get("EDGE_HOME")
            os.environ["EDGE_HOME"] = str(home)
            try:
                written = grill_writeback.leveling(
                    "perfil", "# Perfil\n\nquem o mentorado é", log=log)
                self.assertEqual(written.parent, home / "memory" / "leveling",
                                 "a persona tem que pousar na casa do install")
                self.assertFalse((REPO / "memory" / "leveling" / "perfil.md").exists()
                                 and written.parent == REPO / "memory" / "leveling",
                                 "a persona não pode pousar no genótipo")
                brief = recall.compose_mentee_persona_brief()
                self.assertIn("quem o mentorado é", brief,
                              "o leitor tem que resolver pela mesma raiz que o escritor")
            finally:
                if old is None:
                    os.environ.pop("EDGE_HOME", None)
                else:
                    os.environ["EDGE_HOME"] = old

    def test_explicit_root_still_wins(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "escolhida"
            log = Path(tmp) / "log.jsonl"
            written = grill_writeback.leveling("perfil", "# Perfil\n\nx", root=root, log=log)
            self.assertEqual(written.parent, root)


if __name__ == "__main__":
    unittest.main()
