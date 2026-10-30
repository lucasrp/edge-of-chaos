"""Sessões declaradas humanas pelo dono (30/10/2026): a sessão fixa da consultoria sob demanda é dirigida por
`claude -p --resume`, mas "no wake é pra ser considerada como se fosse uma sessao minha"."""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))

import quente  # noqa: E402
import sessions  # noqa: E402

SID = "11111111-2222-3333-4444-555555555555"


def _one_shot(path, prompt):
    """Uma fala humana só: o formato de um `claude -p` (fica abaixo do piso de diálogo)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"type": "user", "message": {"role": "user", "content": prompt}}) + "\n")
    return path


class DeclaradasTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name)
        self.old = os.environ.get("EDGE_HOME")
        os.environ["EDGE_HOME"] = str(self.home)
        self.path = _one_shot(self.home / "store" / f"{SID}.jsonl", "Pedido do Chief of Staff: item 13. " * 3)

    def tearDown(self):
        if self.old is None:
            os.environ.pop("EDGE_HOME", None)
        else:
            os.environ["EDGE_HOME"] = self.old
        self.tmp.cleanup()

    def _declare(self, text):
        f = self.home / "state" / "sessoes-humanas.txt"
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(text)

    def test_sem_declaracao_one_shot_fica_fora(self):
        s = sessions.Session(id=SID, path=self.path)
        self.assertEqual(sessions.user_session_exclusion_reason(s), "claude-sem-dialogo")
        meta, _ = quente._session_meta_and_turns(self.path)
        meta["id"] = SID
        self.assertFalse(quente.is_substantial(meta))

    def test_declarada_entra_como_sessao_do_dono(self):
        self._declare(f"# comentário\n{SID}  # consultoria sob demanda\n")
        s = sessions.Session(id=SID, path=self.path)
        self.assertIsNone(sessions.user_session_exclusion_reason(s))
        meta, _ = quente._session_meta_and_turns(self.path)
        meta["id"] = SID
        self.assertTrue(quente.is_substantial(meta))

    def test_sem_arquivo_lista_vazia(self):
        self.assertEqual(sessions.declared_human_sessions(), frozenset())


if __name__ == "__main__":
    unittest.main()
