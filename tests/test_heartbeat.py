"""Fase A — o spine. Um beat produz um artefato HTML válido publicado (cliente LLM fake)."""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import _pipeline  # noqa: E402


class FakeClient:
    """chat.completions.create(...).choices[0].message.content"""
    def __init__(self, text):
        comp = type("Comp", (), {"create": lambda _self, **kw: type("R", (), {
            "choices": [type("C", (), {"message": type("M", (), {"content": text})()})()]
        })()})()
        self.chat = type("Chat", (), {"completions": comp})()


ARTIFACT_MD = ("## Resumo executivo\nEste é um resumo de teste com conteúdo suficiente "
               "para passar do piso de caracteres do gate de forma.\n\n"
               "## Seção A\nCorpo da seção A com bastante texto de exemplo.\n\n"
               "## Seção B\nCorpo da seção B.\n")


class FaseA(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.home = Path(self._tmp.name)
        t = self.home / "threads"
        t.mkdir(parents=True)
        (t / "baseline-do-runtime-atual.md").write_text(
            "---\nid: baseline-do-runtime-atual\ntitle: Baseline do runtime atual\n"
            "status: active\nowner: ed\n---\nObservar e documentar o runtime.\n")
        self.res = _pipeline.run_beat(self.home, FakeClient(ARTIFACT_MD), "gpt-5.4")

    def tearDown(self):
        self._tmp.cleanup()

    def test_beat_ok(self):
        self.assertTrue(self.res["ok"], self.res)

    def test_html_entry_published(self):
        entries = list((self.home / "blog" / "entries").glob("*.html"))
        self.assertEqual(len(entries), 1)
        html = entries[0].read_text()
        self.assertIn("<html", html)
        self.assertIn("Baseline do runtime atual", html)
        self.assertIn("<h1>", html)
        self.assertIn("Seção A", html)

    def test_structure_gate_passed(self):
        gate = next(g for g in self.res["gates"] if g["gate"] == "structure")
        self.assertTrue(gate["passed"], gate)

    def test_adversarial_skipped_without_review_client(self):
        adv = next(g for g in self.res["gates"] if g["gate"] == "adversarial")
        self.assertTrue(adv.get("skipped"))

    def test_consolidation_updates_rolling_digest(self):
        digest = self.home / "state" / "chat-digest.md"
        self.assertTrue(digest.exists())
        self.assertIn("Baseline do runtime atual", digest.read_text())

    def test_no_active_thread_returns_not_ok(self):
        empty = Path(self._tmp.name) / "empty"
        (empty / "threads").mkdir(parents=True)
        res = _pipeline.run_beat(empty, FakeClient(ARTIFACT_MD), "gpt-5.4")
        self.assertFalse(res["ok"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
